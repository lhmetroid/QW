"""查明actual_sales_replies结构和质量分偏差"""
import os, sys, json, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    with open(p) as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith('#') or '=' not in l: continue
            k, v = l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import engine
from sqlalchemy import text

run_id = 'caf54fdf-21d4-4732-8963-d548d2d0da2c'

with engine.connect() as conn:
    # === actual_sales_replies 详细内容 ===
    print('=== 1. actual_sales_replies 实际内容 ===')
    for sc_t, rank_t in [('S05', 1), ('S01', 1), ('S11', 1)]:
        row = conn.execute(text('''
            SELECT r.scenario_code, r.scenario_rank,
                   r.step7_reply_scores::text AS rs_raw
            FROM case_iteration_result r
            WHERE r.run_id = :rid AND r.scenario_code = :sc AND r.scenario_rank = :rank
        '''), {'rid': run_id, 'sc': sc_t, 'rank': rank_t}).fetchone()
        if not row: continue
        sc, rank, rs_raw = row
        rs = json.loads(rs_raw) if rs_raw else {}
        v2 = rs.get('reply_scores_v2') or rs
        actual = v2.get('actual_sales_replies') or []
        print(f'\n{sc}-{rank}: actual_sales_replies={len(actual)}个')
        for s in actual:
            print(f'  keys: {list(s.keys())}')
            print(f'  overall_score={s.get("overall_score")}')
            print(f'  scores={s.get("scores")}')
            print(f'  score_reason={s.get("score_reason")}')
            print(f'  content({len(s.get("content",""))}字): {(s.get("content") or "")[:100]}')

    # === 统计actual_sales_replies中overall_score情况 ===
    print('\n=== 2. 全60案例actual_sales_replies评分统计 ===')
    rows = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank,
               r.step7_reply_scores::text AS rs_raw
        FROM case_iteration_result r
        WHERE r.run_id = :rid
        ORDER BY r.scenario_code, r.scenario_rank
    '''), {'rid': run_id}).fetchall()

    has_sales_score = 0
    no_sales_score = 0
    llm1_failed_sales = 0
    sales_score_list = []
    for row in rows:
        sc, rank, rs_raw = row
        rs = json.loads(rs_raw) if rs_raw else {}
        v2 = rs.get('reply_scores_v2') or rs
        actual = v2.get('actual_sales_replies') or []
        if not actual:
            no_sales_score += 1
            continue
        for s in actual:
            ov = s.get('overall_score')
            reason = s.get('score_reason', '')
            if ov is not None:
                has_sales_score += 1
                sales_score_list.append({'case': f'{sc}-{rank}', 'score': ov,
                                         'content': (s.get('content') or '')[:80],
                                         'scores': s.get('scores')})
            elif 'llm1_failed' in str(reason):
                llm1_failed_sales += 1
            else:
                no_sales_score += 1
    print(f'  有销售分: {has_sales_score}, 无销售分(llm1_failed): {llm1_failed_sales}, 无销售分(空/其他): {no_sales_score}')
    if sales_score_list:
        for item in sales_score_list[:5]:
            print(f'  {item["case"]}: {item["score"]}分 | {item["content"]}')
            if item["scores"]:
                s = item["scores"]
                print(f'    conc={s.get("conciseness")} low={s.get("low_barrier")} safe={s.get("safety")}')

    # === overall_score vs formula 差距分析（全49个有分案例）===
    print('\n=== 3. stored_overall vs formula 全量差距分析 ===')
    rows = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank, r.quality_score,
               r.step7_reply_scores::text AS rs_raw
        FROM case_iteration_result r
        WHERE r.run_id = :rid AND r.quality_score IS NOT NULL
        ORDER BY r.quality_score DESC
    '''), {'rid': run_id}).fetchall()

    total_diff = 0
    inflated_count = 0
    deflated_count = 0
    all_diffs = []
    for row in rows:
        sc, rank, qs, rs_raw = row
        rs = json.loads(rs_raw) if rs_raw else {}
        v2 = rs.get('reply_scores_v2') or rs
        ai_cands = v2.get('ai_candidates') or []
        for c in ai_cands:
            ov = c.get('overall_score')
            scores = c.get('scores') or {}
            if ov is None or not scores: continue
            conc = scores.get('conciseness', 0) or 0
            low  = scores.get('low_barrier', 0) or 0
            nonr = scores.get('non_repetition', 0) or 0
            safe = scores.get('safety', 0) or 0
            styl = scores.get('style_match', 0) or 0
            ctx  = scores.get('context_alignment', 0) or 0
            formula = int(max(0, min(100, round(conc*0.18 + low*0.24 + nonr*0.22 + safe*0.22 + styl*0.08 + ctx*0.06))))
            diff = ov - formula
            all_diffs.append(diff)
            total_diff += diff
            if diff > 2: inflated_count += 1
            elif diff < -2: deflated_count += 1

    print(f'  有效对比: {len(all_diffs)}个')
    print(f'  平均差: stored - formula = {total_diff/len(all_diffs):.2f}')
    print(f'  偏高(>2分): {inflated_count}个, 偏低(<-2分): {deflated_count}个, 吻合: {len(all_diffs)-inflated_count-deflated_count}个')

    # 分析conciseness评分问题
    print('\n=== 4. conciseness分数 vs 实际字数矛盾（重点！）===')
    rows = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank,
               r.step7_reply_scores::text AS rs_raw
        FROM case_iteration_result r
        WHERE r.run_id = :rid AND r.quality_score IS NOT NULL
        ORDER BY r.scenario_code, r.scenario_rank
    '''), {'rid': run_id}).fetchall()

    problems = []
    for row in rows:
        sc, rank, rs_raw = row
        rs = json.loads(rs_raw) if rs_raw else {}
        v2 = rs.get('reply_scores_v2') or rs
        ai_cands = v2.get('ai_candidates') or []
        for c in ai_cands:
            ov = c.get('overall_score')
            scores = c.get('scores') or {}
            reply_text = c.get('reply_text', '')
            if ov is None or not scores: continue
            conc = scores.get('conciseness', 0) or 0
            chars = len(reply_text)
            # 按规则：≤50字应能得80+，但给了60
            if chars <= 50 and conc < 75:
                problems.append({'case': f'{sc}-{rank}', 'chars': chars, 'conc': conc,
                                  'overall': ov, 'reply': reply_text[:80]})

    print(f'  字数≤50但conciseness<75分（应高却偏低）: {len(problems)}个')
    for p in problems:
        print(f'  {p["case"]}: {p["chars"]}字 conc={p["conc"]} overall={p["overall"]}')
        print(f'    回复: {p["reply"]}')
