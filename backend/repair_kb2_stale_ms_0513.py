"""
repair_kb2_stale_ms_0513.py
------------------------------
清理 API 触发记录中因 merge 策略导致的 knowledge 节点
knowledge_external_api_ms 残留问题。

问题：KB2 被禁用（API_KB2_ENABLED=false）后，
_set_node_timing 的旧 merge 逻辑不清除 parts_ms 中已有的
knowledge_external_api_ms，导致分析面板 ⑤KB2 一直显示旧的
约 8s 耗时，即使当次实际状态为 skipped_kb2_disabled。

修复逻辑：
  若 result_payload.node_timings_ms.knowledge 的 status
  包含 skipped 且 parts_ms 中存在 knowledge_external_api_ms，
  则将该字段置为 None（清除）。
  同步修复 stage_status 列中的同名字段。
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
            ApiAssistInvocation.triggered_at >= datetime(2026, 5, 1, 0, 0, 0),
        ).all()

        print(f"找到 {len(rows)} 条 API 触发记录（2026-05-01 起）")
        patched = 0

        def fix_kb2_stale(node_timings: dict, kb_ext_status: str) -> bool:
            """就地清除 knowledge.parts_ms.knowledge_external_api_ms（仅当 kb_ext_status 含 skipped）"""
            if "skipped" not in (kb_ext_status or ""):
                return False
            kb_node = node_timings.get("knowledge")
            if not isinstance(kb_node, dict):
                return False
            parts_ms = kb_node.get("parts_ms")
            if not isinstance(parts_ms, dict):
                return False
            if "knowledge_external_api_ms" not in parts_ms:
                return False
            old_val = parts_ms["knowledge_external_api_ms"]
            if old_val is None:
                return False
            parts_ms["knowledge_external_api_ms"] = None
            kb_node["parts_ms"] = parts_ms
            node_timings["knowledge"] = kb_node
            print(f"    清除 knowledge_external_api_ms: {old_val} → None  (kb_ext_api={kb_ext_status})")
            return True

        for row in rows:
            # 优先从独立 stage_status 列取 knowledge_external_api 状态
            ss_col = dict(row.stage_status or {})
            kb_ext_status = ss_col.get("knowledge_external_api") or ""

            payload = dict(row.result_payload or {})
            # 若 result_payload 里的 stage_status 里有值则也参考
            if not kb_ext_status:
                kb_ext_status = (payload.get("stage_status") or {}).get("knowledge_external_api") or ""

            changed = False

            # 修复顶层 node_timings_ms
            node_timings = payload.get("node_timings_ms")
            if isinstance(node_timings, dict):
                if fix_kb2_stale(node_timings, kb_ext_status):
                    payload["node_timings_ms"] = node_timings
                    changed = True

            # 同步修复 stage_status 内的 node_timings_ms
            stage_status = payload.get("stage_status")
            if isinstance(stage_status, dict):
                ss_nt = stage_status.get("node_timings_ms")
                if isinstance(ss_nt, dict):
                    if fix_kb2_stale(ss_nt, kb_ext_status):
                        stage_status["node_timings_ms"] = ss_nt
                        payload["stage_status"] = stage_status
                        changed = True

            # 同步修复独立的 stage_status 列
            ss_col_nt = ss_col.get("node_timings_ms")
            if isinstance(ss_col_nt, dict) and fix_kb2_stale(ss_col_nt, kb_ext_status):
                ss_col["node_timings_ms"] = ss_col_nt
                row.stage_status = copy.deepcopy(ss_col)
                flag_modified(row, "stage_status")
                changed = True

            if changed:
                row.result_payload = copy.deepcopy(payload)
                flag_modified(row, "result_payload")
                print(f"  修复 invocation_id={row.invocation_id}")
                patched += 1

        if patched:
            db.commit()
            print(f"\n完成：共修复 {patched} 条记录，已写入数据库。")
        else:
            print("未找到需要修复的记录（knowledge_external_api_ms 均已为 None 或状态非 skipped）。")

    except Exception as exc:
        db.rollback()
        print(f"修复失败，已回滚：{exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    repair()
