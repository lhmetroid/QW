from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from sqlalchemy import bindparam, text
from database import SessionLocal
from crm_database import CRMSessionLocal

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "logs" / "mail-autosend-cross-table-pending-audit-20260716.json"
OUT = ROOT / "logs" / "mail-autosend-recipient-suite-cleanup-20260717.json"
CONFIRM = "CANCEL-6-DUPLICATE-RECIPIENT-SUITES"
ACTIVE_LOCAL = ("planned","queued","drafting","drafted","commit_queued","committing","commit_failed","sent")

def _business_score(business):
    sent_times = []
    for plan in business.get("plans") or []:
        for history in plan.get("history") or []:
            if str(history.get("status") or "").lower() == "sendsuccess":
                value = history.get("fact_time") or history.get("plan_time")
                if value:
                    sent_times.append(datetime.fromisoformat(value))
    created = [datetime.fromisoformat(p["created_at"]) for p in business.get("plans") or [] if p.get("created_at")]
    first_sent = min(sent_times) if sent_times else datetime.max
    first_created = min(created) if created else datetime.max
    return (-len(sent_times), first_sent, first_created, business["business_key_hash"])

def build_decisions(audit):
    suites = audit.get("recipient_duplicate_suites") or []
    if len(suites) != 6:
        raise RuntimeError(f"expected 6 duplicate recipient suites, got {len(suites)}")
    decisions = []
    for suite in suites:
        businesses = suite.get("businesses") or []
        if len(businesses) != 2:
            raise RuntimeError(f"ambiguous suite {suite.get('recipient_key_hash')}")
        ordered = sorted(businesses, key=_business_score)
        keeper, loser = ordered[0], ordered[1]
        decisions.append({
            "staff":suite["staff"],"scenario":suite["scenario"],
            "recipient_key_hash":suite["recipient_key_hash"],
            "keeper_business_hash":keeper["business_key_hash"],
            "loser_business_hash":loser["business_key_hash"],
            "keeper_plan_ids":[p["plan_id"] for p in keeper.get("plans") or []],
            "loser_plan_ids":[p["plan_id"] for p in loser.get("plans") or []],
        })
    return decisions

def cleanup_orphan_info(audit, apply_changes: bool, confirm: str):
    rows = audit.get("unmapped_physical_pending") or []
    if len(rows) != 6 or any(str(row.get("source")) != "send_info" for row in rows):
        raise RuntimeError(f"expected 6 send_info orphans, got {len(rows)}")
    targets = {(str(row["staff"]),str(row["send_id_hash"])) for row in rows}
    crm = CRMSessionLocal(); pg = SessionLocal()
    try:
        resolved = []
        for staff, wanted_hash in sorted(targets):
            if not staff.isalnum() or len(staff) > 8:
                raise RuntimeError("invalid staff")
            found = crm.execute(text(
                f"SELECT ISNULL(CAST(SendId AS NVARCHAR(80)),''),ISNULL(Status,''),DeleteTime,"
                f"ISNULL(CAST(UseRange AS NVARCHAR(200)),'') FROM [spSendInfo{staff}] "
                f"WHERE MessageType='Email' AND Status='WaitSend' AND DeleteTime IS NULL "
                f"AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
            )).fetchall()
            matches = []
            for send_id, status, deleted, use_range in found:
                digest = hashlib.sha256(f"{staff}|{send_id}".encode("utf-8")).hexdigest()[:16]
                if digest == wanted_hash:
                    matches.append(str(send_id))
            if len(matches) != 1:
                raise RuntimeError(f"orphan hash is not unique staff={staff}")
            send_id = matches[0]
            active = int(pg.execute(text(
                "SELECT COUNT(*) FROM mail_customer_suite_send_plan WHERE inputer_staff_id=:staff "
                "AND crm_send_id=:sid AND status IN ('enqueued','duplicate_skipped') "
                "AND lower(COALESCE(crm_send_status,''))<>'deleted'"
            ), {"staff":staff,"sid":send_id}).scalar() or 0)
            if active:
                raise RuntimeError("orphan gained an active plan; refuse cleanup")
            resolved.append({"staff":staff,"send_id":send_id,"send_id_hash":wanted_hash})
        report = {"generated_at":datetime.now().isoformat(),"applied":bool(apply_changes),
                  "orphan_info_count":len(resolved),"targets":[{"staff":x["staff"],"send_id_hash":x["send_id_hash"]} for x in resolved]}
        orphan_out = ROOT / "logs" / "mail-autosend-orphan-send-info-cleanup-20260717.json"
        orphan_out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        if not apply_changes:
            print(json.dumps({k:v for k,v in report.items() if k!="targets"},ensure_ascii=False)); return
        if confirm != "DELETE-6-ORPHAN-WAITSEND":
            raise SystemExit("--confirm DELETE-6-ORPHAN-WAITSEND required")
        changed = 0
        for row in resolved:
            changed += int(crm.execute(text(
                f"UPDATE [spSendInfo{row['staff']}] SET DeleteTime=GETDATE() WHERE SendId=:sid "
                f"AND MessageType='Email' AND Status='WaitSend' AND DeleteTime IS NULL "
                f"AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
            ), {"sid":row["send_id"]}).rowcount or 0)
        if changed != len(resolved):
            raise RuntimeError("orphan rows changed during cleanup")
        crm.commit(); report.update({"applied_at":datetime.now().isoformat(),"logically_deleted":changed})
        orphan_out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k!="targets"},ensure_ascii=False))
    except Exception:
        crm.rollback(); raise
    finally:
        crm.close(); pg.close()
