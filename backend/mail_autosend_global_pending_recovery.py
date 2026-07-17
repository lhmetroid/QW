from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import bindparam, text
from database import SessionLocal
from crm_database import CRMSessionLocal
from mail_autosend_recovery_runner import NS, get_config, serialize_config

ROOT = Path(__file__).resolve().parent.parent
OUT_DEFAULT = ROOT / "logs" / "mail-autosend-global-pending-preview-20260717.json"
CONFIRM = "APPLY-ALL-PENDING-TIME-ONLY"
INTERVALS = [1,10,19,25]

def content_hashes(db, plan_ids):
    out = {}
    for pos in range(0,len(plan_ids),500):
        chunk=plan_ids[pos:pos+500]
        rows=db.execute(text("SELECT plan_id,md5(COALESCE(subject,'')||E'\\n'||COALESCE(body_html,'')||E'\\n'||COALESCE(body_text,'')) FROM mail_customer_suite_send_plan WHERE plan_id IN :ids").bindparams(bindparam("ids",expanding=True)),{"ids":chunk}).fetchall()
        out.update({str(a):b for a,b in rows})
    return out

def batches(values,size=200):
    values=list(values)
    for pos in range(0,len(values),size): yield values[pos:pos+size]

def main():
    parser=argparse.ArgumentParser(description="全销售CRM待发统一槽位恢复；默认只预演")
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--confirm",default="")
    parser.add_argument("--output",default=str(OUT_DEFAULT))
    args=parser.parse_args()
    if args.apply and args.confirm!=CONFIRM: raise SystemExit(f"--confirm {CONFIRM} required")
    db=SessionLocal(); crm=CRMSessionLocal()
    try:
        cfg=serialize_config(get_config(db))
        if int(cfg.get("daily_cap") or 0)!=50: raise RuntimeError("daily_cap is not 50")
        plans=db.execute(text(
            "SELECT plan_id,customer_id,inputer_staff_id,scenario,suite_step,lower(COALESCE(recipient_email_key,'')),"
            "COALESCE(spqueue_rowid,''),COALESCE(crm_send_id,''),plan_send_time,status "
            "FROM mail_customer_suite_send_plan WHERE status IN ('enqueued','duplicate_skipped')"
        )).fetchall()
        by_staff=defaultdict(list)
        for p in plans:
            staff=str(p[2] or "")
            if re.fullmatch(r"[0-9A-Za-z]{1,8}",staff): by_staff[staff].append(p)
        live=[]; sent_anchors={}; shadow_plans=[]
        for staff,staff_plans in by_staff.items():
            queue_by_row={}
            rowids=sorted({str(p[6] or "") for p in staff_plans if p[6]})
            for chunk in batches(rowids):
                params={f"r{i}":v for i,v in enumerate(chunk)}; marks=",".join(f":r{i}" for i in range(len(chunk)))
                rows=crm.execute(text(f"SELECT CAST(RowId AS NVARCHAR(64)),ISNULL(CAST(SendId AS NVARCHAR(80)),''),PlanSendTime FROM spQueueSend WHERE CAST(RowId AS NVARCHAR(64)) IN ({marks}) AND MessageType='Email' AND ISNULL(InputerStaffId,'')=:staff AND ISNULL(FolderId,'')='OutBox' AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"),{**params,"staff":staff}).fetchall()
                for rowid,sendid,dt in rows: queue_by_row[str(rowid).lower()]={"rowid":str(rowid),"sendid":str(sendid or ""),"dt":dt}
            queue_by_send=defaultdict(list)
            for queue_row in queue_by_row.values():
                if queue_row["sendid"]: queue_by_send[queue_row["sendid"]].append(queue_row)
            sendids=sorted({str(p[7] or "") for p in staff_plans if p[7]})
            info_wait={}; info_sent={}
            for chunk in batches(sendids):
                params={f"s{i}":v for i,v in enumerate(chunk)}; marks=",".join(f":s{i}" for i in range(len(chunk)))
                rows=crm.execute(text(f"SELECT ISNULL(CAST(SendId AS NVARCHAR(80)),''),ISNULL(Status,''),FactSendTime,PlanSendTime,DeleteTime FROM [spSendInfo{staff}] WHERE SendId IN ({marks}) AND MessageType='Email' AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"),params).fetchall()
                for sendid,status,fact,plan_dt,deleted in rows:
                    sid=str(sendid or ""); st=str(status or "")
                    if deleted is None and st in ("WaitSend","Sending"): info_wait[sid]={"dt":plan_dt,"status":st}
                    if deleted is None and st=="SendSuccess":
                        old=info_sent.get(sid); anchor=fact or plan_dt
                        if anchor and (old is None or anchor<old): info_sent[sid]=anchor
            for p in staff_plans:
                rowid=str(p[6] or ""); sid=str(p[7] or ""); queue=queue_by_row.get(rowid.lower()) if rowid else None; info=info_wait.get(sid) if sid else None
                sequence=(str(p[1] or ""),staff,str(p[3] or ""),str(p[5] or ""))
                if not queue and info and sid in queue_by_send:
                    owners=queue_by_send[sid]
                    if len(owners)!=1: raise RuntimeError("ambiguous shadow SendId")
                    shadow_plans.append({"plan_id":str(p[0]),"staff":staff,"sendid":sid,"keeper_rowid":owners[0]["rowid"]})
                    continue
                if queue or info:
                    dt=(queue or info)["dt"]
                    if dt is None: raise RuntimeError("live pending without plan time")
                    live.append({"plan_id":str(p[0]),"customer":str(p[1] or ""),"staff":staff,"scenario":str(p[3] or ""),"step":int(p[4] or 0),"recipient":str(p[5] or ""),"rowid":rowid if queue else "","sendid":str((queue or {}).get("sendid") or sid),"has_info":bool(info),"source":"queue" if queue else "send_info","old_dt":dt,"sequence":sequence})
                sent_dt=info_sent.get(sid)
                if sent_dt:
                    old=sent_anchors.get(sequence)
                    value=(int(p[4] or 0),sent_dt)
                    if old is None or value[0]>old[0] or (value[0]==old[0] and value[1]>old[1]): sent_anchors[sequence]=value
        physical={(x["staff"],x["rowid"] or f"sid:{x['sendid']}") for x in live}
        if len(physical)!=len(live): raise RuntimeError("live physical mapping is not one-to-one")
        today=(datetime.utcnow()+timedelta(hours=8)).date(); now_bj=datetime.utcnow()+timedelta(hours=8)
        changes=[]; per_staff_summary=[]
        for staff in sorted(by_staff):
            staff_live=[x for x in live if x["staff"]==staff]
            mapped_rows=[x["rowid"] for x in staff_live if x["rowid"]]; mapped_sends=[x["sendid"] for x in staff_live if x["sendid"]]
            snapshot=NS["_autosend_crm_pending_snapshot"](staff,today)
            occupied=NS["_autosend_crm_pending_slots"](staff,today,mapped_rows,mapped_sends,snapshot)
            book=NS["_AutosendSlotBook"](occupied,50,today,now_bj.hour*60+now_bj.minute,bool(cfg.get("skip_non_workdays",True)),cfg.get("holiday_dates",[]))
            chains=defaultdict(list)
            for item in staff_live: chains[item["sequence"]].append(item)
            ordered=sorted(chains.items(),key=lambda kv:(min(x["old_dt"] for x in kv[1]),kv[0]))
            staff_changes=0
            for sequence,rows in ordered:
                rows.sort(key=lambda x:x["step"])
                first=rows[0]; first_step=first["step"]
                desired=max(first["old_dt"].date(),today)
                anchor=sent_anchors.get(sequence)
                if anchor and anchor[0]<first_step:
                    required=INTERVALS[first_step-1]-INTERVALS[anchor[0]-1]
                    desired=max(desired,anchor[1].date()+timedelta(days=max(1,required)))
                base_day=None; prev_off=-1; prev_day=None
                for idx,item in enumerate(rows):
                    off=INTERVALS[item["step"]-1]-INTERVALS[first_step-1]
                    off=max(off,prev_off+1) if idx else 0
                    want=desired if idx==0 else base_day+timedelta(days=off)
                    want=max(want,item["old_dt"].date())
                    if prev_day and want<=prev_day: want=prev_day+timedelta(days=1)
                    old_min=item["old_dt"].hour*60+item["old_dt"].minute
                    day,minute,seq=book.take(want,old_min if want==item["old_dt"].date() else None)
                    if idx==0: base_day=day
                    prev_day=day; prev_off=off
                    new_dt=datetime.combine(day,datetime.min.time())+timedelta(minutes=minute)
                    if new_dt!=item["old_dt"]:
                        changes.append({**item,"new_dt":new_dt,"seq":seq}); staff_changes+=1
            per_staff_summary.append({"staff":staff,"live":len(staff_live),"fixed_non_ai":sum(len(v) for v in occupied.values()),"changed":staff_changes})
        plan_ids=[x["plan_id"] for x in live]; before=content_hashes(db,plan_ids)
        if args.apply:
            for staff in sorted({x["staff"] for x in changes}):
                staff_changes=[x for x in changes if x["staff"]==staff]
                for item in staff_changes:
                    if item["rowid"]:
                        count=int(crm.execute(text("UPDATE spQueueSend SET PlanSendTime=:dt WHERE RowId=:rid AND MessageType='Email' AND ISNULL(InputerStaffId,'')=:staff"),{"dt":item["new_dt"],"rid":item["rowid"],"staff":staff}).rowcount or 0)
                        if count!=1: raise RuntimeError("queue changed during global recovery")
                    if item["has_info"] and item["sendid"]:
                        count=int(crm.execute(text(f"UPDATE [spSendInfo{staff}] SET PlanSendTime=:dt WHERE SendId=:sid AND MessageType='Email' AND Status IN ('WaitSend','Sending') AND DeleteTime IS NULL"),{"dt":item["new_dt"],"sid":item["sendid"]}).rowcount or 0)
                        if count<1: raise RuntimeError("send info changed during global recovery")
                crm.commit()
            if shadow_plans:
                db.execute(text("UPDATE mail_customer_suite_send_plan SET status='cancelled',crm_send_status='deleted',status_synced_at=now() WHERE plan_id IN :ids").bindparams(bindparam("ids",expanding=True)),{"ids":[x["plan_id"] for x in shadow_plans]})
            for item in changes:
                db.execute(text("UPDATE mail_customer_suite_send_plan SET plan_send_time=:dt,crm_send_status='WaitSend',status_synced_at=now() WHERE plan_id=:pid"),{"dt":item["new_dt"],"pid":item["plan_id"]})
                db.execute(text("UPDATE mail_autosend_plan_item SET plan_date=:day,plan_time=:tm,send_time=:tm,seq_in_day=:seq,updated_at=now() WHERE COALESCE(customer_id,contact_id)=:customer AND owner_staff_id=:staff AND scenario=:scenario AND suite_step=:step AND lower(COALESCE(recipient_email,''))=:recipient AND status='sent'"),{"day":item["new_dt"].date(),"tm":item["new_dt"].strftime("%H:%M"),"seq":item["seq"],"customer":item["customer"],"staff":item["staff"],"scenario":item["scenario"],"step":item["step"],"recipient":item["recipient"]})
            db.commit()
        after=content_hashes(db,plan_ids)
        if before!=after: raise RuntimeError("content hash changed")
        report={"generated_at":datetime.now().isoformat(),"applied":bool(args.apply),"config":{"daily_cap":50,"intervals":INTERVALS,"slot_gap_minutes":10,"skip_non_workdays":bool(cfg.get("skip_non_workdays",True))},"live_pending":len(live),"live_plan_ids":sorted(x["plan_id"] for x in live),"live_plan_sources":{x["plan_id"]:x["source"] for x in live},"shadow_plan_count":len(shadow_plans),"changed":len(changes),"content_hash_unchanged":before==after,"staff":per_staff_summary,"changes":[{"plan_id":x["plan_id"],"staff":x["staff"],"step":x["step"],"old":x["old_dt"].isoformat(),"new":x["new_dt"].isoformat()} for x in changes]}
        out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k not in ("changes","staff","live_plan_ids","live_plan_sources")},ensure_ascii=False)); print(json.dumps({"staff":per_staff_summary},ensure_ascii=False))
    except Exception:
        crm.rollback(); db.rollback(); raise
    finally:
        crm.close(); db.close()

if __name__=="__main__": main()