from __future__ import annotations

import argparse
import re
from sqlalchemy import text
from database import SessionLocal
from crm_database import CRMSessionLocal
from mail_ai_stats import _crm_send_info_for_missing_send_id


def main():
    parser = argparse.ArgumentParser(description="按唯一主题/计划分钟/AI用途/发件地址恢复缺失 SendId")
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        plan = db.execute(text(
            "SELECT plan_id, crm_send_id, inputer_staff_id, crm_message_id, crm_send_status, "
            "subject, plan_send_time, sender_email, spqueue_rowid, to_emails "
            "FROM mail_customer_suite_send_plan WHERE plan_id=:pid"
        ), {"pid": args.plan_id}).fetchone()
        if plan is None:
            raise RuntimeError("plan_id 不存在")
        staff = str(plan[2] or "")
        if not re.fullmatch(r"[0-9A-Za-z]{1,8}", staff):
            raise RuntimeError("staff_id 不合法")
        crm = CRMSessionLocal()
        try:
            matched = _crm_send_info_for_missing_send_id(crm, f"spSendInfo{staff}", plan)
        finally:
            crm.close()
        if matched is None:
            print({"matched": False, "applied": False, "plan_id": args.plan_id})
            return
        send_id, status, fact_dt, eml_dir, deleted_at = matched
        final_status = "deleted" if deleted_at is not None else str(status or "")
        if args.apply:
            db.execute(text(
                "UPDATE mail_customer_suite_send_plan SET crm_send_id=:sid, crm_send_status=:st, "
                "crm_fact_send_time=:ft, crm_eml_ftp_dir=:eml, status_synced_at=now() WHERE plan_id=:pid"
            ), {"sid": str(send_id or ""), "st": final_status, "ft": fact_dt,
                "eml": str(eml_dir or ""), "pid": args.plan_id})
            db.commit()
        print({"matched": True, "unique": True, "applied": args.apply, "plan_id": args.plan_id,
               "crm_send_id": str(send_id or ""), "status": final_status,
               "fact_time": fact_dt.isoformat() if fact_dt else None})
    finally:
        db.close()


if __name__ == "__main__":
    main()