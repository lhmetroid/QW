# -*- coding: utf-8 -*-
"""Daily LLM mail iteration analysis.

Stores daily aggregates for human edits against emails that were already
enqueued/committed to CRM. Detail rows only keep lightweight indexes; full
original/final bodies are loaded lazily from mail_llm_edit_record.
"""
from __future__ import annotations

import html
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
        "created_at TIMESTAMP DEFAULT now(),"
        "CONSTRAINT uq_mlid_source_row UNIQUE(source, source_row_id)"
        ")"
    ))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_mlid_date_staff ON mail_llm_iteration_detail_index (stat_date, staff_id);"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_mlid_type ON mail_llm_iteration_detail_index (primary_type);"))
    db.commit()


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
    ]
    return {k: 0 for k in keys}


def compute_and_store(db: Session, start: date, end: date) -> dict:
    ensure_tables(db)
    db.execute(text("DELETE FROM mail_llm_iteration_daily_summary WHERE stat_date>=:s AND stat_date<=:e"), {"s": start, "e": end})
    db.execute(text("DELETE FROM mail_llm_iteration_staff_daily_summary WHERE stat_date>=:s AND stat_date<=:e"), {"s": start, "e": end})
    db.execute(text("DELETE FROM mail_llm_iteration_detail_index WHERE stat_date>=:s AND stat_date<=:e"), {"s": start, "e": end})

    daily: dict[date, dict[str, int]] = defaultdict(_empty_counts)
    staff_daily: dict[tuple, dict[str, int]] = defaultdict(_empty_counts)
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
        db.execute(text(
            "INSERT INTO mail_llm_iteration_detail_index "
            "(stat_date, staff_id, source, source_row_id, instance_id, edit_record_id, customer_id, contact_id, "
            "scenario, suite_step, crm_time, subject, edited, subject_changed, body_changed, primary_type, type_flags) "
            "VALUES (:d,:staff,:src,:rid,:iid,:erid,:cid,:contact,:sc,:step,:ct,:sub,:ed,:sch,:bch,:pt,CAST(:flags AS jsonb))"
        ), {
            "d": d, "staff": staff, "src": source, "rid": str(it.get("source_row_id") or ""),
            "iid": it.get("instance_id"), "erid": edit.get("record_id") if edit else None,
            "cid": it.get("customer_id"), "contact": it.get("contact_id"), "sc": it.get("scenario"),
            "step": it.get("suite_step"), "ct": it.get("crm_time"), "sub": (it.get("subject") or "")[:500],
            "ed": edited, "sch": subject_changed, "bch": body_changed, "pt": primary,
            "flags": __import__("json").dumps(flags, ensure_ascii=False),
        })
        detail_count += 1

    for d, c in daily.items():
        db.execute(text(
            "INSERT INTO mail_llm_iteration_daily_summary "
            "(stat_date, crm_total, edited_total, autosend_total, autosend_edited, mail_suite_total, mail_suite_edited, "
            "body_changed_count, subject_changed_count, signature_count, greeting_count, service_count, cta_count, "
            "placeholder_count, other_body_count, computed_at) "
            "VALUES (:d,:crm_total,:edited_total,:autosend_total,:autosend_edited,:mail_suite_total,:mail_suite_edited,"
            ":body_changed_count,:subject_changed_count,:signature_count,:greeting_count,:service_count,:cta_count,"
            ":placeholder_count,:other_body_count,now())"
        ), {"d": d, **c})
    for (d, staff), c in staff_daily.items():
        db.execute(text(
            "INSERT INTO mail_llm_iteration_staff_daily_summary "
            "(stat_date, staff_id, crm_total, edited_total, autosend_total, autosend_edited, mail_suite_total, mail_suite_edited, "
            "body_changed_count, subject_changed_count, signature_count, greeting_count, service_count, cta_count, "
            "placeholder_count, other_body_count, computed_at) "
            "VALUES (:d,:staff,:crm_total,:edited_total,:autosend_total,:autosend_edited,:mail_suite_total,:mail_suite_edited,"
            ":body_changed_count,:subject_changed_count,:signature_count,:greeting_count,:service_count,:cta_count,"
            ":placeholder_count,:other_body_count,now())"
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
        "type_columns": TYPE_COLUMNS,
        "staff_options": list_staff(db),
    }


def list_staff(db: Session) -> list[str]:
    ensure_tables(db)
    return [str(r[0]) for r in db.execute(text(
        "SELECT DISTINCT staff_id FROM mail_llm_iteration_staff_daily_summary "
        "WHERE COALESCE(staff_id,'')<>'' ORDER BY staff_id"
    )).fetchall()]


def detail_rows(db: Session, day: date, metric: str, staff_id: str | None = None, limit: int = 80, offset: int = 0) -> dict:
    ensure_tables(db)
    staff = (staff_id or "").strip()
    clauses = ["d.stat_date=:d"]
    params: dict[str, Any] = {"d": day, "lim": max(1, min(int(limit or 80), 200)), "off": max(0, int(offset or 0))}
    if staff:
        clauses.append("d.staff_id=:staff")
        params["staff"] = staff
    metric_norm = (metric or "").strip()
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
            "orig_subject": m.get("orig_subject") or "",
            "orig_body_html": m.get("orig_body_html") or "",
            "final_subject": m.get("final_subject") or "",
            "final_body_html": m.get("final_body_html") or "",
            "edit_count": int(m.get("edit_count") or 0),
            "last_edited_at": str(m.get("last_edited_at") or ""),
        })
    return {"total": int(total), "items": items}