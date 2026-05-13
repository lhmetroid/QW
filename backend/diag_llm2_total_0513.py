"""诊断：检查今日各 API 触发记录中 llm2.total_ms 的来源"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from database import SessionLocal, ApiAssistInvocation
from datetime import datetime

def get_llm2_total(node_timings):
    return ((node_timings or {}).get("llm2") or {}).get("total_ms")

def get_scoring_ms(node_timings):
    return (((node_timings or {}).get("llm2") or {}).get("parts_ms") or {}).get("reply_scoring_ms")

db = SessionLocal()
try:
    rows = db.query(ApiAssistInvocation).filter(
        ApiAssistInvocation.triggered_at >= datetime(2026, 5, 13),
        ApiAssistInvocation.triggered_at <  datetime(2026, 5, 14),
    ).all()
    print(f"共 {len(rows)} 条记录\n")
    for row in rows:
        rp = row.result_payload or {}
        ss_col = row.stage_status or {}  # 独立 stage_status 列

        # result_payload 顶层
        rp_nt = rp.get("node_timings_ms") or {}
        rp_total = get_llm2_total(rp_nt)
        rp_scoring = get_scoring_ms(rp_nt)

        # result_payload.stage_status
        rp_ss = rp.get("stage_status") or {}
        rp_ss_nt = rp_ss.get("node_timings_ms") or {}
        rp_ss_total = get_llm2_total(rp_ss_nt)
        rp_ss_scoring = get_scoring_ms(rp_ss_nt)

        # 独立 stage_status 列
        ss_nt = ss_col.get("node_timings_ms") or {}
        ss_total = get_llm2_total(ss_nt)
        ss_scoring = get_scoring_ms(ss_nt)

        print(f"invocation_id={str(row.invocation_id)[:8]}")
        print(f"  result_payload.node_timings_ms.llm2.total_ms = {rp_total}  scoring={rp_scoring}")
        print(f"  result_payload.stage_status.node_timings_ms.llm2.total_ms = {rp_ss_total}  scoring={rp_ss_scoring}")
        print(f"  item.stage_status.node_timings_ms.llm2.total_ms = {ss_total}  scoring={ss_scoring}")
        print()
finally:
    db.close()
