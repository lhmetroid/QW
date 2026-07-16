from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import bindparam, text

from crm_database import CRMSessionLocal
from database import SessionLocal


ROOT = Path(__file__).resolve().parent.parent
DETAIL = ROOT / "logs" / "mail-autosend-duplicate-detail-20260716.json"
OUTPUT = ROOT / "logs" / "mail-autosend-duplicate-cleanup-plan-20260716.json"
CONFIRM = "DELETE-13-DUPLICATE-WAITSEND"


def choose_rows(detail: dict) -> tuple[list[dict], list[dict]]:
    chosen: list[dict] = []
    unresolved: list[dict] = []
    for group in detail.get("details") or []:
        rows = group.get("rows") or []
        matches = [row for row in rows if row.get("matches_local_time")]
        keeper = None
        reason = ""
        if len(rows) == 2 and len(matches) == 1:
            keeper = matches[0]
            reason = "keep_the_only_row_matching_local_schedule"
        elif (len(rows) == 2 and not matches and group.get("same_subject") and group.get("same_body")
              and group.get("same_recipient")
              and len({row.get("crm_plan_time") for row in rows}) == 1):
            synced = [row for row in rows if str(row.get("cached_crm_status") or "").lower() == "waitsend"]
            if len(synced) == 1:
                keeper = synced[0]
                reason = "exact_content_time_duplicate_keep_status_synced_row"
        if keeper is None:
            unresolved.append({"customer_id": group.get("customer_id"), "staff": group.get("staff"),
                               "scenario": group.get("scenario"), "step": group.get("step"),
                               "row_count": len(rows), "local_match_count": len(matches)})
            continue
        stale = [row for row in rows if row.get("rowid") != keeper.get("rowid")]
        if len(stale) != 1:
            unresolved.append({"customer_id": group.get("customer_id"), "staff": group.get("staff"),
                               "scenario": group.get("scenario"), "step": group.get("step"),
                               "reason": "stale_row_count_not_one"})
            continue
        chosen.append({"customer_id": group.get("customer_id"), "staff": group.get("staff"),
                       "scenario": group.get("scenario"), "step": group.get("step"),
                       "keep_rowid": keeper.get("rowid"), "delete_rowid": stale[0].get("rowid"),
                       "reason": reason})
    return chosen, unresolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit/apply safe removal of proven duplicate CRM WaitSend rows")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    detail = json.loads(DETAIL.read_text(encoding="utf-8"))
    chosen, unresolved = choose_rows(detail)
    report = {"generated_at": datetime.now().isoformat(), "apply": bool(args.apply),
              "delete_candidates": len(chosen), "unresolved": unresolved, "rows": chosen}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if unresolved or len(chosen) != 13:
        raise SystemExit(f"refuse: candidates={len(chosen)} unresolved={len(unresolved)}")
    if not args.apply:
        print(json.dumps({"dry_run": True, "delete_candidates": len(chosen), "unresolved": 0}, ensure_ascii=False))
        return
    if args.confirm != CONFIRM:
        raise SystemExit(f"refuse: --confirm {CONFIRM} required")

    all_rowids = [row[key] for row in chosen for key in ("keep_rowid", "delete_rowid")]
    crm = CRMSessionLocal()
    pg = SessionLocal()
    try:
        live = crm.execute(
            text(
                "SELECT CAST(RowId AS NVARCHAR(64)), ISNULL(FolderId,''), ISNULL(MessageType,''), "
                "ISNULL(CAST(UseRange AS NVARCHAR(200)),''), ISNULL(InputerStaffId,'') "
                "FROM spQueueSend WHERE CAST(RowId AS NVARCHAR(64)) IN :rowids"
            ).bindparams(bindparam("rowids", expanding=True)),
            {"rowids": all_rowids},
        ).fetchall()
        live_by_id = {str(row[0]).lower(): row for row in live}
        if len(live_by_id) != len(all_rowids):
            raise RuntimeError("queue changed since audit; not all keeper/delete rows are still WaitSend")
        for item in chosen:
            for key in ("keep_rowid", "delete_rowid"):
                row = live_by_id[str(item[key]).lower()]
                if row[1] != "OutBox" or row[2] != "Email" or "宣传邮件-AI" not in row[3] or row[4] != item["staff"]:
                    raise RuntimeError(f"safety recheck failed for {key}={item[key]}")

        deleted_files = 0
        deleted_queue = 0
        for item in chosen:
            rid = item["delete_rowid"]
            deleted_files += int(crm.execute(text("DELETE FROM spQueueSendFile WHERE QueueRowId=:r"), {"r": rid}).rowcount or 0)
            deleted_queue += int(crm.execute(
                text("DELETE FROM spQueueSend WHERE RowId=:r AND ISNULL(FolderId,'')='OutBox' "
                     "AND MessageType='Email' AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"),
                {"r": rid},
            ).rowcount or 0)
        if deleted_queue != len(chosen):
            raise RuntimeError(f"delete count changed: expected={len(chosen)} actual={deleted_queue}")
        crm.commit()

        pg.execute(
            text("UPDATE mail_customer_suite_send_plan SET crm_send_status='deleted', status_synced_at=now() "
                 "WHERE lower(spqueue_rowid) IN :rowids").bindparams(bindparam("rowids", expanding=True)),
            {"rowids": [row["delete_rowid"].lower() for row in chosen]},
        )
        pg.commit()
        report.update({"applied_at": datetime.now().isoformat(), "deleted_queue": deleted_queue,
                       "deleted_file_rows": deleted_files})
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"applied": True, "deleted_queue": deleted_queue,
                          "deleted_file_rows": deleted_files}, ensure_ascii=False))
    except Exception:
        crm.rollback()
        pg.rollback()
        raise
    finally:
        crm.close()
        pg.close()


if __name__ == "__main__":
    main()
