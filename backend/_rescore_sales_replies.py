"""
对 v3 run 中所有案例重新提取销售原始回复并用 LLM-1 打 7 维分，写回 actual_sales_replies。
幂等：score_reason == 'llm1_scored' 的条目自动跳过，可随时中断后续运行继续。
触发点 = step3_thread_business_fact.merged_facts.latest_customer_message
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

db = SessionLocal()

row = db.execute(text("SELECT run_id FROM case_iteration_run WHERE version_no=3")).fetchone()
if not row:
    print("❌ 找不到 v3 run"); db.close(); sys.exit(1)
run_id = row[0]
print(f"v3 run_id = {run_id}\n")

results = db.execute(text(
    "SELECT r.result_id, r.step3_thread_business_fact, r.step7_reply_scores, "
    "       c.core_dialog, r.scenario_code, r.scenario_rank "
    "FROM case_iteration_result r "
    "JOIN case_library_case c ON r.case_id = c.case_id "
    "WHERE r.run_id = :rid ORDER BY r.scenario_code, r.scenario_rank"
), {"rid": run_id}).fetchall()

print(f"共 {len(results)} 条，LLM-1 逐条打分（~18s/条）…\n")
done = skipped = failed = 0

for row in results:
    result_id, step3_raw, step7_raw, core_dialog_raw, sc, rank = row
    label = f"{sc}-{rank}"

    step3  = step3_raw  if isinstance(step3_raw,  dict) else (json.loads(step3_raw)  if step3_raw  else {})
    step7  = step7_raw  if isinstance(step7_raw,  dict) else (json.loads(step7_raw)  if step7_raw  else {})
    dialog = core_dialog_raw if isinstance(core_dialog_raw, list) else (json.loads(core_dialog_raw) if core_dialog_raw else [])

    # 幂等：已有 llm1_scored 则跳过
    existing = step7.get('actual_sales_replies') or []
    if existing and existing[0].get('score_reason') == 'llm1_scored':
        print(f"  ⏭ {label} 已有 LLM-1 分，跳过")
        skipped += 1
        continue

    # 提取触发点后第一条销售消息
    trigger = (step3.get('merged_facts') or {}).get('latest_customer_message') or ''
    trigger_idx = -1
    if trigger:
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get('role') == 'customer' and dialog[i].get('content') == trigger:
                trigger_idx = i
                break

    reply_text = ''
    if trigger_idx >= 0:
        for i in range(trigger_idx + 1, len(dialog)):
            if dialog[i].get('role') == 'sales' and dialog[i].get('content'):
                reply_text = dialog[i]['content']
                break
    if not reply_text:
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get('role') == 'sales' and dialog[i].get('content'):
                reply_text = dialog[i]['content']
                break

    if not reply_text:
        print(f"  ⚠ {label} 无销售消息，跳过")
        skipped += 1
        continue

    flag = '✓触发点' if trigger_idx >= 0 else '（无触发点回退）'

    t0 = time.time()
    try:
        scores_result = IntentEngine.score_reply_candidates(
            summary_json=None,
            knowledge_payload={"hits": [], "thread_business_fact": step3},
            crm_context=None,
            candidates=[],
            actual_sales_replies=[{'content': reply_text, 'id': 'actual_sales_0'}],
        )
        actual_scored = scores_result.get('actual_sales_replies') or []
        elapsed = time.time() - t0

        if actual_scored and actual_scored[0].get('score_reason') == 'llm1_failed':
            print(f"  ✗ {label} LLM-1 失败（{elapsed:.1f}s）: reply={reply_text[:40]!r}")
            failed += 1
            step7['actual_sales_replies'] = actual_scored
        else:
            overall = (actual_scored[0].get('scores') or {}).get('overall') if actual_scored else None
            print(f"  ✓ {label} {flag} overall={overall} ({elapsed:.1f}s) reply={reply_text[:40]!r}")
            step7['actual_sales_replies'] = actual_scored
            done += 1

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ✗ {label} 异常（{elapsed:.1f}s）: {e}")
        failed += 1
        step7['actual_sales_replies'] = [{'content': reply_text, 'score_reason': 'llm1_failed', 'overall_score': None, 'scores': None}]

    db.execute(text(
        "UPDATE case_iteration_result SET step7_reply_scores = :s WHERE result_id = :rid"
    ), {"s": json.dumps(step7, ensure_ascii=False), "rid": result_id})
    db.commit()

db.close()
print(f"\n✅ 完成：LLM-1成功 {done}，跳过 {skipped}，失败 {failed}")
