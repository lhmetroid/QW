# -*- coding: utf-8 -*-
import sys, time, re, statistics
sys.path.insert(0, r"d:/items/QW/backend")
from database import SessionLocal, CaseIterationRun, CaseIterationResult
RUN = "c669ea0e-51a5-4a7a-8dbd-5f8b262c6904"
META = ["【说明", "【后续", "【本次", "【跟进", "```", "风格要求", "备注:", "备注：", "说明:", "说明："]
PLACEHOLDER = ["XX", "X折", "X元", "xx元", "X%"]
# 守价硬让步: 同意降价
HARD = [r"可以降", r"降\s*\d+\s*%", r"少\s*\d+\s*%.*(没问题|可以|行)", r"打\s*\d\s*折", r"可以便宜", r"便宜\s*\d+", r"没问题.*降", r"给你降"]
# 守价软提及: 提到降/折/%但用了缓冲词(需人工复核)
SOFT_NUM = re.compile(r"(降|少|便宜|打折|\d+\s*%|\d+\s*折)")
DEFER = re.compile(r"(申请|确认|算一?下|算算|查一?下|核算|同步你|准信|问下|报上去|跟领导)")
while True:
    db = SessionLocal()
    try:
        r = db.query(CaseIterationRun).filter(CaseIterationRun.run_id == RUN).first()
        rows = db.query(CaseIterationResult).filter(CaseIterationResult.run_id == RUN).order_by(CaseIterationResult.created_at).all()
        done = sum(1 for x in rows if x.latency_ms is not None)
        total = r.total_cases or 0
        st = (r.status or "").lower()
        print(f"[{time.strftime('%H:%M:%S')}] status={r.status} done={done}/{total} success={r.success_cases} failed={r.failed_cases}", flush=True)
        if st in {"success","failed","completed","error","partial"} and total and done >= total:
            done_rows = [x for x in rows if x.latency_ms is not None]
            meta_hits=[]; ph_hits=[]; hard_hits=[]; soft_hits=[]; empties=[]; nfields=0
            for x in done_rows:
                s6 = x.step6_sales_advice or ""
                tag = f"{x.scenario_code}-{x.scenario_rank} T{x.turn_no}"
                if not s6.strip(): empties.append(tag)
                if any(m in s6 for m in META): meta_hits.append((tag, s6[:70]))
                if any(p in s6 for p in PLACEHOLDER): ph_hits.append((tag, s6[:70]))
                if any(re.search(p, s6) for p in HARD): hard_hits.append((tag, s6[:70]))
                elif SOFT_NUM.search(s6): 
                    soft_hits.append((tag, s6[:70], bool(DEFER.search(s6))))
                s1 = x.step1_summary or {}
                if all(k in s1 for k in ['topic','core_demand','key_facts','todo_items','risks','to_be_confirmed','status']): nfields+=1
            lats=[x.latency_ms for x in done_rows if x.latency_ms]
            print("\n========== v13 质量验收 (共%d轮) =========="%len(done_rows), flush=True)
            print(f"real_success: {r.success_cases}/{len(done_rows)} | step1七字段齐全: {nfields}/{len(done_rows)}", flush=True)
            print(f"[硬伤] 元注释残留: {len(meta_hits)}  | 占位符残留: {len(ph_hits)}  | 空回复: {len(empties)}", flush=True)
            print(f"[守价] 硬让步(同意降价): {len(hard_hits)}  | 软提及数字(需复核): {len(soft_hits)}", flush=True)
            if lats: print(f"单轮耗时(含deepseek慢/忽略): avg {statistics.mean(lats)/1000:.2f}s", flush=True)
            def dump(name, items):
                if items:
                    print(f"\n--- {name} ---", flush=True)
                    for it in items[:40]:
                        print("  "+repr(it), flush=True)
            dump("元注释残留(硬伤)", meta_hits)
            dump("占位符残留(硬伤)", ph_hits)
            dump("守价硬让步(硬伤)", hard_hits)
            dump("守价软提及数字(需人工复核, True=已用缓冲词)", soft_hits)
            print("\nDONE", flush=True)
            break
    finally:
        db.close()
    time.sleep(60)
