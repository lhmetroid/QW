# -*- coding: utf-8 -*-
"""邮件统计引擎：统计通过套装页 /static/mail-suite.html 转入 CRM 的 AI 邮件及其成效。

五个指标(每个按各自事件发生当天计):
- 生成数(generated): 当天实际转入 CRM(enqueued)的封数(去掉未勾选/失败), 按转入当天。
- 实发数(sent):     转入邮件真发成功(spSendInfo{销售}.Status=SendSuccess), 按 FactSendTime 当天。
- 回信数(reply):     该 AI 邮件的客户回信(FTP 解析收件 .eml 的 In-Reply-To 精确匹配发送 Message-ID), 按收信当天。
- 有价值数(valuable): 回信经 deepseek 价值判定为有价值, 按收信当天。
- 反馈数(feedback): 该邮件在套装页留过反馈(mail_customer_suite_feedback), 按反馈当天。

时间口径: 本地 PostgreSQL 存的是 UTC, CRM(SQL Server)存的是北京本地时间。
统一按北京时间(UTC+8)分日: 本地时间 +8h 再取 date; CRM 时间直接取 date。
"""
import logging
import re
from datetime import datetime, timedelta, date

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

BJ_OFFSET = timedelta(hours=8)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 我方企业邮箱域(回信发件人不该是我们自己)
_OUR_DOMAINS = ("speed-asia.com",)
_MAIL_AI_USE_RANGE = "宣传邮件-AI"


def bj_date(dt) -> date | None:
    """本地 UTC 时间 -> 北京日期。"""
    if dt is None:
        return None
    return (dt + BJ_OFFSET).date()


def _extract_email(raw: str) -> str:
    m = _EMAIL_RE.search(raw or "")
    return m.group(0).lower() if m else ""


def _all_emails(raw: str) -> list[str]:
    return [e.lower() for e in _EMAIL_RE.findall(raw or "")]


def _staff_partition(prefix: str, staff_id: str) -> str | None:
    """spSendInfo / spReceiveInfo 分表名。staff_id 形如 '0017'。"""
    sid = (staff_id or "").strip()
    if not sid or not re.fullmatch(r"[0-9A-Za-z]{1,8}", sid):
        return None
    return f"{prefix}{sid}"


