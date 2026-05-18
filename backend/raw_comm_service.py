"""
原始沟通清洗服务
- 邮件解析：.eml / .msg / .zip 文件 → mail_raw_unified 表（共享数据库）
- 邮件清洗：HTML去噪、去签名、去引用、去免责声明 → mail_cleaned 表
- 路由：清洗后邮件 → 知识候选；企微会话 → wecom_raw_import
清洗逻辑移植自 other/KnowledgeBase/BackEnd/app/services/mail_cleaner_v2.py
解析逻辑移植自 other/KnowledgeBase/BackEnd/app/services/mail_importer.py
两者均做了 SQLAlchemy/QW 适配，去除 psycopg 直接依赖。
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from zipfile import ZipFile

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 存储路径 ──────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
_UPLOADS_DIR = _BACKEND_DIR / "uploads"


def _ensure_upload_dirs() -> None:
    (_UPLOADS_DIR / "raw_mails").mkdir(parents=True, exist_ok=True)
    (_UPLOADS_DIR / "attachments").mkdir(parents=True, exist_ok=True)


def _mail_storage_path(filename: str) -> Path:
    _ensure_upload_dirs()
    suffix = Path(filename).suffix or ".eml"
    return _UPLOADS_DIR / "raw_mails" / f"{uuid.uuid4().hex}{suffix}"


def _attachment_storage_path(filename: str) -> Path:
    _ensure_upload_dirs()
    suffix = Path(filename).suffix
    return _UPLOADS_DIR / "attachments" / f"{uuid.uuid4().hex}{suffix}"


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mail_uid(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _attachment_uid(mail_uid: str, filename: str, payload: bytes) -> str:
    content_hash = hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(f"{mail_uid}:{filename}:{content_hash}".encode()).hexdigest()


def _decode_filename(value: str | None, default: str = "attachment.bin") -> str:
    if not value:
        return default
    candidate = str(value).strip()
    try:
        decoded = str(make_header(decode_header(candidate))).strip()
        if decoded:
            candidate = decoded
    except Exception:
        pass
    if "%" in candidate:
        try:
            candidate = unquote(candidate) or candidate
        except Exception:
            pass
    candidate = candidate.replace("\r", " ").replace("\n", " ").strip().strip('"')
    return candidate or default


def _decode_header_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        parts: list[str] = []
        for part, charset in decode_header(str(value)):
            if isinstance(part, bytes):
                for enc in ([str(charset).lower()] if charset else []) + ["gb18030", "gbk", "utf-8", "latin1"]:
                    try:
                        parts.append(part.decode(enc))
                        break
                    except Exception:
                        continue
                else:
                    parts.append(part.decode("utf-8", errors="replace"))
            else:
                parts.append(str(part))
        return "".join(parts).strip() or default
    except Exception:
        return str(value or default)


def _normalize_addresses(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]


def _normalize_mail_datetime(value: Any) -> str:
    text_val = str(value or "").strip()
    if not text_val:
        return ""
    try:
        parsed = parsedate_to_datetime(text_val)
        if parsed is None:
            return ""
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _get_safe_header(message: EmailMessage, name: str, default: Any = "") -> Any:
    try:
        for hname, hval in message.raw_items():
            if str(hname).lower() == name.lower():
                return _decode_header_value(hval, str(default or ""))
    except Exception:
        pass
    try:
        val = message.get(name)
        if val is not None:
            str(val)
            return _decode_header_value(val, str(default or ""))
    except Exception:
        try:
            raw = message.get_all(name)
            if raw:
                return _decode_header_value(raw[0], str(default or ""))
        except Exception:
            pass
    return default


def _extract_html_text(html_content: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return html_content


# ── .eml 解析 ─────────────────────────────────────────────────────────────────
def parse_eml_bytes(
    payload: bytes,
    original_name: str,
    stored_path: Path,
    *,
    source_type: str = "manual_import",
    folder_name: str = "manual-import",
    direction: str = "inbound",
    mail_uid: str | None = None,
) -> dict[str, Any]:
    if not mail_uid:
        mail_uid = _mail_uid(payload)
    message = BytesParser(policy=policy.default).parsebytes(payload)

    plain_text = ""
    html_text = ""
    attachments: list[dict[str, Any]] = []

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            cdisp = part.get_content_disposition()
            raw_filename = part.get_filename()
            if cdisp == "attachment" or raw_filename:
                filename = _decode_filename(raw_filename)
                att_payload = part.get_payload(decode=True) or b""
                att_path = _attachment_storage_path(filename)
                att_path.write_bytes(att_payload)
                attachments.append({
                    "attachment_uid": _attachment_uid(mail_uid, filename, att_payload),
                    "filename": filename,
                    "file_ext": Path(filename).suffix.lower(),
                    "mime_type": ctype,
                    "file_size": len(att_payload),
                    "storage_path": str(att_path),
                    "created_at": _utc_now(),
                })
            elif ctype == "text/plain":
                plain_text += (part.get_content() or "").strip() + "\n"
            elif ctype == "text/html":
                html_text += (part.get_content() or "").strip() + "\n"
    else:
        ctype = message.get_content_type()
        if ctype == "text/plain":
            plain_text = message.get_content().strip()
        elif ctype == "text/html":
            html_text = message.get_content().strip()

    body_text = plain_text.strip() or _extract_html_text(html_text)
    message_id = message.get("Message-ID")
    in_reply_to = message.get("In-Reply-To")
    references_text = message.get("References")
    normalized_date = _normalize_mail_datetime(_get_safe_header(message, "Date"))

    return {
        "mail_uid": mail_uid,
        "source_type": source_type,
        "folder_name": folder_name,
        "direction": direction,
        "internet_message_id": message_id,
        "in_reply_to": in_reply_to,
        "references_text": references_text,
        "conversation_key": "",
        "subject": _get_safe_header(message, "Subject", original_name),
        "body_text": body_text or "",
        "from_email": str(_get_safe_header(message, "From", "")),
        "to_emails": _normalize_addresses(str(_get_safe_header(message, "To", ""))),
        "cc_emails": _normalize_addresses(str(_get_safe_header(message, "Cc", ""))),
        "sent_at": normalized_date,
        "received_at": normalized_date,
        "has_attachment": bool(attachments),
        "raw_payload_path": str(stored_path),
        "attachments": attachments,
        "ingested_at": _utc_now(),
    }


def _try_parse_msg(payload: bytes, original_name: str, stored_path: Path) -> dict[str, Any] | None:
    try:
        import extract_msg  # type: ignore
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        try:
            message = extract_msg.Message(tmp_path)
            mail_uid = _mail_uid(payload)
            attachments: list[dict[str, Any]] = []
            for item in message.attachments:
                name = _decode_filename(getattr(item, "longFilename", None) or getattr(item, "shortFilename", None), "attachment.bin")
                att_data = item.data or b""
                att_path = _attachment_storage_path(name)
                att_path.write_bytes(att_data)
                attachments.append({
                    "attachment_uid": _attachment_uid(mail_uid, name, att_data),
                    "filename": name,
                    "file_ext": Path(name).suffix.lower(),
                    "mime_type": "application/octet-stream",
                    "file_size": len(att_data),
                    "storage_path": str(att_path),
                    "created_at": _utc_now(),
                })
            return {
                "mail_uid": mail_uid,
                "source_type": "manual_import",
                "folder_name": "manual-import",
                "direction": "inbound",
                "internet_message_id": getattr(message, "messageId", ""),
                "in_reply_to": "",
                "references_text": "",
                "conversation_key": "",
                "subject": getattr(message, "subject", None) or original_name,
                "body_text": getattr(message, "body", None) or "",
                "from_email": getattr(message, "sender", None) or "",
                "to_emails": _normalize_addresses(getattr(message, "to", None)),
                "cc_emails": _normalize_addresses(getattr(message, "cc", None)),
                "sent_at": _normalize_mail_datetime(getattr(message, "date", None)),
                "received_at": _normalize_mail_datetime(getattr(message, "date", None)),
                "has_attachment": bool(attachments),
                "raw_payload_path": str(stored_path),
                "attachments": attachments,
                "ingested_at": _utc_now(),
            }
        finally:
            os.unlink(tmp_path)
    except Exception as exc:
        logger.warning("extract_msg failed for %s: %s", original_name, exc)
        return None


def parse_mail_file(payload: bytes, filename: str) -> dict[str, Any]:
    """解析单个邮件文件（.eml 或 .msg），返回标准化 dict（与 mail_raw_unified 列对应）"""
    stored_path = _mail_storage_path(filename)
    stored_path.write_bytes(payload)
    suffix = Path(filename).suffix.lower()
    if suffix == ".msg":
        result = _try_parse_msg(payload, filename, stored_path)
        if result:
            return result
    # 默认用 eml 解析（.eml 或 .msg 解析失败时 fallback）
    return parse_eml_bytes(payload, filename, stored_path)


def expand_zip(payload: bytes, zip_filename: str) -> list[dict[str, Any]]:
    """展开 .zip，返回所有 .eml/.msg 文件的解析结果列表"""
    results: list[dict[str, Any]] = []
    stored_path = _mail_storage_path(zip_filename)
    stored_path.write_bytes(payload)
    extract_dir = stored_path.with_suffix("")
    extract_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(stored_path) as archive:
        archive.extractall(extract_dir)
    for item in extract_dir.rglob("*"):
        if item.is_file() and item.suffix.lower() in {".eml", ".msg"}:
            try:
                results.append(parse_mail_file(item.read_bytes(), item.name))
            except Exception as exc:
                logger.warning("解析 zip 内文件失败 %s: %s", item.name, exc)
    return results


# ── 邮件清洗逻辑（来自 mail_cleaner_v2.py） ───────────────────────────────────
HTML_BREAK_RE = re.compile(r"(?i)<\s*(br|/p|/div|/li|/tr|/h\d)\s*/?\s*>")
HTML_BLOCK_RE = re.compile(r"(?is)<(script|style).*?>.*?</\1>")
HTML_TAG_RE = re.compile(r"(?is)<[^>]+>")
MULTI_BLANK_RE = re.compile(r"\n{3,}")
CID_RE = re.compile(r"\[cid:[^\]]+\]")
LOGO_PLACEHOLDER_RE = re.compile(
    r"^\[(?:.*(?:logo|symbol|icon|image|compass|underneath it|is written).*)\]$", re.IGNORECASE
)
EDGE_NOISE_LABEL_RE = re.compile(
    r"^(confidential|internal|external|private|privileged|敏感|机密|保密|内部)$", re.IGNORECASE
)
STRONG_QUOTE_MARKERS = [
    re.compile(r"^>+"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^Begin forwarded message:\s*$", re.IGNORECASE),
    re.compile(r"^On .+wrote:\s*$", re.IGNORECASE),
    re.compile(r"^Le .+a écrit\s*[:：]\s*$", re.IGNORECASE),
    re.compile(r"^Am .+schrieb .+\s*[:：]\s*$", re.IGNORECASE),
    re.compile(r"^El .+escribió[:：]\s*$", re.IGNORECASE),
    re.compile(r"^.+于\s*\d{4}[-/年]\d{1,2}[-/月]\d{1,2}.+写道[:：]\s*$", re.IGNORECASE),
    re.compile(r"^.+在\s*\d{4}[-/年]\d{1,2}[-/月]\d{1,2}.+写道[:：]\s*$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*(原始邮件|原邮件|回复的原邮件|回复的原始邮件|转发邮件)\s*-{2,}$", re.IGNORECASE),
]
WEAK_QUOTE_MARKERS = [
    re.compile(r"^(From|Sent|To|Cc|Subject|Date)\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^(发件人|发送时间|收件人|抄送|主题|日期)\s*[:：]\s*"),
    re.compile(r"^(差出人|宛先|送信日時|件名|ＣＣ)\s*[:：]\s*"),
    re.compile(r"^(De|À|Envoyé|Objet|Cc)\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^(Von|An|Gesendet|Datum|Betreff|Cc)\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^(From|Sent|To|Cc|Subject|Date)\s*$", re.IGNORECASE),
    re.compile(r"^(发件人|发送时间|收件人|抄送|主题|日期)\s*$"),
    re.compile(r"^(差出人|宛先|送信日時|件名|ＣＣ)\s*$"),
    re.compile(r"^[:：]\s*$"),
]
HEADER_SENDER_PATTERNS = [re.compile(r"^(From|发件人|差出人|De|Von)\s*[:：]\s*", re.IGNORECASE)]
HEADER_SUBJECT_PATTERNS = [re.compile(r"^(Subject|主题|件名|Objet|Betreff)\s*[:：]\s*", re.IGNORECASE)]
HEADER_DATE_PATTERNS = [re.compile(r"^(Sent|Date|发送时间|日期|送信日時|Envoyé|Datum)\s*[:：]\s*", re.IGNORECASE)]
SIGNATURE_MARKERS = [
    re.compile(r"^--\s*$"),
    re.compile(r"^best regards[,\s]*$", re.IGNORECASE),
    re.compile(r"^regards[,\s]*$", re.IGNORECASE),
    re.compile(r"^thanks[,\s]*$", re.IGNORECASE),
    re.compile(r"^many thanks[,\s]*$", re.IGNORECASE),
    re.compile(r"^kind regards[,\s]*$", re.IGNORECASE),
    re.compile(r"^sincerely[,\s]*$", re.IGNORECASE),
    re.compile(r"^sent from my iphone$", re.IGNORECASE),
    re.compile(r"^sent from my android$", re.IGNORECASE),
    re.compile(r"^此致$"), re.compile(r"^敬礼$"), re.compile(r"^顺祝商祺$"),
    re.compile(r"^谢谢[！!。\s]*$"), re.compile(r"^感谢[！!。\s]*$"),
    re.compile(r"^来自我的(iPhone|Android)$"),
]
DISCLAIMER_MARKERS = [
    re.compile(r"this email and any attachments", re.IGNORECASE),
    re.compile(r"confidentiality notice", re.IGNORECASE),
    re.compile(r"intended recipient", re.IGNORECASE),
    re.compile(r"solely intended for", re.IGNORECASE),
    re.compile(r"本邮件及其附件包含机密", re.IGNORECASE),
    re.compile(r"如果您并非预期的收件人", re.IGNORECASE),
    re.compile(r"严禁任何未经授权", re.IGNORECASE),
    re.compile(r"本邮件可能包含保密信息", re.IGNORECASE),
    re.compile(r"若误收此邮件", re.IGNORECASE),
]
DISCLAIMER_HINT_RE = re.compile(
    r"(confidential|disclaimer|intended recipient|privileged|do not distribute|virus|liability|unauthorized"
    r"|保密|机密|未经授权|误收|删除|病毒|免责)", re.IGNORECASE
)
CONTACT_INFO_RE = re.compile(
    r"(tel|mobile|phone|dir|fax|web|email|addr|room|tower|road|st|street|中国|上海|北京|邮编|zip|box|floor|level|suite"
    r"|经理|主管|负责人|manager|lead|director|executive|specialist|engineer|consultant|assistant|representative|associate|chief)[:\s+]",
    re.IGNORECASE,
)
SIGNATURE_HINT_RE = re.compile(
    r"(phone|mobile|tel|fax|wechat|weixin|whatsapp|skype|email|e-mail|www\.|http://|https://|@"
    r"|company|co\.,?\s*ltd|limited|corporation|inc\.?|llc|office|room|building|district|road|street|avenue"
    r"|中国|上海|北京|深圳|广州|地址|电话|手机|邮箱|网址|微信|企业微信|视频号|抖音|小红书|大厦|室|号|路)",
    re.IGNORECASE,
)
SIGNATURE_NAME_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,40}$|^[一-鿿]{2,12}(?:\s+[A-Za-z][A-Za-z .'\-]{1,30})?$")
SIGNATURE_NAME_TITLE_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,40}\s*\|\s*.+$")
SIGNATURE_ORG_RE = re.compile(
    r"(co\.,?\s*ltd|limited|corporation|inc\.?|llc|company|group|technology|tech|trading|industrial|factory"
    r"|公司|科技|贸易|工业|有限|集团|工厂)", re.IGNORECASE
)
SIGNATURE_SOCIAL_RE = re.compile(
    r"(企业微信|微信|视频号|抖音|小红书|wechat|whatsapp|skype|linkedin)", re.IGNORECASE
)
BODY_LIKE_RE = re.compile(r"[。！？.!?]|(please|could|would|kindly|thanks for|we can|我们|请|烦请|安排|确认)", re.IGNORECASE)
AUTO_MAIL_PATTERNS = [
    ("out_of_office", re.compile(r"(automatic reply|auto.?reply|out of office|autoreply)", re.IGNORECASE)),
    ("delivery_failed", re.compile(r"(delivery status notification|undeliverable|delivery failed|mail delivery subsystem)", re.IGNORECASE)),
    ("system_notice", re.compile(r"(system notification|do not reply|noreply|no-reply)", re.IGNORECASE)),
]


def _strip_html(text: str) -> str:
    if "<" not in text or ">" not in text:
        return CID_RE.sub("", text)
    cleaned = HTML_BLOCK_RE.sub(" ", text)
    cleaned = HTML_BREAK_RE.sub("\n", cleaned)
    cleaned = HTML_TAG_RE.sub(" ", cleaned)
    return html.unescape(CID_RE.sub("", cleaned))


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _collapse_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in _normalize_newlines(text).split("\n")]
    compact = MULTI_BLANK_RE.sub("\n\n", "\n".join(lines))
    return compact.strip()


def _strip_edge_noise(lines: list[str]) -> list[str]:
    cleaned = list(lines)
    for end in (False, True):
        while cleaned:
            idx = -1 if end else 0
            stripped = cleaned[idx].strip()
            if (not stripped
                    or EDGE_NOISE_LABEL_RE.fullmatch(stripped)
                    or re.fullmatch(r"[\[\](){}<>|/\\*#~·•\-\s]+", stripped)):
                cleaned.pop(idx)
            else:
                break
    return cleaned


def _find_quote_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in STRONG_QUOTE_MARKERS):
            return index
        if any(p.search(stripped) for p in WEAK_QUOTE_MARKERS):
            header_hits = has_sender = has_subject = has_date = 0
            prev_header = False
            for offset in range(index, min(index + 8, len(lines))):
                probe = lines[offset].strip()
                if not probe:
                    continue
                if any(p.search(probe) for p in WEAK_QUOTE_MARKERS):
                    header_hits += 1
                    if any(p.match(probe) for p in HEADER_SENDER_PATTERNS):
                        has_sender = 1
                    if any(p.match(probe) for p in HEADER_SUBJECT_PATTERNS):
                        has_subject = 1
                    if any(p.match(probe) for p in HEADER_DATE_PATTERNS):
                        has_date = 1
                    prev_header = True
                    continue
                if prev_header and ("@" in probe or re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", probe) or len(probe) <= 80):
                    prev_header = False
                    continue
                break
            if header_hits >= 2 and ((has_sender and has_date) or has_subject):
                return index
    return None


def _extract_disclaimer(lines: list[str]) -> tuple[list[str], list[str]]:
    lower_bound = max(0, len(lines) - 24)
    explicit_start: int | None = None
    candidate_start: int | None = None
    hint_count = 0
    for index in range(lower_bound, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in DISCLAIMER_MARKERS):
            explicit_start = index
            break
        if DISCLAIMER_HINT_RE.search(stripped):
            if candidate_start is None:
                candidate_start = index
            hint_count += 1
    if explicit_start is not None:
        return lines[:explicit_start], lines[explicit_start:]
    if candidate_start is not None and hint_count >= 3:
        return lines[:candidate_start], lines[candidate_start:]
    return lines, []


def _signature_score(line: str) -> int:
    stripped = line.strip()
    if not stripped:
        return 0
    score = 0
    if any(p.search(stripped) for p in SIGNATURE_MARKERS):
        score += 4
    if CONTACT_INFO_RE.search(stripped):
        score += 2
    if SIGNATURE_HINT_RE.search(stripped):
        score += 1
    if SIGNATURE_NAME_LINE_RE.match(stripped):
        score += 1
    if SIGNATURE_NAME_TITLE_RE.match(stripped):
        score += 2
    if SIGNATURE_ORG_RE.search(stripped):
        score += 2
    if SIGNATURE_SOCIAL_RE.search(stripped):
        score += 1
    if len(stripped) <= 24 and not BODY_LIKE_RE.search(stripped):
        score += 1
    return score


def _looks_like_body_sentence(line: str) -> bool:
    stripped = line.strip()
    if not stripped or re.fullmatch(r"https?://\S+", stripped, re.IGNORECASE):
        return False
    if any(p.search(stripped) for p in WEAK_QUOTE_MARKERS):
        return False
    return bool(BODY_LIKE_RE.search(stripped))


def _is_signature_start_valid(lines: list[str], start: int) -> bool:
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _looks_like_body_sentence(stripped) and not (_signature_score(stripped) >= 2):
            return False
    return True


def _extract_signature(lines: list[str]) -> tuple[list[str], list[str]]:
    lines = _strip_edge_noise(lines)
    if not lines:
        return [], []
    lower_bound = max(0, len(lines) - 20)
    explicit_candidates: list[int] = []
    candidate_start: int | None = None
    total_score = 0
    for index in range(lower_bound, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in SIGNATURE_MARKERS):
            explicit_candidates.append(index)
        sc = _signature_score(stripped)
        if sc > 0:
            if candidate_start is None:
                candidate_start = index
            total_score += sc
    start: int | None = None
    for cand in explicit_candidates:
        if _is_signature_start_valid(lines, cand):
            start = cand
            break
    if start is None and candidate_start is not None and total_score >= 5:
        for cand in range(candidate_start, len(lines)):
            stripped = lines[cand].strip()
            if not stripped or _signature_score(stripped) <= 0:
                continue
            if _is_signature_start_valid(lines, cand):
                start = cand
                break
    if start is None:
        return lines, []
    while start > 0:
        stripped = lines[start - 1].strip()
        if not stripped:
            break
        if LOGO_PLACEHOLDER_RE.match(stripped) or re.fullmatch(r"[_\-=\*#~]{3,}", stripped):
            start -= 1
        else:
            break
    return lines[:start], lines[start:]


def _normalize_address_list(values: list[str] | str | None) -> list[str]:
    if not values:
        return []
    candidates = values if isinstance(values, list) else [values]
    normalized: list[str] = []
    for _, address in getaddresses(candidates):
        value = address.strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _email_domain(email: str) -> str:
    return email.split("@", 1)[1] if "@" in email else ""


def _normalize_customer_key(email: str) -> str:
    email = email.strip().lower()
    if "@" in email:
        local, domain = email.rsplit("@", 1)
        local = local.split("+")[0]
        return f"{local}@{domain}"
    return email


def _resolve_sender_side(from_email_std: str, participants: list[str], internal_domains: set[str]) -> str:
    from_domain = _email_domain(from_email_std)
    external_participants = [e for e in participants if _email_domain(e) not in internal_domains]
    if from_domain and from_domain in internal_domains:
        return "internal" if not external_participants else "seller"
    return "customer"


def _resolve_customer_key(sender_side: str, from_email_std: str, to_emails_std: list[str], cc_emails_std: list[str], internal_domains: set[str]) -> str:
    if sender_side == "customer" and from_email_std:
        return _normalize_customer_key(from_email_std)
    for candidate in to_emails_std + cc_emails_std:
        if _email_domain(candidate) not in internal_domains:
            return _normalize_customer_key(candidate)
    return ""


def _normalize_subject(subject: str) -> str:
    result = re.sub(
        r"^\s*((re|fw|fwd|reply|sv|aw|wg|rv|tr)\s*[:：]\s*|(回复|答复|回覆|转发|轉寄|转寄|返信|転送)\s*[:：]\s*)+",
        "", subject or "", flags=re.IGNORECASE
    )
    result = re.sub(r"\[external\]|\[ext\]", "", result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip()


def _get_internal_domains(db: Session) -> set[str]:
    """从 mail_account 表获取内部域名集合"""
    try:
        rows = db.execute(text("SELECT email_address FROM mail_account")).fetchall()
        domains: set[str] = set()
        for row in rows:
            email = (row[0] or "").strip().lower()
            if "@" in email:
                domains.add(email.split("@", 1)[1])
        return domains
    except Exception:
        return set()


def clean_mail_payload(raw_mail: dict[str, Any], internal_domains: set[str] | None = None) -> dict[str, Any]:
    """纯文本清洗，不依赖数据库"""
    domains = internal_domains or set()
    raw_text = raw_mail.get("body_text") or ""
    body_text_clean = _collapse_whitespace(_strip_html(raw_text))
    lines = _strip_edge_noise(body_text_clean.split("\n") if body_text_clean else [])

    quote_start = _find_quote_start(lines)
    if quote_start is None:
        main_lines, quoted_lines = lines, []
    else:
        main_lines, quoted_lines = lines[:quote_start], lines[quote_start:]

    main_lines = _strip_edge_noise(main_lines)
    main_lines, disclaimer_lines = _extract_disclaimer(main_lines)
    main_lines, signature_lines = _extract_signature(main_lines)
    main_lines = _strip_edge_noise(main_lines)

    body_main_text = _collapse_whitespace("\n".join(main_lines))
    body_quoted_text = _collapse_whitespace("\n".join(_strip_edge_noise(quoted_lines)))
    signature_text = _collapse_whitespace("\n".join(_strip_edge_noise(signature_lines)))
    disclaimer_text = _collapse_whitespace("\n".join(_strip_edge_noise(disclaimer_lines)))

    subject = raw_mail.get("subject") or ""
    from_email_val = raw_mail.get("from_email") or ""
    is_auto_mail = False
    auto_mail_type = ""
    combined = f"{subject}\n{body_main_text}\n{from_email_val}"
    for auto_type, pattern in AUTO_MAIL_PATTERNS:
        if pattern.search(combined):
            is_auto_mail = True
            auto_mail_type = auto_type
            break

    from_email_std = next(iter(_normalize_address_list(from_email_val)), "")
    to_emails_std = _normalize_address_list(raw_mail.get("to_emails"))
    cc_emails_std = _normalize_address_list(raw_mail.get("cc_emails"))
    participant_emails_std: list[str] = []
    for item in [from_email_std, *to_emails_std, *cc_emails_std]:
        if item and item not in participant_emails_std:
            participant_emails_std.append(item)

    sender_side = _resolve_sender_side(from_email_std, participant_emails_std, domains)
    customer_key = _resolve_customer_key(sender_side, from_email_std, to_emails_std, cc_emails_std, domains)
    contact_emails_customer_side = [e for e in participant_emails_std if _email_domain(e) not in domains]

    return {
        "mail_uid": raw_mail["mail_uid"],
        "body_text_clean": body_text_clean,
        "body_main_text": body_main_text,
        "body_quoted_text": body_quoted_text,
        "signature_text": signature_text,
        "disclaimer_text": disclaimer_text,
        "normalized_subject": _normalize_subject(subject),
        "from_email_std": from_email_std,
        "to_emails_std": to_emails_std,
        "cc_emails_std": cc_emails_std,
        "participant_emails_std": participant_emails_std,
        "sender_side": sender_side,
        "customer_key": customer_key,
        "contact_emails_customer_side": contact_emails_customer_side,
        "contact_emails_all": participant_emails_std,
        "clean_status": "completed",
        "clean_error": "",
        "is_auto_mail": is_auto_mail,
        "auto_mail_type": auto_mail_type,
        "cleaned_at": _utc_now(),
    }


# ── 数据库操作（SQLAlchemy text() 风格） ──────────────────────────────────────
def insert_mail_raw(db: Session, mail: dict[str, Any], batch_id: int | None = None) -> str:
    """将解析好的邮件写入 mail_raw_unified，返回 mail_uid"""
    mail_uid = mail["mail_uid"]
    existing = db.execute(
        text("SELECT mail_uid FROM mail_raw_unified WHERE mail_uid = :uid"), {"uid": mail_uid}
    ).fetchone()
    if existing:
        return mail_uid
    db.execute(text("""
        INSERT INTO mail_raw_unified (
            mail_uid, source_type, import_batch_id, folder_name, direction,
            internet_message_id, in_reply_to, references_text, conversation_key,
            subject, body_text, from_email, to_emails, cc_emails,
            sent_at, received_at, has_attachment, raw_payload_path, ingested_at
        ) VALUES (
            :mail_uid, :source_type, :import_batch_id, :folder_name, :direction,
            :internet_message_id, :in_reply_to, :references_text, :conversation_key,
            :subject, :body_text, :from_email, :to_emails::jsonb, :cc_emails::jsonb,
            :sent_at, :received_at, :has_attachment, :raw_payload_path, NOW()
        )
    """), {
        "mail_uid": mail_uid,
        "source_type": mail.get("source_type", "manual_import"),
        "import_batch_id": batch_id,
        "folder_name": mail.get("folder_name", "manual-import"),
        "direction": mail.get("direction", "inbound"),
        "internet_message_id": mail.get("internet_message_id"),
        "in_reply_to": mail.get("in_reply_to"),
        "references_text": mail.get("references_text"),
        "conversation_key": mail.get("conversation_key", ""),
        "subject": mail.get("subject", ""),
        "body_text": mail.get("body_text", ""),
        "from_email": mail.get("from_email", ""),
        "to_emails": json.dumps(mail.get("to_emails") or [], ensure_ascii=False),
        "cc_emails": json.dumps(mail.get("cc_emails") or [], ensure_ascii=False),
        "sent_at": mail.get("sent_at") or None,
        "received_at": mail.get("received_at") or None,
        "has_attachment": bool(mail.get("has_attachment")),
        "raw_payload_path": mail.get("raw_payload_path", ""),
    })
    return mail_uid


def create_mail_batch(db: Session, source_name: str, import_type: str = "manual_eml") -> int:
    """创建 mail_import_batch 记录，返回 id"""
    row = db.execute(text("""
        INSERT INTO mail_import_batch (import_type, source_name, file_count, success_count, failed_count, import_status, created_at)
        VALUES (:import_type, :source_name, 0, 0, 0, 'pending', NOW())
        RETURNING id
    """), {"import_type": import_type, "source_name": source_name}).fetchone()
    db.commit()
    return row[0]


def upsert_mail_cleaned(db: Session, raw_mail: dict[str, Any]) -> None:
    """清洗邮件正文并写入 mail_cleaned 表"""
    internal_domains = _get_internal_domains(db)
    try:
        payload = clean_mail_payload(raw_mail, internal_domains)
    except Exception as exc:
        payload = {
            "mail_uid": raw_mail["mail_uid"],
            "body_text_clean": "", "body_main_text": "", "body_quoted_text": "",
            "signature_text": "", "disclaimer_text": "", "normalized_subject": "",
            "from_email_std": "", "to_emails_std": [], "cc_emails_std": [],
            "participant_emails_std": [], "sender_side": "", "customer_key": "",
            "contact_emails_customer_side": [], "contact_emails_all": [],
            "clean_status": "failed", "clean_error": str(exc),
            "is_auto_mail": False, "auto_mail_type": "", "cleaned_at": _utc_now(),
        }
    db.execute(text("""
        INSERT INTO mail_cleaned (
            mail_uid, body_text_clean, body_main_text, body_quoted_text,
            signature_text, disclaimer_text, normalized_subject, from_email_std,
            to_emails_std, cc_emails_std, participant_emails_std, sender_side,
            customer_key, contact_emails_customer_side, contact_emails_all,
            clean_status, clean_error, is_auto_mail, auto_mail_type, cleaned_at
        ) VALUES (
            :mail_uid, :body_text_clean, :body_main_text, :body_quoted_text,
            :signature_text, :disclaimer_text, :normalized_subject, :from_email_std,
            :to_emails_std::jsonb, :cc_emails_std::jsonb, :participant_emails_std::jsonb, :sender_side,
            :customer_key, :contact_emails_customer_side::jsonb, :contact_emails_all::jsonb,
            :clean_status, :clean_error, :is_auto_mail, :auto_mail_type, :cleaned_at
        )
        ON CONFLICT (mail_uid) DO UPDATE SET
            body_text_clean=EXCLUDED.body_text_clean, body_main_text=EXCLUDED.body_main_text,
            body_quoted_text=EXCLUDED.body_quoted_text, signature_text=EXCLUDED.signature_text,
            disclaimer_text=EXCLUDED.disclaimer_text, normalized_subject=EXCLUDED.normalized_subject,
            from_email_std=EXCLUDED.from_email_std, to_emails_std=EXCLUDED.to_emails_std,
            cc_emails_std=EXCLUDED.cc_emails_std, participant_emails_std=EXCLUDED.participant_emails_std,
            sender_side=EXCLUDED.sender_side, customer_key=EXCLUDED.customer_key,
            contact_emails_customer_side=EXCLUDED.contact_emails_customer_side,
            contact_emails_all=EXCLUDED.contact_emails_all,
            clean_status=EXCLUDED.clean_status, clean_error=EXCLUDED.clean_error,
            is_auto_mail=EXCLUDED.is_auto_mail, auto_mail_type=EXCLUDED.auto_mail_type,
            cleaned_at=EXCLUDED.cleaned_at
    """), {
        "mail_uid": payload["mail_uid"],
        "body_text_clean": payload["body_text_clean"],
        "body_main_text": payload["body_main_text"],
        "body_quoted_text": payload["body_quoted_text"],
        "signature_text": payload["signature_text"],
        "disclaimer_text": payload["disclaimer_text"],
        "normalized_subject": payload["normalized_subject"],
        "from_email_std": payload["from_email_std"],
        "to_emails_std": json.dumps(payload["to_emails_std"], ensure_ascii=False),
        "cc_emails_std": json.dumps(payload["cc_emails_std"], ensure_ascii=False),
        "participant_emails_std": json.dumps(payload["participant_emails_std"], ensure_ascii=False),
        "sender_side": payload["sender_side"],
        "customer_key": payload["customer_key"],
        "contact_emails_customer_side": json.dumps(payload["contact_emails_customer_side"], ensure_ascii=False),
        "contact_emails_all": json.dumps(payload["contact_emails_all"], ensure_ascii=False),
        "clean_status": payload["clean_status"],
        "clean_error": payload["clean_error"],
        "is_auto_mail": payload["is_auto_mail"],
        "auto_mail_type": payload["auto_mail_type"],
        "cleaned_at": payload["cleaned_at"],
    })
