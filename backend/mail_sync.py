"""
Mail sync service: IMAP, Gmail API, Outlook Graph API.

Ported from other/KnowledgeBase/BackEnd/app/services/imap_sync.py,
                                          gmail_sync.py, outlook_graph.py

Adaptations vs original:
- Uses SQLAlchemy text() + :param style instead of psycopg %s
- Skips thread_builder / trigger_engine / kb_unit_builder (QW handles separately)
- Auto-cleans new mail via upsert_mail_cleaned from raw_comm_service
- Passwords decrypted via mail_crypto.decrypt_text before connecting
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import imaplib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email import policy as email_policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text

from mail_crypto import decrypt_text
from mail_oauth import refresh_gmail_token, refresh_outlook_token
from raw_comm_service import upsert_mail_cleaned

logger = logging.getLogger(__name__)

ProgressCallback = Callable[..., None]

UPLOADS_DIR = Path(__file__).parent / "uploads"


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_header_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        parts = []
        for part, charset in decode_header(str(value)):
            if isinstance(part, bytes):
                for enc in ([str(charset).lower()] if charset else []) + ["gb18030", "utf-8", "latin-1"]:
                    try:
                        parts.append(part.decode(enc)); break
                    except Exception:
                        continue
                else:
                    parts.append(part.decode("utf-8", errors="replace"))
            else:
                parts.append(str(part))
        return "".join(parts).strip() or default
    except Exception:
        return str(value or default)


def _normalize_addresses(value: str | list | None) -> list[str]:
    if not value:
        return []
    candidates = value if isinstance(value, list) else [str(value)]
    return [addr.strip().lower() for _, addr in getaddresses(candidates) if addr.strip()]


def _normalize_datetime(value: Any) -> str | None:
    text_val = str(value or "").strip()
    if not text_val:
        return None
    try:
        dt = parsedate_to_datetime(text_val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _mail_uid(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _store_mail_file(payload: bytes, suffix: str = ".eml") -> Path:
    path = UPLOADS_DIR / "raw_mails" / f"{uuid4().hex}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _store_attachment_file(payload: bytes, filename: str) -> Path:
    suffix = Path(filename).suffix or ".bin"
    path = UPLOADS_DIR / "attachments" / f"{uuid4().hex}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


# ─── DB helpers (SQLAlchemy) ──────────────────────────────────────────────────

def _row_to_account(row) -> dict:
    """Convert DB row to account dict (handles both tuple and Row)."""
    if hasattr(row, '_mapping'):
        return dict(row._mapping)
    return dict(row)


def _message_exists(db: Session, mail_uid: str, internet_message_id: str | None) -> bool:
    if internet_message_id:
        r = db.execute(text(
            "SELECT 1 FROM mail_raw_unified WHERE internet_message_id = :mid LIMIT 1"
        ), {"mid": internet_message_id}).fetchone()
        if r:
            return True
    r = db.execute(text(
        "SELECT 1 FROM mail_raw_unified WHERE mail_uid = :uid LIMIT 1"
    ), {"uid": mail_uid}).fetchone()
    return r is not None


def _persist_message(db: Session, parsed: dict[str, Any], account_id: int | None,
                     batch_id: int | None = None) -> bool:
    """Insert parsed mail into mail_raw_unified. Returns True if newly inserted."""
    if _message_exists(db, parsed["mail_uid"], parsed.get("internet_message_id")):
        return False
    db.execute(text("""
        INSERT INTO mail_raw_unified (
            mail_uid, source_type, source_account_id, import_batch_id, folder_name, direction,
            internet_message_id, in_reply_to, references_text, conversation_key,
            subject, body_text, from_email, to_emails, cc_emails,
            sent_at, received_at, has_attachment, raw_payload_path, ingested_at
        ) VALUES (
            :uid, :stype, :acct, :batch, :folder, :dir,
            :msgid, :irt, :refs, '',
            :subj, :body, :from_, :to_, :cc_,
            :sent, :rcvd, :att, :path, :now
        ) ON CONFLICT (mail_uid) DO NOTHING
    """), {
        "uid": parsed["mail_uid"], "stype": parsed.get("source_type", "imap_sync"),
        "acct": account_id, "batch": batch_id,
        "folder": parsed.get("folder_name", ""), "dir": parsed.get("direction", "inbound"),
        "msgid": parsed.get("internet_message_id"), "irt": parsed.get("in_reply_to"),
        "refs": parsed.get("references_text"),
        "subj": parsed.get("subject", ""), "body": parsed.get("body_text", ""),
        "from_": parsed.get("from_email", ""),
        "to_": json.dumps(parsed.get("to_emails", [])),
        "cc_": json.dumps(parsed.get("cc_emails", [])),
        "sent": parsed.get("sent_at"), "rcvd": parsed.get("received_at"),
        "att": bool(parsed.get("has_attachment")),
        "path": parsed.get("raw_payload_path", ""), "now": _utc_now(),
    })
    db.commit()
    # auto-clean
    try:
        upsert_mail_cleaned(db, parsed)
        db.commit()
    except Exception as exc:
        logger.warning("[mail_sync] auto-clean failed %s: %s", parsed["mail_uid"], exc)
        db.rollback()
    return True


# ─── Sync checkpoint helpers ──────────────────────────────────────────────────

def _get_checkpoint(db: Session, account_id: int, provider: str, folder: str) -> dict | None:
    try:
        r = db.execute(text(
            "SELECT cursor_value, metadata_json FROM sync_checkpoint "
            "WHERE account_id = :a AND provider_type = :p AND folder_name = :f"
        ), {"a": account_id, "p": provider, "f": folder}).fetchone()
        if r:
            meta = r[1] if isinstance(r[1], dict) else (json.loads(r[1]) if r[1] else {})
            return {"cursor_value": r[0], "metadata_json": meta}
    except Exception:
        pass
    return None


def _save_checkpoint(db: Session, account_id: int, provider: str, folder: str,
                     cursor_value: str, metadata: dict | None = None) -> None:
    try:
        db.execute(text("""
            INSERT INTO sync_checkpoint (account_id, provider_type, folder_name, cursor_value, metadata_json, updated_at)
            VALUES (:a, :p, :f, :cv, :meta::jsonb, :now)
            ON CONFLICT (account_id, provider_type, folder_name)
            DO UPDATE SET cursor_value = EXCLUDED.cursor_value, metadata_json = EXCLUDED.metadata_json,
                          updated_at = EXCLUDED.updated_at
        """), {"a": account_id, "p": provider, "f": folder, "cv": cursor_value,
               "meta": json.dumps(metadata or {}), "now": _utc_now()})
        db.commit()
    except Exception as exc:
        logger.warning("[mail_sync] save_checkpoint failed: %s", exc)
        db.rollback()


# ─── Sync job helpers ─────────────────────────────────────────────────────────

def start_sync_job(db: Session, account_id: int, job_type: str) -> int:
    r = db.execute(text("""
        INSERT INTO mail_sync_job (
            account_id, job_type, status, detail, started_at,
            progress_total, progress_done, success_count, failed_count,
            current_stage, current_folder, current_item, metadata_json
        ) VALUES (:a, :jt, 'running', '同步中', :now, 0, 0, 0, 0, 'queued', '', '', '{}'::jsonb)
        RETURNING id
    """), {"a": account_id, "jt": job_type, "now": _utc_now()}).fetchone()
    db.commit()
    return r[0]


def update_sync_job(db: Session, job_id: int, **fields) -> None:
    if not fields:
        return
    parts = [f"{k} = :{k}" for k in fields]
    fields["job_id"] = job_id
    try:
        db.execute(text(f"UPDATE mail_sync_job SET {', '.join(parts)} WHERE id = :job_id"), fields)
        db.commit()
    except Exception as exc:
        logger.warning("[mail_sync] update_sync_job failed: %s", exc)
        db.rollback()


def finish_sync_job(db: Session, job_id: int, *, status: str, detail: str,
                    success: int = 0, failed: int = 0) -> None:
    update_sync_job(db, job_id, status=status, detail=detail,
                    finished_at=_utc_now(), success_count=success, failed_count=failed,
                    current_stage="finished")


def _account_to_sync_dict(account_row) -> dict:
    """Get decrypt passwords for sync."""
    acc = _row_to_account(account_row) if not isinstance(account_row, dict) else dict(account_row)
    acc["imap_password"] = decrypt_text(acc.get("imap_password", ""))
    acc["oauth_client_secret"] = decrypt_text(acc.get("oauth_client_secret", ""))
    acc["oauth_access_token"] = decrypt_text(acc.get("oauth_access_token", ""))
    acc["oauth_refresh_token"] = decrypt_text(acc.get("oauth_refresh_token", ""))
    return acc


# ─── IMAP UTF-7 helpers ───────────────────────────────────────────────────────

def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii"); return True
    except UnicodeEncodeError:
        return False


def _encode_imap_utf7(value: str) -> str:
    if _is_ascii(value):
        return value
    chunks, buf = [], []

    def flush():
        if buf:
            raw = "".join(buf).encode("utf-16-be")
            enc = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
            chunks.append(f"&{enc}-"); buf.clear()

    for ch in value:
        code = ord(ch)
        if 0x20 <= code <= 0x7E and ch != "&":
            flush(); chunks.append(ch)
        elif ch == "&":
            flush(); chunks.append("&-")
        else:
            buf.append(ch)
    flush()
    return "".join(chunks)


def _decode_imap_utf7(value: str) -> str:
    result, i = [], 0
    while i < len(value):
        if value[i] != "&":
            result.append(value[i]); i += 1; continue
        end = value.find("-", i)
        if end == -1:
            result.append(value[i:]); break
        token = value[i+1:end]
        if token == "":
            result.append("&")
        else:
            token = token.replace(",", "/")
            padding = "=" * ((4 - len(token) % 4) % 4)
            result.append(base64.b64decode(token + padding).decode("utf-16-be"))
        i = end + 1
    return "".join(result)


def _decode_folder_name(name: str) -> str:
    try:
        return _decode_imap_utf7(name)
    except Exception:
        return name


# ─── IMAP sync ────────────────────────────────────────────────────────────────

def _build_imap_client(account: dict) -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    host = account["imap_host"].strip()
    port = int(account.get("imap_port") or 993)
    username = (account.get("imap_username") or account.get("email_address", "")).strip()
    password = account.get("imap_password", "").strip()
    use_ssl = bool(account.get("imap_use_ssl", True))
    if not host or not username or not password:
        raise ValueError("IMAP 账号缺少 host / username / password")
    client = imaplib.IMAP4_SSL(host, port, timeout=60) if use_ssl else imaplib.IMAP4(host, port, timeout=60)
    client.login(username, password)
    return client


def _list_imap_folders(client) -> list[str]:
    _, data = client.list()
    pattern = re.compile(r'\(.*?\)\s+"?[^"]*"?\s+(.+)$')
    folders = []
    for item in (data or []):
        raw = item.decode("utf-8", errors="ignore")
        m = pattern.match(raw)
        name = (m.group(1) if m else raw).strip().strip('"')
        folders.append(_decode_folder_name(name))
    return folders


def _infer_direction(folder_name: str) -> str:
    lowered = folder_name.lower()
    sent_kws = ["sent", "draft", "outbox", "已发送", "发件", "寄件", "草稿"]
    return "outbound" if any(k in lowered for k in sent_kws) else "inbound"


def _resolve_folders(client, account: dict) -> list[tuple[str, str]]:
    folders = []
    if account.get("sync_inbox_enabled"):
        folders += [("INBOX", "inbound"), ("收件箱", "inbound")]
    if account.get("sync_sent_enabled"):
        folders += [("Sent", "outbound"), ("Sent Items", "outbound"), ("已发送", "outbound")]
    available = _list_imap_folders(client)
    resolved, seen = [], set()
    for fname, direction in folders:
        actual = next((a for a in available if a.lower() == fname.lower()), None) or fname
        if actual.lower() not in seen:
            resolved.append((actual, direction)); seen.add(actual.lower())
    return resolved or [("INBOX", "inbound")]


def _parse_imap_eml(payload: bytes, folder_name: str, direction: str) -> dict:
    uid = _mail_uid(payload)
    msg = BytesParser(policy=email_policy.default).parsebytes(payload)
    plain, html, attachments = "", "", []

    def get_header(name):
        return _decode_header_value(msg.get(name, ""))

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            cdisp = part.get_content_disposition()
            fname_raw = part.get_filename()
            if cdisp == "attachment" or fname_raw:
                try:
                    data = part.get_payload(decode=True) or b""
                    fname = _decode_header_value(fname_raw, "attachment.bin")
                    stored = _store_attachment_file(data, fname)
                    att_uid = hashlib.sha256(f"{uid}:{fname}:{hashlib.sha256(data).hexdigest()}".encode()).hexdigest()
                    attachments.append({"attachment_uid": att_uid, "filename": fname,
                                        "file_ext": Path(fname).suffix.lower(),
                                        "mime_type": ctype, "file_size": len(data),
                                        "storage_path": str(stored)})
                except Exception:
                    pass
            elif ctype == "text/plain":
                plain += (part.get_content() or "") + "\n"
            elif ctype == "text/html":
                html += (part.get_content() or "") + "\n"
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            plain = msg.get_content() or ""
        elif ctype == "text/html":
            html = msg.get_content() or ""

    body = plain.strip()
    if not body and html:
        from html.parser import HTMLParser
        class _HP(HTMLParser):
            def __init__(self): super().__init__(); self.parts = []
            def handle_data(self, d): self.parts.append(d.strip())
        p = _HP(); p.feed(html)
        body = "\n".join(x for x in p.parts if x)

    stored_path = _store_mail_file(payload)
    sent_at = _normalize_datetime(get_header("Date"))
    return {
        "mail_uid": uid, "source_type": "imap_sync",
        "folder_name": folder_name, "direction": direction,
        "internet_message_id": get_header("Message-ID") or None,
        "in_reply_to": get_header("In-Reply-To") or None,
        "references_text": get_header("References") or None,
        "subject": get_header("Subject"),
        "body_text": body, "from_email": get_header("From"),
        "to_emails": _normalize_addresses(get_header("To")),
        "cc_emails": _normalize_addresses(get_header("Cc")),
        "sent_at": sent_at, "received_at": sent_at,
        "has_attachment": bool(attachments), "attachments": attachments,
        "raw_payload_path": str(stored_path), "ingested_at": _utc_now(),
    }


def run_imap_sync(db: Session, account_row, job_type: str = "incremental_sync",
                  lookback_days: int | None = 30) -> dict:
    account = _account_to_sync_dict(account_row)
    account_id = account["id"]
    job_id = start_sync_job(db, account_id, job_type)
    imported = failed = checked = 0
    try:
        client = _build_imap_client(account)
        try:
            folders = _resolve_folders(client, account)
            for folder_name, direction in folders:
                try:
                    status, _ = client.select(f'"{_encode_imap_utf7(folder_name)}"', readonly=True)
                    if status != "OK":
                        continue
                    checkpoint = _get_checkpoint(db, account_id, "imap", folder_name)
                    if job_type == "incremental_sync" and checkpoint and checkpoint["cursor_value"]:
                        criteria = f"UID {int(checkpoint['cursor_value']) + 1}:*"
                    elif lookback_days and lookback_days > 0:
                        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
                        criteria = f'SINCE "{since}"'
                    else:
                        criteria = "ALL"

                    status2, data = client.uid("SEARCH", None, criteria)
                    if status2 != "OK" or not data or not data[0]:
                        continue
                    ids = data[0].split()
                    max_uid = ""
                    for message_id in ids:
                        checked += 1
                        uid_str = message_id.decode()
                        try:
                            _, fetch_data = client.uid("FETCH", message_id, "(RFC822)")
                            if not fetch_data or not fetch_data[0]:
                                continue
                            raw = fetch_data[0][1] if isinstance(fetch_data[0], tuple) else fetch_data[0]
                            if not isinstance(raw, bytes):
                                continue
                            parsed = _parse_imap_eml(raw, folder_name, direction)
                            if _persist_message(db, parsed, account_id):
                                imported += 1
                            max_uid = uid_str
                        except Exception as exc:
                            logger.warning("[imap_sync] fetch %s/%s failed: %s", folder_name, uid_str, exc)
                            failed += 1
                    if max_uid:
                        _save_checkpoint(db, account_id, "imap", folder_name, max_uid,
                                         {"uidvalidity": ""})
                except Exception as exc:
                    logger.warning("[imap_sync] folder %s error: %s", folder_name, exc)
                    failed += 1
        finally:
            try:
                client.logout()
            except Exception:
                pass
        db.execute(text(
            "UPDATE mail_account SET last_sync_at = :now WHERE id = :id"
        ), {"now": _utc_now(), "id": account_id})
        db.commit()
        finish_sync_job(db, job_id, status="completed",
                        detail=f"完成，共检查 {checked} 封，导入 {imported} 封，失败 {failed}",
                        success=imported, failed=failed)
        return {"status": "completed", "checked": checked, "imported": imported, "failed": failed}
    except Exception as exc:
        logger.error("[imap_sync] account %s failed: %s", account_id, exc)
        finish_sync_job(db, job_id, status="failed", detail=str(exc), success=imported, failed=failed)
        return {"status": "failed", "error": str(exc)}


# ─── Gmail sync (via REST API) ────────────────────────────────────────────────

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


async def _gmail_authorized_client(account: dict) -> tuple[httpx.AsyncClient, dict | None]:
    """Returns (client, new_token_info_or_None). new_token_info should be saved to DB."""
    token_refresh = None
    expires_at_str = account.get("oauth_token_expires_at") or ""
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
                token_refresh = await refresh_gmail_token(account)
                account = {**account, "oauth_access_token": token_refresh["access_token"]}
        except Exception:
            pass
    headers = {"Authorization": f"Bearer {account['oauth_access_token']}"}
    return httpx.AsyncClient(headers=headers, timeout=30), token_refresh


def _gmail_parse_message(message: dict, direction: str, folder_name: str) -> dict:
    payload = message.get("payload", {})
    headers_list = payload.get("headers", [])
    def get_h(name):
        return next((h["value"] for h in headers_list if h["name"].lower() == name.lower()), "")

    def extract_body(part, depth=0):
        if depth > 5:
            return "", ""
        mime = part.get("mimeType", "")
        body_data = (part.get("body") or {}).get("data", "")
        if mime == "text/plain" and body_data:
            return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace"), ""
        if mime == "text/html" and body_data:
            return "", base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        plain, html = "", ""
        for sub in part.get("parts", []):
            p, h = extract_body(sub, depth + 1)
            plain += p; html += h
        return plain, html

    plain, html = extract_body(payload)
    if not plain and html:
        from html.parser import HTMLParser
        class _HP(HTMLParser):
            def __init__(self): super().__init__(); self.parts = []
            def handle_data(self, d): self.parts.append(d.strip())
        p = _HP(); p.feed(html)
        plain = "\n".join(x for x in p.parts if x)

    uid = hashlib.sha256(message["id"].encode()).hexdigest()
    sent_at = _normalize_datetime(get_h("Date"))
    return {
        "mail_uid": uid, "source_type": "gmail_sync",
        "folder_name": folder_name, "direction": direction,
        "internet_message_id": get_h("Message-ID") or message["id"],
        "in_reply_to": get_h("In-Reply-To") or None,
        "references_text": get_h("References") or None,
        "subject": get_h("Subject"),
        "body_text": plain.strip(), "from_email": get_h("From"),
        "to_emails": _normalize_addresses(get_h("To")),
        "cc_emails": _normalize_addresses(get_h("Cc")),
        "sent_at": sent_at, "received_at": sent_at,
        "has_attachment": bool(message.get("payload", {}).get("parts")),
        "attachments": [], "raw_payload_path": "", "ingested_at": _utc_now(),
    }


async def _run_gmail_sync_async(db: Session, account: dict) -> dict:
    account_id = account["id"]
    imported = failed = 0
    client, token_refresh = await _gmail_authorized_client(account)
    if token_refresh:
        db.execute(text(
            "UPDATE mail_account SET oauth_access_token=:at, oauth_refresh_token=:rt, "
            "oauth_token_expires_at=:exp, updated_at=:now WHERE id=:id"
        ), {"at": token_refresh["access_token"], "rt": token_refresh["refresh_token"],
            "exp": token_refresh["expires_at"], "now": _utc_now(), "id": account_id})
        db.commit()
    folder_specs = [("INBOX", "inbound")]
    if account.get("sync_sent_enabled"):
        folder_specs.append(("SENT", "outbound"))
    async with client:
        for label, direction in folder_specs:
            checkpoint = _get_checkpoint(db, account_id, "gmail", label)
            params: dict = {"maxResults": "200", "labelIds": label}
            if checkpoint and checkpoint["cursor_value"]:
                params["pageToken"] = checkpoint["cursor_value"]
            page_token = None
            while True:
                if page_token:
                    params["pageToken"] = page_token
                r = await client.get(f"{_GMAIL_API}/messages", params=params)
                if r.status_code != 200:
                    break
                data = r.json()
                messages = data.get("messages", [])
                for msg_stub in messages:
                    try:
                        r2 = await client.get(f"{_GMAIL_API}/messages/{msg_stub['id']}",
                                              params={"format": "full"})
                        if r2.status_code != 200:
                            failed += 1; continue
                        parsed = _gmail_parse_message(r2.json(), direction, label)
                        if _persist_message(db, parsed, account_id):
                            imported += 1
                    except Exception as exc:
                        logger.warning("[gmail_sync] msg %s: %s", msg_stub["id"], exc)
                        failed += 1
                next_page = data.get("nextPageToken")
                if next_page:
                    page_token = next_page
                    _save_checkpoint(db, account_id, "gmail", label, next_page)
                else:
                    _save_checkpoint(db, account_id, "gmail", label, "")
                    break
    return {"imported": imported, "failed": failed}


def run_gmail_sync(db: Session, account_row, job_type: str = "incremental_sync") -> dict:
    account = _account_to_sync_dict(account_row)
    account_id = account["id"]
    job_id = start_sync_job(db, account_id, job_type)
    try:
        result = asyncio.run(_run_gmail_sync_async(db, account))
        db.execute(text("UPDATE mail_account SET last_sync_at=:now WHERE id=:id"),
                   {"now": _utc_now(), "id": account_id})
        db.commit()
        finish_sync_job(db, job_id, status="completed",
                        detail=f"Gmail 同步完成：导入 {result['imported']}，失败 {result['failed']}",
                        success=result["imported"], failed=result["failed"])
        return {"status": "completed", **result}
    except Exception as exc:
        logger.error("[gmail_sync] account %s: %s", account_id, exc)
        finish_sync_job(db, job_id, status="failed", detail=str(exc))
        return {"status": "failed", "error": str(exc)}


# ─── Outlook Graph sync ───────────────────────────────────────────────────────

_GRAPH_API = "https://graph.microsoft.com/v1.0"


def _outlook_parse_message(msg: dict, direction: str, folder_name: str) -> dict:
    def extract_emails(items):
        return [i.get("emailAddress", {}).get("address", "") for i in (items or []) if i]

    uid = hashlib.sha256(msg["id"].encode()).hexdigest()
    body_text = msg.get("body", {}).get("content", "")
    if msg.get("body", {}).get("contentType", "") == "html":
        from html.parser import HTMLParser
        class _HP(HTMLParser):
            def __init__(self): super().__init__(); self.parts = []
            def handle_data(self, d): self.parts.append(d.strip())
        p = _HP(); p.feed(body_text)
        body_text = "\n".join(x for x in p.parts if x)
    sent_at = _normalize_datetime(msg.get("sentDateTime"))
    return {
        "mail_uid": uid, "source_type": "outlook_sync",
        "folder_name": folder_name, "direction": direction,
        "internet_message_id": msg.get("internetMessageId") or msg["id"],
        "in_reply_to": None, "references_text": None,
        "subject": msg.get("subject", ""),
        "body_text": body_text,
        "from_email": (msg.get("from") or {}).get("emailAddress", {}).get("address", ""),
        "to_emails": extract_emails(msg.get("toRecipients")),
        "cc_emails": extract_emails(msg.get("ccRecipients")),
        "sent_at": sent_at, "received_at": _normalize_datetime(msg.get("receivedDateTime")),
        "has_attachment": bool(msg.get("hasAttachments")),
        "attachments": [], "raw_payload_path": "", "ingested_at": _utc_now(),
    }


async def _run_outlook_sync_async(db: Session, account: dict) -> dict:
    account_id = account["id"]
    imported = failed = 0
    expires_at_str = account.get("oauth_token_expires_at") or ""
    token_refresh = None
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
                token_refresh = await refresh_outlook_token(account)
                account = {**account, "oauth_access_token": token_refresh["access_token"]}
        except Exception:
            pass
    if token_refresh:
        db.execute(text(
            "UPDATE mail_account SET oauth_access_token=:at, oauth_refresh_token=:rt, "
            "oauth_token_expires_at=:exp, updated_at=:now WHERE id=:id"
        ), {"at": token_refresh["access_token"], "rt": token_refresh["refresh_token"],
            "exp": token_refresh["expires_at"], "now": _utc_now(), "id": account_id})
        db.commit()
    headers = {"Authorization": f"Bearer {account['oauth_access_token']}",
               "Content-Type": "application/json"}
    folder_specs = [("inbox", "inbound")]
    if account.get("sync_sent_enabled"):
        folder_specs.append(("sentitems", "outbound"))
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        for folder_id, direction in folder_specs:
            url = f"{_GRAPH_API}/me/mailFolders/{folder_id}/messages"
            params = {"$top": "50", "$select": "id,subject,body,from,toRecipients,ccRecipients,"
                      "sentDateTime,receivedDateTime,hasAttachments,internetMessageId"}
            checkpoint = _get_checkpoint(db, account_id, "outlook", folder_id)
            if checkpoint and checkpoint["cursor_value"]:
                params["$skipToken"] = checkpoint["cursor_value"]
            skip_token = None
            while True:
                if skip_token:
                    params["$skipToken"] = skip_token
                r = await client.get(url, params=params)
                if r.status_code != 200:
                    break
                data = r.json()
                for msg in data.get("value", []):
                    try:
                        parsed = _outlook_parse_message(msg, direction, folder_id)
                        if _persist_message(db, parsed, account_id):
                            imported += 1
                    except Exception as exc:
                        logger.warning("[outlook_sync] msg %s: %s", msg.get("id"), exc)
                        failed += 1
                next_link = data.get("@odata.nextLink", "")
                if next_link:
                    # extract skipToken from nextLink
                    m = re.search(r"\$skipToken=([^&]+)", next_link)
                    skip_token = m.group(1) if m else None
                    if skip_token:
                        _save_checkpoint(db, account_id, "outlook", folder_id, skip_token)
                    else:
                        break
                else:
                    _save_checkpoint(db, account_id, "outlook", folder_id, "")
                    break
    return {"imported": imported, "failed": failed}


def run_outlook_sync(db: Session, account_row, job_type: str = "incremental_sync") -> dict:
    account = _account_to_sync_dict(account_row)
    account_id = account["id"]
    job_id = start_sync_job(db, account_id, job_type)
    try:
        result = asyncio.run(_run_outlook_sync_async(db, account))
        db.execute(text("UPDATE mail_account SET last_sync_at=:now WHERE id=:id"),
                   {"now": _utc_now(), "id": account_id})
        db.commit()
        finish_sync_job(db, job_id, status="completed",
                        detail=f"Outlook 同步完成：导入 {result['imported']}，失败 {result['failed']}",
                        success=result["imported"], failed=result["failed"])
        return {"status": "completed", **result}
    except Exception as exc:
        logger.error("[outlook_sync] account %s: %s", account_id, exc)
        finish_sync_job(db, job_id, status="failed", detail=str(exc))
        return {"status": "failed", "error": str(exc)}


# ─── Ensure DB tables exist ───────────────────────────────────────────────────

def ensure_sync_tables(db: Session) -> None:
    """Create sync_checkpoint table if not exists (other tables created by other project)."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS sync_checkpoint (
                id BIGSERIAL PRIMARY KEY,
                account_id BIGINT NOT NULL,
                provider_type TEXT NOT NULL,
                folder_name TEXT NOT NULL,
                cursor_value TEXT NOT NULL DEFAULT '',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TEXT NOT NULL,
                UNIQUE (account_id, provider_type, folder_name)
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mail_account (
                id BIGSERIAL PRIMARY KEY,
                account_name TEXT NOT NULL,
                email_address TEXT NOT NULL UNIQUE,
                provider_type TEXT NOT NULL DEFAULT 'imap',
                auth_type TEXT NOT NULL DEFAULT 'password',
                sync_inbox_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                sync_sent_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                sync_deleted_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                sync_folder_config JSONB NOT NULL DEFAULT '[]'::jsonb,
                status TEXT NOT NULL DEFAULT 'draft',
                access_scope TEXT NOT NULL DEFAULT '',
                imap_host TEXT NOT NULL DEFAULT '',
                imap_port INTEGER NOT NULL DEFAULT 993,
                imap_username TEXT NOT NULL DEFAULT '',
                imap_password TEXT NOT NULL DEFAULT '',
                imap_use_ssl BOOLEAN NOT NULL DEFAULT TRUE,
                oauth_client_id TEXT NOT NULL DEFAULT '',
                oauth_client_secret TEXT NOT NULL DEFAULT '',
                oauth_tenant_id TEXT NOT NULL DEFAULT 'common',
                oauth_redirect_uri TEXT NOT NULL DEFAULT '',
                oauth_scope TEXT NOT NULL DEFAULT '',
                oauth_access_token TEXT NOT NULL DEFAULT '',
                oauth_refresh_token TEXT NOT NULL DEFAULT '',
                oauth_token_expires_at TIMESTAMPTZ,
                oauth_state TEXT NOT NULL DEFAULT '',
                last_sync_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mail_sync_job (
                id BIGSERIAL PRIMARY KEY,
                account_id BIGINT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                finished_at TEXT,
                fetched_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 0,
                progress_done INTEGER NOT NULL DEFAULT 0,
                current_stage TEXT NOT NULL DEFAULT '',
                current_folder TEXT NOT NULL DEFAULT '',
                current_item TEXT NOT NULL DEFAULT '',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mail_import_batch (
                id BIGSERIAL PRIMARY KEY,
                import_type TEXT NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                file_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                import_status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mail_raw_unified (
                id BIGSERIAL PRIMARY KEY,
                mail_uid TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                source_account_id BIGINT,
                import_batch_id BIGINT,
                folder_name TEXT NOT NULL DEFAULT '',
                direction TEXT NOT NULL DEFAULT 'inbound',
                internet_message_id TEXT,
                in_reply_to TEXT,
                references_text TEXT,
                conversation_key TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                from_email TEXT NOT NULL DEFAULT '',
                to_emails JSONB NOT NULL DEFAULT '[]'::jsonb,
                cc_emails JSONB NOT NULL DEFAULT '[]'::jsonb,
                sent_at TIMESTAMPTZ,
                received_at TIMESTAMPTZ,
                has_attachment BOOLEAN NOT NULL DEFAULT FALSE,
                raw_payload_path TEXT NOT NULL DEFAULT '',
                ingested_at TEXT NOT NULL
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mail_cleaned (
                id BIGSERIAL PRIMARY KEY,
                mail_uid TEXT NOT NULL UNIQUE,
                normalized_subject TEXT NOT NULL DEFAULT '',
                body_main_text TEXT NOT NULL DEFAULT '',
                body_quoted_text TEXT NOT NULL DEFAULT '',
                signature_text TEXT NOT NULL DEFAULT '',
                disclaimer_text TEXT NOT NULL DEFAULT '',
                sender_side TEXT NOT NULL DEFAULT '',
                customer_key TEXT NOT NULL DEFAULT '',
                clean_status TEXT NOT NULL DEFAULT 'pending',
                clean_error TEXT,
                cleaned_at TEXT
            )
        """))
        db.commit()
    except Exception as exc:
        logger.warning("[mail_sync] ensure_sync_tables: %s", exc)
        db.rollback()
