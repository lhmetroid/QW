"""
重新提取销售原始回复（触发点后第一条）并更新 v3 run 中的 actual_sales_replies。
触发点 = step3_thread_business_fact.merged_facts.latest_customer_message
取 core_dialog 中触发点之后的第一条 role=sales 消息。
"""
import sys, os, io, json
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

# 取 v3 run_id
row = db.execute(text("SELECT run_id FROM case_iteration_run WHERE version_no=3")).fetchone()
if not row:
    print("❌ 找不到 v3 run"); db.close(); sys.exit(1)
run_id = row[0]
print(f"v3 run_id = {run_id}")

# 读全部结果
results = db.execute(text(
    "SELECT r.result_id, r.step3_thread_business_fact, r.step7_reply_scores, "
    "       c.core_dialog, r.scenario_code, r.scenario_rank "
    "FROM case_iteration_result r "
    "JOIN case_library_case c ON r.case_id = c.case_id "
    "WHERE r.run_id = :rid"
), {"rid": run_id}).fetchall()

print(f"共 {len(results)} 条结果，开始重新提取销售原始回复…\n")

updated = 0
no_trigger = 0
no_reply = 0

for row in results:
    result_id, step3_raw, step7_raw, core_dialog_raw, sc, rank = row

    # 解析 JSON
    step3 = step3_raw if isinstance(step3_raw, dict) else (json.loads(step3_raw) if step3_raw else {})
    step7 = step7_raw if isinstance(step7_raw, dict) else (json.loads(step7_raw) if step7_raw else {})
    dialog = core_dialog_raw if isinstance(core_dialog_raw, list) else (json.loads(core_dialog_raw) if core_dialog_raw else [])

    # 取触发点
    trigger = (step3.get('merged_facts') or {}).get('latest_customer_message') or ''

    # 找触发点在 dialog 中的最后位置
    trigger_idx = -1
    if trigger:
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get('role') == 'customer' and dialog[i].get('content') == trigger:
                trigger_idx = i
                break

    if trigger_idx < 0:
        # 没找到触发点，取最后一条 sales 消息
        reply_text = ''
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get('role') == 'sales' and dialog[i].get('content'):
                reply_text = dialog[i]['content']
                break
        no_trigger += 1
        trigger_used = False
    else:
        # 找触发点后第一条 sales 消息
        reply_text = ''
        for i in range(trigger_idx + 1, len(dialog)):
            if dialog[i].get('role') == 'sales' and dialog[i].get('content'):
                reply_text = dialog[i]['content']
                break
        trigger_used = True

    if not reply_text:
        no_reply += 1
        continue

    # 用 7 维启发式打分
    try:
        scores_result = IntentEngine.score_reply_candidates(
            summary_json=None,
            knowledge_payload={"hits": []},
            crm_context=None,
            candidates=[],
            actual_sales_replies=[{'content': reply_text, 'id': 'actual_sales_0'}],
            skip_llm=True,
        )
        actual_scored = scores_result.get('actual_sales_replies') or []
    except Exception as e:
        print(f"  ⚠ {sc}-{rank} 打分异常：{e}")
        actual_scored = [{'reply_text': reply_text, 'overall_score': None}]

    # 合并回 step7_reply_scores
    step7['actual_sales_replies'] = actual_scored

    db.execute(text(
        "UPDATE case_iteration_result SET step7_reply_scores = :s WHERE result_id = :rid"
    ), {"s": json.dumps(step7, ensure_ascii=False), "rid": result_id})

    score = (actual_scored[0].get('scores') or {}).get('overall') if actual_scored else None
    flag = '✓' if trigger_used else '（无触发点，取最后）'
    print(f"  {sc}-{rank} {flag} reply={reply_text[:40]!r} overall={score}")
    updated += 1

db.commit()
db.close()

print(f"\n✅ 完成：更新 {updated} 条；无触发点 {no_trigger} 条；无回复 {no_reply} 条")
