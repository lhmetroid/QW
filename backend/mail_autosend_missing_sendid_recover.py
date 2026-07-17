from __future__ import annotations

import argparse
import re
from sqlalchemy import text
from database import SessionLocal
from crm_database import CRMSessionLocal
from mail_ai_stats import _crm_send_info_for_missing_send_id


def main():
    parser = argparse.ArgumentParser(description="以 CRM RowId 为主恢复错配/缺失 SendId；仅无队列行时才做唯一分表匹配")
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        plan = db.execute(text(
            "SELECT plan_id, crm_send_id, inputer_staff_id, crm_message_id, crm_send_status, "
            "subject, plan_send_time, sender_email, spqueue_rowid, to_emails,customer_id,scenario,suite_step,"
            "lower(COALESCE(recipient_email_key,'')) FROM mail_customer_suite_send_plan WHERE plan_id=:pid"
        ), {"pid": args.plan_id}).fetchone()
        if plan is None:
            raise RuntimeError("plan_id 不存在")
        staff = str(plan[2] or "")
        if not re.fullmatch(r"[0-9A-Za-z]{1,8}", staff):
            raise RuntimeError("staff_id 不合法")
        crm = CRMSessionLocal()
        try:
            queue = None
            rowid = str(plan[8] or "")
            if rowid:
                queue = crm.execute(text(
                    "SELECT ISNULL(CAST(SendId AS NVARCHAR(80)),''),PlanSendTime,ISNULL(InputerStaffId,''),"
                    "ISNULL(FolderId,''),ISNULL(CAST(UseRange AS NVARCHAR(200)),'') FROM spQueueSend "
                    "WHERE RowId=:rid AND MessageType='Email'"
                ), {"rid":rowid}).fetchone()
            if queue:
                if str(queue[2] or "") != staff or str(queue[3] or "") != "OutBox" or "宣传邮件-AI" not in str(queue[4] or ""):
                    raise RuntimeError("CRM RowId 安全校验失败")
                send_id, plan_dt = str(queue[0] or ""), queue[1]
                if not send_id:
                    raise RuntimeError("CRM 队列行仍无 SendId")
                final_status, fact_dt, eml_dir, source = "WaitSend", None, "", "queue_rowid"
            else:
                matched = _crm_send_info_for_missing_send_id(crm, f"spSendInfo{staff}", plan)
                if matched is None:
                    print({"matched":False,"applied":False,"plan_id":args.plan_id})
                    return
                send_id, status, fact_dt, eml_dir, deleted_at = matched
                send_id = str(send_id or "")
                final_status = "deleted" if deleted_at is not None else str(status or "")
                plan_dt, source = plan[6], "unique_send_info"
        finally:
            crm.close()
        if args.apply:
            db.execute(text(
                "UPDATE mail_customer_suite_send_plan SET crm_send_id=:sid,crm_send_status=:st,"
                "plan_send_time=COALESCE(:pt,plan_send_time),crm_fact_send_time=:ft,crm_eml_ftp_dir=:eml,"
                "status_synced_at=now() WHERE plan_id=:pid"
            ), {"sid":send_id,"st":final_status,"pt":plan_dt,"ft":fact_dt,"eml":str(eml_dir or ""),"pid":args.plan_id})
            if plan_dt is not None:
                db.execute(text(
                    "UPDATE mail_autosend_plan_item SET crm_send_id=:sid,status='sent',plan_date=:day,"
                    "plan_time=:tm,send_time=:tm,updated_at=now() WHERE COALESCE(customer_id,contact_id)=:customer "
                    "AND owner_staff_id=:staff AND scenario=:scenario AND suite_step=:step "
                    "AND lower(COALESCE(recipient_email,''))=:recipient"
                ), {"sid":send_id,"day":plan_dt.date(),"tm":plan_dt.strftime("%H:%M"),"customer":str(plan[10] or ""),
                    "staff":staff,"scenario":str(plan[11] or ""),"step":int(plan[12] or 0),"recipient":str(plan[13] or "")})
            db.commit()
        print({"matched":True,"unique":True,"applied":args.apply,"plan_id":args.plan_id,
               "source":source,"crm_send_id":send_id,"status":final_status,
               "plan_time":plan_dt.isoformat() if plan_dt else None})
    finally:
        db.close()

if __name__ == "__main__":
    main()