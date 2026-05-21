# -*- coding: utf-8 -*-
import sys, time, re, statistics
sys.path.insert(0, r"d:/items/QW/backend")
from database import SessionLocal, CaseIterationRun, CaseIterationResult
RUN = "8faf812e-3c82-4d61-b3e7-62ff593cb506"
META = ["【说明","【后续","【本次","【跟进","```","风格要求","备注:","备注：","说明:","说明："]
PH = re.compile(r"(x{2,}|X{2,}|[xX]+@|@x+\.|1[xX]{3,}|PO[xX]{2,}|[xX]+折|[xX]+元)")
HARD = re.compile(r"(可以降|降\s*\d+\s*%|少\s*\d+\s*%.*(没问题|可以|行)|打\s*\d\s*折|可以便宜|给你降)")
SOFT = re.compile(r"(能降一些|单价能降|可以让一点|算个具体数|给你个低价|便宜一些)")
# 泛泛兜底(零推进)短语 — 分布右移的代理指标
EMPTY = re.compile(r"(保持联系|随时喊我|随时找我|随时招呼|有需要随时|留意查收|我再发一遍|想先了解哪个|稍后回复你|稍后回复哈)")
while True:
    db = SessionLocal()
    try:
        r = db.query(CaseIterationRun).filter(CaseIterationRun.run_id == RUN).first()
        rows = db.query(CaseIterationResult).filter(CaseIterationResult.run_id == RUN).order_by(CaseIterationResult.created_at).all()
        done = sum(1 for x in rows if x.latency_ms is not None); total = r.total_cases or 0
        st = (r.status or "").lower()
        print(f"[{time.strftime('%H:%M:%S')}] status={r.status} done={done}/{total} success={r.success_cases} failed={r.failed_cases}", flush=True)
        if st in {"success","failed","completed","error","partial"} and total and done >= total:
            dr = [x for x in rows if x.latency_ms is not None]
            meta=[]; ph=[]; hard=[]; soft=[]; empty=[]; nf=0
            for x in dr:
                s6 = x.step6_sales_advice or ""; tag=f"{x.scenario_code}-{x.scenario_rank} T{x.turn_no}"
                if any(m in s6 for m in META): meta.append(tag)
                if PH.search(s6): ph.append((tag,s6[:50]))
                if HARD.search(s6): hard.append((tag,s6[:50]))
                elif SOFT.search(s6): soft.append((tag,s6[:50]))
                if EMPTY.search(s6): empty.append((tag,s6[:46]))
                s1=x.step1_summary or {}
                if all(k in s1 for k in ['topic','core_demand','key_facts','todo_items','risks','to_be_confirmed','status']): nf+=1
            lats=[x.latency_ms for x in dr if x.latency_ms]
            print("\n===== v14 QC (%d轮) ====="%len(dr), flush=True)
            print(f"real_success {r.success_cases}/{len(dr)} | 七字段 {nf}/{len(dr)}", flush=True)
            print(f"[硬伤] 元注释 {len(meta)} | 占位符(含邮箱) {len(ph)} | 守价硬让步 {len(hard)}", flush=True)
            print(f"[守价软让步] {len(soft)}", flush=True)
            print(f"[泛泛兜底短语命中] {len(empty)}  (v13 同口径约 30+，看是否明显下降=分布右移)", flush=True)
            if lats: print(f"单轮 avg {statistics.mean(lats)/1000:.2f}s (deepseek慢已忽略)", flush=True)
            for nm,it in [("占位符",ph),("守价硬让步",hard),("守价软让步",soft),("泛泛兜底残留",empty)]:
                if it:
                    print(f"--- {nm} ---", flush=True)
                    for x in it[:30]: print("  "+repr(x), flush=True)
            print("\nDONE", flush=True); break
    finally:
        db.close()
    time.sleep(60)
