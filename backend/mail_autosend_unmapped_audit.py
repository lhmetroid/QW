from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from crm_database import CRMSessionLocal
from database import SessionLocal


OUT = Path(__file__).resolve().parent.parent / "logs" / "mail-autosend-unmapped-audit-20260716.json"


def email_key(value: str) -> str:
    match = re.search(r"([^<>\s,;]+@[^<>\s,;]+)", str(value or ""))
    return match.group(1).lower() if match else ""


def normalized_text(value: str) -> str:
    text_value = re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))
    return re.sub(r"\s+", " ", text_value).strip()


def main() -> None:
    pg = SessionLocal()
    crm = CRMSessionLocal()
    try:
        plans = pg.execute(text(
            "SELECT plan_id,inputer_staff_id,COALESCE(spqueue_rowid,''),COALESCE(crm_send_id,''),"
            "customer_id,scenario,suite_step,plan_send_time,COALESCE(crm_send_status,'') "
            "FROM mail_customer_suite_send_plan WHERE status IN ('enqueued','duplicate_skipped')"
        )).fetchall()
        by_row = {str(row[2] or "").lower(): row for row in plans if row[2]}
        by_send = {(str(row[1] or ""), str(row[3] or "")): row for row in plans if row[3]}
        queue = crm.execute(text(
            "SELECT CAST(RowId AS NVARCHAR(64)),InputerStaffId,ISNULL(CAST(SendId AS NVARCHAR(80)),''),PlanSendTime, "
            "ISNULL(Subject,''),ISNULL(CAST(Receiver AS NVARCHAR(MAX)),''),ISNULL(CAST(EmailContent AS NVARCHAR(MAX)),'') "
            "FROM spQueueSend WHERE MessageType='Email' AND PlanSendTime>=CONVERT(date,GETDATE()) "
            "AND ISNULL(UseRange,'') LIKE '%宣传邮件-AI%'"
        )).fetchall()
        all_plans = pg.execute(text(
            "SELECT plan_id,inputer_staff_id,COALESCE(to_emails,''),COALESCE(subject,''),COALESCE(body_text,''),"
            "status,plan_send_time,COALESCE(spqueue_rowid,''),COALESCE(crm_send_id,''),customer_id,scenario,suite_step "
            "FROM mail_customer_suite_send_plan"
        )).fetchall()
        local_items = pg.execute(text(
            "SELECT item_id,owner_staff_id,COALESCE(recipient_email,''),COALESCE(subject,''),status,plan_date,plan_time,"
            "COALESCE(customer_id,contact_id),scenario,suite_step,COALESCE(body_html,'') FROM mail_autosend_plan_item"
        )).fetchall()
        items = []
        for rowid, staff, send_id, plan_time, subject, receiver, body_text in queue:
            if str(rowid).lower() in by_row:
                continue
            plan = by_send.get((str(staff or ""), str(send_id or ""))) if send_id else None
            recipient = email_key(receiver)
            plan_candidates = [candidate for candidate in all_plans if str(candidate[1] or "") == str(staff or "")
                               and email_key(candidate[2]) == recipient and str(candidate[3] or "") == str(subject or "")]
            item_candidates = [candidate for candidate in local_items if str(candidate[1] or "") == str(staff or "")
                               and email_key(candidate[2]) == recipient and str(candidate[3] or "") == str(subject or "")]
            crm_body_hash = hashlib.md5(str(body_text or "").encode("utf-8", "ignore")).hexdigest()
            items.append({"rowid": str(rowid), "staff": str(staff or ""),
                          "send_id_present": bool(send_id), "plan_time": plan_time.isoformat() if plan_time else None,
                          "matched_by_send_id": bool(plan), "plan_id": str(plan[0]) if plan else None,
                          "local_plan_time": plan[7].isoformat() if plan and plan[7] else None,
                          "cached_status": str(plan[8] or "") if plan else None,
                          "exact_plan_candidates": [{"plan_id": str(candidate[0]), "status": str(candidate[5] or ""),
                              "plan_time": candidate[6].isoformat() if candidate[6] else None,
                              "rowid_present": bool(candidate[7]), "send_id_present": bool(candidate[8]),
                              "customer_id": str(candidate[9] or ""), "scenario": str(candidate[10] or ""),
                              "suite_step": int(candidate[11] or 0),
                              "body_hash_matches": hashlib.md5(str(candidate[4] or "").encode("utf-8", "ignore")).hexdigest() == crm_body_hash}
                              for candidate in plan_candidates],
                          "exact_local_candidates": [{"item_id": str(candidate[0]), "status": str(candidate[4] or ""),
                              "plan_time": f"{candidate[5].isoformat()}T{str(candidate[6])[:5]}",
                              "customer_id": str(candidate[7] or ""), "scenario": str(candidate[8] or ""),
                              "suite_step": int(candidate[9] or 0),
                              "body_hash_matches": hashlib.md5(normalized_text(candidate[10]).encode("utf-8", "ignore")).hexdigest() ==
                                  hashlib.md5(normalized_text(body_text).encode("utf-8", "ignore")).hexdigest()}
                              for candidate in item_candidates]})
        result = {"generated_at": datetime.now().isoformat(), "read_only": True,
                  "unmapped_by_rowid": len(items),
                  "matched_by_send_id": sum(bool(item["matched_by_send_id"]) for item in items),
                  "truly_unmapped": sum(not item["matched_by_send_id"] for item in items),
                  "items": items}
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: result[key] for key in ("unmapped_by_rowid", "matched_by_send_id", "truly_unmapped")},
                         ensure_ascii=False))
    finally:
        crm.close()
        pg.close()


if __name__ == "__main__":
    main()