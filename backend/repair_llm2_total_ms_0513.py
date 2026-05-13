"""
repair_llm2_total_ms_0513.py
------------------------------
回收 2026-05-13 的 API 触发记录中因异步评分累加导致的 llm2.total_ms 虚高问题。

问题：_complete_api_reply_scoring_async() 在主请求返回后异步执行评分，
将 scoring_ms（约 22s）加到原有的 llm2.total_ms 上，导致分析面板
"⑥LLM2" 耗时显示虚高（如 33.41s，实际请求延迟仅约 11s）。

修复逻辑：
  若 result_payload.node_timings_ms.llm2.parts_ms 中存在 reply_scoring_ms，
  则将 llm2.total_ms 还原为 total_ms - reply_scoring_ms。
  同步修复 stage_status.node_timings_ms.llm2.total_ms。
"""

import sys
import os
import copy

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, ApiAssistInvocation
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified


def repair():
    db = SessionLocal()
    try:
        rows = db.query(ApiAssistInvocation).filter(
            ApiAssistInvocation.triggered_at >= datetime(2026, 5, 13, 0, 0, 0),
            ApiAssistInvocation.triggered_at <  datetime(2026, 5, 14, 0, 0, 0),
        ).all()

        print(f"找到 {len(rows)} 条 2026-05-13 API 触发记录")
        patched = 0

        def fix_llm2_total(node_timings: dict) -> bool:
            """就地修复 node_timings 里的 llm2.total_ms，返回是否有改动"""
            llm2_node = node_timings.get("llm2")
            if not isinstance(llm2_node, dict):
                return False
            parts_ms = llm2_node.get("parts_ms")
            if not isinstance(parts_ms, dict):
                return False
            scoring_ms = parts_ms.get("reply_scoring_ms")
            if scoring_ms is None:
                return False
            old_total = llm2_node.get("total_ms")
            if not isinstance(old_total, (int, float)):
                return False
            corrected = round(old_total - float(scoring_ms), 2)
            if corrected <= 0:
                print(f"    跳过（corrected={corrected} <= 0，数据异常）")
                return False
            llm2_node["total_ms"] = corrected
            node_timings["llm2"] = llm2_node
            return True

        for row in rows:
            payload = dict(row.result_payload or {})
            changed = False

            # 修复顶层 node_timings_ms
            node_timings = payload.get("node_timings_ms")
            if isinstance(node_timings, dict):
                old_total = (node_timings.get("llm2") or {}).get("total_ms")
                scoring_ms = ((node_timings.get("llm2") or {}).get("parts_ms") or {}).get("reply_scoring_ms")
                if fix_llm2_total(node_timings):
                    new_total = node_timings["llm2"]["total_ms"]
                    payload["node_timings_ms"] = node_timings
                    changed = True
                    print(f"  修复 invocation_id={row.invocation_id}  "
                          f"llm2.total_ms: {old_total} → {new_total}  "
                          f"（减去 reply_scoring_ms={scoring_ms}）")

            # 同步修复 stage_status 内的 node_timings_ms
            stage_status = payload.get("stage_status")
            if isinstance(stage_status, dict):
                ss_nt = stage_status.get("node_timings_ms")
                if isinstance(ss_nt, dict):
                    if fix_llm2_total(ss_nt):
                        stage_status["node_timings_ms"] = ss_nt
                        payload["stage_status"] = stage_status
                        changed = True

            # 同步修复独立的 stage_status 列
            ss_col = dict(row.stage_status or {})
            ss_col_nt = ss_col.get("node_timings_ms")
            if isinstance(ss_col_nt, dict) and fix_llm2_total(ss_col_nt):
                ss_col["node_timings_ms"] = ss_col_nt
                row.stage_status = copy.deepcopy(ss_col)
                flag_modified(row, "stage_status")
                changed = True

            if changed:
                row.result_payload = copy.deepcopy(payload)
                flag_modified(row, "result_payload")
                patched += 1

        if patched:
            db.commit()
            print(f"\n完成：共修复 {patched} 条记录，已写入数据库。")
        else:
            print("未找到需要修复的记录（reply_scoring_ms 均已为空或 total_ms 正常）。")

    except Exception as exc:
        db.rollback()
        print(f"修复失败，已回滚：{exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    repair()
