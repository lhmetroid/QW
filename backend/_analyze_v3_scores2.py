"""深度分析v3: 11个ai=None案例的真实结构 + 销售分为空原因"""
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
    rows = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank, r.quality_score,
               r.step7_reply_scores::text AS rs_raw,
               r.quality_status, r.stage_status::text AS stage_raw
        FROM case_iteration_result r
        WHERE r.run_id = :rid
        ORDER BY r.quality_score DESC NULLS LAST
    '''), {'rid': run_id}).fetchall()

    # === 分析11个"ai候选有但无overall_score"案例 ===
    print('=== 1. AI候选有但overall_score为空的11个案例（分数从何来）===\n')
    for row in rows:
        sc, rank, qs, rs_raw, qst, stage_raw = row
        try:
            rs = json.loads(rs_raw) if rs_raw else {}
            v2 = rs.get('reply_scores_v2') or rs
            ai_cands = v2.get('ai_candidates') or []
            has_score = any(c.get('overall_score') is not None for c in ai_cands)
            if not has_score and ai_cands:
                print(f'--- {sc}-{rank}: qs={qs} ---')
                c = ai_cands[0]
                print(f'  candidate_id={c.get("candidate_id")} score_reason={c.get("score_reason")}')
                print(f'  overall_score={c.get("overall_score")} scores={c.get("scores")}')
                print(f'  reply_text({len(c.get("reply_text",""))}字): {(c.get("reply_text") or "")[:120]}')
                # 看quality_score从哪个字段来
                print(f'  reply_scores顶层keys: {list(rs.keys())}')
                # 看是否有legacy字段
                for k in ['total', 'kb1_score', 'kb2_score', 'quality_score', 'overall']:
                    if k in rs:
                        print(f'  legacy字段 {k}={rs[k]}')
        except Exception as e:
            print(f'  {sc}-{rank} err: {e}')

    print('\n\n=== 2. 销售分为空 - 查看step7_reply_scores中sales_scores结构 ===\n')
    # 采样几个案例看结构
    sample_cases = [('S05', 1), ('S06', 3), ('S01', 1)]
    for sc_t, rank_t in sample_cases:
        row = conn.execute(text('''
            SELECT r.scenario_code, r.scenario_rank,
                   r.step7_reply_scores::text AS rs_raw,
                   r.stage_status::text AS stage_raw
            FROM case_iteration_result r
            WHERE r.run_id = :rid AND r.scenario_code = :sc AND r.scenario_rank = :rank
        '''), {'rid': run_id, 'sc': sc_t, 'rank': rank_t}).fetchone()
        if not row:
            continue
        sc, rank, rs_raw, stage_raw = row
        print(f'--- {sc}-{rank} ---')
        try:
            rs = json.loads(rs_raw) if rs_raw else {}
            v2 = rs.get('reply_scores_v2') or rs
            sales_list = v2.get('sales_scores') or []
            print(f'  sales_scores count: {len(sales_list)}')
            if sales_list:
                for s in sales_list[:2]:
                    print(f'  sales entry keys: {list(s.keys())}')
                    print(f'  overall_score={s.get("overall_score")} score_reason={s.get("score_reason")}')
            else:
                print(f'  sales_scores为空列表')
                # 看reply_scores整体结构
                print(f'  v2 keys: {list(v2.keys())}')
                print(f'  reply_scores全内容前300字: {rs_raw[:300]}')
        except Exception as e:
            print(f'  err: {e}')

    print('\n\n=== 3. 从step6_sales_advice看是否有销售回复传入评分 ===\n')
    for sc_t, rank_t in [('S05', 1), ('S11', 1), ('S01', 1)]:
        row = conn.execute(text('''
            SELECT r.scenario_code, r.scenario_rank,
                   r.step6_sales_advice::text AS adv_raw
            FROM case_iteration_result r
            WHERE r.run_id = :rid AND r.scenario_code = :sc AND r.scenario_rank = :rank
        '''), {'rid': run_id, 'sc': sc_t, 'rank': rank_t}).fetchone()
        if not row:
            continue
        sc, rank, adv_raw = row
        print(f'--- {sc}-{rank} ---')
        try:
            adv = json.loads(adv_raw) if adv_raw else {}
            # 看actual_sales_replies字段
            actual = adv.get('actual_sales_replies') or []
            print(f'  actual_sales_replies count: {len(actual)}')
            if actual:
                for s in actual[:2]:
                    print(f'  keys: {list(s.keys())} content={str(s.get("content",""))[:80]}')
            else:
                print(f'  step6 keys: {list(adv.keys())}')
                print(f'  step6前200字: {adv_raw[:200]}')
        except Exception as e:
            print(f'  err: {e}')

    print('\n\n=== 4. 比较质疑的高分案例：S06-3(95分)完整内容 ===\n')
    row = conn.execute(text('''
        SELECT r.step7_reply_scores::text, r.step6_sales_advice::text,
               r.step4_knowledge::text, r.step1_summary::text
        FROM case_iteration_result r
        WHERE r.run_id = :rid AND r.scenario_code = 'S06' AND r.scenario_rank = 3
    '''), {'rid': run_id}).fetchone()
    if row:
        rs_raw, adv_raw, kb_raw, sum_raw = row
        try:
            rs = json.loads(rs_raw) if rs_raw else {}
            v2 = rs.get('reply_scores_v2') or rs
            ai_cands = v2.get('ai_candidates') or []
            print(f'ai_candidates({len(ai_cands)}个):')
            for c in ai_cands:
                print(f'  id={c.get("candidate_id")} overall={c.get("overall_score")} reason={c.get("score_reason")}')
                print(f'  scores={c.get("scores")}')
                print(f'  reply({len(c.get("reply_text",""))}字): {(c.get("reply_text") or "")[:200]}')
            # 摘要
            s = json.loads(sum_raw) if sum_raw else {}
            print(f'\n摘要: topic={s.get("topic")} demand={s.get("core_demand")}')
        except Exception as e:
            print(f'err: {e}')
            print(f'rs_raw前200: {rs_raw[:200] if rs_raw else ""}')
