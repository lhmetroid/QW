# -*- coding: utf-8 -*-
import sys, time, re, statistics
sys.path.insert(0, r"d:/items/QW/backend")
from database import SessionLocal, CaseIterationRun, CaseIterationResult
RUN = "49fca3ca-b089-4580-aaed-cf1f2d0bfe20"
META=["【说明","【后续","【本次","【跟进","```","风格要求","备注:","说明:"]
PH=re.compile(r"(x{2,}|X{2,}|[xX]+@|@x+\.|1[xX]{3,}|PO[xX]{2,}|[xX]+折|[xX]+元)")
HARD=re.compile(r"(可以降|降\s*\d+\s*%|少\s*\d+\s*%.*(没问题|可以|行)|打\s*\d\s*折|可以便宜|给你降)")
SOFT=re.compile(r"(能降一些|单价能降|可以让一点|算个具体数|算个低价|给你个低价|便宜一些)")
while True:
    db=SessionLocal()
    try:
        r=db.query(CaseIterationRun).filter(CaseIterationRun.run_id==RUN).first()
        rows=db.query(CaseIterationResult).filter(CaseIterationResult.run_id==RUN).all()
        done=sum(1 for x in rows if x.latency_ms is not None); total=r.total_cases or 0
        st=(r.status or "").lower()
        print(f"[{time.strftime('%H:%M:%S')}] {r.status} done={done}/{total} success={r.success_cases}", flush=True)
        if st in {"success","failed","completed","error","partial"} and total and done>=total:
            dr=[x for x in rows if x.latency_ms is not None]
            meta=ph=hard=soft=nf=0
            phlist=[]
            for x in dr:
                s6=x.step6_sales_advice or ""
                if any(m in s6 for m in META): meta+=1
                if PH.search(s6): ph+=1; phlist.append((x.scenario_code,x.scenario_rank,x.turn_no,s6[:40]))
                if HARD.search(s6): hard+=1
                elif SOFT.search(s6): soft+=1
                s1=x.step1_summary or {}
                if all(k in s1 for k in ['topic','core_demand','key_facts','todo_items','risks','to_be_confirmed','status']): nf+=1
            lats=[x.latency_ms for x in dr if x.latency_ms]
            print("\n===== v16(v15复跑) QC (%d) ====="%len(dr), flush=True)
            print(f"success {r.success_cases} | 七字段 {nf} | 元注释 {meta} | 占位符 {ph} | 守价硬 {hard} | 守价软 {soft}", flush=True)
            if lats: print(f"单轮 avg {statistics.mean(lats)/1000:.2f}s", flush=True)
            for x in phlist: print("  占位符:",x, flush=True)
            print("DONE", flush=True); break
    finally:
        db.close()
    time.sleep(60)
