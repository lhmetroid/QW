from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from crm_database import CRMSessionLocal
from database import SessionLocal


ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "logs" / "mail-autosend-unmapped-audit-20260716.json"
OUTPUT = ROOT / "logs" / "mail-autosend-orphan-link-recovery-20260716.json"
SCOPE = ROOT / "logs" / "mail-autosend-orphan-link-scope-20260716.json"
CONFIRM = "LINK-3-ORPHAN-WAITSEND"


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    targets = []
    for row in audit.get("items") or []:
        local = row.get("exact_local_candidates") or []
        plans = row.get("exact_plan_candidates") or []
        if not plans and len(local) == 1 and local[0].get("body_hash_matches") and local[0].get("status") == "commit_failed":
            targets.append({"rowid": row["rowid"], "staff": row["staff"], "item_id": local[0]["item_id"]})
    if len(targets) != 3:
        raise RuntimeError(f"expected 3 uniquely matched orphan rows, got {len(targets)}")
    if args.apply and args.confirm != CONFIRM:
        raise SystemExit(f"--confirm {CONFIRM} required")
    report = {"generated_at": datetime.now().isoformat(), "apply": bool(args.apply), "target_count": len(targets),
              "targets": targets}
    if not args.apply:
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"dry_run": True, "target_count": len(targets)}, ensure_ascii=False))
        return

    pg = SessionLocal()
    crm = CRMSessionLocal()
    linked = []
    try:
        for target in targets:
            queue = crm.execute(text(
                "SELECT PlanSendTime,ISNULL(CAST(SendId AS NVARCHAR(80)),''),ISNULL(Subject,''),"
                "ISNULL(CAST(EmailContent AS NVARCHAR(MAX)),''),ISNULL(InputerStaffId,''),ISNULL(FolderId,''),"
                "ISNULL(MessageType,''),ISNULL(CAST(UseRange AS NVARCHAR(200)),'') "
                "FROM spQueueSend WHERE RowId=:rowid"
            ), {"rowid": target["rowid"]}).fetchone()
            if not queue or queue[4] != target["staff"] or queue[5] != "OutBox" or queue[6] != "Email" or "宣传邮件-AI" not in queue[7]:
                raise RuntimeError(f"CRM safety recheck failed for rowid={target['rowid']}")
            item = pg.execute(text(
                "SELECT COALESCE(customer_id,contact_id),scenario,suite_step,COALESCE(recipient_email,''),"
                "COALESCE(subject,''),COALESCE(body_html,''),owner_staff_id,status FROM mail_autosend_plan_item "
                "WHERE item_id=:item FOR UPDATE"
            ), {"item": target["item_id"]}).fetchone()
            if not item or item[6] != target["staff"] or item[7] != "commit_failed" or item[4] != queue[2]:
                raise RuntimeError(f"local safety recheck failed for item={target['item_id']}")
            if normalized_text(item[5]) != normalized_text(queue[3]):
                raise RuntimeError(f"body changed since audit for item={target['item_id']}")
            exists = pg.execute(text(
                "SELECT plan_id FROM mail_customer_suite_send_plan WHERE lower(COALESCE(spqueue_rowid,''))=lower(:rowid) "
                "OR (COALESCE(crm_send_id,'')<>'' AND crm_send_id=:sendid AND inputer_staff_id=:staff)"
            ), {"rowid": target["rowid"], "sendid": str(queue[1] or ""), "staff": target["staff"]}).fetchone()
            if exists:
                raise RuntimeError(f"row became linked since audit: rowid={target['rowid']}")
            plan_id = pg.execute(text(
                "INSERT INTO mail_customer_suite_send_plan "
                "(customer_id,scenario,suite_step,to_emails,subject,body_html,body_text,plan_send_time,"
                "inputer_staff_id,recipient_email_key,status,spqueue_rowid,crm_send_id,crm_send_status,status_synced_at,created_at) "
                "VALUES (:customer,:scenario,:step,:email,:subject,:body_html,:body_text,:plan_time,:staff,"
                ":email_key,'enqueued',:rowid,:sendid,'WaitSend',now(),now()) RETURNING plan_id"
            ), {"customer": item[0], "scenario": item[1], "step": int(item[2]), "email": item[3],
                "email_key": str(item[3]).strip().lower(), "subject": item[4], "body_html": item[5],
                "body_text": queue[3], "plan_time": queue[0], "staff": target["staff"],
                "rowid": target["rowid"], "sendid": str(queue[1] or "")}).scalar()
            pg.execute(text(
                "UPDATE mail_autosend_plan_item SET status='sent',crm_send_id=:sendid,plan_date=:day,"
                "plan_time=:time,send_time=:time,commit_error=NULL,committed_at=COALESCE(committed_at,now()),updated_at=now() "
                "WHERE item_id=:item"
            ), {"sendid": str(queue[1] or ""), "day": queue[0].date(), "time": queue[0].strftime("%H:%M"),
                "item": target["item_id"]})
            linked.append({**target, "plan_id": str(plan_id), "crm_plan_time": queue[0].isoformat()})
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        crm.close()
        pg.close()
    report.update({"applied_at": datetime.now().isoformat(), "linked": linked})
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    SCOPE.write_text(json.dumps({"generated_at": datetime.now().isoformat(), "read_only": True,
                                 "records": [{"staff_id": row["staff"], "item_id": row["item_id"]} for row in linked]},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": True, "linked": len(linked)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
