from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import bindparam, text
from database import SessionLocal
from crm_database import CRMSessionLocal

MOVABLE = ("planned", "queued", "drafting", "drafted", "commit_queued", "committing", "commit_failed")
HOLIDAYS_2026 = {date.fromisoformat(x) for x in (
    "2026-01-01,2026-01-02,2026-01-03,2026-02-15,2026-02-16,2026-02-17,2026-02-18,2026-02-19,"
    "2026-02-20,2026-02-21,2026-02-22,2026-02-23,2026-04-04,2026-04-05,2026-04-06,"
    "2026-05-01,2026-05-02,2026-05-03,2026-05-04,2026-05-05,2026-06-19,2026-06-20,2026-06-21,"
    "2026-09-25,2026-09-26,2026-09-27,2026-10-01,2026-10-02,2026-10-03,2026-10-04,"
    "2026-10-05,2026-10-06,2026-10-07"
).split(",")}
WORKDAYS_2026 = {date.fromisoformat(x) for x in (
    "2026-01-04,2026-02-14,2026-02-28,2026-05-09,2026-09-20,2026-10-10"
).split(",")}

def non_workday(day):
    if day in WORKDAYS_2026: return False
    return day in HOLIDAYS_2026 or day.weekday() >= 5


def chunks(values, size=200):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    backup = json.loads(Path(args.backup).read_text(encoding="utf-8"))
    wait_records = [x for x in backup["records"] if (x.get("crm_truth") or {}).get("status") == "WaitSend"]
    item_ids = {x["item_id"] for x in wait_records}
    plan_ids = {x["send_plan_id"] for x in wait_records if x.get("send_plan_id")}
    staffs = sorted({x["staff_id"] for x in backup["records"] if x.get("staff_id")})

    pg = SessionLocal()
    try:
        item_map = {}
        for batch in chunks(item_ids, 500):
            for item_id, pdate, ptime, status in pg.execute(text(
                "SELECT item_id, plan_date, plan_time, status FROM mail_autosend_plan_item WHERE item_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": batch}).fetchall():
                item_map[str(item_id)] = (pdate, str(ptime or "")[:5], str(status or ""))
        plan_map = {}
        for batch in chunks(plan_ids, 500):
            for pid, ptime, rowid, crm_status, fact_time in pg.execute(text(
                "SELECT plan_id, plan_send_time, COALESCE(spqueue_rowid,''), COALESCE(crm_send_status,''), "
                "crm_fact_send_time FROM mail_customer_suite_send_plan WHERE plan_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": batch}).fetchall():
                plan_map[str(pid)] = (ptime, str(rowid or ""), str(crm_status or ""), fact_time)
        local_future = pg.execute(text(
            "SELECT owner_staff_id, plan_date, plan_time, item_id FROM mail_autosend_plan_item "
            "WHERE owner_staff_id IN :staffs AND status IN :statuses AND plan_date>=CURRENT_DATE"
        ).bindparams(bindparam("staffs", expanding=True), bindparam("statuses", expanding=True)),
            {"staffs": staffs, "statuses": list(MOVABLE)}).fetchall()
        controlled_rowids = {str(r[0] or "").lower() for r in pg.execute(text(
            "SELECT DISTINCT p.spqueue_rowid FROM mail_customer_suite_send_plan p "
            "JOIN mail_autosend_plan_item i ON p.customer_id=COALESCE(i.customer_id,i.contact_id) "
            "AND p.inputer_staff_id=i.owner_staff_id AND p.scenario=i.scenario AND p.suite_step=i.suite_step "
            "AND lower(COALESCE(p.recipient_email_key,''))=lower(COALESCE(i.recipient_email,'')) "
            "WHERE i.status='sent' AND COALESCE(p.spqueue_rowid,'')<>''"
        )).fetchall() if str(r[0] or "")}
    finally:
        pg.close()

    crm_queue = {}
    all_crm = []
    crm = CRMSessionLocal()
    try:
        rowids = {value[1] for value in plan_map.values() if value[1]}
        for batch in chunks(rowids):
            params = {f"r{i}": value for i, value in enumerate(batch)}
            marks = ",".join(f":r{i}" for i in range(len(batch)))
            rows = crm.execute(text(
                f"SELECT CAST(RowId AS NVARCHAR(64)), PlanSendTime FROM spQueueSend "
                f"WHERE CAST(RowId AS NVARCHAR(64)) IN ({marks}) AND MessageType='Email'"
            ), params).fetchall()
            crm_queue.update({str(rowid).lower(): ptime for rowid, ptime in rows})
        params = {f"s{i}": value for i, value in enumerate(staffs)}
        marks = ",".join(f":s{i}" for i in range(len(staffs)))
        all_crm = crm.execute(text(
            f"SELECT InputerStaffId, PlanSendTime, CAST(RowId AS NVARCHAR(64)), "
            f"CASE WHEN ISNULL(UseRange,'') LIKE '%宣传邮件-AI%' THEN 1 ELSE 0 END "
            f"FROM spQueueSend WHERE InputerStaffId IN ({marks}) AND MessageType='Email' "
            f"AND PlanSendTime>=CONVERT(date,GETDATE())"
        ), params).fetchall()
    finally:
        crm.close()

    mismatches = []
    resolved_transitions = []
    for old in wait_records:
        item = item_map.get(old["item_id"])
        plan = plan_map.get(old.get("send_plan_id"))
        queue_dt = crm_queue.get(plan[1].lower()) if plan else None
        if not item or not plan:
            mismatches.append({"item_id": old["item_id"], "reason": "missing_current_row",
                               "has_item": bool(item), "has_plan": bool(plan), "has_queue": bool(queue_dt),
                               "plan_id": old.get("send_plan_id"), "rowid": plan[1] if plan else None})
            continue
        if not queue_dt:
            cached = plan[2].lower()
            if cached == "sendsuccess" and plan[3] is not None:
                resolved_transitions.append({"item_id": old["item_id"], "status": "send_success",
                                             "fact_send_time": plan[3].isoformat()})
                continue
            if cached == "deleted":
                resolved_transitions.append({"item_id": old["item_id"], "status": "deleted"})
                continue
            mismatches.append({"item_id": old["item_id"], "reason": "missing_current_queue_without_final_status",
                               "has_item": True, "has_plan": True, "has_queue": False,
                               "plan_id": old.get("send_plan_id"), "rowid": plan[1], "cached_status": plan[2]})
            continue
        local_dt = datetime.combine(item[0], datetime.strptime(item[1], "%H:%M").time())
        if local_dt != plan[0] or local_dt != queue_dt or plan[2].lower() != "waitsend":
            mismatches.append({"item_id": old["item_id"], "reason": "time_or_status_diff",
                               "local": local_dt.isoformat(), "send_plan": plan[0].isoformat(),
                               "crm": queue_dt.isoformat(), "cached_status": plan[2]})

    slots = defaultdict(list)
    for staff, pdate, ptime, item_id in local_future:
        minute = int(str(ptime)[:2]) * 60 + int(str(ptime)[3:5])
        slots[(str(staff), pdate)].append((minute, "local", str(item_id), True))
    ai_non_workdays = []
    for staff, pdate, ptime, item_id in local_future:
        if non_workday(pdate):
            ai_non_workdays.append({"staff": str(staff), "date": pdate.isoformat(), "item_id": str(item_id)})
    for staff, ptime, rowid, is_ai in all_crm:
        controlled = str(rowid).lower() in controlled_rowids
        slots[(str(staff), ptime.date())].append((ptime.hour * 60 + ptime.minute,
                                                  "crm_ai" if controlled else "crm_other",
                                                  str(rowid), controlled))
        if controlled and non_workday(ptime.date()):
            ai_non_workdays.append({"staff": str(staff), "date": ptime.date().isoformat(), "rowid": str(rowid)})
    over_cap = []
    gap_violations = []
    for (staff, day), values in sorted(slots.items()):
        if len(values) > 50:
            over_cap.append({"staff": staff, "date": day.isoformat(), "count": len(values)})
        values.sort()
        for left, right in zip(values, values[1:]):
            if right[0] - left[0] < 10 and (left[3] or right[3]):
                gap_violations.append({"staff": staff, "date": day.isoformat(),
                                       "left_minute": left[0], "right_minute": right[0],
                                       "left_source": left[1], "right_source": right[1],
                                       "left_id": left[2], "right_id": right[2]})

    result = {
        "generated_at": datetime.now().isoformat(), "waitsend_checked": len(wait_records),
        "item_map_count": len(item_map), "plan_map_count": len(plan_map), "crm_queue_count": len(crm_queue),
        "three_way_mismatches": mismatches, "resolved_transitions": resolved_transitions, "over_cap_days": over_cap,
        "gap_violations": gap_violations, "ai_weekend_rows": ai_non_workdays,
        "max_combined_daily_count": max((len(x) for x in slots.values()), default=0),
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "waitsend_checked": result["waitsend_checked"],
        "item_map_count": result["item_map_count"], "plan_map_count": result["plan_map_count"], "crm_queue_count": result["crm_queue_count"],
        "three_way_mismatches": len(mismatches), "resolved_transitions": len(resolved_transitions), "over_cap_days": len(over_cap),
        "gap_violations": len(gap_violations), "ai_weekend_rows": len(ai_non_workdays),
        "max_combined_daily_count": result["max_combined_daily_count"],
    }, ensure_ascii=False))
    if mismatches or over_cap or gap_violations or ai_non_workdays:
        raise SystemExit(1)


if __name__ == "__main__":
    main()