def _crm_table_exists(crm, name: str) -> bool:
    try:
        row = crm.execute(
            text("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME=:n"), {"n": name}
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _crm_column_exists(crm, table: str, column: str) -> bool:
    try:
        row = crm.execute(text(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=:t AND COLUMN_NAME=:c"
        ), {"t": table, "c": column}).fetchone()
        return bool(row)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# FTP: 拉取 .eml 并解析头部(回信精确匹配)
# ---------------------------------------------------------------------------
def fetch_eml_headers(eml_rel_path: str) -> dict:
    """从 SFTP 拉取 .eml, 解析关键头部。失败返回 {}。

    eml_rel_path 形如 '2026\\06\\23\\uuid'(CRM 存反斜杠), 转成正斜杠。
    """
    rel = (eml_rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return {}
    import paramiko
    import mail_sftp
    from email.parser import BytesParser
    from email import policy
    t = None
    try:
        t = mail_sftp._open_transport()
        sftp = paramiko.SFTPClient.from_transport(t)
        with sftp.open(rel, "rb") as f:
            # 只需头部: 读到首个空行即可, 这里读前 64KB 足够覆盖头区
            raw = f.read(65536)
        # 截到头部结束(空行), 避免大正文解析
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            sep = raw.find(b"\n\n")
        head_bytes = raw[: sep if sep != -1 else len(raw)]
        msg = BytesParser(policy=policy.default).parsebytes(head_bytes)
        return {
            "message_id": (msg.get("Message-ID") or msg.get("Message-Id") or "").strip(),
            "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
            "references": (msg.get("References") or "").strip(),
            "from": str(msg.get("From") or "").strip(),
            "subject": str(msg.get("Subject") or "").strip(),
        }
    except Exception as exc:
        logger.warning("MAIL_AI_FETCH_EML_FAILED path=%s err=%s", rel, exc)
        return {}
    finally:
        try:
            if t:
                t.close()
        except Exception:
            pass


def _norm_msgid(v: str) -> str:
    """归一 Message-ID: 去尖括号空白小写, 便于包含匹配。"""
    return (v or "").strip().strip("<>").strip().lower()


# 回复/转发前缀(中英文常见)。归一主题用于"主题串接"兜底匹配。
_SUBJECT_PREFIX_RE = re.compile(
    r"^\s*(re|aw|sv|答复|回复|回覆|转发|轉發|fw|fwd)\s*[:：]\s*", re.I
)


def _norm_subject(s: str) -> str:
    """归一主题: 反复剥离 RE:/答复:/FW: 等前缀, 去首尾空白并小写, 便于回信与原邮件主题精确比对。"""
    t = (s or "").strip()
    for _ in range(6):
        nt = _SUBJECT_PREFIX_RE.sub("", t)
        if nt == t:
            break
        t = nt.strip()
    return t.strip().lower()


# 接收端(CRM 发信软件)对回信解析后, 把原始 AI 邮件的 Message-ID 整段写进 spReceiveInfo{销售}.Message_ID 列,
# 格式固定为 <AIMAIL-{SendId}-{StaffId}-{发件邮箱}>。SendId 自身含 '-'(如 Mal_S260625-000003), StaffId 不含 '-'/'@',
# 故贪婪取第一段为 SendId、第二段为 StaffId、第三段为邮箱(与发送端 C# 正则一致)。
_AIMAIL_COL_RE = re.compile(r"AIMAIL-(.+)-([^-@]+)-(.+@.+)", re.I)


def extract_send_id_from_msgid_col(value: str) -> str:
    """从 spReceiveInfo.Message_ID 列值提取原始发送 SendId。无 AIMAIL token 返回空串。"""
    m = _AIMAIL_COL_RE.search((value or "").strip().strip("<>"))
    return m.group(1).strip() if m else ""


# 发送端规则: Message-ID 形如 <AIMAIL-{SendId}@域> 或 <AIMAIL-{SendId}-{uniq}@域>。
# SendId 是唯一关联键(发送端有, 本地 crm_send_id 也存); uniq 可选、由发送端生成、读取端忽略。
# 正则只抓 AIMAIL- 到 @/>/空白 之间的整段 token(可能是 SendId, 也可能是 SendId-uniq), 再按 SendId 匹配。
_AI_MSGID_RE = re.compile(r"AIMAIL-([^@>\s]+)", re.I)


def extract_ai_tokens_from_refs(*header_values: str) -> list[str]:
    """从 In-Reply-To/References 头提取所有 AIMAIL- 后的 token(SendId 或 SendId-uniq)。"""
    found: list[str] = []
    for hv in header_values:
        for m in _AI_MSGID_RE.findall(hv or ""):
            t = m.strip()
            if t:
                found.append(t)
    return found


def ai_token_matches_send_id(token: str, send_id: str) -> bool:
    """token 命中 send_id: 完全相等(无 uniq) 或 以 send_id- 开头(发送端追加了 uniq)。"""
    sid = (send_id or "").strip()
    tok = (token or "").strip()
    if not sid or not tok:
        return False
    return tok == sid or tok.startswith(sid + "-")


# ---------------------------------------------------------------------------
# 1) 同步真发状态: 本地 send_plan <- CRM spSendInfo{销售}.SendId
# ---------------------------------------------------------------------------
def _crm_send_info_for_missing_send_id(crm, table_name: str, plan) -> object | None:
    """Fallback when CRM SendId was not readable immediately after queue insert.

    Some CRM sender deployments remove the queue row and only later expose the generated SendId in
    spSendInfo{staff}. In that case local crm_send_id stays empty, so match by the narrow immutable
    fields we inserted: exact subject, planned send minute, AI UseRange, and sender address.
    """
    subject = (plan[5] or "").strip()
    sender = (plan[7] or "").strip().lower()
    if "@" not in sender or "*" in sender:
        sender = ""
    plan_time = plan[6]
    if not subject or not plan_time:
        return None
    start = plan_time - timedelta(minutes=2)
    end = plan_time + timedelta(minutes=10)
    rows = crm.execute(text(
        f"SELECT TOP 2 SendId, Status, FactSendTime, EmlFtpDir, DeleteTime "
        f"FROM [{table_name}] "
        f"WHERE Subject=:sub AND PlanSendTime>=:a AND PlanSendTime<:b "
        f"AND UseRange=:ur "
        f"AND (:sender='' OR LOWER(CAST(COALESCE(SendAddress,'') AS NVARCHAR(MAX))) LIKE :sender_like) "
        f"ORDER BY FactSendTime DESC, PlanSendTime DESC"
    ), {
        "sub": subject,
        "a": start,
        "b": end,
        "ur": _MAIL_AI_USE_RANGE,
        "sender": sender,
        "sender_like": f"%{sender}%" if sender else "%",
    }).fetchall()
    if len(rows) != 1:
        return None
    return rows[0]


def sync_send_status(db: Session, lookback_days: int = 120) -> dict:
    """对最近 lookback_days 转入的 enqueued 计划, 用 SendId 关联 spSendInfo{销售} 回填真发状态;
    真发成功且尚无 message_id 的, 拉发送 .eml 解析 Message-ID(供回信匹配)。"""
    from crm_database import CRMSessionLocal
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    plans = db.execute(text(
        "SELECT plan_id, crm_send_id, inputer_staff_id, crm_message_id, crm_send_status, "
        "       subject, plan_send_time, sender_email "
        "FROM mail_customer_suite_send_plan "
        "WHERE status='enqueued' AND created_at>=:cut"
    ), {"cut": cutoff}).fetchall()
    if not plans:
        return {"checked": 0, "sent": 0}
    by_staff: dict[str, list] = {}
    for p in plans:
        by_staff.setdefault((p[2] or "").strip(), []).append(p)
    crm = CRMSessionLocal()
    checked = 0
    sent = 0
    try:
        for staff_id, rows in by_staff.items():
            tbl = _staff_partition("spSendInfo", staff_id)
            if not tbl or not _crm_table_exists(crm, tbl):
                continue
            send_ids = [r[1] for r in rows if r[1]]
            # 分批 IN 查询
            info = {}
            if send_ids:
                for i in range(0, len(send_ids), 200):
                    chunk = send_ids[i:i + 200]
                    params = {f"s{j}": v for j, v in enumerate(chunk)}
                    placeholders = ",".join(f":s{j}" for j in range(len(chunk)))
                    q = crm.execute(text(
                        f"SELECT SendId, Status, FactSendTime, EmlFtpDir, DeleteTime "
                        f"FROM [{tbl}] WHERE SendId IN ({placeholders})"
                    ), params).fetchall()
                    for rr in q:
                        info[str(rr[0])] = rr
            for r in rows:
                checked += 1
                rec = info.get(str(r[1])) if r[1] else None
                recovered_send_id = None
                if rec is None and not r[1]:
                    rec = _crm_send_info_for_missing_send_id(crm, tbl, r)
                    if rec is not None and rec[0]:
                        recovered_send_id = str(rec[0])
                plan_id = r[0]
                if rec is None:
                    # SendId 不在 spSendInfo: 仍在队列待发 或 已被删除。缺 SendId 的未来计划保持空状态, 等后续真发后再反查。
                    if r[1]:
                        db.execute(text(
                            "UPDATE mail_customer_suite_send_plan "
                            "SET crm_send_status=COALESCE(crm_send_status,'pending_or_deleted'), status_synced_at=now() "
                            "WHERE plan_id=:pid"
                        ), {"pid": plan_id})
                    continue
                status_v = (str(rec[1]) if rec[1] else "").strip()
                fact = rec[2]
                eml_dir = (str(rec[3]) if rec[3] else "").strip()
                deleted = rec[4] is not None
                final_status = "deleted" if deleted else status_v
                db.execute(text(
                    "UPDATE mail_customer_suite_send_plan "
                    "SET crm_send_id=COALESCE(crm_send_id,:sid), crm_send_status=:st, "
                    "crm_fact_send_time=:ft, crm_eml_ftp_dir=:ed, status_synced_at=now() "
                    "WHERE plan_id=:pid"
                ), {"sid": recovered_send_id, "st": final_status, "ft": fact, "ed": eml_dir, "pid": plan_id})
                if status_v == "SendSuccess" and not deleted:
                    sent += 1
                    # 解析发送 Message-ID(仅一次)
                    if not (r[3] or "").strip() and eml_dir:
                        hdr = fetch_eml_headers(eml_dir)
                        mid = _norm_msgid(hdr.get("message_id"))
                        if mid:
                            db.execute(text(
                                "UPDATE mail_customer_suite_send_plan SET crm_message_id=:m WHERE plan_id=:pid"
                            ), {"m": mid, "pid": plan_id})
        db.commit()
    finally:
        crm.close()
    return {"checked": checked, "sent": sent}


# ---------------------------------------------------------------------------
# 2) 回信发现: spReceiveInfo{销售} 候选 -> FTP 解析 In-Reply-To 精确匹配
# ---------------------------------------------------------------------------
def discover_replies(db: Session, lookback_days: int = 120, max_fetch: int = 400) -> dict:
    """对真发成功且已解析 message_id 的 AI 邮件, 在对应销售的 spReceiveInfo 分表里找候选回信
    (发件人=我方收件客户邮箱 且 收信晚于实发), 拉收件 .eml 解析 In-Reply-To/References,
    若包含我们的发送 Message-ID 即判定为回信; 若发送 .eml 无 Message-ID(CRM 经 Exchange 真发常见),
    再用"发件人+归一主题精确串接+收信晚于实发"兜底定位, 写入 mail_ai_reply_analysis。"""
    from crm_database import CRMSessionLocal
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    plans = db.execute(text(
        "SELECT plan_id, crm_send_id, customer_id, inputer_staff_id, to_emails, "
        "       crm_message_id, crm_fact_send_time, subject "
        "FROM mail_customer_suite_send_plan "
        "WHERE status='enqueued' AND crm_send_status='SendSuccess' AND created_at>=:cut"
    ), {"cut": cutoff}).fetchall()
    if not plans:
        return {"candidates": 0, "matched": 0}
    # 已记录的 (plan_id, reply_crm_rowid) 去重集
    existing = set(
        (str(a), str(b)) for a, b in db.execute(text(
            "SELECT plan_id, reply_crm_rowid FROM mail_ai_reply_analysis"
        )).fetchall()
    )
    by_staff: dict[str, list] = {}
    for p in plans:
        by_staff.setdefault((p[3] or "").strip(), []).append(p)

    crm = CRMSessionLocal()
    candidates = 0
    matched = 0
    fetched = 0
    try:
        for staff_id, rows in by_staff.items():
            tbl = _staff_partition("spReceiveInfo", staff_id)
            if not tbl or not _crm_table_exists(crm, tbl):
                continue
            # 该销售下: send_id -> plan(精确回链键); 客户邮箱 -> [plan...](兜底); 最早实发时间(限定扫描窗口)
            send_id_to_plan: dict[str, object] = {}
            email_to_plans: dict[str, list] = {}
            min_time = None
            for p in rows:
                sid = (p[1] or "").strip()
                if sid:
                    send_id_to_plan.setdefault(sid, p)
                for e in _all_emails(p[4]):
                    if any(d in e for d in _OUR_DOMAINS):
                        continue
                    email_to_plans.setdefault(e, []).append(p)
                ft = p[6]
                if ft and (min_time is None or ft < min_time):
                    min_time = ft
            if min_time is None:
                continue

            # ---- 主路径: 直读 spReceiveInfo{销售}.Message_ID 列 ----
            # 接收端已把回信里的 <AIMAIL-{SendId}-{StaffId}-{邮箱}> 解析后写入该列。正则取 SendId 与本地 crm_send_id
            # 精确匹配即可定位发出的那封 AI 邮件, 无需拉 .eml、不依赖发件人/主题, 最稳。
            if send_id_to_plan and _crm_column_exists(crm, tbl, "Message_ID"):
                amrows = crm.execute(text(
                    f"SELECT RowId, Sender, Subject, ReceiveTime, EmailContent, PureText, Message_ID "
                    f"FROM [{tbl}] WHERE MessageType='Email' AND ReceiveTime>=:mt "
                    f"AND Message_ID LIKE '%AIMAIL-%' ORDER BY ReceiveTime DESC"
                ), {"mt": min_time}).fetchall()
                for c in amrows:
                    reply_rowid = str(c[0])
                    sid = extract_send_id_from_msgid_col(c[6])
                    p = send_id_to_plan.get(sid) if sid else None
                    if p is None or (str(p[0]), reply_rowid) in existing:
                        continue
                    candidates += 1
                    body = (c[4] or c[5] or "")
                    if isinstance(body, bytes):
                        body = body.decode("utf-8", "replace")
                    db.execute(text(
                        "INSERT INTO mail_ai_reply_analysis "
                        "(plan_id, crm_send_id, customer_id, staff_id, reply_crm_rowid, reply_sender, "
                        " reply_subject, reply_body, reply_received_at, match_method, created_at) "
                        "VALUES (:pid,:sid,:cid,:stf,:rid,:snd,:sub,:body,:rt,:mm, now()) "
                        "ON CONFLICT (plan_id, reply_crm_rowid) DO NOTHING"
                    ), {
                        "pid": p[0], "sid": p[1], "cid": p[2], "stf": staff_id,
                        "rid": reply_rowid, "snd": _extract_email(c[1] or ""),
                        "sub": (c[2] or "")[:500], "body": body[:20000],
                        "rt": c[3], "mm": "crm_message_id_col",
                    })
                    existing.add((str(p[0]), reply_rowid))
                    matched += 1

            # ---- 兜底路径: 老邮件(发送端未注入 AIMAIL Message-ID)按 发件人 + .eml/主题 串接 ----
            if not email_to_plans:
                continue
            emails = list(email_to_plans.keys())
            # 候选收信: 发件人含我方客户邮箱 且 收信晚于最早实发时间
            like_clauses = []
            params = {"mt": min_time}
            for j, e in enumerate(emails):
                like_clauses.append(f"Sender LIKE :e{j}")
                params[f"e{j}"] = f"%{e}%"
            where_sender = " OR ".join(like_clauses)
            q = crm.execute(text(
                f"SELECT RowId, Sender, Subject, EmlFtpDir, ReceiveTime, EmailContent, PureText "
                f"FROM [{tbl}] WHERE MessageType='Email' AND ReceiveTime>=:mt "
                f"AND EmlFtpDir IS NOT NULL AND ({where_sender}) "
                f"ORDER BY ReceiveTime DESC"
            ), params).fetchall()
            for c in q:
                reply_rowid = str(c[0])
                sender_raw = c[1] or ""
                sender_email = ""
                for e in emails:
                    if e in sender_raw.lower():
                        sender_email = e
                        break
                if not sender_email:
                    continue
                cand_plans = email_to_plans.get(sender_email, [])
                # 该客户邮箱关联的、且尚未对该回信登记过的计划
                pend_plans = [p for p in cand_plans if (str(p[0]), reply_rowid) not in existing]
                if not pend_plans:
                    continue
                candidates += 1
                if fetched >= max_fetch:
                    continue
                fetched += 1
                hdr = fetch_eml_headers(c[3])
                in_reply_to = hdr.get("in_reply_to") or ""
                references = hdr.get("references") or ""
                refs = (_norm_msgid(in_reply_to) + " " + references.lower())
                if not refs.strip():
                    continue
                # 主路径(发送端规则): 从 In-Reply-To/References 提取 token, 按 crm_send_id 匹配(uniq 忽略)
                ref_tokens = extract_ai_tokens_from_refs(in_reply_to, references)
                body = (c[5] or c[6] or "")
                if isinstance(body, bytes):
                    body = body.decode("utf-8", "replace")
                rtime = c[4]
                reply_subj_norm = _norm_subject(c[2])
                for p in pend_plans:
                    method = None
                    if ref_tokens and any(ai_token_matches_send_id(t, p[1]) for t in ref_tokens):
                        method = "eml_message_id_rule"      # 发送端规则: SendId 内嵌 Message-ID
                    else:
                        mid = _norm_msgid(p[5])
                        if mid and mid in refs:
                            method = "eml_in_reply_to"      # 兜底: 系统自生成 Message-ID(需先拉发送 .eml 解析)
                        elif (reply_subj_norm and _norm_subject(p[7]) == reply_subj_norm
                              and (p[6] is None or rtime is None or rtime >= p[6])):
                            # 末路兜底: CRM 经 Exchange 真发, 发送 .eml 无 Message-ID 头(真发时才由 MTA 赋), 本地/CRM 均无从记录,
                            # 故 In-Reply-To 永远匹配不上。改用线程主题精确串接: 发件人=我方收件客户(候选已保证) +
                            # 归一后主题完全相等(剥离 RE:/答复: 等前缀) + 收信不早于实发, 唯一定位到具体那一步。
                            method = "eml_subject_thread"
                    if not method:
                        continue
                    db.execute(text(
                        "INSERT INTO mail_ai_reply_analysis "
                        "(plan_id, crm_send_id, customer_id, staff_id, reply_crm_rowid, reply_sender, "
                        " reply_subject, reply_body, reply_received_at, match_method, created_at) "
                        "VALUES (:pid,:sid,:cid,:stf,:rid,:snd,:sub,:body,:rt,:mm, now()) "
                        "ON CONFLICT (plan_id, reply_crm_rowid) DO NOTHING"
                    ), {
                        "pid": p[0], "sid": p[1], "cid": p[2], "stf": staff_id,
                        "rid": reply_rowid, "snd": sender_email, "sub": (c[2] or "")[:500],
                        "body": body[:20000], "rt": rtime, "mm": method,
                    })
                    existing.add((str(p[0]), reply_rowid))
                    matched += 1
        db.commit()
    finally:
        crm.close()
    return {"candidates": candidates, "matched": matched, "fetched": fetched}


# ---------------------------------------------------------------------------
# 3) 价值分析: 对未判定的回信调 deepseek
# ---------------------------------------------------------------------------
_VALUE_PROMPT = (
    "你是B2B外贸销售助理。下面是客户对我方一封开发/营销邮件的回信。请判断这封回信是否\"有价值\"。\n"
    "有价值 = 客户表达了真实意向/需求/问题/可推进的合作信号(如询价、要资料、约时间、提出具体问题、表示感兴趣)。\n"
    "无价值 = 自动回复/休假回复、退订、明确拒绝且无后续、纯礼貌客套无信息、退信、与业务无关、垃圾邮件。\n"
    "只输出JSON: {\"is_valuable\": true/false, \"reason\": \"一句话中文理由\"}。\n\n"
    "回信主题: {subject}\n回信正文:\n{body}\n"
)


def analyze_values(db: Session, llm_call, limit: int = 60) -> dict:
    """对 is_valuable 为空的回信逐封调 deepseek 判定价值。llm_call(prompt)->{parsed,model,error}。"""
    rows = db.execute(text(
        "SELECT reply_id, reply_subject, reply_body FROM mail_ai_reply_analysis "
        "WHERE is_valuable IS NULL ORDER BY reply_received_at DESC NULLS LAST LIMIT :lim"
    ), {"lim": limit}).fetchall()
    done = 0
    valuable = 0
    for r in rows:
        body = (r[2] or "")[:4000]
        prompt = _VALUE_PROMPT.replace("{subject}", (r[1] or "")[:300]).replace("{body}", body)
        try:
            res = llm_call(prompt)
        except Exception as exc:
            logger.warning("MAIL_AI_VALUE_LLM_FAILED reply=%s err=%s", r[0], exc)
            continue
        parsed = (res or {}).get("parsed") if isinstance(res, dict) else None
        if not isinstance(parsed, dict):
            continue
        is_val = bool(parsed.get("is_valuable"))
        reason = str(parsed.get("reason") or "")[:1000]
        model = str((res or {}).get("model") or "")[:120]
        db.execute(text(
            "UPDATE mail_ai_reply_analysis SET is_valuable=:v, value_reason=:r, value_model=:m, analyzed_at=now() "
            "WHERE reply_id=:id"
        ), {"v": is_val, "r": reason, "m": model, "id": r[0]})
        done += 1
        if is_val:
            valuable += 1
    db.commit()
    return {"analyzed": done, "valuable": valuable}


# ---------------------------------------------------------------------------
# 4) 按天聚合 + 落库
# ---------------------------------------------------------------------------
# 占位/未分配销售账号(如 "？待分配"): 不作为真实销售计入按销售统计, 落回全体。
_PLACEHOLDER_STAFF_KEYWORDS = ("待分配", "未分配", "待定", "公共", "公海")


def _is_placeholder_staff_name(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return True
    return n.startswith("？") or n.startswith("?") or any(k in n for k in _PLACEHOLDER_STAFF_KEYWORDS)


def _bucket_counts(db: Session, start: date, end: date):
    """返回 {(date, staff_id): {metric: n}} 与全销售汇总 staff_id=''。日期均为北京日期。"""
    agg: dict[tuple, dict] = {}

    def add(d, staff, key, n=1):
        if d is None or d < start or d > end:
            return
        for s in dict.fromkeys([(staff or ""), ""]):  # 该销售 + 全体(''); 去重避免 staff 为空时重复累加
            cell = agg.setdefault((d, s), {"generated": 0, "sent": 0, "reply": 0, "valuable": 0, "feedback": 0})
            cell[key] += n

    # 生成数: enqueued, 按 created_at(UTC->BJ)
    for r in db.execute(text(
        "SELECT created_at, inputer_staff_id FROM mail_customer_suite_send_plan WHERE status='enqueued'"
    )).fetchall():
        add(bj_date(r[0]), (r[1] or "").strip(), "generated")
    # 实发数: SendSuccess, 按 FactSendTime(CRM 本地时间, 直接取 date)
    for r in db.execute(text(
        "SELECT crm_fact_send_time, inputer_staff_id FROM mail_customer_suite_send_plan "
        "WHERE status='enqueued' AND crm_send_status='SendSuccess' AND crm_fact_send_time IS NOT NULL"
    )).fetchall():
        d = r[0].date() if r[0] else None
        add(d, (r[1] or "").strip(), "sent")
    # 回信数 / 有价值数: 按 reply_received_at(CRM 本地时间)
    for r in db.execute(text(
        "SELECT reply_received_at, staff_id, is_valuable FROM mail_ai_reply_analysis"
    )).fetchall():
        d = r[0].date() if r[0] else None
        add(d, (r[1] or "").strip(), "reply")
        if r[2]:
            add(d, (r[1] or "").strip(), "valuable")
    # 客户 -> 销售映射: 反馈表无销售字段, 按该客户在 send_plan 里计划数最多的 inputer_staff_id 归属。
    cust_staff: dict[str, str] = {}
    cust_staff_best: dict[str, int] = {}
    for r in db.execute(text(
        "SELECT customer_id, inputer_staff_id, count(*) AS n FROM mail_customer_suite_send_plan "
        "WHERE status='enqueued' AND customer_id IS NOT NULL AND inputer_staff_id IS NOT NULL "
        "AND inputer_staff_id<>'' GROUP BY customer_id, inputer_staff_id"
    )).fetchall():
        cid = (r[0] or "").strip()
        sid = (r[1] or "").strip()
        n = int(r[2] or 0)
        if not cid or not sid:
            continue
        if n > cust_staff_best.get(cid, 0):
            cust_staff_best[cid] = n
            cust_staff[cid] = sid
    # 反馈数: 按"客户对应销售"归属。范围内反馈先取 send_plan 映射; 未命中的(仅预览未转入CRM的客户)
    # 再查 CRM usrCustomerContact.Owner 取客户联系人负责人(逗号分隔取第一个); 仍查不到才仅计全体。
    fb_rows = []
    for r in db.execute(text(
        "SELECT created_at, customer_id FROM mail_customer_suite_feedback"
    )).fetchall():
        d = bj_date(r[0])
        if d is not None and start <= d <= end:
            fb_rows.append((d, (r[1] or "").strip()))
    unmapped = sorted({cid for (_, cid) in fb_rows if cid and cid not in cust_staff})
    if unmapped:
        try:
            from crm_database import CRMSessionLocal
            crm = CRMSessionLocal()
            try:
                # contact -> 第一个负责人工号
                contact_owner: dict[str, str] = {}
                for i in range(0, len(unmapped), 200):
                    chunk = unmapped[i:i + 200]
                    params = {f"c{j}": v for j, v in enumerate(chunk)}
                    ph = ",".join(f":c{j}" for j in range(len(chunk)))
                    for row in crm.execute(text(
                        f"SELECT ContactId, ISNULL(CAST(Owner AS NVARCHAR(200)),'') "
                        f"FROM usrCustomerContact WHERE ContactId IN ({ph})"
                    ), params).fetchall():
                        cid = str(row[0]).strip()
                        owner = str(row[1] or "").replace("，", ",").split(",")[0].strip()
                        if cid and owner:
                            contact_owner[cid] = owner
                # 负责人工号 -> 中文名, 用于过滤"待分配"等占位销售
                owner_ids = sorted(set(contact_owner.values()))
                owner_name: dict[str, str] = {}
                for i in range(0, len(owner_ids), 200):
                    chunk = owner_ids[i:i + 200]
                    params = {f"s{j}": v for j, v in enumerate(chunk)}
                    ph = ",".join(f":s{j}" for j in range(len(chunk)))
                    for row in crm.execute(text(
                        f"SELECT StaffId, ISNULL(CAST(StaffName AS NVARCHAR(120)),'') "
                        f"FROM usrStaff WHERE StaffId IN ({ph})"
                    ), params).fetchall():
                        owner_name[str(row[0]).strip()] = str(row[1] or "").strip()
                for cid, owner in contact_owner.items():
                    if _is_placeholder_staff_name(owner_name.get(owner, "")):
                        continue  # 待分配/未分配等占位销售: 不计入按销售, 落回全体
                    cust_staff[cid] = owner
            finally:
                crm.close()
        except Exception:
            logger.warning("MAIL_FEEDBACK_OWNER_LOOKUP_FAILED", exc_info=True)
    for (d, cid) in fb_rows:
        add(d, cust_staff.get(cid, ""), "feedback")
    return agg


def compute_and_store_daily(db: Session, start: date, end: date) -> None:
    """重算 [start,end] 每天每销售的指标并 upsert。今天 is_final=false, 历史日 is_final=true。"""
    agg = _bucket_counts(db, start, end)
    today_bj = (datetime.utcnow() + BJ_OFFSET).date()
    # 先清掉范围内旧值(避免销售集合变化残留), 再写
    db.execute(text("DELETE FROM mail_ai_daily_stats WHERE stat_date>=:s AND stat_date<=:e"),
               {"s": start, "e": end})
    for (d, staff), c in agg.items():
        db.execute(text(
            "INSERT INTO mail_ai_daily_stats "
            "(stat_date, staff_id, generated_count, sent_count, reply_count, valuable_count, feedback_count, is_final, computed_at) "
            "VALUES (:d,:s,:g,:se,:r,:v,:f,:fin, now()) "
            "ON CONFLICT (stat_date, staff_id) DO UPDATE SET "
            "generated_count=EXCLUDED.generated_count, sent_count=EXCLUDED.sent_count, "
            "reply_count=EXCLUDED.reply_count, valuable_count=EXCLUDED.valuable_count, "
            "feedback_count=EXCLUDED.feedback_count, is_final=EXCLUDED.is_final, computed_at=now()"
        ), {"d": d, "s": staff, "g": c["generated"], "se": c["sent"], "r": c["reply"],
            "v": c["valuable"], "f": c["feedback"], "fin": d < today_bj})
    db.commit()


def refresh_all(db: Session, llm_call, lookback_days: int = 120) -> dict:
    """完整刷新: 同步真发 -> 发现回信 -> 价值分析 -> 重算最近 lookback_days 的日表。"""
    r1 = sync_send_status(db, lookback_days=lookback_days)
    r2 = discover_replies(db, lookback_days=lookback_days)
    r3 = analyze_values(db, llm_call)
    today_bj = (datetime.utcnow() + BJ_OFFSET).date()
    start = today_bj - timedelta(days=lookback_days)
    compute_and_store_daily(db, start, today_bj)
    return {"send_status": r1, "replies": r2, "values": r3}


# ---------------------------------------------------------------------------
# 5) 查询: 汇总表 + 明细
# ---------------------------------------------------------------------------
def query_daily(db: Session, start: date, end: date, staff_id: str | None) -> list[dict]:
    staff = (staff_id or "").strip()
    rows = db.execute(text(
        "SELECT stat_date, generated_count, sent_count, reply_count, valuable_count, feedback_count, is_final "
        "FROM mail_ai_daily_stats WHERE stat_date>=:s AND stat_date<=:e AND staff_id=:st "
        "ORDER BY stat_date DESC"
    ), {"s": start, "e": end, "st": staff}).fetchall()
    return [{
        "stat_date": r[0].isoformat(),
        "generated_count": r[1], "sent_count": r[2], "reply_count": r[3],
        "valuable_count": r[4], "feedback_count": r[5], "is_final": bool(r[6]),
    } for r in rows]


def query_daily_by_staff(db: Session, day: date) -> list[dict]:
    """某一天 各销售(staff_id 非空) 的 5 指标, 按生成数降序。供"按销售单日统计"表格。"""
    rows = db.execute(text(
        "SELECT staff_id, generated_count, sent_count, reply_count, valuable_count, feedback_count, is_final "
        "FROM mail_ai_daily_stats WHERE stat_date=:d AND staff_id<>'' "
        "ORDER BY generated_count DESC, sent_count DESC, staff_id"
    ), {"d": day}).fetchall()
    return [{
        "staff_id": r[0],
        "generated_count": r[1], "sent_count": r[2], "reply_count": r[3],
        "valuable_count": r[4], "feedback_count": r[5], "is_final": bool(r[6]),
    } for r in rows]


def list_staff(db: Session) -> list[str]:
    rows = db.execute(text(
        "SELECT DISTINCT inputer_staff_id FROM mail_customer_suite_send_plan "
        "WHERE status='enqueued' AND inputer_staff_id IS NOT NULL AND inputer_staff_id<>'' "
        "ORDER BY inputer_staff_id"
    )).fetchall()
    return [r[0] for r in rows]


def detail_rows(db: Session, metric: str, day: date, staff_id: str | None) -> list[dict]:
    """某天某指标的明细邮件清单(含联系人/主题/正文; 反馈/价值内容有才显示)。day 为北京日期。"""
    staff = (staff_id or "").strip()
    staff_clause = " AND inputer_staff_id=:st" if staff else ""
    # 本地 UTC 时间窗 = 北京当天[00:00,24:00) - 8h
    bj_start = datetime(day.year, day.month, day.day) - BJ_OFFSET
    bj_end = bj_start + timedelta(days=1)

    if metric == "generated":
        q = ("SELECT customer_id, to_emails, subject, body_html, scenario, suite_step, crm_send_status "
             "FROM mail_customer_suite_send_plan WHERE status='enqueued' "
             "AND created_at>=:a AND created_at<:b" + staff_clause + " ORDER BY created_at DESC")
        rows = db.execute(text(q), {"a": bj_start, "b": bj_end, "st": staff}).fetchall()
        return [{"customer_id": r[0], "contact": r[1], "subject": r[2], "body_html": r[3],
                 "scenario": r[4], "suite_step": r[5], "send_status": r[6]} for r in rows]

    if metric == "sent":
        # 实发按 CRM 本地时间, 直接用北京当天
        cstart = datetime(day.year, day.month, day.day)
        cend = cstart + timedelta(days=1)
        q = ("SELECT customer_id, to_emails, subject, body_html, scenario, suite_step, crm_fact_send_time "
             "FROM mail_customer_suite_send_plan WHERE status='enqueued' AND crm_send_status='SendSuccess' "
             "AND crm_fact_send_time>=:a AND crm_fact_send_time<:b" + staff_clause + " ORDER BY crm_fact_send_time DESC")
        rows = db.execute(text(q), {"a": cstart, "b": cend, "st": staff}).fetchall()
        return [{"customer_id": r[0], "contact": r[1], "subject": r[2], "body_html": r[3],
                 "scenario": r[4], "suite_step": r[5], "fact_send_time": r[6].isoformat() if r[6] else None} for r in rows]

    if metric in ("reply", "valuable"):
        cstart = datetime(day.year, day.month, day.day)
        cend = cstart + timedelta(days=1)
        staff_clause2 = " AND staff_id=:st" if staff else ""
        val_clause = " AND is_valuable=TRUE" if metric == "valuable" else ""
        q = ("SELECT customer_id, reply_sender, reply_subject, reply_body, reply_received_at, "
             "is_valuable, value_reason FROM mail_ai_reply_analysis "
             "WHERE reply_received_at>=:a AND reply_received_at<:b" + staff_clause2 + val_clause +
             " ORDER BY reply_received_at DESC")
        rows = db.execute(text(q), {"a": cstart, "b": cend, "st": staff}).fetchall()
        return [{"customer_id": r[0], "contact": r[1], "subject": r[2], "body_text": r[3],
                 "received_at": r[4].isoformat() if r[4] else None,
                 "is_valuable": r[5], "value_reason": r[6]} for r in rows]

    if metric == "feedback":
        q = ("SELECT customer_id, contact_email, final_subject, final_body_html, feedback_text, scenario, suite_step "
             "FROM mail_customer_suite_feedback WHERE created_at>=:a AND created_at<:b ORDER BY created_at DESC")
        rows = db.execute(text(q), {"a": bj_start, "b": bj_end}).fetchall()
        return [{"customer_id": r[0], "contact": r[1], "subject": r[2], "body_html": r[3],
                 "feedback_text": r[4], "scenario": r[5], "suite_step": r[6]} for r in rows]

    return []
