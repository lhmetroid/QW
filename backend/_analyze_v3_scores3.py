"""查明: 1.11个llm1_failed案例DB中quality_score实际值  2.销售分为何全空  3.overall公式验证"""
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
    # === 1. 直接查11个llm1_failed案例的DB quality_score ===
    print('=== 1. 11个llm1_failed案例的DB字段 ===')
    rows = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank, r.quality_score,
               r.quality_status, r.kb1_eval_score, r.kb2_eval_score
        FROM case_iteration_result r
        WHERE r.run_id = :rid
          AND r.scenario_code || '-' || r.scenario_rank IN
              ('S06-3','S06-5','S02-4','S05-2','S07-2','S07-3','S06-4','S03-2','S07-1','S03-3','S03-1')
        ORDER BY r.quality_score DESC NULLS LAST
    '''), {'rid': run_id}).fetchall()
    for row in rows:
        sc, rank, qs, qst, kb1, kb2 = row
        print(f'  {sc}-{rank}: quality_score={qs} kb1={kb1} kb2={kb2} status={qst}')

    # === 2. 检验overall公式是否和stored_score吻合 ===
    print('\n=== 2. formula验证（已评分的49个案例样本）===')
    rows2 = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank, r.quality_score,
               r.step7_reply_scores::text AS rs_raw
        FROM case_iteration_result r
        WHERE r.run_id = :rid
        ORDER BY r.quality_score DESC NULLS LAST
        LIMIT 20
    '''), {'rid': run_id}).fetchall()

    mismatches = []
    for row in rows2:
        sc, rank, qs, rs_raw = row
        try:
            rs = json.loads(rs_raw) if rs_raw else {}
            v2 = rs.get('reply_scores_v2') or rs
            ai_cands = v2.get('ai_candidates') or []
            for c in ai_cands:
                ov = c.get('overall_score')
                scores = c.get('scores') or {}
                if ov is None or not scores: continue
                # recalculate formula
                conc = scores.get('conciseness', 0) or 0
                low  = scores.get('low_barrier', 0) or 0
                nonr = scores.get('non_repetition', 0) or 0
                safe = scores.get('safety', 0) or 0
                styl = scores.get('style_match', 0) or 0
                ctx  = scores.get('context_alignment', 0) or 0
                formula_val = conc*0.18 + low*0.24 + nonr*0.22 + safe*0.22 + styl*0.08 + ctx*0.06
                formula_int = int(max(0, min(100, round(formula_val))))
                reply_text = c.get('reply_text', '')
                print(f'  {sc}-{rank}: stored={ov} formula={formula_int} diff={ov-formula_int}'
                      f'  chars={len(reply_text)} conc={conc}')
                if abs(ov - formula_int) > 2:
                    mismatches.append({'case': f'{sc}-{rank}', 'stored': ov, 'formula': formula_int,
                                       'diff': ov-formula_int, 'conc': conc, 'chars': len(reply_text)})
        except Exception as e:
            print(f'  {sc}-{rank} err: {e}')

    if mismatches:
        print(f'\n  差距>2分的有 {len(mismatches)} 个:')
        for m in mismatches:
            print(f'    {m}')

    # === 3. 销售分为空：检查_caselib_run_real是否传入了actual_sales_replies ===
    print('\n=== 3. step7_reply_scores中actual_sales_replies字段 ===')
    row = conn.execute(text('''
        SELECT r.step7_reply_scores::text
        FROM case_iteration_result r
        WHERE r.run_id = :rid AND r.scenario_code = 'S05' AND r.scenario_rank = 1
    '''), {'rid': run_id}).fetchone()
    if row and row[0]:
        rs = json.loads(row[0])
        v2 = rs.get('reply_scores_v2') or rs
        actual = v2.get('actual_sales_replies') or []
        print(f'  actual_sales_replies in reply_scores_v2: {len(actual)}个')
        print(f'  reply_scores_v2 全部keys: {list(v2.keys())}')

    # === 4. 重点: 高分案例回复质量分析（手工维度验证）===
    print('\n=== 4. 全部评分案例详细内容（按分降序）===')
    rows4 = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank, r.quality_score,
               r.step7_reply_scores::text AS rs_raw,
               r.step1_summary::text AS sum_raw
        FROM case_iteration_result r
        WHERE r.run_id = :rid
        ORDER BY r.quality_score DESC NULLS LAST
        LIMIT 30
    '''), {'rid': run_id}).fetchall()

    for row in rows4:
        sc, rank, qs, rs_raw, sum_raw = row
        if qs is None: break
        try:
            rs = json.loads(rs_raw) if rs_raw else {}
            v2 = rs.get('reply_scores_v2') or rs
            ai_cands = v2.get('ai_candidates') or []
            s = json.loads(sum_raw) if sum_raw else {}
            demand = (s.get('core_demand') or '')[:40]
            best = max((c for c in ai_cands if c.get('overall_score') is not None),
                       key=lambda c: c['overall_score'], default=None)
            if not best: continue
            scores = best.get('scores') or {}
            reply_text = best.get('reply_text', '')
            conc = scores.get('conciseness', 0) or 0
            low = scores.get('low_barrier', 0) or 0
            # formula
            nonr = scores.get('non_repetition', 0) or 0
            safe = scores.get('safety', 0) or 0
            styl = scores.get('style_match', 0) or 0
            ctx = scores.get('context_alignment', 0) or 0
            formula = int(round(conc*0.18 + low*0.24 + nonr*0.22 + safe*0.22 + styl*0.08 + ctx*0.06))
            print(f'\n  {sc}-{rank}: stored={qs} formula={formula} chars={len(reply_text)}')
            print(f'  需求: {demand}')
            print(f'  回复: {reply_text[:120]}')
            print(f'  conc={conc} low={low} nonrep={nonr} safe={safe} style={styl} ctx={ctx}')
        except Exception as e:
            print(f'  {sc}-{rank} err: {e}')
