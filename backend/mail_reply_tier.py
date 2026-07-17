# -*- coding: utf-8 -*-
"""邮件回信价值分层 + 无效地址鉴定 + 联动取消/替换后续发送计划。

对应需求(邮件走查清单 第5块):
- 5.1 无效地址鉴定: 从退信(bounce)识别失效收件地址, 落库 mail_invalid_recipient。
- 5.2 联动取消/替换: 某地址失效后, 该联系人后续未发的自动排期,
      有其他有效地址则替换, 无则取消; 输出三层结果(死掉/替换/备用)。
- 5.3 回信按 4 类价值分层: 在原有二分类 is_valuable 上新增 value_tier。

本模块只依赖 sqlalchemy 与本地表; 取"联系人其他有效地址"通过 valid_email_resolver 回调注入,
避免本模块直接依赖 CRM/main。所有分类为确定性规则, 供 LLM 判定兜底/覆盖。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session


# value_tier 取值(从强到弱) + 无效
TIER_INQUIRY = "inquiry"    # 主动询问/询价(最强意向)
TIER_REFERRAL = "referral"  # 让你联系别人/转介绍
TIER_FUTURE = "future"      # 以后有机会会找你(潜在)
TIER_RECEIVED = "received"  # 仅收到/确认收到/礼貌客套
TIER_NONE = "none"          # 无价值/拒绝/无关/自动回复
TIER_INVALID = "invalid"    # 退信/无效地址(不是真正回信)

TIER_ORDER = [TIER_INQUIRY, TIER_REFERRAL, TIER_FUTURE, TIER_RECEIVED, TIER_NONE, TIER_INVALID]

TIER_LABELS = {
    TIER_INQUIRY: "主动询价",
    TIER_REFERRAL: "转介绍/找他人",
    TIER_FUTURE: "以后再联系",
    TIER_RECEIVED: "仅确认收到",
    TIER_NONE: "无价值",
    TIER_INVALID: "退信/无效",
}

# 计入"有价值"(与旧 is_valuable 口径一致): 询价/转介绍/以后再联系。
VALUABLE_TIERS = {TIER_INQUIRY, TIER_REFERRAL, TIER_FUTURE}


# ---- 确定性识别正则 ----
# 退信/无效地址: 发件人是投递系统, 或正文含明确投递失败措辞。
_BOUNCE_SENDER_RE = re.compile(
    r"(mailer-daemon|postmaster|mail\s*delivery\s*(sub)?system|no-?reply.*(deliver|bounce))",
    re.I,
)
_BOUNCE_BODY_RE = re.compile(
    r"(undeliverable|delivery\s+(has\s+)?failed|delivery\s+status\s+notification|"
    r"550[\s\-]|551[\s\-]|553[\s\-]|554[\s\-]|user\s+unknown|no\s+such\s+user|"
    r"mailbox\s+(is\s+)?(unavailable|not\s+found|full)|recipient\s+(address\s+)?rejected|"
    r"address\s+not\s+found|does\s+not\s+exist|退信|无法投递|投递失败|拒收|用户不存在|"
    r"该(邮箱|用户|地址)不存在|邮箱(地址)?(错误|无效|已满|不存在))",
    re.I,
)
# 从退信正文提取真正失效的收件地址(常见 "Final-Recipient: rfc822; x@y" / "<x@y>: ... failed")
_FAILED_ADDR_RES = [
    re.compile(r"final-recipient:\s*(?:rfc822;)?\s*<?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})>?", re.I),
    re.compile(r"original-recipient:\s*(?:rfc822;)?\s*<?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})>?", re.I),
    re.compile(r"<([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})>[^\n]{0,40}(?:fail|reject|unknown|not\s+exist)", re.I),
]
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# 4 类价值信号
_INQUIRY_RE = re.compile(
    r"(询价|报价|多少钱|价格|报个价|方案|发(一?份|个)?(资料|报价|方案|介绍|样本|清单)|"
    r"需要.{0,8}(报价|资料|方案|样本|介绍)|想(了解|咨询|要|做)|麻烦.{0,6}(发|报|给)|"
    r"能否.{0,10}(报价|提供|发)|什么时候(能|可以)|交期|周期多久|quote|price|pricing|"
    r"send.{0,10}(quote|catalog|proposal|sample)|how\s+much|interested\s+in\s+(a|your))",
    re.I,
)
_FUTURE_RE = re.compile(
    r"(以后.{0,6}(有|再|联系|需要)|后续.{0,6}(有|再|需要|联系)|有(需要|机会|需求).{0,6}(再|会|联系|找)|"
    r"暂时?不需要|目前(没有|不)需要.{0,10}(以后|后续|有需要)|保持联系|keep\s+in\s+touch|"
    r"再联系|将来|下次(有)?需要|有合适.{0,6}(再|会))",
    re.I,
)
_RECEIVED_RE = re.compile(
    r"(收到|已收到|谢谢|感谢|多谢|好的|了解了?|知道了|noted|received|thanks|thank\s+you|ok\b|okay)",
    re.I,
)
_AUTO_REPLY_RE = re.compile(
    r"(自动回复|自动答复|auto[-\s]?reply|out\s+of\s+office|离职|休假|年假|请假|"
    r"不在(办公室|岗)|正在休假|放假|vacation|annual\s+leave)",
    re.I,
)
_REJECT_RE = re.compile(
    r"(退订|取消订阅|unsubscribe|do\s+not\s+contact|不要再(发|联系)|别再(发|联系)|"
    r"停止发送|垃圾邮件|不感兴趣|没有(兴趣|需求|需要)且|请勿(再)?(发送|打扰))",
    re.I,
)
# 转介绍信号(与 mail_ai_stats 保持一致口径)
_REFERRAL_RE = re.compile(
    r"(找|联系|对接|转给|转发给|推荐给|介绍给|问一下).{0,18}"
    r"(业务相关|相关业务|相关负责人|负责人|相关同事|业务同事|对应同事|采购|市场|项目|销售|商务|部门|团队|人士|人员)",
    re.I,
)
_FIND_OTHER_RE = re.compile(
    r"(最好找|你?去找|建议你?找|改?找|另?找|联系).{0,12}(的人|别人|其他人|他们的人|对方)",
    re.I,
)


def is_bounce(subject: str | None, body: str | None, sender: str | None) -> bool:
    """是否退信/无法投递。"""
    snd = (sender or "")
    txt = f"{subject or ''}\n{body or ''}"
    if _BOUNCE_SENDER_RE.search(snd):
        return True
    if _BOUNCE_BODY_RE.search(txt):
        return True
    return False


def extract_failed_address(body: str | None, exclude_domains: tuple[str, ...] = ("speed-asia.com",)) -> str:
    """从退信正文提取失效收件地址。找不到结构化字段时, 取正文里第一个非我方域邮箱。"""
    b = body or ""
    for rex in _FAILED_ADDR_RES:
        m = rex.search(b)
        if m:
            addr = m.group(1).lower()
            if not any(addr.endswith("@" + d) or addr.endswith("." + d) for d in exclude_domains):
                return addr
    for addr in (e.lower() for e in _EMAIL_RE.findall(b)):
        if not any(addr.endswith("@" + d) or addr.endswith("." + d) for d in exclude_domains):
            return addr
    return ""


def classify_reply_tier(subject: str | None, body: str | None, sender: str | None) -> str | None:
    """确定性回信分层。返回 tier 或 None(不确定, 交给 LLM 判定)。

    优先级: 退信 > 询价 > 转介绍 > 以后再联系 > (拒绝/自动回复=无价值) > 仅收到。
    """
    if is_bounce(subject, body, sender):
        return TIER_INVALID
    txt = f"{subject or ''}\n{body or ''}".strip()
    if not txt:
        return None
    if _INQUIRY_RE.search(txt):
        return TIER_INQUIRY
    if _REFERRAL_RE.search(txt) or _FIND_OTHER_RE.search(txt):
        return TIER_REFERRAL
    if _REJECT_RE.search(txt) or _AUTO_REPLY_RE.search(txt):
        return TIER_NONE
    if _FUTURE_RE.search(txt):
        return TIER_FUTURE
    if _RECEIVED_RE.search(txt):
        return TIER_RECEIVED
    return None


def tier_from_llm_valuable(is_valuable: bool, reason: str | None) -> str:
    """LLM 只给了 is_valuable 时, 结合理由粗分到 tier(尽量不降级 valuable 口径)。"""
    r = reason or ""
    if is_valuable:
        if _REFERRAL_RE.search(r) or _FIND_OTHER_RE.search(r) or "转介绍" in r or "对接" in r:
            return TIER_REFERRAL
        if _FUTURE_RE.search(r) or "以后" in r or "后续" in r:
            return TIER_FUTURE
        return TIER_INQUIRY
    return TIER_NONE


def tier_is_valuable(tier: str | None) -> bool:
    return (tier or "") in VALUABLE_TIERS


# ---------------------------------------------------------------------------
# 建表 / 迁移
# ---------------------------------------------------------------------------
def ensure_tables(db: Session) -> None:
    # 5.3: 回信分层列
    db.execute(text("ALTER TABLE mail_ai_reply_analysis ADD COLUMN IF NOT EXISTS value_tier VARCHAR(20);"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_mar_tier ON mail_ai_reply_analysis (value_tier);"))
    # 5.1: 无效收件地址登记表
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS mail_invalid_recipient ("
        "email VARCHAR(255) PRIMARY KEY,"
        "customer_id VARCHAR(120) NOT NULL DEFAULT '',"
        "contact_id VARCHAR(120) NOT NULL DEFAULT '',"
        "reason VARCHAR(200) NOT NULL DEFAULT '',"
        "source_reply_id UUID,"
        "replacement_email VARCHAR(255) NOT NULL DEFAULT '',"
        "cancelled_plan_count INTEGER NOT NULL DEFAULT 0,"
        "replaced_plan_count INTEGER NOT NULL DEFAULT 0,"
        "standby_email_count INTEGER NOT NULL DEFAULT 0,"
        "detected_at TIMESTAMP DEFAULT now()"
        ")"
    ))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_minv_customer ON mail_invalid_recipient (customer_id);"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_minv_detected ON mail_invalid_recipient (detected_at);"))
    # 5.2: 自动排期项联动列(取消/替换标记)
    db.execute(text("ALTER TABLE mail_autosend_plan_item ADD COLUMN IF NOT EXISTS invalid_recipient BOOLEAN NOT NULL DEFAULT FALSE;"))
    db.execute(text("ALTER TABLE mail_autosend_plan_item ADD COLUMN IF NOT EXISTS replaced_from_email VARCHAR(255) NOT NULL DEFAULT '';"))
    db.execute(text("ALTER TABLE mail_autosend_plan_item ADD COLUMN IF NOT EXISTS recipient_replaced_at TIMESTAMP;"))
    db.execute(text("ALTER TABLE mail_autosend_plan_item ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(200) NOT NULL DEFAULT '';"))
    db.commit()


# 视作"后续未发, 可取消/可替换"的排期状态。已发(sent)/已入CRM 不动。
# 状态名与 main.py 实际写入口径一致: 生成失败=failed, 同步CRM失败=commit_failed(均属未发, 可联动)。
PENDING_PLAN_STATUSES = ("planned", "drafting", "drafted", "queued", "commit_queued", "failed", "commit_failed")
CANCELLED_INVALID_STATUS = "cancelled_invalid"


def reconcile_tier(tier: str | None, is_valuable: bool) -> str:
    """让 value_tier 与 is_valuable 在"有价值边界"上一致, 避免两套口径给出不同的有价值数。

    - 退信(invalid)保持不变(它天然 is_valuable=False)。
    - is_valuable=False 但 tier 落在有价值层(关键词误命中, 如"不需要报价") -> 归为无价值 none。
    - is_valuable=True 但 tier 落在 received/none -> 用有价值层(referral/future/inquiry)。
    """
    t = tier or TIER_NONE
    if t == TIER_INVALID:
        return t
    if is_valuable and t not in VALUABLE_TIERS:
        return tier_from_llm_valuable(True, "")
    if (not is_valuable) and t in VALUABLE_TIERS:
        return TIER_NONE
    return t


def apply_invalid_recipient(
    db: Session,
    *,
    email: str,
    customer_id: str = "",
    contact_id: str = "",
    reason: str = "bounce",
    source_reply_id: str | None = None,
    valid_email_resolver: Callable[[str, str], list[str]] | None = None,
    link_plans: bool = True,
) -> dict:
    """登记无效地址并联动后续排期(取消/替换)。返回三层结果。

    valid_email_resolver(customer_id, contact_id) -> list[str]: 该联系人当前所有有效地址(降序优先)。
    link_plans=False(联动开关未打开): **只登记无效地址, 不取消/不替换任何排期**, 仍返回可替换/备用地址供人工参考。
    """
    ensure_tables(db)
    inv = (email or "").strip().lower()
    if not inv:
        raise ValueError("email is required")

    # 后续未发、收件人=失效地址的排期项(优先按 contact_id 收敛, 否则按 recipient_email)
    plan_clause = "LOWER(recipient_email)=:inv AND status = ANY(:pend)"
    params: dict[str, Any] = {"inv": inv, "pend": list(PENDING_PLAN_STATUSES)}
    if (contact_id or "").strip():
        plan_clause = "contact_id=:contact AND " + plan_clause
        params["contact"] = contact_id.strip()
    pending = db.execute(text(
        f"SELECT item_id, contact_id, customer_id, recipient_email FROM mail_autosend_plan_item "
        f"WHERE {plan_clause}"
    ), params).fetchall() if link_plans else []

    # 候选替换地址: 该联系人其他有效地址(去掉失效地址本身与已知无效地址)
    known_invalid = {inv}
    for r in db.execute(text("SELECT email FROM mail_invalid_recipient")).fetchall():
        known_invalid.add(str(r[0]).lower())
    candidates: list[str] = []
    if valid_email_resolver is not None:
        try:
            for e in (valid_email_resolver(customer_id, contact_id) or []):
                el = (e or "").strip().lower()
                if el and el not in known_invalid and el not in candidates:
                    candidates.append(el)
        except Exception:
            candidates = []
    replacement = candidates[0] if candidates else ""
    standby = candidates[1:] if len(candidates) > 1 else []

    cancelled = 0
    replaced = 0
    now_ts = db.execute(text("SELECT now()")).scalar()
    for row in pending:
        item_id = row[0]
        if replacement:
            db.execute(text(
                "UPDATE mail_autosend_plan_item SET recipient_email=:rep, replaced_from_email=:old, "
                "invalid_recipient=TRUE, recipient_replaced_at=:ts, updated_at=:ts WHERE item_id=:id"
            ), {"rep": replacement, "old": inv, "ts": now_ts, "id": item_id})
            replaced += 1
        else:
            db.execute(text(
                "UPDATE mail_autosend_plan_item SET status=:st, invalid_recipient=TRUE, "
                "cancel_reason=:reason, updated_at=:ts WHERE item_id=:id"
            ), {"st": CANCELLED_INVALID_STATUS, "reason": (reason or "invalid_recipient")[:200], "ts": now_ts, "id": item_id})
            cancelled += 1

    db.execute(text(
        "INSERT INTO mail_invalid_recipient "
        "(email, customer_id, contact_id, reason, source_reply_id, replacement_email, "
        " cancelled_plan_count, replaced_plan_count, standby_email_count, detected_at) "
        "VALUES (:e,:cid,:contact,:reason,:src,:rep,:canc,:repl,:standby, now()) "
        "ON CONFLICT (email) DO UPDATE SET "
        "customer_id=EXCLUDED.customer_id, contact_id=EXCLUDED.contact_id, reason=EXCLUDED.reason, "
        "source_reply_id=EXCLUDED.source_reply_id, replacement_email=EXCLUDED.replacement_email, "
        "cancelled_plan_count=mail_invalid_recipient.cancelled_plan_count+EXCLUDED.cancelled_plan_count, "
        "replaced_plan_count=mail_invalid_recipient.replaced_plan_count+EXCLUDED.replaced_plan_count, "
        "standby_email_count=EXCLUDED.standby_email_count"
    ), {
        "e": inv, "cid": customer_id or "", "contact": contact_id or "", "reason": (reason or "")[:200],
        "src": source_reply_id, "rep": replacement, "canc": cancelled, "repl": replaced,
        "standby": len(standby),
    })
    db.commit()
    return {
        # 三层结果
        "invalid_email": inv,
        "died_marked": True,                 # 层1: 失效地址已标记
        "replacement_email": replacement,    # 层2: 替换上去的有效地址(空=无可替换)
        "replaced_plan_count": replaced,     # 层2: 被替换的后续封数
        "cancelled_plan_count": cancelled,   # 无替换时: 取消的后续封数
        "standby_emails": standby,           # 层3: 备用有效地址
        "standby_email_count": len(standby),
        "pending_affected": len(pending),
        "link_plans": bool(link_plans),      # False = 联动开关未开, 只登记未动排期
    }


def tier_summary(db: Session, start: date, end: date, staff_id: str | None = None) -> dict:
    """回信 4 类价值分层统计 + 无效地址联动统计(按北京日, reply_received_at)。"""
    ensure_tables(db)
    staff = (staff_id or "").strip()
    where = ["(reply_received_at + interval '8 hour')::date >= :s",
             "(reply_received_at + interval '8 hour')::date <= :e"]
    params: dict[str, Any] = {"s": start, "e": end}
    if staff:
        where.append("staff_id=:staff")
        params["staff"] = staff
    wsql = " AND ".join(where)
    rows = db.execute(text(
        f"SELECT COALESCE(value_tier,'unclassified') AS tier, COUNT(*) AS n "
        f"FROM mail_ai_reply_analysis WHERE {wsql} GROUP BY COALESCE(value_tier,'unclassified')"
    ), params).fetchall()
    tier_counts = {t: 0 for t in TIER_ORDER}
    tier_counts["unclassified"] = 0
    for r in rows:
        tier_counts[str(r[0])] = int(r[1])
    reply_total = sum(int(r[1]) for r in rows)
    valuable_total = sum(tier_counts.get(t, 0) for t in VALUABLE_TIERS)

    # 与回信统计同口径: 按北京日归属(detected_at 存 UTC)
    inv_where = ["(detected_at + interval '8 hour')::date >= :s", "(detected_at + interval '8 hour')::date <= :e"]
    inv_params: dict[str, Any] = {"s": start, "e": end}
    if staff:
        # 无效地址表无 staff 维度, 按 customer 归属销售较重, 这里仅在全量口径统计。
        pass
    inv = db.execute(text(
        f"SELECT COUNT(*) AS died, "
        f"COALESCE(SUM(CASE WHEN replacement_email<>'' THEN 1 ELSE 0 END),0) AS with_repl, "
        f"COALESCE(SUM(cancelled_plan_count),0) AS canc, "
        f"COALESCE(SUM(replaced_plan_count),0) AS repl, "
        f"COALESCE(SUM(standby_email_count),0) AS standby "
        f"FROM mail_invalid_recipient WHERE {' AND '.join(inv_where)}"
    ), inv_params).fetchone()

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "staff_id": staff,
        "tier_labels": TIER_LABELS,
        "tier_order": TIER_ORDER,
        "tier_counts": tier_counts,
        "reply_total": reply_total,
        "valuable_total": valuable_total,
        # 无效地址三层结果汇总
        "invalid": {
            "died_addresses": int(inv[0] or 0),           # 层1: 鉴定出的失效地址数
            "addresses_with_replacement": int(inv[1] or 0),
            "replaced_plans": int(inv[3] or 0),           # 层2: 被替换的后续封数
            "cancelled_plans": int(inv[2] or 0),          # 无替换时取消的后续封数
            "standby_addresses": int(inv[4] or 0),        # 层3: 备用有效地址数
        },
    }


def backfill_tiers(db: Session, limit: int = 2000) -> dict:
    """对已判定 is_valuable 但缺 value_tier 的历史回信, 用确定性规则回填分层。"""
    ensure_tables(db)
    rows = db.execute(text(
        "SELECT reply_id, reply_subject, reply_body, reply_sender, is_valuable, value_reason "
        "FROM mail_ai_reply_analysis WHERE value_tier IS NULL "
        "ORDER BY reply_received_at DESC NULLS LAST LIMIT :lim"
    ), {"lim": limit}).fetchall()
    updated = 0
    for r in rows:
        tier = classify_reply_tier(r[1], r[2], r[3])
        if tier is None:
            tier = tier_from_llm_valuable(bool(r[4]), r[5])
        # 与已判 is_valuable 对齐, 避免分层与有价值口径矛盾
        tier = reconcile_tier(tier, bool(r[4]))
        db.execute(text(
            "UPDATE mail_ai_reply_analysis SET value_tier=:t WHERE reply_id=:id"
        ), {"t": tier, "id": r[0]})
        updated += 1
    db.commit()
    return {"updated": updated}
