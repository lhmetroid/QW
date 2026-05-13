"""
repair_api_compare_timing_0513.py
----------------------------------
回收 2026-05-13 的 API 触发记录中因 timing 污染写入的 llm2_compare_ms。

问题：sidebar_assist() 在合并旧摘要的 node_timings_ms 时，会把上次网页触发留下的
llm2_compare_ms（如 22s）带入当前 API 触发的 result_payload，导致分析面板对比模型
耗时列显示非零值（实际对比模型在 API 模式下从未运行）。

修复范围：api_assist_invocation 表中 triggered_at 为 2026-05-13 的所有记录，
将 result_payload.node_timings_ms.llm2.parts_ms.llm2_compare_ms 置为 null / 移除。
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, ApiAssistInvocation
from datetime import date, datetime, timezone


TARGET_DATE = date(2026, 5, 13)


def repair():
    db = SessionLocal()
    try:
        rows = db.query(ApiAssistInvocation).filter(
            ApiAssistInvocation.triggered_at >= datetime(2026, 5, 13, 0, 0, 0),
            ApiAssistInvocation.triggered_at <  datetime(2026, 5, 14, 0, 0, 0),
        ).all()

        print(f"找到 {len(rows)} 条 2026-05-13 API 触发记录")
        patched = 0

        for row in rows:
            payload = dict(row.result_payload or {})
            node_timings = payload.get("node_timings_ms")
            if not isinstance(node_timings, dict):
                continue
            llm2_node = node_timings.get("llm2")
            if not isinstance(llm2_node, dict):
                continue
            parts_ms = llm2_node.get("parts_ms")
            if not isinstance(parts_ms, dict):
                continue
            if "llm2_compare_ms" not in parts_ms:
                continue

            old_val = parts_ms.pop("llm2_compare_ms")
            llm2_node["parts_ms"] = parts_ms
            node_timings["llm2"] = llm2_node
            payload["node_timings_ms"] = node_timings

            # 同步清 stage_status 内的 node_timings_ms
            stage_status = dict(payload.get("stage_status") or {})
            ss_nt = dict(stage_status.get("node_timings_ms") or {})
            ss_llm2 = dict(ss_nt.get("llm2") or {})
            ss_parts = dict(ss_llm2.get("parts_ms") or {})
            ss_parts.pop("llm2_compare_ms", None)
            ss_llm2["parts_ms"] = ss_parts
            ss_nt["llm2"] = ss_llm2
            stage_status["node_timings_ms"] = ss_nt
            payload["stage_status"] = stage_status

            row.result_payload = payload
            patched += 1
            print(f"  修复 invocation_id={row.invocation_id}  旧值 llm2_compare_ms={old_val}")

        if patched:
            db.commit()
            print(f"\n完成：共修复 {patched} 条记录，已写入数据库。")
        else:
            print("未找到需要修复的记录（llm2_compare_ms 均已为空）。")

    except Exception as exc:
        db.rollback()
        print(f"修复失败，已回滚：{exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    repair()
