# -*- coding: utf-8 -*-
"""轮询 V10 迭代进度：终态(success/partial/failed)时输出并退出；约每20分钟输出一次进度心跳。"""
import sys, io, time
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from database import SessionLocal, CaseIterationRun

RID = "2c3a2b62-59f4-4b88-892f-27c5a6f0c969"
i = 0
last_done = -1
stall = 0
while True:
    i += 1
    try:
        db = SessionLocal()
        r = db.query(CaseIterationRun).filter(CaseIterationRun.run_id == RID).first()
        st, done, tot, ok, fail = r.status, r.completed_cases, r.total_cases, r.success_cases, r.failed_cases
        db.close()
    except Exception as e:
        print(f"poll-error: {e}", flush=True)
        time.sleep(60); continue
    if st in ("success", "partial", "failed"):
        print(f"V10完成 status={st} done={done}/{tot} ok={ok} fail={fail}", flush=True)
        break
    # 停滞检测：连续多次 done 不变则报警
    if done == last_done:
        stall += 1
    else:
        stall = 0
        last_done = done
    if stall == 8:  # 约16分钟无进展
        print(f"V10可能停滞 status={st} done={done}/{tot}（连续16分钟无进展）", flush=True)
    if i % 10 == 1:  # 约每20分钟心跳
        print(f"V10进度 status={st} done={done}/{tot} ok={ok} fail={fail}", flush=True)
    time.sleep(120)
