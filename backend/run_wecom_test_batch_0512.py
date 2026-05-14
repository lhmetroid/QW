"""企微 2026-05-12 全节点测试触发批跑

与 run_wecom_test_batch.py 的差异：
1. 日期改为 2026-05-12（今日）
2. 挑选 3 个完整会话（5-10 轮来回），而非跨会话挑最佳单节点
3. 对每个会话从头到尾触发所有客户锚点（连续客户消息只在最后一条触发）
4. 仅触发真实客户消息节点（不触发内部人员对话）
"""
from __future__ import annotations

import argparse
import json
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from database import ApiAssistInvocation, MessageLog, SessionLocal, WecomTriggerRecord
from kb_evaluation_worker import process_eval_record
from main import (
    _build_analysis_result_for_target,
    _build_trigger_analytics_row,
    _collect_actual_sales_replies,
    _create_wecom_trigger_record,
    _reply_block_text,
    _sync_wecom_trigger_record_result,
    _upsert_reply_chain_snapshot,
    _visible_messages_until_anchor,
    refresh_snapshot_knowledge_task,
    reanalyze_snapshot_task,
    sanitize_text,
)

TARGET_DATE = "2026-05-12"

TRIVIAL_ANCHOR_TEXTS = {
    "ok", "okay", "好的", "好滴", "收到", "谢谢", "谢谢您", "木有哎",
    "哪个？", "哪个?", "[thumbsup]", "[图片消息]", "[voiptext类型报文]",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量重跑 2026-05-12 企微历史客户节点（全节点模式）。")
    parser.add_argument("--date", default=TARGET_DATE, help="要分析的日期，格式 YYYY-MM-DD")
    parser.add_argument("--sessions", type=int, default=3, help="挑选的会话数量")
    parser.add_argument("--min-rounds", type=int, default=5, help="最少来回轮次（客户-销售）")
    parser.add_argument("--max-rounds", type=int, default=10, help="最多来回轮次（客户-销售）")
    parser.add_argument("--session-prefix", default="single_", help="筛选的会话前缀，默认仅单聊")
    parser.add_argument("--skip-kb-eval", action="store_true", help="跳过知识库评估 API 打分")
    parser.add_argument("--output-dir", default="", help="报告输出目录，默认写入测试数据/企微512测试触发")
    return parser.parse_args()


def parse_day(day_text: str) -> tuple[datetime, datetime]:
    day = datetime.fromisoformat(day_text[:10])
    return day, day + timedelta(days=1)


def normalize_anchor_text(text: str) -> str:
    return sanitize_text(text or "").strip().lower()


def is_meaningful_anchor(text: str) -> bool:
    normalized = normalize_anchor_text(text)
    if not normalized:
        return False
    if normalized in TRIVIAL_ANCHOR_TEXTS:
        return False
    if normalized.startswith("[") and normalized.endswith("]"):
        return False
    if len(normalized) < 4 and "?" not in normalized and "？" not in normalized:
        return False
    return True


def count_dialogue_rounds(messages: list[MessageLog]) -> int:
    """统计来回轮次：连续客户消息组 + 至少一条后续销售回复算一轮。"""
    rounds = 0
    i = 0
    while i < len(messages):
        if messages[i].sender_type == "customer":
            # 找到连续客户消息组的末尾
            j = i
            while j + 1 < len(messages) and messages[j + 1].sender_type == "customer":
                j += 1
            # 检查后续是否有销售回复
            if j + 1 < len(messages) and messages[j + 1].sender_type == "sales":
                rounds += 1
            i = j + 1
        else:
            i += 1
    return rounds


def extract_anchor_nodes(messages: list[MessageLog]) -> list[MessageLog]:
    """从会话消息流中提取所有触发锚点。
    规则：连续客户消息组，只取最后一条；且后续需要有销售回复。
    """
    anchors: list[MessageLog] = []
    i = 0
    while i < len(messages):
        if messages[i].sender_type == "customer":
            j = i
            while j + 1 < len(messages) and messages[j + 1].sender_type == "customer":
                j += 1
            # messages[j] 是连续客户组的最后一条
            if j + 1 < len(messages) and messages[j + 1].sender_type == "sales":
                if is_meaningful_anchor(messages[j].content or ""):
                    anchors.append(messages[j])
            i = j + 1
        else:
            i += 1
    return anchors


def select_sessions(
    *,
    start: datetime,
    end: datetime,
    session_count: int,
    min_rounds: int,
    max_rounds: int,
    session_prefix: str,
) -> list[tuple[str, list[MessageLog]]]:
    """从今日数据中挑选符合来回轮次要求的会话，返回 (session_id, all_messages) 列表。"""
    db = SessionLocal()
    try:
        # 今日有客户消息的会话 ID
        today_customer_sessions = db.query(MessageLog.user_id).filter(
            MessageLog.timestamp >= start,
            MessageLog.timestamp < end,
            MessageLog.is_mock.is_(False),
            MessageLog.sender_type == "customer",
            MessageLog.user_id.like(f"{session_prefix}%"),
        ).distinct().all()
        session_ids = [row.user_id for row in today_customer_sessions]

        # 拉取每个会话的完整历史（不限日期，需要上下文）
        candidates: list[tuple[str, list[MessageLog], int]] = []
        for sid in session_ids:
            msgs = db.query(MessageLog).filter(
                MessageLog.user_id == sid,
                MessageLog.is_mock.is_(False),
            ).order_by(MessageLog.id.asc()).all()
            # 仅统计今日消息的来回轮次
            today_msgs = [m for m in msgs if start <= m.timestamp < end]
            rounds = count_dialogue_rounds(today_msgs)
            if min_rounds <= rounds <= max_rounds:
                candidates.append((sid, msgs, rounds))

        # 按轮次从高到低排序，取前 session_count 个
        candidates.sort(key=lambda x: x[2], reverse=True)
        return [(sid, msgs) for sid, msgs, _ in candidates[:session_count]]
    finally:
        db.close()


def ensure_snapshot(session_id: str, anchor_message_id: int, all_messages: list[MessageLog]) -> str:
    db = SessionLocal()
    try:
        anchor_message = next((m for m in all_messages if int(m.id) == anchor_message_id), None)
        if not anchor_message:
            raise RuntimeError(f"未找到锚点消息: {session_id}#{anchor_message_id}")
        snapshot = _upsert_reply_chain_snapshot(
            db,
            session_id=session_id,
            anchor_message=anchor_message,
            all_messages=all_messages,
        )
        db.commit()
        db.refresh(snapshot)
        return str(snapshot.snapshot_id)
    finally:
        db.close()


def run_single_anchor(
    session_id: str,
    anchor_msg: MessageLog,
    all_messages: list[MessageLog],
    *,
    run_kb_eval: bool,
    date_str: str,
) -> dict:
    anchor_message_id = int(anchor_msg.id)
    snapshot_id = ensure_snapshot(session_id, anchor_message_id, all_messages)

    record_id = _create_wecom_trigger_record(
        session_id=session_id,
        snapshot_id=snapshot_id,
        run_id=uuid.uuid4().hex[:12],
        trigger_source="test",
        trigger_kind="batch_test_full_run",
        request_status="running",
        request_payload={
            "mode": "batch_test_full_run_0512",
            "date": date_str,
            "anchor_message_id": anchor_message_id,
        },
    )
    if not record_id:
        raise RuntimeError(f"创建测试触发记录失败: {session_id}#{anchor_message_id}")

    reanalyze_snapshot_task(session_id, snapshot_id, 1, record_id)
    refresh_snapshot_knowledge_task(session_id, snapshot_id, "knowledge_v2", record_id)
    refresh_snapshot_knowledge_task(session_id, snapshot_id, "knowledge_external_api", record_id)
    reanalyze_snapshot_task(session_id, snapshot_id, 2, record_id)
    _sync_wecom_trigger_record_result(
        record_id=record_id,
        session_id=session_id,
        snapshot_id=snapshot_id,
        request_status="done",
        error_message=None,
    )

    db = SessionLocal()
    try:
        record = db.query(WecomTriggerRecord).filter(WecomTriggerRecord.record_id == record_id).first()
        if not record:
            raise RuntimeError(f"测试触发记录不存在: {record_id}")
        if run_kb_eval:
            process_eval_record(db, record, "WecomTriggerRecord")
            db.refresh(record)
        result_payload = dict(record.result_payload or {})
        if not result_payload:
            result_payload = _build_analysis_result_for_target(db, session_id=session_id, snapshot_id=snapshot_id)

        actual_sales_replies = _collect_actual_sales_replies(all_messages, anchor_message_id)
        reply_text = _reply_block_text(actual_sales_replies, strip_noise=True)

        analytics_row = _build_trigger_analytics_row(
            row_id=str(record.record_id),
            triggered_at=record.triggered_at,
            trigger_source=record.trigger_source,
            trigger_kind=record.trigger_kind,
            request_status=record.request_status,
            session_id=record.session_id,
            snapshot_id=record.snapshot_id,
            run_id=record.run_id,
            anchor_message_id=record.anchor_message_id,
            anchor_message_time=record.anchor_message_time,
            anchor_message_text=record.anchor_message_text,
            input_messages=record.input_messages,
            recent_customer_messages=record.recent_customer_messages,
            manual_reply_text=record.actual_sales_reply_text,
            result_payload=result_payload,
            requested_step=record.requested_step,
            requested_channel=record.requested_channel,
            kb1_eval_score=float(record.kb1_eval_score) if record.kb1_eval_score is not None else None,
            kb1_eval_reason=record.kb1_eval_reason,
            kb2_eval_score=float(record.kb2_eval_score) if record.kb2_eval_score is not None else None,
            kb2_eval_reason=record.kb2_eval_reason,
            quality_annotations=record.quality_annotations,
        )
        return {
            "session_id": session_id,
            "anchor_message_id": anchor_message_id,
            "anchor_message_time": anchor_msg.timestamp.isoformat(),
            "anchor_message_text": sanitize_text(anchor_msg.content or ""),
            "actual_sales_reply_text": reply_text,
            "record_id": str(record.record_id),
            "snapshot_id": snapshot_id,
            "request_status": record.request_status,
            "result_payload": result_payload,
            "analytics_row": analytics_row,
        }
    finally:
        db.close()


def build_report_markdown(day_text: str, sessions_results: list[dict]) -> str:
    """生成 Markdown 报告，包含逐会话、逐节点分析和优化建议。"""
    all_analytics: list[dict] = []
    for s in sessions_results:
        for r in s["nodes"]:
            all_analytics.append(r["analytics_row"])

    kb1_scores = [float(a["kb1_eval_score"]) for a in all_analytics if a.get("kb1_eval_score") is not None]
    kb2_scores = [float(a["kb2_eval_score"]) for a in all_analytics if a.get("kb2_eval_score") is not None]
    manual_biz_scores = [float(a["manual_business_score"]) for a in all_analytics if a.get("manual_business_score") is not None]

    step_time_keys = [
        ("step_1_time_ms", "输入构建"),
        ("step_2_time_ms", "FastTrack"),
        ("step_3_time_ms", "LLM1摘要"),
        ("step_4_time_ms", "CRM"),
        ("step_5_kb1_time_ms", "KB1检索"),
        ("step_5_kb2_time_ms", "KB2检索"),
        ("step_6_time_ms", "LLM2生成"),
        ("step_7_time_ms", "校验"),
    ]
    step_avgs: dict[str, float] = {}
    for key, label in step_time_keys:
        vals = [float(a[key]) for a in all_analytics if a.get(key) is not None]
        step_avgs[label] = round(sum(vals) / len(vals), 1) if vals else 0.0

    total_nodes = sum(len(s["nodes"]) for s in sessions_results)

    lines = [
        f"# 企微 {day_text} 全节点测试触发报告",
        "",
        "## 执行概要",
        f"- 日期：`{day_text}`",
        f"- 触发来源：`test`（全节点批跑）",
        f"- 选取会话数：`{len(sessions_results)}`",
        f"- 触发节点总数：`{total_nodes}`",
        f"- 平均知识库1评估分：`{round(sum(kb1_scores)/len(kb1_scores), 2) if kb1_scores else '-'}`",
        f"- 平均知识库2评估分：`{round(sum(kb2_scores)/len(kb2_scores), 2) if kb2_scores else '-'}`",
        f"- 平均人工业务质量分：`{round(sum(manual_biz_scores)/len(manual_biz_scores), 2) if manual_biz_scores else '-'}`",
        "",
        "## 各阶段平均耗时（ms）",
    ]
    for label, avg in step_avgs.items():
        lines.append(f"- {label}：`{avg}` ms")
    lines.append("")

    lines.append("## 逐会话节点详情")
    for si, sess in enumerate(sessions_results, start=1):
        sid = sess["session_id"]
        nodes = sess["nodes"]
        lines.extend([
            f"",
            f"### 会话 {si}：`{sid}`（共 {len(nodes)} 个触发节点）",
        ])
        for ni, node in enumerate(nodes, start=1):
            a = node["analytics_row"]
            p = node["result_payload"] or {}
            lines.extend([
                f"#### 节点 {ni}  锚点消息 #{node['anchor_message_id']}",
                f"- 时间：`{node['anchor_message_time'].replace('T', ' ')[:19]}`",
                f"- 客户消息：{node['anchor_message_text']}",
                f"- 人工回复：{sanitize_text(node['actual_sales_reply_text']) or '-'}",
                f"- 触发记录：`{node['record_id']}`",
                f"- 摘要：主题=`{sanitize_text(str(p.get('topic') or '-'))}`；诉求=`{sanitize_text(str(p.get('core_demand') or '-'))}`；状态=`{sanitize_text(str(p.get('status') or '-'))}`",
                f"- 阶段耗时：输入=`{a.get('step_1_time_ms')}`ms  FastTrack=`{a.get('step_2_time_ms')}`ms  LLM1=`{a.get('step_3_time_ms')}`ms  CRM=`{a.get('step_4_time_ms')}`ms  KB1=`{a.get('step_5_kb1_time_ms')}`ms  KB2=`{a.get('step_5_kb2_time_ms')}`ms  LLM2=`{a.get('step_6_time_ms')}`ms  校验=`{a.get('step_7_time_ms')}`ms",
                f"- 评分：KB1=`{a.get('kb1_eval_score')}`  KB2=`{a.get('kb2_eval_score')}`  人工业务=`{a.get('manual_business_score')}`",
                f"- KB1建议：{sanitize_text(str(a.get('step_6_main_kb1_content') or '-'))[:120]}",
                f"- KB2建议：{sanitize_text(str(a.get('step_6_main_kb2_content') or '-'))[:120]}",
                "",
            ])

    # 优化建议
    low_quality = [n for s in sessions_results for n in s["nodes"]
                   if (n["analytics_row"].get("manual_business_score") or 100) < 80]
    kb2_better = sum(
        1 for s in sessions_results for n in s["nodes"]
        if (n["analytics_row"].get("step_6_main_kb2_score") or 0) >
           (n["analytics_row"].get("step_6_main_kb1_score") or 0)
    )
    slow_llm1 = [a for a in all_analytics if (a.get("step_3_time_ms") or 0) > 5000]
    slow_kb = [a for a in all_analytics if (a.get("step_5_kb1_time_ms") or 0) > 3000 or
               (a.get("step_5_kb2_time_ms") or 0) > 3000]

    lines.extend([
        "## 5.12 优化建议",
        "",
        "### 1. 质量分析",
        f"- 人工业务质量低于 80 分的节点：`{len(low_quality)}` 个",
        "  - 建议将这些节点的人工回复与 AI 建议逐条对比，补充或修正知识库素材。",
        f"- KB2 主候选优于 KB1 的节点：`{kb2_better}` 个",
        "  - 若比例偏高，说明内部知识库在部分场景检索质量不足，需优先补入对应场景的高质量切片。",
        "",
        "### 2. 耗时分析",
        f"- LLM1（摘要）平均耗时：`{step_avgs.get('LLM1摘要', 0)}` ms，慢节点（>5s）：`{len(slow_llm1)}` 个",
        "  - 建议检查 LLM1 prompt 长度，超长上下文可压缩最近消息窗口（当前保留最近 N 条）。",
        f"- KB 检索平均耗时 KB1=`{step_avgs.get('KB1检索', 0)}` ms / KB2=`{step_avgs.get('KB2检索', 0)}` ms，慢节点：`{len(slow_kb)}` 个",
        "  - embedding 检索超 3s 通常因向量维度高或索引冷启动，可考虑预热或降维。",
        f"- LLM2（生成）平均耗时：`{step_avgs.get('LLM2生成', 0)}` ms",
        "  - 若生成超 8s，建议启用流式输出 + 前端骨架屏，降低用户感知延迟。",
        "",
        "### 3. 脚本优化建议",
        "- 今日全节点触发覆盖了会话从头到尾，可观察模型在「对话早期 vs 中后期」的表现差异：",
        "  - 早期节点上下文少，摘要应更保守（避免过度推断）；",
        "  - 中后期节点应充分利用已有 thread_business_fact 而非重新推断。",
        "- 对于连续客户消息（仅触发最后一条）的场景，建议在 prompt 中将整组消息拼入，而非只用最后一条。",
        "- 建议按「场景类型」（询价/确认/推进/告知）分组评估，找到质量最弱的场景优先治理。",
    ])
    return "\n".join(lines)


def resolve_output_dir(raw_value: str) -> Path:
    if raw_value:
        return Path(raw_value).resolve()
    return Path(__file__).resolve().parent.parent / "测试数据" / "企微512测试触发"


def main() -> None:
    args = parse_args()
    start, end = parse_day(args.date)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Step 1] 挑选 {args.date} 中 {args.min_rounds}-{args.max_rounds} 轮来回的会话...")
    sessions = select_sessions(
        start=start,
        end=end,
        session_count=args.sessions,
        min_rounds=args.min_rounds,
        max_rounds=args.max_rounds,
        session_prefix=args.session_prefix,
    )
    if not sessions:
        # 放宽限制再试
        print(f"  未找到 {args.min_rounds}-{args.max_rounds} 轮会话，放宽到 3-20 轮...")
        sessions = select_sessions(
            start=start,
            end=end,
            session_count=args.sessions,
            min_rounds=3,
            max_rounds=20,
            session_prefix=args.session_prefix,
        )
    if not sessions:
        raise RuntimeError(f"{args.date} 未找到符合条件的企微会话（前缀={args.session_prefix}）")

    print(f"  找到 {len(sessions)} 个会话：{[sid for sid, _ in sessions]}")

    sessions_results: list[dict] = []
    for sess_idx, (session_id, all_messages) in enumerate(sessions, start=1):
        anchor_nodes = extract_anchor_nodes(all_messages)
        # 进一步过滤：只触发日期当天的锚点（anchor 时间在 start-end 内）
        today_anchors = [m for m in anchor_nodes if start <= m.timestamp < end]
        print(f"\n[Step 2/{sess_idx}] 会话 {session_id}：找到 {len(today_anchors)} 个今日锚点节点")

        node_results: list[dict] = []
        for node_idx, anchor_msg in enumerate(today_anchors, start=1):
            print(f"  [{node_idx}/{len(today_anchors)}] 触发锚点 #{anchor_msg.id} "
                  f"{anchor_msg.timestamp.strftime('%H:%M:%S')} "
                  f"{sanitize_text(anchor_msg.content or '')[:40]}")
            try:
                result = run_single_anchor(
                    session_id=session_id,
                    anchor_msg=anchor_msg,
                    all_messages=all_messages,
                    run_kb_eval=not args.skip_kb_eval,
                    date_str=args.date,
                )
                node_results.append(result)
                print(f"    -> 记录ID {result['record_id']}  状态={result['request_status']}")
            except Exception as exc:
                print(f"    [ERROR] {exc}")
                node_results.append({
                    "session_id": session_id,
                    "anchor_message_id": int(anchor_msg.id),
                    "anchor_message_time": anchor_msg.timestamp.isoformat(),
                    "anchor_message_text": sanitize_text(anchor_msg.content or ""),
                    "actual_sales_reply_text": "",
                    "record_id": None,
                    "snapshot_id": None,
                    "request_status": "error",
                    "result_payload": {},
                    "analytics_row": {},
                    "error": str(exc),
                })

        sessions_results.append({"session_id": session_id, "nodes": node_results})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_slug = args.date.replace("-", "")
    json_path = output_dir / f"企微{date_slug}_全节点批跑_{timestamp}.json"
    md_path = output_dir / f"企微{date_slug}_全节点批跑_{timestamp}.md"

    payload = {
        "date": args.date,
        "generated_at": datetime.now().isoformat(),
        "mode": "full_session_all_nodes",
        "selection_rule": {
            "sessions": args.sessions,
            "min_rounds": args.min_rounds,
            "max_rounds": args.max_rounds,
            "session_prefix": args.session_prefix,
            "consecutive_customer_last_only": True,
            "today_anchors_only": True,
        },
        "sessions": sessions_results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(build_report_markdown(args.date, sessions_results), encoding="utf-8")

    total_nodes = sum(len(s["nodes"]) for s in sessions_results)
    success_nodes = sum(1 for s in sessions_results for n in s["nodes"] if n.get("request_status") == "done")
    print(json.dumps({
        "status": "success",
        "date": args.date,
        "session_count": len(sessions_results),
        "total_nodes": total_nodes,
        "success_nodes": success_nodes,
        "json_report": str(json_path),
        "markdown_report": str(md_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
