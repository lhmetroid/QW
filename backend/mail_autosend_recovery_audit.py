from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import bindparam, text
from database import SessionLocal
from crm_database import CRMSessionLocal

ACTIVE = ("planned", "queued", "drafting", "drafted", "commit_queued", "committing", "commit_failed", "sent")


def parse_intervals(value):
    out = [int(x.strip()) for x in str(value or "").split(",") if x.strip().lstrip("-").isdigit()]
    return out or [1, 10, 19, 25]


def gap(values, step):
    idx = max(0, int(step or 1) - 1)
    return values[idx] if idx < len(values) else values[-1]


def chunks(values, size=200):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]


def main():
    parser = argparse.ArgumentParser(description="只读审计邮件套装排期/CRM状态，不执行更新")
    parser.add_argument("--staff", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--all-active", action="store_true")
    args = parser.parse_args()

    pg = SessionLocal()
    try:
        params = {"statuses": list(ACTIVE)}
        staff_sql = ""
        if args.staff:
            staff_sql = " AND i.owner_staff_id=:staff"
            params["staff"] = args.staff
        rows = pg.execute(
            text(
                "SELECT i.item_id, i.run_id, i.contact_id, COALESCE(i.customer_id,i.contact_id), "
                "i.owner_staff_id, i.scenario, i.suite_step, i.plan_date, i.plan_time, i.status, "
                "COALESCE(r.interval_days_csv,''), lower(COALESCE(i.recipient_email,'')) "
                "FROM mail_autosend_plan_item i LEFT JOIN mail_autosend_run r ON r.run_id=i.run_id "
                "WHERE i.status IN :statuses" + staff_sql +
                " ORDER BY i.run_id, i.contact_id, i.scenario, i.suite_step"
            ).bindparams(bindparam("statuses", expanding=True)), params,
        ).fetchall()

        groups = defaultdict(list)
        for row in rows:
            groups[(str(row[1] or ""), str(row[2] or ""), str(row[5] or ""))].append(row)
        affected = []
        for key, suite in groups.items():
            suite.sort(key=lambda x: int(x[6] or 0))
            if len(suite) < 2:
                continue
            intervals = parse_intervals(suite[0][10])
            first_day = suite[0][7].date() if hasattr(suite[0][7], "hour") else suite[0][7]
            first_gap = gap(intervals, suite[0][6])
            prev_day = None
            bad = False
            for row in suite:
                day = row[7].date() if hasattr(row[7], "hour") else row[7]
                required = gap(intervals, row[6]) - first_gap
                if day is None or first_day is None or (prev_day is not None and day <= prev_day) or day < first_day.fromordinal(first_day.toordinal() + required):
                    bad = True
                prev_day = day
            if bad:
                affected.extend(suite)

        if args.all_active:
            affected = list(rows)
        customer_ids = sorted({str(r[3] or "") for r in affected if str(r[3] or "")})
        plans = []
        for batch in chunks(customer_ids):
            plans.extend(pg.execute(
                text(
                    "SELECT plan_id, customer_id, inputer_staff_id, scenario, suite_step, plan_send_time, "
                    "status, COALESCE(spqueue_rowid,''), COALESCE(crm_send_id,''), "
                    "COALESCE(crm_send_status,''), crm_fact_send_time, lower(COALESCE(recipient_email_key,'')), created_at "
                    "FROM mail_customer_suite_send_plan WHERE customer_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)), {"ids": batch},
            ).fetchall())
    finally:
        pg.close()

    queue_by_rowid = {}
    sent_by_key = {}
    crm = CRMSessionLocal()
    try:
        by_staff_rowids = defaultdict(list)
        by_staff_sendids = defaultdict(list)
        for p in plans:
            if p[7]: by_staff_rowids[str(p[2] or "")].append(str(p[7]))
            if p[8]: by_staff_sendids[str(p[2] or "")].append(str(p[8]))
        for staff, rowids in by_staff_rowids.items():
            for batch in chunks(set(rowids)):
                params = {f"r{i}": value for i, value in enumerate(batch)}
                marks = ",".join(f":r{i}" for i in range(len(batch)))
                for rowid, send_id, plan_dt in crm.execute(text(
                    f"SELECT CAST(RowId AS NVARCHAR(64)), ISNULL(CAST(SendId AS NVARCHAR(80)),''), PlanSendTime "
                    f"FROM spQueueSend WHERE CAST(RowId AS NVARCHAR(64)) IN ({marks}) AND MessageType='Email'"
                ), params).fetchall():
                    queue_by_rowid[str(rowid).lower()] = {"status": "WaitSend", "send_id": str(send_id or ""), "plan_time": plan_dt.isoformat() if plan_dt else None}
        for staff, sendids in by_staff_sendids.items():
            if not staff.isalnum() or len(staff) > 8:
                continue
            for batch in chunks(set(sendids)):
                params = {f"s{i}": value for i, value in enumerate(batch)}
                marks = ",".join(f":s{i}" for i in range(len(batch)))
                try:
                    found = crm.execute(text(
                        f"SELECT SendId, ISNULL(Status,''), FactSendTime, PlanSendTime, DeleteTime "
                        f"FROM [spSendInfo{staff}] WHERE SendId IN ({marks}) AND MessageType='Email'"
                    ), params).fetchall()
                except Exception:
                    crm.rollback()
                    continue
                for send_id, status, fact_dt, plan_dt, deleted_at in found:
                    sent_by_key[(staff, str(send_id))] = {
                        "status": "deleted" if deleted_at else str(status or ""),
                        "fact_time": fact_dt.isoformat() if fact_dt else None,
                        "plan_time": plan_dt.isoformat() if plan_dt else None,
                    }
    finally:
        crm.close()

    plan_map = defaultdict(list)
    for p in plans:
        plan_map[(str(p[1] or ""),str(p[2] or ""),str(p[3] or ""),int(p[4] or 0),str(p[11] or ""))].append(p)
    def plan_rank(p):
        queue_live = bool(str(p[7] or "") and str(p[7]).lower() in queue_by_rowid)
        info = sent_by_key.get((str(p[2] or ""),str(p[8] or ""))) if str(p[8] or "") else None
        info_live = bool(info and str(info.get("status") or "").lower() in ("waitsend","sending","sendsuccess"))
        active = str(p[6] or "") in ("enqueued","duplicate_skipped")
        return (queue_live, info_live, active, p[12] or datetime.min, str(p[0]))

    records = []
    for r in affected:
        key = (str(r[3] or ""),str(r[4] or ""),str(r[5] or ""),int(r[6] or 0),str(r[11] or ""))
        candidates = sorted(plan_map.get(key, []), key=plan_rank, reverse=True)
        plan = candidates[0] if candidates else None
        truth = None
        if plan:
            truth = queue_by_rowid.get(str(plan[7] or "").lower()) or sent_by_key.get((str(plan[2] or ""), str(plan[8] or "")))
        records.append({
            "item_id": str(r[0]), "run_id": str(r[1] or ""), "contact_id": str(r[2] or ""),
            "customer_id": str(r[3] or ""), "staff_id": str(r[4] or ""), "scenario": str(r[5] or ""),
            "suite_step": int(r[6] or 0), "local_plan_date": r[7].isoformat() if r[7] else None,
            "local_plan_time": str(r[8] or ""), "local_status": str(r[9] or ""),
            "interval_days_csv": str(r[10] or ""),
            "send_plan_id": str(plan[0]) if plan else None,
            "send_plan_time": plan[5].isoformat() if plan and plan[5] else None,
            "send_plan_status": str(plan[6] or "") if plan else None,
            "spqueue_rowid": str(plan[7] or "") if plan else None,
            "crm_send_id": str(plan[8] or "") if plan else None,
            "cached_crm_status": str(plan[9] or "") if plan else None,
            "cached_fact_time": plan[10].isoformat() if plan and plan[10] else None,
            "crm_truth": truth,
        })

    suite_keys = {(x["run_id"], x["contact_id"], x["scenario"]) for x in records}
    summary = {
        "generated_at": datetime.now().isoformat(), "read_only": True, "staff_filter": args.staff or None,
        "active_items_checked": len(rows), "affected_suites": len(suite_keys), "affected_items": len(records),
        "crm_waitsend_items": sum(1 for x in records if (x.get("crm_truth") or {}).get("status") == "WaitSend"),
        "crm_send_success_items": sum(1 for x in records if (x.get("crm_truth") or {}).get("status") == "SendSuccess"),
        "records": records,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, ensure_ascii=False))


if __name__ == "__main__":
    main()