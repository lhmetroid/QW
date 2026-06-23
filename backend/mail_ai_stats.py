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
def sync_send_status(db: Session, lookback_days: int = 120) -> dict:
    """对最近 lookback_days 转入的 enqueued 计划, 用 SendId 关联 spSendInfo{销售} 回填真发状态;
    真发成功且尚无 message_id 的, 拉发送 .eml 解析 Message-ID(供回信匹配)。"""
    from crm_database import CRMSessionLocal
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    plans = db.execute(text(
        "SELECT plan_id, crm_send_id, inputer_staff_id, crm_message_id, crm_send_status "
        "FROM mail_customer_suite_send_plan "
        "WHERE status='enqueued' AND crm_send_id IS NOT NULL AND created_at>=:cut"
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
            send_ids = [r[1] for r in rows]
            # 分批 IN 查询
            info = {}
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
                rec = info.get(str(r[1]))
                plan_id = r[0]
                if rec is None:
                    # SendId 不在 spSendInfo: 仍在队列待发 或 已被删除。保持/标记 unknown。
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
                    "SET crm_send_status=:st, crm_fact_send_time=:ft, crm_eml_ftp_dir=:ed, status_synced_at=now() "
                    "WHERE plan_id=:pid"
                ), {"st": final_status, "ft": fact, "ed": eml_dir, "pid": plan_id})
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
    若包含我们的发送 Message-ID 即判定为回信, 写入 mail_ai_reply_analysis。"""
    from crm_database import CRMSessionLocal
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    plans = db.execute(text(
        "SELECT plan_id, crm_send_id, customer_id, inputer_staff_id, to_emails, "
        "       crm_message_id, crm_fact_send_time "
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
            # 该销售下: 客户邮箱 -> [plan...]; message_id -> plan
            email_to_plans: dict[str, list] = {}
            min_time = None
            for p in rows:
                for e in _all_emails(p[4]):
                    if any(d in e for d in _OUR_DOMAINS):
                        continue
                    email_to_plans.setdefault(e, []).append(p)
                ft = p[6]
                if ft and (min_time is None or ft < min_time):
                    min_time = ft
            if not email_to_plans or min_time is None:
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
                for p in pend_plans:
                    method = None
                    if ref_tokens and any(ai_token_matches_send_id(t, p[1]) for t in ref_tokens):
                        method = "eml_message_id_rule"      # 发送端规则: SendId 内嵌 Message-ID
                    else:
                        mid = _norm_msgid(p[5])
                        if mid and mid in refs:
                            method = "eml_in_reply_to"      # 兜底: 系统自生成 Message-ID(需先拉发送 .eml 解析)
                    if not method:
                        continue
                    db.execute(text(
                        "INSERT INTO mail_ai_reply_analysis "
                        "(plan_id, crm_send_id, customer_id, staff_id, reply_crm_rowid, reply_sender, "
                        " reply_subject, reply_body, reply_received_at, match_method) "
                        "VALUES (:pid,:sid,:cid,:stf,:rid,:snd,:sub,:body,:rt,:mm) "
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
def _bucket_counts(db: Session, start: date, end: date):
    """返回 {(date, staff_id): {metric: n}} 与全销售汇总 staff_id=''。日期均为北京日期。"""
    agg: dict[tuple, dict] = {}

    def add(d, staff, key, n=1):
        if d is None or d < start or d > end:
            return
        for s in (staff or "", ""):  # 同时累加到该销售和全体('')
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
    # 反馈数: mail_customer_suite_feedback, 按 created_at(UTC->BJ)。销售维度无直接字段, 仅计入全体。
    for r in db.execute(text(
        "SELECT created_at FROM mail_customer_suite_feedback"
    )).fetchall():
        d = bj_date(r[0])
        if d is not None and start <= d <= end:
            cell = agg.setdefault((d, ""), {"generated": 0, "sent": 0, "reply": 0, "valuable": 0, "feedback": 0})
            cell["feedback"] += 1
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
