"""
对 v3 run 中所有案例用 LLM-1 同时打分 AI 候选 + 销售原始回复，写回 step7_reply_scores。
幂等：ai_candidates[0] 和 actual_sales_replies[0] 均为 llm1_scored 则跳过。
可随时中断后续运行继续（逐条 commit）。
"""
import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    for l in open(p):
        l = l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, v = l.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import SessionLocal
from sqlalchemy import text
from intent_engine import IntentEngine

def _j(v):
    if v is None: return None
    if isinstance(v, (dict, list)): return v
    try: return json.loads(v)
    except: return None

db = SessionLocal()

row = db.execute(text("SELECT run_id FROM case_iteration_run WHERE version_no=3")).fetchone()
if not row:
    print("❌ 找不到 v3 run"); db.close(); sys.exit(1)
run_id = row[0]
print(f"v3 run_id = {run_id}\n")

results = db.execute(text(
    "SELECT r.result_id, r.scenario_code, r.scenario_rank, "
    "       r.step1_summary, r.step2_crm_info, r.step3_thread_business_fact, "
    "       r.step4_knowledge, r.step7_reply_styles, r.step7_reply_scores, "
    "       c.core_dialog "
    "FROM case_iteration_result r "
    "JOIN case_library_case c ON r.case_id = c.case_id "
    "WHERE r.run_id = :rid ORDER BY r.scenario_code, r.scenario_rank"
), {"rid": run_id}).fetchall()

print(f"共 {len(results)} 条，LLM-1 逐条打分 AI候选+销售回复（~20s/条）…\n")
done = skipped = failed = 0

for row in results:
    (result_id, sc, rank,
     step1_raw, step2_raw, step3_raw,
     step4_raw, styles_raw, step7_raw,
     dialog_raw) = row
    label = f"{sc}-{rank}"

    step1   = _j(step1_raw)  or {}
    step2   = _j(step2_raw)  or {}
    step3   = _j(step3_raw)  or {}
    step4   = _j(step4_raw)  or {}
    styles  = _j(styles_raw) or []
    step7   = _j(step7_raw)  or {}
    dialog  = _j(dialog_raw) or []

    # 幂等：AI 和 销售 都已有有效的 overall 分数则跳过
    ai_existing    = step7.get('ai_candidates') or []
    sales_existing = step7.get('actual_sales_replies') or []
    def _has_score(entry_list):
        if not entry_list: return False
        e = entry_list[0]
        if e.get('score_reason') == 'llm1_failed': return False
        return (e.get('scores') or {}).get('overall') is not None
    if _has_score(ai_existing) and _has_score(sales_existing):
        print(f"  ⏭ {label} 全部已打分，跳过")
        skipped += 1
        continue

    # 构建 AI 候选列表（来自 step7_reply_styles）
    candidates = []
    for s in (styles if isinstance(styles, list) else []):
        if not isinstance(s, dict): continue
        candidates.append({
            "candidate_id":      s.get("candidate_id"),
            "model_slot":        s.get("model_slot"),
            "model_label":       s.get("model_label"),
            "model_display_name":s.get("model_display_name"),
            "knowledge_source":  s.get("knowledge_source"),
            "knowledge_source_label": s.get("knowledge_source_label"),
            "style_id":          s.get("style_id"),
            "style_title":       s.get("style_title"),
            "reply_style":       s.get("reply_style"),
            "content":           s.get("reply_reference") or s.get("text") or s.get("content") or "",
            "status":            s.get("status") or "done",
        })

    # 提取触发点后第一条销售消息
    trigger = (step3.get('merged_facts') or {}).get('latest_customer_message') or ''
    trigger_idx = -1
    if trigger:
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get('role') == 'customer' and dialog[i].get('content') == trigger:
                trigger_idx = i; break

    reply_text = ''
    if trigger_idx >= 0:
        for i in range(trigger_idx + 1, len(dialog)):
            if dialog[i].get('role') == 'sales' and dialog[i].get('content'):
                reply_text = dialog[i]['content']; break
    if not reply_text:
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get('role') == 'sales' and dialog[i].get('content'):
                reply_text = dialog[i]['content']; break

    if not candidates and not reply_text:
        print(f"  ⚠ {label} 无 AI 候选且无销售回复，跳过")
        skipped += 1
        continue

    actual_list = [{'content': reply_text, 'id': 'actual_sales_0'}] if reply_text else []
    flag = '触发点' if trigger_idx >= 0 else '回退末条'

    # 构建 knowledge_payload
    knowledge_payload = {
        "knowledge_v2":          step4.get("knowledge_v2") or {},
        "knowledge_external_api":step4.get("knowledge_external_api") or {},
        "thread_business_fact":  step3,
        "hits":                  [],
    }

    t0 = time.time()
    try:
        scores_result = IntentEngine.score_reply_candidates(
            summary_json=step1,
            knowledge_payload=knowledge_payload,
            crm_context=step2,
            candidates=candidates,
            actual_sales_replies=actual_list,
        )
        elapsed = time.time() - t0

        ai_scored    = scores_result.get('ai_candidates') or []
        sales_scored = scores_result.get('actual_sales_replies') or []

        ai_ok    = bool(ai_scored    and ai_scored[0].get('score_reason') == 'llm1_scored')
        sales_ok = bool(sales_scored and sales_scored[0].get('score_reason') == 'llm1_scored')

        if not ai_ok and not sales_ok:
            print(f"  ✗ {label} LLM-1 失败（{elapsed:.1f}s）")
            failed += 1
        else:
            ai_overall    = (ai_scored[0].get('scores') or {}).get('overall') if ai_scored else None
            sales_overall = (sales_scored[0].get('scores') or {}).get('overall') if sales_scored else None
            print(f"  ✓ {label} ai={ai_overall} sales={sales_overall} ({flag}) ({elapsed:.1f}s)")
            done += 1

        step7_new = dict(step7)
        step7_new['ai_candidates']        = ai_scored
        step7_new['actual_sales_replies'] = sales_scored
        step7_new['best_ai_candidate_id'] = ai_scored[0]['candidate_id'] if ai_scored else None
        if scores_result.get('scored_by'):
            step7_new['scored_by']  = scores_result['scored_by']
        if scores_result.get('generated_at'):
            step7_new['generated_at'] = scores_result['generated_at']

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ✗ {label} 异常（{elapsed:.1f}s）: {e}")
        failed += 1
        # 失败时不覆盖已有的有效分数，直接跳过本条 DB 写入
        step7_new = None

    if step7_new is None:
        continue

    # 更新 step7_reply_scores 和 quality_score
    ai_list = step7_new.get('ai_candidates') or []
    new_quality = None
    if ai_list and ai_list[0].get('overall_score') is not None:
        new_quality = round(float(ai_list[0]['overall_score']), 2)

    if new_quality is not None:
        db.execute(text(
            "UPDATE case_iteration_result "
            "SET step7_reply_scores = :s, quality_score = :q "
            "WHERE result_id = :rid"
        ), {"s": json.dumps(step7_new, ensure_ascii=False), "q": new_quality, "rid": result_id})
    else:
        db.execute(text(
            "UPDATE case_iteration_result SET step7_reply_scores = :s WHERE result_id = :rid"
        ), {"s": json.dumps(step7_new, ensure_ascii=False), "rid": result_id})
    db.commit()

db.close()
print(f"\n✅ 完成：LLM-1成功 {done}，跳过 {skipped}，失败 {failed}")
