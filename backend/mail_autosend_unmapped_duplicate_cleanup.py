from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from crm_database import CRMSessionLocal


ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "logs" / "mail-autosend-unmapped-audit-20260716.json"
OUTPUT = ROOT / "logs" / "mail-autosend-unmapped-duplicate-cleanup-20260716.json"
CONFIRM = "DELETE-1-UNMAPPED-DUPLICATE-WAITSEND"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    candidates = []
    for row in audit.get("items") or []:
        plans = row.get("exact_plan_candidates") or []
        if len(plans) == 1 and plans[0].get("body_hash_matches") and plans[0].get("rowid_present"):
            candidates.append({"delete_rowid": row["rowid"], "staff": row["staff"],
                               "keep_plan_id": plans[0]["plan_id"], "customer_id": plans[0]["customer_id"],
                               "scenario": plans[0]["scenario"], "suite_step": plans[0]["suite_step"]})
    if len(candidates) != 1:
        raise RuntimeError(f"expected one exact unmapped duplicate, got {len(candidates)}")
    report = {"generated_at": datetime.now().isoformat(), "apply": bool(args.apply),
              "delete_candidates": len(candidates), "rows": candidates}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.apply:
        print(json.dumps({"dry_run": True, "delete_candidates": 1}, ensure_ascii=False))
        return
    if args.confirm != CONFIRM:
        raise SystemExit(f"--confirm {CONFIRM} required")
    crm = CRMSessionLocal()
    try:
        target = candidates[0]
        row = crm.execute(text(
            "SELECT ISNULL(FolderId,''),ISNULL(MessageType,''),ISNULL(CAST(UseRange AS NVARCHAR(200)),''),"
            "ISNULL(InputerStaffId,'') FROM spQueueSend WHERE RowId=:rowid"
        ), {"rowid": target["delete_rowid"]}).fetchone()
        if not row or row[0] != "OutBox" or row[1] != "Email" or "宣传邮件-AI" not in row[2] or row[3] != target["staff"]:
            raise RuntimeError("CRM duplicate changed since audit; refuse delete")
        deleted_files = int(crm.execute(text("DELETE FROM spQueueSendFile WHERE QueueRowId=:rowid"),
                                        {"rowid": target["delete_rowid"]}).rowcount or 0)
        deleted_queue = int(crm.execute(text(
            "DELETE FROM spQueueSend WHERE RowId=:rowid AND ISNULL(FolderId,'')='OutBox' "
            "AND MessageType='Email' AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
        ), {"rowid": target["delete_rowid"]}).rowcount or 0)
        if deleted_queue != 1:
            raise RuntimeError("duplicate queue row changed during delete")
        crm.commit()
        report.update({"applied_at": datetime.now().isoformat(), "deleted_queue": deleted_queue,
                       "deleted_file_rows": deleted_files})
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"applied": True, "deleted_queue": deleted_queue,
                          "deleted_file_rows": deleted_files}, ensure_ascii=False))
    except Exception:
        crm.rollback()
        raise
    finally:
        crm.close()


if __name__ == "__main__":
    main()