def cleanup_shared_physical_refs(audit, apply_changes: bool, confirm: str):
    groups = audit.get("shared_physical_references") or []
    if len(groups) != 25:
        raise RuntimeError(f"expected 25 shared physical references, got {len(groups)}")
    decisions = []
    for group in groups:
        rows = group.get("rows") or []
        keepers = [row for row in rows if row.get("source") == "both"]
        if (len(rows) != 2 or len(keepers) != 1
                or len({row.get("business_key_hash") for row in rows}) != 1
                or len({row.get("content_hash") for row in rows}) != 1
                or len({row.get("queue_receiver_hash") for row in rows}) != 1
                or len({str(row.get("rowid") or "").lower() for row in rows}) != 1):
            raise RuntimeError("ambiguous shared physical reference")
        keeper = keepers[0]
        loser = next(row for row in rows if row["plan_id"] != keeper["plan_id"])
        decisions.append({"physical_key_hash":group["physical_key_hash"],"keeper":keeper,"loser":loser})
    pg = SessionLocal(); crm = CRMSessionLocal()
    try:
        ids = [row[side]["plan_id"] for row in decisions for side in ("keeper","loser")]
        plans = pg.execute(text(
            "SELECT plan_id,customer_id,inputer_staff_id,scenario,suite_step,lower(COALESCE(recipient_email_key,'')),"
            "COALESCE(spqueue_rowid,''),COALESCE(crm_send_id,''),status,"
            "md5(COALESCE(subject,'')||E'\\n'||COALESCE(body_html,'')) FROM mail_customer_suite_send_plan WHERE plan_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)), {"ids":ids}).fetchall()
        by_id = {str(row[0]):row for row in plans}
        if len(by_id) != len(ids):
            raise RuntimeError("shared reference plan rows changed")
        resolved=[]
        for decision in decisions:
            keeper=by_id[decision["keeper"]["plan_id"]]; loser=by_id[decision["loser"]["plan_id"]]
            if ((str(keeper[1]),str(keeper[2]),str(keeper[3]),int(keeper[4]),str(keeper[5])) !=
                (str(loser[1]),str(loser[2]),str(loser[3]),int(loser[4]),str(loser[5]))
                or str(keeper[6]).lower() != str(loser[6]).lower() or keeper[9] != loser[9]):
                raise RuntimeError("shared reference identity/content changed")
            staff=str(keeper[2]); rowid=str(keeper[6])
            queue=crm.execute(text(
                "SELECT CAST(RowId AS NVARCHAR(64)),ISNULL(CAST(SendId AS NVARCHAR(80)),''),PlanSendTime,"
                "ISNULL(InputerStaffId,''),ISNULL(FolderId,''),ISNULL(CAST(UseRange AS NVARCHAR(200)),'') "
                "FROM spQueueSend WHERE RowId=:rid AND MessageType='Email'"
            ),{"rid":rowid}).fetchone()
            if not queue or str(queue[3])!=staff or str(queue[4])!="OutBox" or "宣传邮件-AI" not in str(queue[5]):
                raise RuntimeError("shared reference queue safety check failed")
            resolved.append({"keeper_id":str(keeper[0]),"loser_id":str(loser[0]),"customer":str(keeper[1]),
                             "staff":staff,"scenario":str(keeper[3]),"step":int(keeper[4]),"recipient":str(keeper[5]),
                             "rowid":str(queue[0]),"send_id":str(queue[1]),"plan_dt":queue[2],
                             "physical_key_hash":decision["physical_key_hash"]})
        report={"generated_at":datetime.now().isoformat(),"applied":bool(apply_changes),
                "shared_reference_groups":len(resolved),"cancelled_shadow_plans":len(resolved),
                "crm_queue_rows_changed":0,"content_changed":False,
                "targets":[{"physical_key_hash":x["physical_key_hash"],"keeper_id":x["keeper_id"],"loser_id":x["loser_id"]} for x in resolved]}
        out=ROOT / "logs" / "mail-autosend-shared-physical-ref-cleanup-20260717.json"
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        if not apply_changes:
            print(json.dumps({k:v for k,v in report.items() if k!="targets"},ensure_ascii=False)); return
        if confirm != "CANCEL-25-SHARED-PHYSICAL-REFS":
            raise SystemExit("--confirm CANCEL-25-SHARED-PHYSICAL-REFS required")
        for row in resolved:
            pg.execute(text("UPDATE mail_customer_suite_send_plan SET status='cancelled',crm_send_status='deleted',status_synced_at=now() WHERE plan_id=:pid"),{"pid":row["loser_id"]})
            pg.execute(text("UPDATE mail_customer_suite_send_plan SET status='enqueued',spqueue_rowid=:rid,crm_send_id=:sid,plan_send_time=:dt,crm_send_status='WaitSend',status_synced_at=now() WHERE plan_id=:pid"),
                       {"rid":row["rowid"],"sid":row["send_id"],"dt":row["plan_dt"],"pid":row["keeper_id"]})
            pg.execute(text("UPDATE mail_autosend_plan_item SET plan_date=:day,plan_time=:tm,send_time=:tm,status='sent',updated_at=now() WHERE COALESCE(customer_id,contact_id)=:customer AND owner_staff_id=:staff AND scenario=:scenario AND suite_step=:step AND lower(COALESCE(recipient_email,''))=:recipient AND status IN :statuses").bindparams(bindparam("statuses",expanding=True)),
                       {"day":row["plan_dt"].date(),"tm":row["plan_dt"].strftime("%H:%M"),"customer":row["customer"],"staff":row["staff"],"scenario":row["scenario"],"step":row["step"],"recipient":row["recipient"],"statuses":list(ACTIVE_LOCAL)})
        pg.commit()
        report.update({"applied_at":datetime.now().isoformat(),"crm_queue_rows_changed":0})
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k!="targets"},ensure_ascii=False))
    except Exception:
        pg.rollback(); raise
    finally:
        crm.close(); pg.close()
