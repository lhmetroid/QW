import sys, os, json, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
from database import SessionLocal, CaseIterationRun, CaseIterationResult

DIMENSIONS = [
    {"key": "overall", "label": "总分"},
    {"key": "low_barrier", "label": "易回复"},
    {"key": "non_repetition", "label": "差异化"},
    {"key": "safety", "label": "稳妥度"},
    {"key": "conciseness", "label": "微信感"},
    {"key": "style_match", "label": "风格匹配"},
    {"key": "context_alignment", "label": "上下文贴合"},
]

# (scenario_rank, turn_no) -> (overall, conciseness, low_barrier, non_repetition, safety, style_match, context_alignment, reason)
SC = {
    (1, 1): (91, 90, 90, 92, 92, 90, 90, "承接自然，主动准备方案且不催促，语气亲和到位"),
    (1, 2): (88, 90, 88, 82, 92, 90, 88, "计划复述清晰，但与上一轮内容略重复"),
    (1, 3): (84, 85, 88, 72, 90, 88, 80, "内容与前两轮高度重复(先后次序/Priority1/对盘)，差异化不足，触发重复扣分"),
    (1, 4): (88, 85, 90, 92, 85, 88, 92, "直接给出4500具体报价并附质量背书+申请引导，针对性强；报价承诺略有风险"),
    (1, 5): (90, 90, 90, 90, 88, 88, 92, "确认价格并明确开工路径(发文件-确认格式)，决断清晰"),
    (2, 1): (91, 92, 88, 92, 92, 90, 88, "简洁顺畅地推进到电话沟通，语气自然"),
    (2, 2): (89, 90, 90, 92, 85, 90, 90, "确认含税开票并主动提供配合，针对性好；未点明6%税率略欠精确"),
    (2, 3): (90, 85, 90, 92, 90, 90, 92, "确认代寄并主动询问寄送地址数以便报价，推进有力"),
    (2, 4): (87, 85, 85, 90, 85, 88, 92, "坚持价格同时以赠送样书化解，比生硬拒绝更柔和；赠品承诺略有风险"),
    (2, 5): (89, 90, 88, 90, 90, 88, 90, "确认规格拆分并约定次日报成本，聚焦清晰不拖沓"),
}

db = SessionLocal()
try:
    run = db.query(CaseIterationRun).filter_by(version_no=9).first()
    print("v9 run_id:", run.run_id)
    results = db.query(CaseIterationResult).filter_by(run_id=run.run_id).all()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    for rr in results:
        key = (rr.scenario_rank, rr.turn_no)
        if key not in SC:
            print("  跳过(无评分):", rr.scenario_code, rr.scenario_rank, "T", rr.turn_no)
            continue
        ov, cc, lb, nr, sf, sm, ca, reason = SC[key]
        scores_flat = {
            "overall": ov, "low_barrier": lb, "non_repetition": nr, "safety": sf,
            "conciseness": cc, "style_match": sm, "context_alignment": ca,
        }
        candidate_id = "llm2__manual_scored"
        candidate = {
            "candidate_id": candidate_id,
            "model_slot": "llm2",
            "model_label": "主模型",
            "model_display_name": "LLM-2",
            "knowledge_source": "knowledge_v2",
            "knowledge_source_label": "知识库1",
            "style_id": "style_1",
            "style_title": "亲和微信风",
            "reply_text": rr.step6_sales_advice or "",
            "overall_score": ov,
            "scores": scores_flat,
            "score_reason": reason,
        }
        # 保留已有 step7_reply_scores 的其它键(如 actual_sales_replies)
        existing = rr.step7_reply_scores
        if isinstance(existing, str):
            try: existing = json.loads(existing)
            except Exception: existing = {}
        existing = existing or {}
        s7 = dict(existing)
        s7["generated_at"] = now
        s7["scored_by"] = {"model": "manual", "provider": "human", "score_mode": "manual"}
        s7["dimensions"] = DIMENSIONS
        s7["ai_candidates"] = [candidate]
        s7["best_ai_candidate_id"] = candidate_id
        s7.setdefault("actual_sales_replies", existing.get("actual_sales_replies", []))

        rr.step7_reply_scores = s7
        rr.quality_score = float(ov)
        print(f"  {rr.scenario_code}-{rr.scenario_rank} T{rr.turn_no}: AI质量分={ov}  {scores_flat}")
    db.commit()
    print("v9 AI 质量分写入完成。")
finally:
    db.close()
