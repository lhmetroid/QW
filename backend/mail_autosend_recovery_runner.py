from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session
from database import MailAutosendConfig, SessionLocal

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "backend" / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

FUNCTIONS = {
    "_autosend_parse_interval_csv", "_autosend_parse_date_csv", "_autosend_holiday_set",
    "_cn_holiday_plan_sets", "_autosend_is_non_workday", "_autosend_next_workday",
    "_autosend_parse_hhmm", "_autosend_fmt_hhmm", "_autosend_crm_pending_snapshot",
    "_autosend_crm_pending_slots", "_autosend_crm_sent_snapshot",
    "_autosend_apply_crm_time_changes", "_autosend_reschedule_plan", "_autosend_receiver_key",
}
CLASSES = {"_AutosendSlotBook"}
NODES = []
for node in TREE.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        NODES.append(node)
    elif isinstance(node, ast.ClassDef) and node.name in CLASSES:
        NODES.append(node)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_CN_HOLIDAY_PLAN_BY_YEAR":
        NODES.append(node)

logger = logging.getLogger("mail_autosend_recovery")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def get_config(db):
    row = db.query(MailAutosendConfig).order_by(MailAutosendConfig.config_id).first()
    if row is None:
        raise RuntimeError("mail_autosend_config 不存在，拒绝恢复")
    return row


def serialize_config(row):
    parse_dates = NS["_autosend_parse_date_csv"]
    return {
        "daily_cap": int(row.daily_cap or 10),
        "skip_non_workdays": bool(getattr(row, "skip_non_workdays", True)),
        "holiday_dates": parse_dates(getattr(row, "holiday_dates_csv", None) or ""),
    }


NS = {
    "Any": Any, "Session": Session, "date": date, "datetime": datetime, "timedelta": timedelta,
    "re": re, "text": text, "bindparam": bindparam, "logger": logger,
    "_AUTOSEND_MOVABLE_SQL_IN": "'planned','queued','drafting','drafted','commit_queued','commit_failed'",
    "_AUTOSEND_RESCHEDULE_LEAD_MINUTES": 10, "_AUTOSEND_RESCHEDULE_MAX_DAYS": 180,
    "_AUTOSEND_SLOT_GAP_MINUTES": 10, "_AUTOSEND_DAY_START_MINUTE": 540,
    "_AUTOSEND_DAY_END_MINUTE": 1110,
    "_EMAIL_IN_RECEIVER_RE": re.compile(r"<([^<>@\s]+@[^<>\s]+)>")
}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(MAIN), "exec"), NS)
NS["_autosend_get_or_create_config"] = get_config
NS["_autosend_serialize_config"] = serialize_config


def source_hash():
    return hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()


def content_hashes(db, item_ids):
    out = {}
    for i in range(0, len(item_ids), 500):
        batch = item_ids[i:i + 500]
        rows = db.execute(text(
            "SELECT item_id, md5(COALESCE(subject,'') || E'\\n' || COALESCE(body_html,'') || E'\\n' || COALESCE(llm_prompt,'')) "
            "FROM mail_autosend_plan_item WHERE item_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)), {"ids": batch}).fetchall()
        out.update({str(item_id): digest for item_id, digest in rows})
    return out


def main():
    parser = argparse.ArgumentParser(description="邮件套装排期恢复；默认只预演")
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.apply and args.confirm != "APPLY-SCHEDULE-TIME-ONLY":
        raise SystemExit("apply 需要 --confirm APPLY-SCHEDULE-TIME-ONLY")

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    if not audit.get("read_only"):
        raise RuntimeError("审计文件缺少 read_only 标志")
    by_staff = {}
    for record in audit.get("records", []):
        by_staff.setdefault(str(record.get("staff_id") or ""), set()).add(str(record["item_id"]))
    if not by_staff or any(not staff for staff in by_staff):
        raise RuntimeError("审计文件没有有效销售范围")

    db = SessionLocal()
    try:
        config = serialize_config(get_config(db))
        if config["daily_cap"] != 50:
            raise RuntimeError(f"当前每日上限是 {config['daily_cap']}，不是用户确认的 50，拒绝恢复")
        all_ids = sorted({item for values in by_staff.values() for item in values})
        before_hash = content_hashes(db, all_ids)
        results = []
        for staff in sorted(by_staff):
            ids = sorted(by_staff[staff])
            logger.info("%s staff=%s suitescope_items=%s", "APPLY" if args.apply else "PREVIEW", staff, len(ids))
            result = NS["_autosend_reschedule_plan"](db, staff, bool(args.apply), ids)
            results.append(result)
        after_hash = content_hashes(db, all_ids)
        if before_hash != after_hash:
            raise RuntimeError("主题/正文/Prompt 哈希发生变化，恢复安全门失败")
    finally:
        db.close()

    output = {
        "generated_at": datetime.now().isoformat(), "applied": bool(args.apply),
        "source_sha256": source_hash(), "audit_file": str(Path(args.audit)),
        "config": config, "staff_count": len(by_staff), "item_scope_count": len(all_ids),
        "content_hash_unchanged": before_hash == after_hash, "results": results,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "applied": output["applied"], "staff_count": output["staff_count"],
        "item_scope_count": output["item_scope_count"], "content_hash_unchanged": output["content_hash_unchanged"],
        "changed": sum(int(x.get("changed") or 0) for x in results),
        "crm_pending_movable": sum(int(x.get("crm_pending_movable") or 0) for x in results),
        "first_slot": min((x.get("first_slot") for x in results if x.get("first_slot")), default=None),
        "last_slot": max((x.get("last_slot") for x in results if x.get("last_slot")), default=None),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()