def main():
    parser = argparse.ArgumentParser(description="取消同销售/同邮箱/同场景的重复待发套装；默认只预演")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--cleanup-orphan-info", action="store_true")
    parser.add_argument("--cleanup-shared-refs", action="store_true")
    args = parser.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if not audit.get("read_only"):
        raise RuntimeError("audit is not read-only")
    if args.cleanup_orphan_info:
        cleanup_orphan_info(audit, bool(args.apply), args.confirm)
        return
    if args.cleanup_shared_refs:
        cleanup_shared_physical_refs(audit, bool(args.apply), args.confirm)
        return
    decisions = build_decisions(audit)
    all_plan_ids = sorted({pid for d in decisions for pid in d["keeper_plan_ids"] + d["loser_plan_ids"]})
    pg = SessionLocal(); crm = CRMSessionLocal()
    try:
        plan_rows = pg.execute(text(
            "SELECT plan_id,customer_id,inputer_staff_id,scenario,suite_step,lower(COALESCE(recipient_email_key,'')),"
            "COALESCE(spqueue_rowid,''),COALESCE(crm_send_id,''),status "
            "FROM mail_customer_suite_send_plan WHERE plan_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)), {"ids":all_plan_ids}).fetchall()
        by_id = {str(row[0]):row for row in plan_rows}
        if len(by_id) != len(all_plan_ids):
            raise RuntimeError("send plan rows changed; refuse cleanup")
        queue_deletes = []
        info_deletes = []
        loser_rows = []
        keeper_send_ids = {str(by_id[pid][7] or "") for d in decisions for pid in d["keeper_plan_ids"] if str(by_id[pid][7] or "")}
        for decision in decisions:
            for pid in decision["loser_plan_ids"]:
                row = by_id[pid]
                staff, rowid, send_id = str(row[2] or ""), str(row[6] or ""), str(row[7] or "")
                if staff != decision["staff"] or str(row[3] or "") != decision["scenario"]:
                    raise RuntimeError("audit/business identity changed; refuse cleanup")
                queue = None
                if rowid:
                    queue = crm.execute(text(
                        "SELECT CAST(RowId AS NVARCHAR(64)),ISNULL(CAST(SendId AS NVARCHAR(80)),''),"
                        "ISNULL(InputerStaffId,''),ISNULL(FolderId,''),ISNULL(CAST(UseRange AS NVARCHAR(200)),'') "
                        "FROM spQueueSend WHERE RowId=:rid AND MessageType='Email'"
                    ), {"rid":rowid}).fetchone()
                    if queue and (str(queue[2] or "") != staff or str(queue[3] or "") != "OutBox" or "宣传邮件-AI" not in str(queue[4] or "")):
                        raise RuntimeError("queue safety check failed")
                info = None
                if send_id:
                    info = crm.execute(text(
                        f"SELECT ISNULL(Status,''),DeleteTime,ISNULL(CAST(UseRange AS NVARCHAR(200)),'') "
                        f"FROM [spSendInfo{staff}] WHERE SendId=:sid AND MessageType='Email' "
                        f"ORDER BY CASE ISNULL(Status,'') WHEN 'WaitSend' THEN 0 WHEN 'Sending' THEN 1 "
                        f"WHEN 'SendSuccess' THEN 2 ELSE 3 END, CASE WHEN DeleteTime IS NULL THEN 0 ELSE 1 END"
                    ), {"sid":send_id}).fetchone()
                    if not queue and info and info[1] is None and str(info[0] or "").lower() == "sendsuccess":
                        continue  # 已发送历史只保留事实，不取消、不改写
                if queue:
                    queue_deletes.append({"plan_id":pid,"staff":staff,"rowid":rowid,"send_id":str(queue[1] or send_id)})
                if info and info[1] is None and str(info[0] or "").lower() in ("waitsend","sending") and send_id not in keeper_send_ids:
                    if "宣传邮件-AI" not in str(info[2] or ""):
                        raise RuntimeError("send info safety check failed")
                    info_deletes.append({"plan_id":pid,"staff":staff,"send_id":send_id})
                loser_rows.append(row)
        queue_deletes = list({x["rowid"].lower():x for x in queue_deletes}.values())
        info_deletes = list({(x["staff"],x["send_id"]):x for x in info_deletes}.values())
        report = {
            "generated_at":datetime.now().isoformat(),"applied":bool(args.apply),
            "suite_count":len(decisions),"loser_plan_count":len(loser_rows),
            "queue_delete_count":len(queue_deletes),"info_logical_delete_count":len(info_deletes),
            "decisions":decisions,
        }
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        if not args.apply:
            print(json.dumps({k:v for k,v in report.items() if k!="decisions"},ensure_ascii=False))
            return
        if args.confirm != CONFIRM:
            raise SystemExit(f"--confirm {CONFIRM} required")
        deleted_files = deleted_queue = deleted_info = 0
        for row in queue_deletes:
            deleted_files += int(crm.execute(text("DELETE FROM spQueueSendFile WHERE QueueRowId=:rid"),{"rid":row["rowid"]}).rowcount or 0)
            count = int(crm.execute(text(
                "DELETE FROM spQueueSend WHERE RowId=:rid AND MessageType='Email' AND ISNULL(FolderId,'')='OutBox' "
                "AND ISNULL(InputerStaffId,'')=:staff AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
            ),{"rid":row["rowid"],"staff":row["staff"]}).rowcount or 0)
            if count != 1:
                raise RuntimeError("queue changed during cleanup")
            deleted_queue += count
        for row in info_deletes:
            count = int(crm.execute(text(
                f"UPDATE [spSendInfo{row['staff']}] SET DeleteTime=GETDATE() WHERE SendId=:sid "
                f"AND MessageType='Email' AND Status IN ('WaitSend','Sending') AND DeleteTime IS NULL "
                f"AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
            ),{"sid":row["send_id"]}).rowcount or 0)
            if count != 1:
                raise RuntimeError("send info changed during cleanup")
            deleted_info += count
        crm.commit()
        loser_ids = [str(row[0]) for row in loser_rows]
        pg.execute(text(
            "UPDATE mail_customer_suite_send_plan SET status='cancelled',crm_send_status='deleted',status_synced_at=now() "
            "WHERE plan_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)), {"ids":loser_ids})
        local_cancelled = 0
        for row in loser_rows:
            local_cancelled += int(pg.execute(text(
                "UPDATE mail_autosend_plan_item SET status='cancelled',commit_error='重复联系人套装已取消',updated_at=now() "
                "WHERE COALESCE(customer_id,contact_id)=:customer AND owner_staff_id=:staff AND scenario=:scenario "
                "AND suite_step=:step AND lower(COALESCE(recipient_email,''))=:recipient AND status IN :statuses"
            ).bindparams(bindparam("statuses", expanding=True)), {
                "customer":str(row[1] or ""),"staff":str(row[2] or ""),"scenario":str(row[3] or ""),
                "step":int(row[4] or 0),"recipient":str(row[5] or ""),"statuses":list(ACTIVE_LOCAL),
            }).rowcount or 0)
        pg.commit()
        report.update({"applied_at":datetime.now().isoformat(),"deleted_queue":deleted_queue,
                       "deleted_queue_files":deleted_files,"logically_deleted_send_info":deleted_info,
                       "local_items_cancelled":local_cancelled})
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k!="decisions"},ensure_ascii=False))
    except Exception:
        crm.rollback(); pg.rollback(); raise
    finally:
        crm.close(); pg.close()

if __name__ == "__main__":
    main()