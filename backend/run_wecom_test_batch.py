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

TRIVIAL_ANCHOR_TEXTS = {
    "ok",
    "okay",
    "好的",
    "好滴",
    "收到",
    "谢谢",
    "谢谢您",
    "木有哎",
    "哪个？",
    "哪个?",
    "[thumbsup]",
    "[图片消息]",
    "[voiptext类型报文]",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量重跑 2026-05-11 企微历史客户节点，并记录为测试触发。")
    parser.add_argument("--date", default="2026-05-11", help="要分析的日期，格式 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=10, help="最多挑选多少条节点")
    parser.add_argument("--max-per-session", type=int, default=2, help="同一会话最多保留多少条节点")
    parser.add_argument("--session-prefix", default="single_", help="筛选的会话前缀，默认仅单聊")
    parser.add_argument("--skip-kb-eval", action="store_true", help="跳过知识库评估 API 打分")
    parser.add_argument("--output-dir", default="", help="报告输出目录，默认写入测试数据/企微511测试触发")
    return parser.parse_args()


def parse_day(day_text: str) -> tuple[datetime, datetime]:
    day = datetime.fromisoformat(day_text[:10])
    return day, day + timedelta(days=1)


def normalize_anchor_text(text: str) -> str:
    value = sanitize_text(text or "").strip()
    return value.lower()


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


def score_candidate(*, anchor_text: str, visible_count: int, reply_count: int, reply_text: str) -> float:
    text = sanitize_text(anchor_text or "")
    score = float(len(text))
    score += min(visible_count, 15) * 2.0
    score += min(reply_count, 4) * 8.0
    score += min(len(reply_text), 120) * 0.2
    score += sum(text.count(ch) for ch in "？?。！!；;：:") * 3.0
    if any(keyword in text for keyword in ("报价", "付款", "开票", "预算", "排版", "PPT", "资料", "老师", "设备")):
        score += 8.0
    return round(score, 2)


def select_candidates(
    *,
    start: datetime,
    end: datetime,
    limit: int,
    max_per_session: int,
    session_prefix: str,
) -> list[dict]:
    db = SessionLocal()
    try:
        api_keys = {
            (row.session_id, int(row.anchor_message_id or 0))
            for row in db.query(ApiAssistInvocation.session_id, ApiAssistInvocation.anchor_message_id).all()
            if row.anchor_message_id
        }
        customer_msgs = db.query(MessageLog).filter(
            MessageLog.timestamp >= start,
            MessageLog.timestamp < end,
            MessageLog.is_mock.is_(False),
            MessageLog.sender_type == "customer",
            MessageLog.user_id.like(f"{session_prefix}%"),
        ).order_by(MessageLog.timestamp.asc(), MessageLog.id.asc()).all()
        session_ids = sorted({item.user_id for item in customer_msgs})
        all_messages_by_session: dict[str, list[MessageLog]] = {}
        if session_ids:
            all_logs = db.query(MessageLog).filter(
                MessageLog.is_mock.is_(False),
                MessageLog.user_id.in_(session_ids),
            ).order_by(MessageLog.user_id.asc(), MessageLog.id.asc()).all()
            for log in all_logs:
                all_messages_by_session.setdefault(log.user_id, []).append(log)

        scored: list[dict] = []
        for msg in customer_msgs:
            key = (msg.user_id, int(msg.id))
            if key in api_keys:
                continue
            if not is_meaningful_anchor(msg.content or ""):
                continue
            all_messages = all_messages_by_session.get(msg.user_id) or []
            visible_messages = _visible_messages_until_anchor(all_messages, int(msg.id))
            actual_sales_replies = _collect_actual_sales_replies(all_messages, int(msg.id))
            if not actual_sales_replies:
                continue
            reply_text = _reply_block_text(actual_sales_replies, strip_noise=True)
            if not sanitize_text(reply_text).strip():
                continue
            first_reply_time = actual_sales_replies[0].get("time")
            if not str(first_reply_time or "").startswith(start.date().isoformat()):
                continue
            scored.append({
                "session_id": msg.user_id,
                "anchor_message_id": int(msg.id),
                "anchor_message_time": msg.timestamp.isoformat(),
                "anchor_message_text": sanitize_text(msg.content or ""),
                "visible_count": len(visible_messages),
                "reply_count": len(actual_sales_replies),
                "actual_sales_reply_text": reply_text,
                "score": score_candidate(
                    anchor_text=msg.content or "",
                    visible_count=len(visible_messages),
                    reply_count=len(actual_sales_replies),
                    reply_text=reply_text,
                ),
            })

        scored.sort(key=lambda item: (item["score"], item["anchor_message_time"]), reverse=True)
        selected: list[dict] = []
        per_session = Counter()
        for item in scored:
            if per_session[item["session_id"]] >= max_per_session:
                continue
            selected.append(item)
            per_session[item["session_id"]] += 1
            if len(selected) >= limit:
                break
        return selected
    finally:
        db.close()


def ensure_snapshot(session_id: str, anchor_message_id: int) -> str:
    db = SessionLocal()
    try:
        all_messages = db.query(MessageLog).filter(
            MessageLog.user_id == session_id,
            MessageLog.is_mock.is_(False),
        ).order_by(MessageLog.id.asc()).all()
        anchor_message = next((item for item in all_messages if int(item.id) == int(anchor_message_id)), None)
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


def run_single_candidate(candidate: dict, *, run_kb_eval: bool) -> dict:
    session_id = candidate["session_id"]
    anchor_message_id = int(candidate["anchor_message_id"])
    snapshot_id = ensure_snapshot(session_id, anchor_message_id)
    record_id = _create_wecom_trigger_record(
        session_id=session_id,
        snapshot_id=snapshot_id,
        run_id=uuid.uuid4().hex[:12],
        trigger_source="test",
        trigger_kind="batch_test_full_run",
        request_status="running",
        request_payload={
            "mode": "batch_test_full_run",
            "date": candidate["anchor_message_time"][:10],
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
            result_payload = _build_analysis_result_for_target(
                db,
                session_id=session_id,
                snapshot_id=snapshot_id,
            )
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
            "candidate": candidate,
            "record_id": str(record.record_id),
            "snapshot_id": snapshot_id,
            "request_status": record.request_status,
            "result_payload": result_payload,
            "analytics_row": analytics_row,
        }
    finally:
        db.close()


def build_summary_keywords(rows: list[dict]) -> list[tuple[str, int]]:
    keywords = ["报价", "付款", "开票", "预算", "排版", "PPT", "资料", "老师", "设备", "翻译", "交稿"]
    counter = Counter()
    for row in rows:
        payload = row.get("result_payload") or {}
        text = " ".join(
            sanitize_text(str(item or ""))
            for item in [
                row.get("candidate", {}).get("anchor_message_text"),
                payload.get("topic"),
                payload.get("core_demand"),
                payload.get("status"),
            ]
        )
        for keyword in keywords:
            if keyword in text:
                counter[keyword] += 1
    return counter.most_common()


def build_report_markdown(day_text: str, rows: list[dict]) -> str:
    analytics_rows = [item["analytics_row"] for item in rows]
    manual_business_scores = [float(item["manual_business_score"]) for item in analytics_rows if item.get("manual_business_score") is not None]
    manual_scores = [float(item["manual_quality_score"]) for item in analytics_rows if item.get("manual_quality_score") is not None]
    kb1_scores = [float(item["kb1_eval_score"]) for item in analytics_rows if item.get("kb1_eval_score") is not None]
    kb2_scores = [float(item["kb2_eval_score"]) for item in analytics_rows if item.get("kb2_eval_score") is not None]
    better_kb2 = 0
    for item in analytics_rows:
        left = item.get("step_6_main_kb1_score")
        right = item.get("step_6_main_kb2_score")
        if right is not None and (left is None or float(right) > float(left)):
            better_kb2 += 1
    keywords = build_summary_keywords(rows)
    reply_types = Counter()
    low_quality_cases = []
    for row in rows:
        payload = row.get("result_payload") or {}
        key_facts = payload.get("key_facts") if isinstance(payload.get("key_facts"), dict) else {}
        reply_type = str(key_facts.get("latest_customer_reply_type") or "").strip() or "unknown"
        reply_types[reply_type] += 1
        manual_score = row["analytics_row"].get("manual_business_score")
        if manual_score is not None and float(manual_score) < 80:
            low_quality_cases.append(row)

    lines = [
        f"# 企微 2026-05-11 测试触发批量回放报告",
        "",
        "## 执行范围",
        f"- 日期：`{day_text}`",
        f"- 触发来源：`test`",
        f"- 节点数：`{len(rows)}`",
        f"- 平均人工业务质量分：`{round(sum(manual_business_scores) / len(manual_business_scores), 2) if manual_business_scores else '-'} `",
        f"- 平均人工贴合代理分：`{round(sum(manual_scores) / len(manual_scores), 2) if manual_scores else '-'} `",
        f"- 平均知识库1评估分：`{round(sum(kb1_scores) / len(kb1_scores), 2) if kb1_scores else '-'} `",
        f"- 平均知识库2评估分：`{round(sum(kb2_scores) / len(kb2_scores), 2) if kb2_scores else '-'} `",
        f"- 知识库2主候选优于知识库1的节点数：`{better_kb2}`",
        "",
        "## 场景分布",
        f"- 高频关键词：`{', '.join(f'{key}:{value}' for key, value in keywords[:8]) or '-'}`",
        f"- 最新客户回复类型：`{', '.join(f'{key}:{value}' for key, value in reply_types.items()) or '-'}`",
        "",
        "## 逐条结果",
    ]
    for index, item in enumerate(rows, start=1):
        candidate = item["candidate"]
        analytics = item["analytics_row"]
        payload = item["result_payload"] or {}
        lines.extend([
            f"### {index}. {candidate['session_id']} / 锚点 {candidate['anchor_message_id']}",
            f"- 触发记录：`{item['record_id']}`",
            f"- 锚点时间：`{candidate['anchor_message_time'].replace('T', ' ')[:19]}`",
            f"- 客户节点：{candidate['anchor_message_text']}",
            f"- 人工回复：{sanitize_text(candidate['actual_sales_reply_text']) or '-'}",
            f"- 摘要结论：主题=`{sanitize_text(str(payload.get('topic') or '-'))}`；诉求=`{sanitize_text(str(payload.get('core_demand') or '-'))}`；状态=`{sanitize_text(str(payload.get('status') or '-'))}`",
            f"- 阶段耗时：输入=`{analytics.get('step_1_time_ms')}`ms；FastTrack=`{analytics.get('step_2_time_ms')}`ms；LLM1=`{analytics.get('step_3_time_ms')}`ms；CRM=`{analytics.get('step_4_time_ms')}`ms；KB1=`{analytics.get('step_5_kb1_time_ms')}`ms；KB2=`{analytics.get('step_5_kb2_time_ms')}`ms；LLM2总=`{analytics.get('step_6_time_ms')}`ms；校验=`{analytics.get('step_7_time_ms')}`ms",
            f"- 评分结论：人工业务质量=`{analytics.get('manual_business_score')}`；人工贴合代理分=`{analytics.get('manual_quality_score')}`；知识库1评估=`{analytics.get('kb1_eval_score')}`；知识库2评估=`{analytics.get('kb2_eval_score')}`",
            f"- 主候选(KB1)：{sanitize_text(str(analytics.get('step_6_main_kb1_content') or '-'))}",
            f"- 主候选(KB2)：{sanitize_text(str(analytics.get('step_6_main_kb2_content') or '-'))}",
            "",
        ])

    lines.extend([
        "## 下一步优化建议",
        f"1. 先补场景治理。当前样本关键词以 `{', '.join(key for key, _ in keywords[:4]) or '业务执行'}` 为主，说明 5 月 11 日高价值节点不全是标准销售问答，包含大量交付推进/资料协同场景。建议在线程事实层新增 `交付推进 / 文件排版 / 预算待批 / 付款开票` 明确场景标签，再按场景切换提示词和回复模板。",
        f"2. 强化低负担承接规则。最新客户回复类型里 `{', '.join(f'{key}:{value}' for key, value in reply_types.items())}` 若以确认类、补充类居多，模型应更少追问，更多做承接、确认下一步和降低回复门槛。",
        f"3. 用人工实发反哺候选。当前人工业务质量低于 80 分的节点数为 `{len(low_quality_cases)}`。建议把这些节点的人工回复块回流成“高质量回复片段/场景 SOP”，尤其是人工明显更短、更直接的情况。",
        f"4. 对比两路知识库命中差异。知识库2主候选优于知识库1的节点数为 `{better_kb2}`。若该值偏高，说明内部知识库在部分场景的覆盖、切片或标签仍弱，优先补入本次 10 条中的高分人工回复及其上下文。",
        "5. 持续保存阶段耗时。现在测试触发已经会自动回写完整 `result_payload` 和各阶段耗时，后续可直接按同样脚本扩展到更多日期，建立按场景、按销售、按知识源的质量/耗时对照基线。",
    ])
    return "\n".join(lines)


def resolve_output_dir(raw_value: str) -> Path:
    if raw_value:
        return Path(raw_value).resolve()
    return Path(__file__).resolve().parent.parent / "测试数据" / "企微511测试触发"


def main() -> None:
    args = parse_args()
    start, end = parse_day(args.date)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = select_candidates(
        start=start,
        end=end,
        limit=args.limit,
        max_per_session=args.max_per_session,
        session_prefix=args.session_prefix,
    )
    if not candidates:
        raise RuntimeError(f"{args.date} 未找到符合条件的企微历史节点")

    results = []
    for index, candidate in enumerate(candidates, start=1):
        print(f"[{index}/{len(candidates)}] 运行 {candidate['session_id']}#{candidate['anchor_message_id']} ...")
        results.append(run_single_candidate(candidate, run_kb_eval=not args.skip_kb_eval))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"企微{args.date.replace('-', '')}_测试触发批跑_{timestamp}.json"
    md_path = output_dir / f"企微{args.date.replace('-', '')}_测试触发批跑_{timestamp}.md"
    payload = {
        "date": args.date,
        "generated_at": datetime.now().isoformat(),
        "selection_rule": {
            "limit": args.limit,
            "max_per_session": args.max_per_session,
            "session_prefix": args.session_prefix,
            "excluded_existing_api_invocations": True,
            "meaningful_anchor_filter": True,
        },
        "rows": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(build_report_markdown(args.date, results), encoding="utf-8")
    print(json.dumps({
        "status": "success",
        "date": args.date,
        "row_count": len(results),
        "json_report": str(json_path),
        "markdown_report": str(md_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
