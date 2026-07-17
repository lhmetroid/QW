from __future__ import annotations
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
from database import SessionLocal
from crm_database import CRMSessionLocal

OUT = Path(__file__).resolve().parent.parent / "logs" / "mail-autosend-cross-table-pending-audit-20260716.json"
ACTIVE = ("planned","queued","drafting","drafted","commit_queued","committing","commit_failed","sent")

def key_hash(key):
    return hashlib.sha256("|".join(map(str, key)).encode("utf-8")).hexdigest()[:16]

pg = SessionLocal()
crm = CRMSessionLocal()
try:
    plans = pg.execute(text(
        "SELECT plan_id,customer_id,inputer_staff_id,scenario,suite_step,"
        "lower(COALESCE(recipient_email_key,'')),COALESCE(spqueue_rowid,''),"
        "COALESCE(crm_send_id,''),plan_send_time,COALESCE(crm_send_status,''),status,created_at,"
        "md5(COALESCE(subject,'') || E'\\n' || COALESCE(body_html,'')) "
        "FROM mail_customer_suite_send_plan WHERE status IN ('enqueued','duplicate_skipped')"
    )).fetchall()
    all_plan_refs = defaultdict(list)
    for p in plans:
        if str(p[7] or ""):
            all_plan_refs[(str(p[2] or ""),str(p[7] or ""))].append({
                "plan_id":str(p[0]),"plan_status":str(p[10] or ""),"cached_status":str(p[9] or ""),
                "rowid_hash":key_hash((str(p[2] or ""),str(p[6] or "").lower())) if str(p[6] or "") else "",
            })
    local_rows = pg.execute(text(
        "SELECT COALESCE(customer_id,contact_id),owner_staff_id,scenario,suite_step,"
        "lower(COALESCE(recipient_email,'')),plan_date,plan_time,status,item_id,updated_at "
        "FROM mail_autosend_plan_item WHERE status IN "
        "('planned','queued','drafting','drafted','commit_queued','committing','commit_failed','sent')"
    )).fetchall()
    local_by_key = defaultdict(list)
    for row in local_rows:
        key = (str(row[0] or ""),str(row[1] or ""),str(row[2] or ""),int(row[3] or 0),str(row[4] or ""))
        dt = datetime.combine(row[5], datetime.strptime(str(row[6])[:5], "%H:%M").time()) if row[5] and row[6] else None
        local_by_key[key].append({"item_id":str(row[8]),"plan_time":dt.isoformat() if dt else None,
                                  "status":str(row[7] or ""),"updated_at":row[9].isoformat() if row[9] else None})

    queue_by_row = {}
    staffs = sorted({str(p[2] or "") for p in plans if str(p[2] or "")})
    for staff in staffs:
        rows = crm.execute(text(
            "SELECT CAST(RowId AS NVARCHAR(64)),ISNULL(CAST(SendId AS NVARCHAR(80)),''),PlanSendTime,"
            "ISNULL(Subject,''),ISNULL(Receiver,''),ISNULL(CAST(EmailContent AS NVARCHAR(MAX)),'') "
            "FROM spQueueSend WHERE InputerStaffId=:staff AND MessageType='Email' "
            "AND ISNULL(FolderId,'')='OutBox' AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
        ), {"staff": staff}).fetchall()
        for rowid, send_id, plan_dt, subject, receiver, email_content in rows:
            queue_by_row[str(rowid).lower()] = {
                "staff":staff,"rowid":str(rowid),"send_id":str(send_id or ""),"plan_time":plan_dt,
                "subject_hash":key_hash((subject or "",)),"receiver_hash":key_hash((str(receiver or "").lower(),)),
                "body_hash":key_hash((email_content or "",)),"subject_raw":str(subject or ""),"receiver_raw":str(receiver or ""),
            }

    info_by_key = {}
    for staff in staffs:
        if not staff.isalnum() or len(staff) > 8:
            continue
        rows = crm.execute(text(
            f"SELECT ISNULL(CAST(SendId AS NVARCHAR(80)),''),PlanSendTime,ISNULL(Subject,''),ISNULL(Receiver,''),"
            f"ISNULL(CAST(EmailContent AS NVARCHAR(MAX)),ISNULL(CAST(PureText AS NVARCHAR(MAX)),'')) "
            f"FROM [spSendInfo{staff}] WHERE MessageType='Email' AND Status IN ('WaitSend','Sending') "
            f"AND DeleteTime IS NULL AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
        )).fetchall()
        for send_id, plan_dt, subject, receiver, email_content in rows:
            info_by_key[(staff, str(send_id))] = {
                "staff":staff,"send_id":str(send_id),"plan_time":plan_dt,
                "subject_hash":key_hash((subject or "",)),"receiver_hash":key_hash((str(receiver or "").lower(),)),
                "body_hash":key_hash((email_content or "",)),"subject_raw":str(subject or ""),"receiver_raw":str(receiver or ""),
            }

    queue_count_by_send = defaultdict(int)
    for queue_row in queue_by_row.values():
        if queue_row.get("send_id"):
            queue_count_by_send[(queue_row["staff"],queue_row["send_id"])] += 1
    duplicate_queue_send_ids = [{"staff":key[0],"send_id_hash":key_hash((key[0],key[1])),"queue_count":count}
                                for key,count in queue_count_by_send.items() if count > 1]
    grouped = defaultdict(dict)
    all_physical_plan_refs = defaultdict(list)
    transition_id_mismatches = []
    for p in plans:
        staff = str(p[2] or "")
        rowid = str(p[6] or "")
        send_id = str(p[7] or "")
        queue = queue_by_row.get(rowid.lower()) if rowid else None
        info = info_by_key.get((staff, send_id)) if send_id else None
        if queue is None and info is None:
            continue
        if queue and info and str(queue.get("send_id") or "") != send_id:
            transition_id_mismatches.append({
                "plan_id":str(p[0]),"staff":staff,
                "business_key_hash":key_hash((str(p[1] or ""), staff, str(p[3] or ""), int(p[4] or 0), str(p[5] or ""))),
                "plan_send_id":send_id,"queue_send_id":str(queue.get("send_id") or ""),
                "queue_plan_time":queue["plan_time"].isoformat() if queue.get("plan_time") else None,
                "info_plan_time":info["plan_time"].isoformat() if info.get("plan_time") else None,
            })
        key = (str(p[1] or ""), staff, str(p[3] or ""), int(p[4] or 0), str(p[5] or ""))
        physical_rows = []
        if queue:
            source = "both" if (info and str(queue.get("send_id") or "") == send_id) else "queue"
            physical_rows.append((f"queue:{staff}:{rowid.lower()}", source, queue, info if source == "both" else None))
        if info and (not queue or str(queue.get("send_id") or "") != send_id):
            # 分表 SendId 只有在没有对应队列行时才是独立物理记录；迁移并存不重复计数。
            if queue_count_by_send.get((staff,send_id),0) == 0:
                physical_rows.append((f"send:{staff}:{send_id}", "send_info", None, info))
        for physical, source, queue_row, info_row in physical_rows:
            physical_send_id = str((info_row or queue_row).get("send_id") or send_id)
            mapped_row = {
                "plan_id":str(p[0]),"source":source,
                "rowid":rowid if queue_row else "","send_id":physical_send_id,
                "queue_plan_time":queue_row["plan_time"].isoformat() if queue_row and queue_row["plan_time"] else None,
                "info_plan_time":info_row["plan_time"].isoformat() if info_row and info_row["plan_time"] else None,
                "send_plan_time":p[8].isoformat() if p[8] else None,
                "cached_status":str(p[9] or ""),"plan_status":str(p[10] or ""),
                "created_at":p[11].isoformat() if p[11] else None,"content_hash":str(p[12] or ""),
                "queue_subject_hash":queue_row.get("subject_hash") if queue_row else None,
                "queue_receiver_hash":queue_row.get("receiver_hash") if queue_row else None,
                "info_subject_hash":info_row.get("subject_hash") if info_row else None,
                "info_receiver_hash":info_row.get("receiver_hash") if info_row else None,
                "queue_body_hash":queue_row.get("body_hash") if queue_row else None,
                "info_body_hash":info_row.get("body_hash") if info_row else None,
            }
            all_physical_plan_refs[physical].append({**mapped_row, "business_key_hash":key_hash(key)})
            old = grouped[key].get(physical)
            if old is None:
                grouped[key][physical] = mapped_row
            else:
                def keeper_rank(row):
                    queue_send_matches = bool(row["rowid"] and row["send_id"] and
                                              queue_by_row.get(row["rowid"].lower(), {}).get("send_id") == row["send_id"])
                    time_matches = (row["queue_plan_time"] or row["info_plan_time"]) == row["send_plan_time"]
                    return (queue_send_matches, time_matches, row["cached_status"] in ("WaitSend", "Sending"),
                            row["created_at"] or "", row["plan_id"])
                if keeper_rank(mapped_row) > keeper_rank(old):
                    grouped[key][physical] = mapped_row

    mapped_plan_id_set = {row["plan_id"] for physical in grouped.values() for row in physical.values()}
    unrepresented_live_plans = []
    for p in plans:
        if str(p[0]) in mapped_plan_id_set:
            continue
        staff = str(p[2] or ""); rowid = str(p[6] or ""); send_id = str(p[7] or "")
        queue = queue_by_row.get(rowid.lower()) if rowid else None
        info = info_by_key.get((staff,send_id)) if send_id else None
        if queue or info:
            business_key=(str(p[1] or ""),staff,str(p[3] or ""),int(p[4] or 0),str(p[5] or ""))
            unrepresented_live_plans.append({
                "plan_id":str(p[0]),"staff":staff,"business_key_hash":key_hash(business_key),
                "rowid_hash":key_hash((staff,rowid.lower())) if rowid else "","send_id_hash":key_hash((staff,send_id.lower())) if send_id else "",
                "queue_live":bool(queue),"info_live":bool(info),"existing_business_physical_count":len(grouped.get(business_key,{})),
                "existing_plan_ids":[row["plan_id"] for row in grouped.get(business_key,{}).values()],
                "existing_rowid_hashes":[key_hash((staff,row["rowid"].lower())) if row["rowid"] else "" for row in grouped.get(business_key,{}).values()],
            })
    physical_references = defaultdict(list)
    for key, physical in grouped.items():
        for physical_key, row in physical.items():
            physical_references[physical_key].append({
                "business_key_hash":key_hash(key),"staff":key[1],"scenario":key[2],
                "suite_step":key[3],"plan_id":row["plan_id"],"source":row["source"],
                "plan_time":row["queue_plan_time"] or row["info_plan_time"],
                "rowid_hash":key_hash((key[1],row["rowid"])) if row["rowid"] else "",
                "send_id_hash":key_hash((key[1],row["send_id"])) if row["send_id"] else "",
                "content_hash":row["content_hash"],"created_at":row["created_at"],
                "send_plan_time":row["send_plan_time"],"cached_status":row["cached_status"],
                "queue_subject_hash":row["queue_subject_hash"],"queue_receiver_hash":row["queue_receiver_hash"],
                "info_subject_hash":row["info_subject_hash"],"info_receiver_hash":row["info_receiver_hash"],
                "queue_body_hash":row["queue_body_hash"],"info_body_hash":row["info_body_hash"],
                "recipient_key_hash":key_hash((key[4],)),"local_rows":local_by_key.get(key,[]),
            })
    shared_physical_references = [{"physical_key_hash":key_hash((physical_key,)),"reference_count":len(rows),"rows":rows}
                                  for physical_key, rows in all_physical_plan_refs.items() if len(rows) > 1]
    recipient_step_groups = defaultdict(list)
    for business_key, physical in grouped.items():
        recipient_key = (business_key[1], business_key[2], business_key[3], business_key[4])
        for physical_key, row in physical.items():
            recipient_step_groups[recipient_key].append({
                "business_key_hash":key_hash(business_key),"physical_key_hash":key_hash((physical_key,)),
                "plan_id":row["plan_id"],"source":row["source"],"rowid_hash":key_hash((business_key[1],row["rowid"])) if row["rowid"] else "",
                "send_id_hash":key_hash((business_key[1],row["send_id"])) if row["send_id"] else "",
                "plan_time":row["queue_plan_time"] or row["info_plan_time"],"content_hash":row["content_hash"],
                "queue_body_hash":row["queue_body_hash"],"info_body_hash":row["info_body_hash"],
                "local_rows":local_by_key.get(business_key,[]),
            })
    history_by_key = defaultdict(list)
    for staff in staffs:
        if not staff.isalnum() or len(staff) > 8:
            continue
        rows = crm.execute(text(
            f"SELECT ISNULL(CAST(SendId AS NVARCHAR(80)),''),ISNULL(Status,''),FactSendTime,PlanSendTime,DeleteTime "
            f"FROM [spSendInfo{staff}] WHERE MessageType='Email' "
            f"AND ISNULL(CAST(UseRange AS NVARCHAR(200)),'') LIKE '%宣传邮件-AI%'"
        )).fetchall()
        for send_id, status, fact_time, plan_time, delete_time in rows:
            history_by_key[(staff,str(send_id))].append({
                "status":"deleted" if delete_time else str(status or ""),
                "fact_time":fact_time.isoformat() if fact_time else None,
                "plan_time":plan_time.isoformat() if plan_time else None,
            })
    live_recipient_step_duplicates = []
    for key, rows in recipient_step_groups.items():
        if len({row["business_key_hash"] for row in rows}) > 1:
            live_recipient_step_duplicates.append({
                "staff":key[0],"scenario":key[1],"suite_step":key[2],"recipient_key_hash":key_hash((key[3],)),
                "business_key_count":len({row["business_key_hash"] for row in rows}),
                "physical_count":len({row["physical_key_hash"] for row in rows}),"rows":rows,
            })
    duplicate_suite_keys = {(row["staff"],row["scenario"],row["recipient_key_hash"])
                            for row in live_recipient_step_duplicates}
    duplicate_suite_plans = defaultdict(lambda: defaultdict(list))
    for p in plans:
        suite_key = (str(p[2] or ""),str(p[3] or ""),key_hash((str(p[5] or ""),)))
        if suite_key not in duplicate_suite_keys:
            continue
        business_hash = key_hash((str(p[1] or ""),str(p[2] or ""),str(p[3] or ""),str(p[5] or "")))
        queue = queue_by_row.get(str(p[6] or "").lower()) if p[6] else None
        histories = history_by_key.get((str(p[2] or ""),str(p[7] or "")),[])
        duplicate_suite_plans[suite_key][business_hash].append({
            "plan_id":str(p[0]),"suite_step":int(p[4] or 0),"rowid_hash":key_hash((str(p[2] or ""),str(p[6] or ""))) if p[6] else "",
            "send_id_hash":key_hash((str(p[2] or ""),str(p[7] or ""))) if p[7] else "",
            "queue_live":bool(queue),"queue_plan_time":queue["plan_time"].isoformat() if queue and queue["plan_time"] else None,
            "history":histories,"cached_status":str(p[9] or ""),"plan_status":str(p[10] or ""),
            "created_at":p[11].isoformat() if p[11] else None,
        })
    recipient_duplicate_suites = []
    for suite_key, businesses in duplicate_suite_plans.items():
        recipient_duplicate_suites.append({
            "staff":suite_key[0],"scenario":suite_key[1],"recipient_key_hash":suite_key[2],
            "business_count":len(businesses),
            "businesses":[{"business_key_hash":business_hash,"plans":rows} for business_hash,rows in businesses.items()],
        })
    duplicates = []
    for key, physical in grouped.items():
        if len(physical) > 1:
            duplicates.append({
                "business_key_hash":key_hash(key),"staff":key[1],"scenario":key[2],
                "suite_step":key[3],"physical_count":len(physical),
                "local_rows":local_by_key.get(key,[]),"rows":list(physical.values())
            })
    trigger_rows = crm.execute(text(
        "SELECT tr.name, OBJECT_DEFINITION(tr.object_id) FROM sys.triggers tr "
        "WHERE tr.parent_id=OBJECT_ID('spQueueSend')"
    )).fetchall()
    trigger_definitions = [{"name":str(row[0] or ""),"definition":str(row[1] or "")} for row in trigger_rows]
    send_id_schema = [dict(zip(("column","default_name","default_definition","is_identity","is_computed"), row)) for row in crm.execute(text(
        "SELECT c.name,dc.name,dc.definition,c.is_identity,c.is_computed FROM sys.columns c "
        "LEFT JOIN sys.default_constraints dc ON dc.parent_object_id=c.object_id AND dc.parent_column_id=c.column_id "
        "WHERE c.object_id=OBJECT_ID('spQueueSend') AND c.name='SendId'"
    )).fetchall()]
    physical_pending = {}
    queue_keys_by_send = defaultdict(list)
    for queue in queue_by_row.values():
        physical_key = (queue["staff"], f"queue:{queue['rowid'].lower()}")
        physical_pending[physical_key] = {"source":"queue","plan_time":queue["plan_time"],"rowid":queue["rowid"],
                                          "send_id":queue["send_id"],"subject_hash":queue.get("subject_hash"),"receiver_hash":queue.get("receiver_hash"),
                                          "body_hash":queue.get("body_hash"),"subject_raw":queue.get("subject_raw"),"receiver_raw":queue.get("receiver_raw")}
        if queue["send_id"]:
            queue_keys_by_send[(queue["staff"],queue["send_id"])].append(physical_key)
    for (staff, send_id), info in info_by_key.items():
        queue_keys = queue_keys_by_send.get((staff,send_id),[])
        if len(queue_keys) == 1:
            physical = physical_pending[queue_keys[0]]
            physical["source"] = "both"
            if physical["plan_time"] != info["plan_time"]:
                physical["info_plan_time"] = info["plan_time"]
        elif not queue_keys:
            physical_key = (staff, f"send:{send_id}")
            physical_pending[physical_key] = {"source":"send_info","plan_time":info["plan_time"],"rowid":"","send_id":send_id,
                                              "subject_hash":info.get("subject_hash"),"receiver_hash":info.get("receiver_hash"),
                                              "body_hash":info.get("body_hash"),"subject_raw":info.get("subject_raw"),"receiver_raw":info.get("receiver_raw")}
    plan_rowids = {str(p[6] or "").lower() for p in plans if str(p[6] or "")}
    plan_sendids = {(str(p[2] or ""),str(p[7] or "")) for p in plans if str(p[7] or "")}
    mapped_signatures = defaultdict(list)
    for business_key, physical in grouped.items():
        for row in physical.values():
            subject_hash = row["queue_subject_hash"] or row["info_subject_hash"]
            receiver_hash = row["queue_receiver_hash"] or row["info_receiver_hash"]
            body_hash = row["queue_body_hash"] or row["info_body_hash"]
            if subject_hash and receiver_hash and body_hash:
                mapped_signatures[(business_key[1],subject_hash,receiver_hash,body_hash)].append({
                    "business_key_hash":key_hash(business_key),"plan_id":row["plan_id"],"source":row["source"],
                })
    unmapped_physical_pending = []
    for (staff, send_id), physical in physical_pending.items():
        mapped = ((physical.get("rowid") and str(physical["rowid"]).lower() in plan_rowids)
                  or ((staff, str(physical.get("send_id") or "")) in plan_sendids))
        if not mapped:
            email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", str(physical.get("receiver_raw") or ""))
            email_key = email_match.group(0).lower() if email_match else ""
            subject_raw = str(physical.get("subject_raw") or "")
            local_candidates = pg.execute(text(
                "SELECT item_id,COALESCE(customer_id,contact_id),scenario,suite_step,status,plan_date,plan_time "
                "FROM mail_autosend_plan_item WHERE owner_staff_id=:staff AND COALESCE(subject,'')=:subject "
                "AND lower(COALESCE(recipient_email,''))=:email"
            ), {"staff":staff,"subject":subject_raw,"email":email_key}).fetchall() if email_key else []
            send_plan_candidates = pg.execute(text(
                "SELECT plan_id,customer_id,scenario,suite_step,status,plan_send_time,COALESCE(crm_send_status,'') "
                "FROM mail_customer_suite_send_plan WHERE inputer_staff_id=:staff AND COALESCE(subject,'')=:subject "
                "AND lower(COALESCE(recipient_email_key,''))=:email"
            ), {"staff":staff,"subject":subject_raw,"email":email_key}).fetchall() if email_key else []
            unmapped_physical_pending.append({
                "staff":staff,"source":physical["source"],"send_id_hash":key_hash((staff,send_id)),
                "rowid_hash":key_hash((staff,physical.get("rowid"))) if physical.get("rowid") else "",
                "plan_time":physical["plan_time"].isoformat() if physical.get("plan_time") else None,
                "all_plan_refs":all_plan_refs.get((staff,str(physical.get("send_id") or "")),[]),
                "exact_content_refs":mapped_signatures.get((staff,physical.get("subject_hash"),physical.get("receiver_hash"),physical.get("body_hash")),[]),
                "local_candidates":[{"item_id":str(x[0]),"business_key_hash":key_hash((str(x[1] or ""),staff,str(x[2] or ""),int(x[3] or 0),email_key)),"status":str(x[4] or ""),"plan_time":(datetime.combine(x[5],datetime.strptime(str(x[6])[:5],"%H:%M").time()).isoformat() if x[5] and x[6] else None)} for x in local_candidates],
                "send_plan_candidates":[{"plan_id":str(x[0]),"business_key_hash":key_hash((str(x[1] or ""),staff,str(x[2] or ""),int(x[3] or 0),email_key)),"status":str(x[4] or ""),"plan_time":x[5].isoformat() if x[5] else None,"cached_status":str(x[6] or "")} for x in send_plan_candidates],
            })
    slots = defaultdict(list)
    for (staff, send_id), physical in physical_pending.items():
        if physical["plan_time"] is not None:
            slots[(staff, physical["plan_time"])].append({
                "source":physical["source"],"send_id_hash":key_hash((staff, send_id)),
                "rowid_hash":key_hash((staff, physical["rowid"])) if physical["rowid"] else "",
                "info_plan_time":physical.get("info_plan_time").isoformat() if physical.get("info_plan_time") else None,
            })
    slot_collisions = [{"staff":key[0],"plan_time":key[1].isoformat(),"physical_count":len(rows),"rows":rows}
                       for key, rows in slots.items() if len(rows) > 1]
    result = {
        "generated_at":datetime.now().isoformat(),"read_only":True,
        "plan_rows_checked":len(plans),"live_business_keys":len(grouped),
        "mapped_live_plan_ids":sorted(mapped_plan_id_set),
        "unrepresented_live_plan_count":len(unrepresented_live_plans),
        "unrepresented_live_plans":unrepresented_live_plans,
        "cross_table_duplicate_keys":len(duplicates),
        "cross_table_duplicate_physical_rows":sum(x["physical_count"] for x in duplicates),
        "transition_id_mismatch_count":len(transition_id_mismatches),
        "transition_id_mismatches":transition_id_mismatches,
        "shared_physical_reference_count":len(shared_physical_references),
        "shared_physical_references":shared_physical_references,
        "live_recipient_step_duplicate_count":len(live_recipient_step_duplicates),
        "live_recipient_step_duplicates":live_recipient_step_duplicates,
        "recipient_duplicate_suite_count":len(recipient_duplicate_suites),
        "recipient_duplicate_suites":recipient_duplicate_suites,
        "trigger_definitions":trigger_definitions,
        "send_id_schema":send_id_schema,
        "physical_pending_count":len(physical_pending),
        "duplicate_queue_send_id_count":len(duplicate_queue_send_ids),
        "duplicate_queue_send_ids":duplicate_queue_send_ids,
        "unmapped_physical_pending_count":len(unmapped_physical_pending),
        "unmapped_physical_pending":unmapped_physical_pending,
        "slot_collision_count":len(slot_collisions),
        "slot_collisions":slot_collisions,
        "duplicates":duplicates,
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"mapped_live_plan_ids","unrepresented_live_plans","duplicates","transition_id_mismatches","shared_physical_references","live_recipient_step_duplicates","recipient_duplicate_suites","trigger_definitions","send_id_schema","unmapped_physical_pending","slot_collisions","duplicate_queue_send_ids"}},ensure_ascii=False))
finally:
    crm.close()
    pg.close()