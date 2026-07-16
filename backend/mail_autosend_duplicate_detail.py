from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import bindparam, text

from crm_database import CRMSessionLocal
from database import SessionLocal


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "logs" / "mail-autosend-crm-orphan-audit-20260716.json"
OUTPUT = ROOT / "logs" / "mail-autosend-duplicate-detail-20260716.json"


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    duplicate_groups = source.get("duplicate_pending") or []
    rowids = [str(row["rowid"]) for group in duplicate_groups for row in group.get("rows") or []]
    pg = SessionLocal()
    crm = CRMSessionLocal()
    try:
        plans = pg.execute(
            text(
                "SELECT plan_id, customer_id, inputer_staff_id, scenario, suite_step, spqueue_rowid, "
                "status, plan_send_time, created_at, COALESCE(crm_send_id,''), COALESCE(crm_send_status,''), "+
                "md5(COALESCE(subject,'')), md5(COALESCE(body_html,'')), lower(COALESCE(recipient_email_key,'')) "
                "FROM mail_customer_suite_send_plan WHERE lower(spqueue_rowid) IN :rowids"
            ).bindparams(bindparam("rowids", expanding=True)),
            {"rowids": [value.lower() for value in rowids]},
        ).fetchall()
        plan_by_rowid = {str(row[5]).lower(): row for row in plans}
        crm_rows = crm.execute(
            text(
                "SELECT CAST(q.RowId AS NVARCHAR(64)), q.PlanSendTime, q.InputTime, "
                "ISNULL(CAST(q.SendId AS NVARCHAR(80)),''), COUNT(f.RowId) "
                "FROM spQueueSend q LEFT JOIN spQueueSendFile f ON f.QueueRowId=q.RowId "
                "WHERE CAST(q.RowId AS NVARCHAR(64)) IN :rowids GROUP BY q.RowId,q.PlanSendTime,q.InputTime,q.SendId"
            ).bindparams(bindparam("rowids", expanding=True)),
            {"rowids": rowids},
        ).fetchall()
        crm_by_rowid = {str(row[0]).lower(): row for row in crm_rows}

        local_by_key: dict[tuple[str, str, str, int], list[dict]] = defaultdict(list)
        keys = {
            (str(group["customer_id"]), str(group["staff"]), str(group["scenario"]), int(group["step"]))
            for group in duplicate_groups
        }
        for customer_id, staff, scenario, step in keys:
            rows = pg.execute(
                text(
                    "SELECT item_id, status, plan_date, plan_time, created_at FROM mail_autosend_plan_item "
                    "WHERE owner_staff_id=:staff AND scenario=:scenario AND suite_step=:step "
                    "AND (customer_id=:customer OR contact_id=:customer) ORDER BY created_at DESC"
                ),
                {"customer": customer_id, "staff": staff, "scenario": scenario, "step": step},
            ).fetchall()
            for row in rows:
                local_by_key[(customer_id, staff, scenario, step)].append(
                    {"item_id": str(row[0]), "status": str(row[1]),
                     "plan_time": f"{row[2].isoformat()}T{str(row[3])[:5]}",
                     "created_at": row[4].isoformat() if row[4] else None}
                )

        details = []
        for group in duplicate_groups:
            key = (str(group["customer_id"]), str(group["staff"]), str(group["scenario"]), int(group["step"]))
            local_items = local_by_key.get(key, [])
            local_times = {item["plan_time"][:16] for item in local_items if item["status"] != "deleted"}
            rows_out = []
            for raw in group.get("rows") or []:
                rid = str(raw["rowid"])
                plan = plan_by_rowid.get(rid.lower())
                crm_row = crm_by_rowid.get(rid.lower())
                crm_time = crm_row[1].isoformat() if crm_row and crm_row[1] else None
                rows_out.append({
                    "rowid": rid,
                    "crm_plan_time": crm_time,
                    "matches_local_time": bool(crm_time and crm_time[:16] in local_times),
                    "crm_input_time": crm_row[2].isoformat() if crm_row and crm_row[2] else None,
                    "send_id_present": bool(crm_row and crm_row[3]),
                    "file_rows": int(crm_row[4] or 0) if crm_row else 0,
                    "plan_id": str(plan[0]) if plan else None,
                    "plan_status": str(plan[6]) if plan else None,
                    "plan_created_at": plan[8].isoformat() if plan and plan[8] else None,
                    "cached_crm_status": str(plan[10]) if plan else None,
                    "subject_hash": str(plan[11]) if plan else None,
                    "body_hash": str(plan[12]) if plan else None,
                    "recipient_key_hash": str(plan[13]) if plan else None,
                })
            details.append({"customer_id": key[0], "staff": key[1], "scenario": key[2], "step": key[3],
                            "same_subject": len({row["subject_hash"] for row in rows_out}) == 1,
                            "same_body": len({row["body_hash"] for row in rows_out}) == 1,
                            "same_recipient": len({row["recipient_key_hash"] for row in rows_out}) == 1,
                            "local_items": local_items, "rows": rows_out})
        result = {"generated_at": datetime.now().isoformat(), "read_only": True,
                  "duplicate_groups": len(details), "details": details}
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"duplicate_groups": len(details), "rows": sum(len(x["rows"]) for x in details),
                          "groups_with_one_local_match": sum(sum(1 for r in x["rows"] if r["matches_local_time"]) == 1 for x in details),
                          "groups_without_local_match": sum(not any(r["matches_local_time"] for r in x["rows"]) for x in details)},
                         ensure_ascii=False))
    finally:
        crm.close()
        pg.close()


if __name__ == "__main__":
    main()
