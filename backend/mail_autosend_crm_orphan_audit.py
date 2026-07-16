from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from sqlalchemy import bindparam, text
from database import SessionLocal
from crm_database import CRMSessionLocal

OUT=Path(__file__).resolve().parent.parent/'logs'/'mail-autosend-crm-orphan-audit-20260716.json'
pg=SessionLocal(); crm=CRMSessionLocal()
try:
    plans=pg.execute(text("SELECT plan_id,customer_id,inputer_staff_id,scenario,suite_step,recipient_email_key,spqueue_rowid,crm_send_id,plan_send_time,crm_send_status,crm_fact_send_time FROM mail_customer_suite_send_plan WHERE status IN ('enqueued','duplicate_skipped')")).fetchall()
    plan_by_row={str(p[6] or '').lower():p for p in plans if p[6]}
    staffs=sorted({str(p[2] or '') for p in plans if p[2]})
    params={f's{i}':v for i,v in enumerate(staffs)}; marks=','.join(f':s{i}' for i in range(len(staffs)))
    queue=crm.execute(text(f"SELECT CAST(RowId AS NVARCHAR(64)),InputerStaffId,PlanSendTime,CASE WHEN ISNULL(UseRange,'') LIKE '%宣传邮件-AI%' THEN 1 ELSE 0 END FROM spQueueSend WHERE InputerStaffId IN ({marks}) AND MessageType='Email' AND PlanSendTime>=CONVERT(date,GETDATE())"),params).fetchall()
    ai=[q for q in queue if q[3]]
    mapped=[q for q in ai if str(q[0]).lower() in plan_by_row]
    keys=defaultdict(list)
    for q in mapped:
        p=plan_by_row[str(q[0]).lower()]
        key=(str(p[1] or ''),str(p[2] or ''),str(p[3] or ''),int(p[4] or 0),str(p[5] or '').lower())
        keys[key].append((q,p))
    duplicate_pending={k:v for k,v in keys.items() if len(v)>1}
    sendids=defaultdict(list)
    for p in plans:
        if p[7]: sendids[str(p[2] or '')].append(str(p[7]))
    sent_success=set()
    for staff,ids in sendids.items():
        if not staff.isalnum() or len(staff)>8: continue
        for pos in range(0,len(ids),200):
            chunk=list(set(ids[pos:pos+200])); pp={f'i{j}':v for j,v in enumerate(chunk)}; mm=','.join(f':i{j}' for j in range(len(chunk)))
            try: rows=crm.execute(text(f"SELECT SendId FROM [spSendInfo{staff}] WHERE SendId IN ({mm}) AND MessageType='Email' AND Status='SendSuccess' AND DeleteTime IS NULL"),pp).fetchall()
            except Exception: crm.rollback(); continue
            sent_success.update((staff,str(r[0])) for r in rows)
    sent_keys=set()
    for p in plans:
        if (str(p[2] or ''),str(p[7] or '')) in sent_success:
            sent_keys.add((str(p[1] or ''),str(p[2] or ''),str(p[3] or ''),int(p[4] or 0),str(p[5] or '').lower()))
    pending_after_sent={k:v for k,v in keys.items() if k in sent_keys}
    result={'generated_at':datetime.now().isoformat(),'read_only':True,'crm_ai_future':len(ai),'mapped_send_plan':len(mapped),'unmapped_send_plan':len(ai)-len(mapped),'duplicate_pending_keys':len(duplicate_pending),'duplicate_pending_rows':sum(len(v) for v in duplicate_pending.values()),'pending_after_send_success_keys':len(pending_after_sent),'pending_after_send_success_rows':sum(len(v) for v in pending_after_sent.values()),'duplicate_pending':[{'customer_id':k[0],'staff':k[1],'scenario':k[2],'step':k[3],'rows':[{'rowid':str(q[0]),'plan_time':q[2].isoformat(),'plan_id':str(p[0])} for q,p in v]} for k,v in duplicate_pending.items()],'pending_after_send_success':[{'customer_id':k[0],'staff':k[1],'scenario':k[2],'step':k[3],'rows':[{'rowid':str(q[0]),'plan_time':q[2].isoformat(),'plan_id':str(p[0])} for q,p in v]} for k,v in pending_after_sent.items()]}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in result.items() if not isinstance(v,list)})
finally: crm.close();pg.close()