# -*- coding: utf-8 -*-
"""Daily LLM mail iteration analysis.

Stores daily aggregates for human edits against emails that were already
enqueued/committed to CRM. Detail rows only keep lightweight indexes; full
original/final bodies are loaded lazily from mail_llm_edit_record.
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


TYPE_COLUMNS = {
    "正文任意改动": "body_changed_count",
    "主题改动": "subject_changed_count",
    "签名/联系方式调整": "signature_count",
    "称呼/开头语言调整": "greeting_count",
    "业务线/服务描述调整": "service_count",
    "结尾动作/语气调整": "cta_count",
    "占位/测试痕迹处理": "placeholder_count",
    "其他正文措辞调整": "other_body_count",
}

PRIMARY_ORDER = [
    "占位/测试痕迹处理",
    "签名/联系方式调整",
    "称呼/开头语言调整",
    "业务线/服务描述调整",
    "结尾动作/语气调整",
    "主题改动",
    "其他正文措辞调整",
]

TERM_GROUPS = {
    "签名/联系方式调整": [
        "market2", "speed-asia.com", "总经理助理", "事必达团队", "angela",
        "phone", "email", "tel", "电话", "邮箱", "@", "www.",
    ],
    "称呼/开头语言调整": ["hi ", "dear ", "hello", "您好", "你好", "尊敬的", "老师", "经理"],
    "业务线/服务描述调整": [
        "视频", "笔译", "口译", "印刷", "排版", "制版", "制作", "翻译",
        "字幕", "录音", "本地化", "宣传", "画册", "样本", "资料",
    ],
    "结尾动作/语气调整": [
        "方便", "参考供应商", "随时联系", "随时联系我们", "有需要", "供您参考",
        "会议", "电话沟通", "期待", "回复", "打扰",
    ],
    "占位/测试痕迹处理": ["case_company_", "[你的名字]", "{{", "}}", "xxx", " xx ", "m2", "xxxx"],
}

SCENARIO_LABELS = {
    "re_activation": "老客户激活",
    "new_business_promotion": "新业务推广",
    "new_contact_intro": "新接手联系人介绍",
}

SUGGESTION_TARGETS = {
    "签名/联系方式调整": "通用签名/发件人配置",
    "称呼/开头语言调整": "套装脚本开头",
    "业务线/服务描述调整": "套装脚本业务线段落",
    "结尾动作/语气调整": "套装脚本结尾动作",
    "占位/测试痕迹处理": "通用出口质检",
    "主题改动": "套装脚本主题",
    "其他正文措辞调整": "套装脚本正文表达",
}

SUGGESTION_TEXTS = {
    "签名/联系方式调整": "代码改：生成正文时禁止 LLM 输出签名/电话/邮箱；保存前统一调用销售签名/公共邮箱签名配置追加。脚本补充要求：正文结尾不要写任何署名、职位、电话、邮箱、网址。",
    "称呼/开头语言调整": "脚本改：首句固定为“{联系人称呼}，您好。”；无联系人姓名时用“您好”，英文联系人用“Hi {FirstName},”，禁止臆造老师/经理/先生/女士。",
    "业务线/服务描述调整": "脚本改：业务描述段只允许使用本次勾选的套装范围变量 `{selected_suite_services}`，每封最多写 2 个服务点；删除“笔译、口译、印刷、视频、本地化”等全量罗列句。",
    "结尾动作/语气调整": "脚本改：结尾统一使用场景 CTA 模板。老客户激活写“如果近期有相关资料需要处理，我可以先帮您看下适合的安排。”；新业务推广写“如果您愿意，我可以发一份对应服务介绍给您参考。”；新联系人介绍写“后续相关资料也可以直接发我，我来协助衔接。”",
    "占位/测试痕迹处理": "代码改：保存草稿和同步 CRM 前新增硬拦截，正则命中 case_company、{{...}}、[你的名字]、xxx、m2 等测试占位时禁止同步并回炉重写。",
    "主题改动": "脚本改：主题单独生成，禁止从正文首句截取。模板改为“关于{客户业务场景}资料处理的一点参考”或“{服务点}支持的一点参考”，长度控制 18 个中文以内。",
    "其他正文措辞调整": "脚本改：新增要求“少用泛泛营销判断，多写可执行协助动作；每段不超过 2 句；不写无法从 CRM/历史合作证明的结论”。把高频人工替换词沉淀进示例词表。",
}


def ensure_tables(db: Session) -> None:
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS mail_llm_iteration_daily_summary ("
        "stat_date DATE PRIMARY KEY,"
        "crm_total INTEGER NOT NULL DEFAULT 0,"
        "edited_total INTEGER NOT NULL DEFAULT 0,"
        "autosend_total INTEGER NOT NULL DEFAULT 0,"
        "autosend_edited INTEGER NOT NULL DEFAULT 0,"
        "mail_suite_total INTEGER NOT NULL DEFAULT 0,"
        "mail_suite_edited INTEGER NOT NULL DEFAULT 0,"
        "body_changed_count INTEGER NOT NULL DEFAULT 0,"
        "subject_changed_count INTEGER NOT NULL DEFAULT 0,"
        "signature_count INTEGER NOT NULL DEFAULT 0,"
        "greeting_count INTEGER NOT NULL DEFAULT 0,"
        "service_count INTEGER NOT NULL DEFAULT 0,"
        "cta_count INTEGER NOT NULL DEFAULT 0,"
        "placeholder_count INTEGER NOT NULL DEFAULT 0,"
        "other_body_count INTEGER NOT NULL DEFAULT 0,"
        "ai_suggestion_count INTEGER NOT NULL DEFAULT 0,"
        "computed_at TIMESTAMP DEFAULT now()"
        ")"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS mail_llm_iteration_staff_daily_summary ("
        "stat_date DATE NOT NULL,"
        "staff_id VARCHAR(120) NOT NULL,"
        "crm_total INTEGER NOT NULL DEFAULT 0,"
        "edited_total INTEGER NOT NULL DEFAULT 0,"
        "autosend_total INTEGER NOT NULL DEFAULT 0,"
        "autosend_edited INTEGER NOT NULL DEFAULT 0,"
        "mail_suite_total INTEGER NOT NULL DEFAULT 0,"
        "mail_suite_edited INTEGER NOT NULL DEFAULT 0,"
        "body_changed_count INTEGER NOT NULL DEFAULT 0,"
        "subject_changed_count INTEGER NOT NULL DEFAULT 0,"
        "signature_count INTEGER NOT NULL DEFAULT 0,"
        "greeting_count INTEGER NOT NULL DEFAULT 0,"
        "service_count INTEGER NOT NULL DEFAULT 0,"
        "cta_count INTEGER NOT NULL DEFAULT 0,"
        "placeholder_count INTEGER NOT NULL DEFAULT 0,"
        "other_body_count INTEGER NOT NULL DEFAULT 0,"
        "ai_suggestion_count INTEGER NOT NULL DEFAULT 0,"
        "computed_at TIMESTAMP DEFAULT now(),"
        "CONSTRAINT uq_mlias_date_staff UNIQUE(stat_date, staff_id)"
        ")"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS mail_llm_iteration_detail_index ("
        "detail_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "stat_date DATE NOT NULL,"
        "staff_id VARCHAR(120) NOT NULL DEFAULT '',"
        "source VARCHAR(40) NOT NULL,"
        "source_row_id VARCHAR(80) NOT NULL,"
        "instance_id VARCHAR(120),"
        "edit_record_id UUID,"
        "customer_id VARCHAR(120),"
        "contact_id VARCHAR(120),"
        "scenario VARCHAR(80),"
        "suite_step INTEGER,"
        "crm_time TIMESTAMP,"
        "subject VARCHAR(500),"
        "edited BOOLEAN NOT NULL DEFAULT FALSE,"
        "subject_changed BOOLEAN NOT NULL DEFAULT FALSE,"
        "body_changed BOOLEAN NOT NULL DEFAULT FALSE,"
        "primary_type VARCHAR(80),"
        "type_flags JSONB NOT NULL DEFAULT '[]'::jsonb,"
        "ai_suggestion_count INTEGER NOT NULL DEFAULT 0,"
        "ai_suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,"
        "created_at TIMESTAMP DEFAULT now(),"
        "CONSTRAINT uq_mlid_source_row UNIQUE(source, source_row_id)"
        ")"
    ))
    db.execute(text("ALTER TABLE mail_llm_iteration_daily_summary ADD COLUMN IF NOT EXISTS ai_suggestion_count INTEGER NOT NULL DEFAULT 0;"))
    db.execute(text("ALTER TABLE mail_llm_iteration_staff_daily_summary ADD COLUMN IF NOT EXISTS ai_suggestion_count INTEGER NOT NULL DEFAULT 0;"))
    db.execute(text("ALTER TABLE mail_llm_iteration_detail_index ADD COLUMN IF NOT EXISTS ai_suggestion_count INTEGER NOT NULL DEFAULT 0;"))
    db.execute(text("ALTER TABLE mail_llm_iteration_detail_index ADD COLUMN IF NOT EXISTS ai_suggestions JSONB NOT NULL DEFAULT '[]'::jsonb;"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_mlid_date_staff ON mail_llm_iteration_detail_index (stat_date, staff_id);"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_mlid_type ON mail_llm_iteration_detail_index (primary_type);"))
    # AI建议"落地渠道/生效时间/人工验证"状态: 按建议组(scope|target|suggestion_type)记录, 与逐封明细解耦。
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS mail_llm_iteration_suggestion_status ("
        "group_key VARCHAR(400) PRIMARY KEY,"
        "scope VARCHAR(80) NOT NULL DEFAULT '',"
        "target VARCHAR(200) NOT NULL DEFAULT '',"
        "suggestion_type VARCHAR(120) NOT NULL DEFAULT '',"
        "landed_channel VARCHAR(20) NOT NULL DEFAULT '',"  # 'script'=脚本 / 'code'=代码 / ''=未落地
        "landed_note TEXT NOT NULL DEFAULT '',"             # 具体落在哪(脚本开头/某函数)
        "landed_at TIMESTAMP,"                              # 落地生效时间点
        "verified BOOLEAN NOT NULL DEFAULT FALSE,"          # 人工已验证
        "verified_by VARCHAR(120) NOT NULL DEFAULT '',"
        "verified_at TIMESTAMP,"                            # 人工验证时间点
        "updated_at TIMESTAMP DEFAULT now()"
        ")"
    ))
    db.commit()


# 展示用类型列: 去掉笼统的"正文任意改动"(body_changed_count), 只保留具体改动点。
DISPLAY_TYPE_COLUMNS = {k: v for k, v in TYPE_COLUMNS.items() if k != "正文任意改动"}

LANDED_CHANNEL_LABELS = {
    "script": "脚本",
    "code": "代码",
    "": "未落地",
}


def _group_status_key_str(scope: Any, target: Any, suggestion_type: Any) -> str:
    return f"{scope or ''}||{target or ''}||{suggestion_type or ''}"


def _load_suggestion_statuses(db: Session) -> dict[str, dict]:
    rows = db.execute(text("SELECT * FROM mail_llm_iteration_suggestion_status")).fetchall()
    return {str(r._mapping.get("group_key")): dict(r._mapping) for r in rows}


def set_suggestion_status(
    db: Session,
    *,
    group_key: str,
    scope: str = "",
    target: str = "",
    suggestion_type: str = "",
    landed_channel: str | None = None,
    landed_note: str | None = None,
    verified: bool | None = None,
    verified_by: str = "",
) -> dict:
    """Upsert 建议组落地/验证状态。landed_channel/verified 为 None 表示本次不改动该维度。"""
    ensure_tables(db)
    gk = (group_key or "").strip()
    if not gk:
        raise ValueError("group_key is required")
    existing = db.execute(text(
        "SELECT * FROM mail_llm_iteration_suggestion_status WHERE group_key=:k"
    ), {"k": gk}).fetchone()
    cur = dict(existing._mapping) if existing else {}
    new_channel = cur.get("landed_channel", "") or ""
    new_note = cur.get("landed_note", "") or ""
    new_landed_at = cur.get("landed_at")
    new_verified = bool(cur.get("verified", False))
    new_verified_at = cur.get("verified_at")
    new_verified_by = cur.get("verified_by", "") or ""

    if landed_channel is not None:
        channel = (landed_channel or "").strip()
        if channel and channel not in ("script", "code"):
            raise ValueError("landed_channel must be 'script' | 'code' | ''")
        new_channel = channel
        if channel:
            new_landed_at = cur.get("landed_at") if cur.get("landed_channel") == channel and cur.get("landed_at") else None
            if new_landed_at is None:
                new_landed_at = db.execute(text("SELECT now()")).scalar()
        else:
            new_landed_at = None
    if landed_note is not None:
        new_note = (landed_note or "").strip()
    if verified is not None:
        new_verified = bool(verified)
        if new_verified:
            new_verified_at = db.execute(text("SELECT now()")).scalar()
            new_verified_by = (verified_by or "").strip()
        else:
            new_verified_at = None
            new_verified_by = ""

    db.execute(text(
        "INSERT INTO mail_llm_iteration_suggestion_status "
        "(group_key, scope, target, suggestion_type, landed_channel, landed_note, landed_at, verified, verified_by, verified_at, updated_at) "
        "VALUES (:k,:scope,:target,:st,:ch,:note,:lat,:ver,:vby,:vat,now()) "
        "ON CONFLICT (group_key) DO UPDATE SET "
        "scope=EXCLUDED.scope, target=EXCLUDED.target, suggestion_type=EXCLUDED.suggestion_type, "
        "landed_channel=EXCLUDED.landed_channel, landed_note=EXCLUDED.landed_note, landed_at=EXCLUDED.landed_at, "
        "verified=EXCLUDED.verified, verified_by=EXCLUDED.verified_by, verified_at=EXCLUDED.verified_at, updated_at=now()"
    ), {
        "k": gk, "scope": scope or cur.get("scope") or "", "target": target or cur.get("target") or "",
        "st": suggestion_type or cur.get("suggestion_type") or "",
        "ch": new_channel, "note": new_note, "lat": new_landed_at,
        "ver": new_verified, "vby": new_verified_by, "vat": new_verified_at,
    })
    db.commit()
    row = db.execute(text(
        "SELECT * FROM mail_llm_iteration_suggestion_status WHERE group_key=:k"
    ), {"k": gk}).fetchone()
    out = dict(row._mapping)
    out["landed_channel_label"] = LANDED_CHANNEL_LABELS.get(out.get("landed_channel") or "", out.get("landed_channel") or "未落地")
    out["landed_at"] = str(out.get("landed_at") or "")
    out["verified_at"] = str(out.get("verified_at") or "")
    out["updated_at"] = str(out.get("updated_at") or "")
    return out


def _norm_html(value: str | None) -> str:
    s = html.unescape(value or "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _term_delta(orig: str, final: str, terms: list[str]) -> bool:
    lo = orig.lower()
    lf = final.lower()
    return any(lo.count(t.lower()) != lf.count(t.lower()) for t in terms)


def classify_edit(row: dict[str, Any] | None) -> tuple[list[str], str, bool, bool]:
    if not row:
        return [], "", False, False
    subject_changed = (row.get("orig_subject") or "").strip() != (row.get("final_subject") or "").strip()
    orig = _norm_html(row.get("orig_body_html"))
    final = _norm_html(row.get("final_body_html"))
    body_changed = orig != final
    flags: list[str] = []
    if body_changed:
        flags.append("正文任意改动")
    if subject_changed:
        flags.append("主题改动")
    for name, terms in TERM_GROUPS.items():
        o = orig
        f = final
        if name == "称呼/开头语言调整":
            o, f = orig[:180], final[:180]
        elif name == "结尾动作/语气调整":
            o, f = orig[-320:], final[-320:]
        if _term_delta(o, f, terms):
            flags.append(name)
    if body_changed and not any(f in flags for f in (
        "签名/联系方式调整", "称呼/开头语言调整", "业务线/服务描述调整",
        "结尾动作/语气调整", "占位/测试痕迹处理",
    )):
        flags.append("其他正文措辞调整")
    primary = ""
    if row.get("edited"):
        for candidate in PRIMARY_ORDER:
            if candidate in flags:
                primary = candidate
                break
        if not primary:
            primary = "其他文本调整"
    return flags, primary, subject_changed, body_changed


def _scenario_step_label(scenario: str | None, suite_step: Any) -> str:
    scene = SCENARIO_LABELS.get(str(scenario or ""), str(scenario or "") or "未识别套装")
    if suite_step:
        return f"{scene} 第{suite_step}封"
    return scene


def _suggestion_scope(flag: str) -> str:
    if flag in ("签名/联系方式调整", "占位/测试痕迹处理"):
        return "通用部分"
    return "套装脚本"


def _suggestion_group_key(suggestion: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(suggestion.get("scope") or ""),
        str(suggestion.get("target") or ""),
        str(suggestion.get("suggestion_type") or ""),
    )


def build_ai_suggestions(item: dict[str, Any], flags: list[str], primary: str) -> list[dict[str, Any]]:
    """Turn human-edit signals into concrete, groupable script fixes."""
    if not item.get("edited"):
        return []
    ordered = [f for f in PRIMARY_ORDER if f in flags]
    if "主题改动" in flags and "主题改动" not in ordered:
        ordered.append("主题改动")
    if "其他正文措辞调整" in flags and "其他正文措辞调整" not in ordered:
        ordered.append("其他正文措辞调整")
    if not ordered and primary:
        ordered.append(primary)
    scenario_step = _scenario_step_label(item.get("scenario"), item.get("suite_step"))
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for flag in ordered:
        text = SUGGESTION_TEXTS.get(flag)
        if not text or flag in seen:
            continue
        seen.add(flag)
        scope = _suggestion_scope(flag)
        target = SUGGESTION_TARGETS.get(flag, "套装脚本")
        suggestions.append({
            "scope": scope,
            "target": target,
            "affected_suite_step": scenario_step,
            "scenario": item.get("scenario") or "",
            "scenario_label": SCENARIO_LABELS.get(str(item.get("scenario") or ""), str(item.get("scenario") or "")),
            "suite_step": item.get("suite_step"),
            "suggestion_type": flag,
            "suggestion": text,
            "source": item.get("source") or "",
            "staff_id": str(item.get("staff_id") or ""),
            "customer_id": item.get("customer_id") or "",
            "contact_id": item.get("contact_id") or "",
            "evidence": f"{flag}：{item.get('subject') or '无主题'}"[:180],
        })
    return suggestions


def _edit_records(db: Session, instance_ids: list[str]) -> tuple[dict[str, dict], dict[tuple, list[dict]]]:
    rows: list[dict] = []
    ids = sorted({str(x or "").strip() for x in instance_ids if str(x or "").strip()})
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        if not chunk:
            continue
        rows.extend([dict(r._mapping) for r in db.execute(text(
            "SELECT record_id, instance_id, source, customer_kh, contact_id, owner_staff_id, scenario, suite_step, "
            "orig_subject, orig_body_html, final_subject, final_body_html, edited, edit_count, generated_at, last_edited_at "
            "FROM mail_llm_edit_record WHERE instance_id = ANY(:ids)"
        ), {"ids": chunk}).fetchall()])
    rows.extend([dict(r._mapping) for r in db.execute(text(
        "SELECT record_id, instance_id, source, customer_kh, contact_id, owner_staff_id, scenario, suite_step, "
        "orig_subject, orig_body_html, final_subject, final_body_html, edited, edit_count, generated_at, last_edited_at "
        "FROM mail_llm_edit_record WHERE source='mail_suite' AND edited=TRUE"
    )).fetchall()])
    by_instance = {str(r.get("instance_id") or ""): r for r in rows if r.get("instance_id")}
    suite_keys: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("source") != "mail_suite" or not r.get("edited"):
            continue
        key = (
            str(r.get("customer_kh") or ""),
            str(r.get("scenario") or ""),
            int(r.get("suite_step") or 0),
            str(r.get("owner_staff_id") or ""),
        )
        suite_keys[key].append(r)
    return by_instance, suite_keys

def _crm_items(db: Session, start: date, end: date) -> list[dict]:
    items: list[dict] = []
    autos = [dict(r._mapping) for r in db.execute(text(
        "SELECT item_id::text AS source_row_id, 'autosend' AS source, owner_staff_id AS staff_id, "
        "customer_id, contact_id, scenario, suite_step, subject, body_html, llm_instance_id AS instance_id, "
        "COALESCE(committed_at, updated_at, created_at) AS crm_time, "
        "COALESCE(committed_at::date, updated_at::date, created_at::date) AS stat_date "
        "FROM mail_autosend_plan_item "
        "WHERE (status IN ('sent','committed','crm_sent','sent_done','send_success') OR crm_send_id IS NOT NULL OR committed_at IS NOT NULL) "
        "AND COALESCE(committed_at::date, updated_at::date, created_at::date)>=:s "
        "AND COALESCE(committed_at::date, updated_at::date, created_at::date)<=:e"
    ), {"s": start, "e": end}).fetchall()]
    by_instance, suite_keys = _edit_records(db, [str(it.get("instance_id") or "") for it in autos])
    for it in autos:
        edit = by_instance.get(str(it.get("instance_id") or ""))
        it["edit_record"] = edit
        it["edited"] = bool(edit and edit.get("edited"))
        items.append(it)

    suites = [dict(r._mapping) for r in db.execute(text(
        "SELECT plan_id::text AS source_row_id, 'mail_suite' AS source, inputer_staff_id AS staff_id, "
        "customer_id, '' AS contact_id, scenario, suite_step, subject, body_html, NULL AS instance_id, "
        "created_at AS crm_time, created_at::date AS stat_date "
        "FROM mail_customer_suite_send_plan "
        "WHERE (status='enqueued' OR crm_send_id IS NOT NULL) "
        "AND created_at::date>=:s AND created_at::date<=:e"
    ), {"s": start, "e": end}).fetchall()]
    for it in suites:
        key = (
            str(it.get("customer_id") or ""),
            str(it.get("scenario") or ""),
            int(it.get("suite_step") or 0),
            str(it.get("staff_id") or ""),
        )
        matches = suite_keys.get(key) or []
        edit = matches[-1] if matches else None
        it["edit_record"] = edit
        it["edited"] = bool(edit)
        items.append(it)
    return items


def _empty_counts() -> dict[str, int]:
    keys = [
        "crm_total", "edited_total", "autosend_total", "autosend_edited",
        "mail_suite_total", "mail_suite_edited",
        *TYPE_COLUMNS.values(),
        "ai_suggestion_count",
    ]
    return {k: 0 for k in keys}


def compute_and_store(db: Session, start: date, end: date) -> dict:
    ensure_tables(db)
    db.execute(text("DELETE FROM mail_llm_iteration_daily_summary WHERE stat_date>=:s AND stat_date<=:e"), {"s": start, "e": end})
    db.execute(text("DELETE FROM mail_llm_iteration_staff_daily_summary WHERE stat_date>=:s AND stat_date<=:e"), {"s": start, "e": end})
    db.execute(text("DELETE FROM mail_llm_iteration_detail_index WHERE stat_date>=:s AND stat_date<=:e"), {"s": start, "e": end})

    daily: dict[date, dict[str, int]] = defaultdict(_empty_counts)
    staff_daily: dict[tuple, dict[str, int]] = defaultdict(_empty_counts)
    daily_suggestion_keys: dict[date, set[tuple[str, str, str]]] = defaultdict(set)
    staff_suggestion_keys: dict[tuple, set[tuple[str, str, str]]] = defaultdict(set)
    detail_count = 0

    for it in _crm_items(db, start, end):
        d = it.get("stat_date")
        staff = str(it.get("staff_id") or "")
        source = str(it.get("source") or "")
        edit = it.get("edit_record") or {}
        flags, primary, subject_changed, body_changed = classify_edit(edit)
        edited = bool(it.get("edited"))
        if not edited:
            flags, primary, subject_changed, body_changed = [], "", False, False
        suggestions = build_ai_suggestions(it, flags, primary) if edited else []
        for bucket in (daily[d], staff_daily[(d, staff)]):
            bucket["crm_total"] += 1
            if edited:
                bucket["edited_total"] += 1
            if source == "autosend":
                bucket["autosend_total"] += 1
                if edited:
                    bucket["autosend_edited"] += 1
            elif source == "mail_suite":
                bucket["mail_suite_total"] += 1
                if edited:
                    bucket["mail_suite_edited"] += 1
            for flag in flags:
                col = TYPE_COLUMNS.get(flag)
                if col:
                    bucket[col] += 1
        for suggestion in suggestions:
            key = _suggestion_group_key(suggestion)
            daily_suggestion_keys[d].add(key)
            staff_suggestion_keys[(d, staff)].add(key)
        db.execute(text(
            "INSERT INTO mail_llm_iteration_detail_index "
            "(stat_date, staff_id, source, source_row_id, instance_id, edit_record_id, customer_id, contact_id, "
            "scenario, suite_step, crm_time, subject, edited, subject_changed, body_changed, primary_type, type_flags, "
            "ai_suggestion_count, ai_suggestions) "
            "VALUES (:d,:staff,:src,:rid,:iid,:erid,:cid,:contact,:sc,:step,:ct,:sub,:ed,:sch,:bch,:pt,CAST(:flags AS jsonb),"
            ":sugg_count,CAST(:suggestions AS jsonb))"
        ), {
            "d": d, "staff": staff, "src": source, "rid": str(it.get("source_row_id") or ""),
            "iid": it.get("instance_id"), "erid": edit.get("record_id") if edit else None,
            "cid": it.get("customer_id"), "contact": it.get("contact_id"), "sc": it.get("scenario"),
            "step": it.get("suite_step"), "ct": it.get("crm_time"), "sub": (it.get("subject") or "")[:500],
            "ed": edited, "sch": subject_changed, "bch": body_changed, "pt": primary,
            "flags": json.dumps(flags, ensure_ascii=False),
            "sugg_count": len(suggestions),
            "suggestions": json.dumps(suggestions, ensure_ascii=False),
        })
        detail_count += 1

    for d, c in daily.items():
        c["ai_suggestion_count"] = len(daily_suggestion_keys.get(d, set()))
        db.execute(text(
            "INSERT INTO mail_llm_iteration_daily_summary "
            "(stat_date, crm_total, edited_total, autosend_total, autosend_edited, mail_suite_total, mail_suite_edited, "
            "body_changed_count, subject_changed_count, signature_count, greeting_count, service_count, cta_count, "
            "placeholder_count, other_body_count, ai_suggestion_count, computed_at) "
            "VALUES (:d,:crm_total,:edited_total,:autosend_total,:autosend_edited,:mail_suite_total,:mail_suite_edited,"
            ":body_changed_count,:subject_changed_count,:signature_count,:greeting_count,:service_count,:cta_count,"
            ":placeholder_count,:other_body_count,:ai_suggestion_count,now())"
        ), {"d": d, **c})
    for (d, staff), c in staff_daily.items():
        c["ai_suggestion_count"] = len(staff_suggestion_keys.get((d, staff), set()))
        db.execute(text(
            "INSERT INTO mail_llm_iteration_staff_daily_summary "
            "(stat_date, staff_id, crm_total, edited_total, autosend_total, autosend_edited, mail_suite_total, mail_suite_edited, "
            "body_changed_count, subject_changed_count, signature_count, greeting_count, service_count, cta_count, "
            "placeholder_count, other_body_count, ai_suggestion_count, computed_at) "
            "VALUES (:d,:staff,:crm_total,:edited_total,:autosend_total,:autosend_edited,:mail_suite_total,:mail_suite_edited,"
            ":body_changed_count,:subject_changed_count,:signature_count,:greeting_count,:service_count,:cta_count,"
            ":placeholder_count,:other_body_count,:ai_suggestion_count,now())"
        ), {"d": d, "staff": staff, **c})
    db.commit()
    return {"days": len(daily), "staff_days": len(staff_daily), "detail_rows": detail_count}


def _row_dict(row) -> dict:
    out = dict(row._mapping)
    crm = int(out.get("crm_total") or 0)
    edited = int(out.get("edited_total") or 0)
    out["edit_rate_pct"] = round(edited * 100.0 / crm, 1) if crm else 0.0
    return out


def query_summary(db: Session, start: date, end: date, staff_id: str | None = None) -> dict:
    ensure_tables(db)
    staff = (staff_id or "").strip()
    if staff:
        rows = [_row_dict(r) for r in db.execute(text(
            "SELECT * FROM mail_llm_iteration_staff_daily_summary "
            "WHERE stat_date>=:s AND stat_date<=:e AND staff_id=:staff ORDER BY stat_date DESC"
        ), {"s": start, "e": end, "staff": staff}).fetchall()]
    else:
        rows = [_row_dict(r) for r in db.execute(text(
            "SELECT * FROM mail_llm_iteration_daily_summary "
            "WHERE stat_date>=:s AND stat_date<=:e ORDER BY stat_date DESC"
        ), {"s": start, "e": end}).fetchall()]
    staff_rows = [_row_dict(r) for r in db.execute(text(
        "SELECT * FROM mail_llm_iteration_staff_daily_summary "
        "WHERE stat_date>=:s AND stat_date<=:e "
        "AND (:staff='' OR staff_id=:staff) ORDER BY stat_date DESC, crm_total DESC, staff_id"
    ), {"s": start, "e": end, "staff": staff}).fetchall()]
    totals = _empty_counts()
    for r in rows:
        for k in totals:
            totals[k] += int(r.get(k) or 0)
    totals["edit_rate_pct"] = round(totals["edited_total"] * 100.0 / totals["crm_total"], 1) if totals["crm_total"] else 0.0
    return {
        "daily": rows,
        "staff_daily": staff_rows,
        "totals": totals,
        # 1.5: 前端只展示具体改动点, 去掉笼统的"正文任意改动"列。底层仍保留 body_changed_count 供追溯。
        "type_columns": DISPLAY_TYPE_COLUMNS,
        "staff_options": list_staff(db),
    }


def list_staff(db: Session) -> list[str]:
    ensure_tables(db)
    return [str(r[0]) for r in db.execute(text(
        "SELECT DISTINCT staff_id FROM mail_llm_iteration_staff_daily_summary "
        "WHERE COALESCE(staff_id,'')<>'' ORDER BY staff_id"
    )).fetchall()]


def _detail_base_filters(day: date, staff_id: str | None = None) -> tuple[list[str], dict[str, Any]]:
    staff = (staff_id or "").strip()
    clauses = ["d.stat_date=:d"]
    params: dict[str, Any] = {"d": day}
    if staff:
        clauses.append("d.staff_id=:staff")
        params["staff"] = staff
    return clauses, params


def _ai_suggestion_summary_rows(db: Session, day: date, staff_id: str | None, limit: int, offset: int) -> dict:
    clauses, params = _detail_base_filters(day, staff_id)
    clauses.append("d.ai_suggestion_count>0")
    where = " AND ".join(clauses)
    rows = db.execute(text(f"""
        SELECT d.detail_id, d.stat_date, d.staff_id, d.source, d.customer_id, d.contact_id, d.scenario,
               d.suite_step, d.crm_time, d.subject, d.ai_suggestions
        FROM mail_llm_iteration_detail_index d
        WHERE {where}
        ORDER BY d.crm_time DESC NULLS LAST, d.source_row_id
    """), params).fetchall()
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        m = dict(r._mapping)
        suggestions = m.get("ai_suggestions") or []
        if isinstance(suggestions, str):
            suggestions = json.loads(suggestions)
        for suggestion in suggestions:
            key = _suggestion_group_key(suggestion)
            g = grouped.get(key)
            if not g:
                g = {
                    "suggestion_group": True,
                    "scope": suggestion.get("scope") or "",
                    "target": suggestion.get("target") or "",
                    "suggestion_type": suggestion.get("suggestion_type") or "",
                    "suggestion": suggestion.get("suggestion") or "",
                    "scenario": suggestion.get("scenario") or "",
                    "scenario_label": suggestion.get("scenario_label") or "",
                    "suite_step": suggestion.get("suite_step"),
                    "hit_count": 0,
                    "sources": Counter(),
                    "staff_ids": Counter(),
                    "sample_customer_id": "",
                    "sample_contact_id": "",
                    "sample_subject": "",
                    "sample_evidence": "",
                    "sample_detail_id": "",
                }
                grouped[key] = g
            g["hit_count"] += 1
            g["sources"][m.get("source") or ""] += 1
            g["staff_ids"][m.get("staff_id") or ""] += 1
            if not g["sample_customer_id"]:
                g["sample_customer_id"] = m.get("customer_id") or ""
                g["sample_contact_id"] = m.get("contact_id") or ""
                g["sample_subject"] = m.get("subject") or ""
                g["sample_evidence"] = suggestion.get("evidence") or ""
                g["sample_detail_id"] = str(m.get("detail_id") or "")
    items = sorted(grouped.values(), key=lambda x: (-int(x["hit_count"]), x["target"], x["suggestion_type"]))
    total = len(items)
    start = max(0, int(offset or 0))
    stop = start + max(1, min(int(limit or 80), 200))
    paged = items[start:stop]
    statuses = _load_suggestion_statuses(db)
    for item in paged:
        item["sources"] = ", ".join(f"{k}:{v}" for k, v in item["sources"].most_common() if k)
        item["staff_ids"] = ", ".join(f"{k}:{v}" for k, v in item["staff_ids"].most_common() if k)
        gk = _group_status_key_str(item.get("scope"), item.get("target"), item.get("suggestion_type"))
        st = statuses.get(gk) or {}
        item["group_key"] = gk
        item["landed_channel"] = st.get("landed_channel") or ""
        item["landed_channel_label"] = LANDED_CHANNEL_LABELS.get(st.get("landed_channel") or "", "未落地")
        item["landed_note"] = st.get("landed_note") or ""
        item["landed_at"] = str(st.get("landed_at") or "")
        item["verified"] = bool(st.get("verified"))
        item["verified_by"] = st.get("verified_by") or ""
        item["verified_at"] = str(st.get("verified_at") or "")
    return {"total": total, "items": paged}


def suggestion_samples(
    db: Session,
    day: date,
    group_key: str,
    staff_id: str | None = None,
    limit: int = 80,
    offset: int = 0,
) -> dict:
    """1.4 下钻: 某条 AI 建议(建议组)命中的逐封原始生成 vs 人工改后正文。"""
    ensure_tables(db)
    gk = (group_key or "").strip()
    if not gk:
        raise ValueError("group_key is required")
    clauses, params = _detail_base_filters(day, staff_id)
    clauses.append("d.ai_suggestion_count>0")
    where = " AND ".join(clauses)
    rows = db.execute(text(f"""
        SELECT d.detail_id, d.stat_date, d.staff_id, d.source, d.customer_id, d.contact_id, d.scenario,
               d.suite_step, d.crm_time, d.subject, d.primary_type, d.type_flags, d.ai_suggestions,
               e.orig_subject, e.orig_body_html, e.final_subject, e.final_body_html, e.edit_count, e.last_edited_at
        FROM mail_llm_iteration_detail_index d
        LEFT JOIN mail_llm_edit_record e ON e.record_id=d.edit_record_id
        WHERE {where}
        ORDER BY d.crm_time DESC NULLS LAST, d.source_row_id
    """), params).fetchall()
    items: list[dict] = []
    for r in rows:
        m = dict(r._mapping)
        suggestions = m.get("ai_suggestions") or []
        if isinstance(suggestions, str):
            suggestions = json.loads(suggestions)
        hit = None
        for s in suggestions:
            if _group_status_key_str(s.get("scope"), s.get("target"), s.get("suggestion_type")) == gk:
                hit = s
                break
        if hit is None:
            continue
        items.append({
            "detail_id": str(m.get("detail_id") or ""),
            "stat_date": str(m.get("stat_date") or ""),
            "staff_id": m.get("staff_id") or "",
            "source": m.get("source") or "",
            "customer_id": m.get("customer_id") or "",
            "contact_id": m.get("contact_id") or "",
            "scenario": m.get("scenario") or "",
            "scenario_label": SCENARIO_LABELS.get(m.get("scenario") or "", m.get("scenario") or ""),
            "suite_step": m.get("suite_step"),
            "crm_time": str(m.get("crm_time") or ""),
            "subject": m.get("subject") or "",
            "primary_type": m.get("primary_type") or "",
            "type_flags": m.get("type_flags") or [],
            "evidence": hit.get("evidence") or "",
            "orig_subject": m.get("orig_subject") or "",
            "orig_body_html": m.get("orig_body_html") or "",
            "final_subject": m.get("final_subject") or "",
            "final_body_html": m.get("final_body_html") or "",
            "edit_count": int(m.get("edit_count") or 0),
            "last_edited_at": str(m.get("last_edited_at") or ""),
        })
    total = len(items)
    start = max(0, int(offset or 0))
    stop = start + max(1, min(int(limit or 80), 200))
    return {"total": total, "items": items[start:stop]}


def detail_rows(db: Session, day: date, metric: str, staff_id: str | None = None, limit: int = 80, offset: int = 0) -> dict:
    ensure_tables(db)
    metric_norm = (metric or "").strip()
    if metric_norm == "ai_suggestion_count":
        return _ai_suggestion_summary_rows(db, day, staff_id, limit, offset)
    clauses, params = _detail_base_filters(day, staff_id)
    params.update({"lim": max(1, min(int(limit or 80), 200)), "off": max(0, int(offset or 0))})
    if metric_norm == "edited_total":
        clauses.append("d.edited=TRUE")
    elif metric_norm == "crm_total":
        pass
    elif metric_norm == "autosend_total":
        clauses.append("d.source='autosend'")
    elif metric_norm == "mail_suite_total":
        clauses.append("d.source='mail_suite'")
    elif metric_norm == "autosend_edited":
        clauses.append("d.source='autosend'")
        clauses.append("d.edited=TRUE")
    elif metric_norm == "mail_suite_edited":
        clauses.append("d.source='mail_suite'")
        clauses.append("d.edited=TRUE")
    else:
        flag = next((name for name, col in TYPE_COLUMNS.items() if col == metric_norm or name == metric_norm), "")
        if flag:
            clauses.append("d.type_flags ? :flag")
            params["flag"] = flag
        else:
            raise ValueError(f"unsupported metric: {metric_norm}")
    where = " AND ".join(clauses)
    total = db.execute(text(f"SELECT COUNT(*) FROM mail_llm_iteration_detail_index d WHERE {where}"), params).scalar() or 0
    rows = db.execute(text(f"""
        SELECT d.*, e.orig_subject, e.orig_body_html, e.final_subject, e.final_body_html, e.edit_count, e.last_edited_at
        FROM mail_llm_iteration_detail_index d
        LEFT JOIN mail_llm_edit_record e ON e.record_id=d.edit_record_id
        WHERE {where}
        ORDER BY d.edited DESC, d.crm_time DESC NULLS LAST, d.source_row_id
        LIMIT :lim OFFSET :off
    """), params).fetchall()
    items = []
    for r in rows:
        m = dict(r._mapping)
        items.append({
            "detail_id": str(m.get("detail_id") or ""),
            "stat_date": str(m.get("stat_date") or ""),
            "staff_id": m.get("staff_id") or "",
            "source": m.get("source") or "",
            "customer_id": m.get("customer_id") or "",
            "contact_id": m.get("contact_id") or "",
            "scenario": m.get("scenario") or "",
            "scenario_label": SCENARIO_LABELS.get(m.get("scenario") or "", m.get("scenario") or ""),
            "suite_step": m.get("suite_step"),
            "crm_time": str(m.get("crm_time") or ""),
            "subject": m.get("subject") or "",
            "edited": bool(m.get("edited")),
            "primary_type": m.get("primary_type") or "",
            "type_flags": m.get("type_flags") or [],
            "ai_suggestion_count": int(m.get("ai_suggestion_count") or 0),
            "ai_suggestions": m.get("ai_suggestions") or [],
            "orig_subject": m.get("orig_subject") or "",
            "orig_body_html": m.get("orig_body_html") or "",
            "final_subject": m.get("final_subject") or "",
            "final_body_html": m.get("final_body_html") or "",
            "edit_count": int(m.get("edit_count") or 0),
            "last_edited_at": str(m.get("last_edited_at") or ""),
        })
    return {"total": int(total), "items": items}
