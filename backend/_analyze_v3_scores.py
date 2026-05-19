"""分析v3高分案例的打分合理性"""
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
    # 全部60个案例
    rows = conn.execute(text('''
        SELECT r.scenario_code, r.scenario_rank, r.quality_score,
               r.step7_reply_scores::text AS rs_raw,
               r.quality_status
        FROM case_iteration_result r
        WHERE r.run_id = :rid
        ORDER BY r.quality_score DESC
    '''), {'rid': run_id}).fetchall()

    print(f'=== v3 全部60个案例评分分析 ===\n')

    null_ai_count = 0
    null_sales_count = 0
    score_analysis = []

    for row in rows:
        sc, rank, qs, rs_raw, qst = row
        try:
            rs = json.loads(rs_raw) if rs_raw else {}
            v2 = rs.get('reply_scores_v2') or rs
            ai_cands = v2.get('ai_candidates') or []
            sales_list = v2.get('sales_scores') or []

            # 最高AI候选
            best_ai = None
            for c in ai_cands:
                ov = c.get('overall_score')
                if ov is not None:
                    if best_ai is None or ov > best_ai.get('overall_score', 0):
                        best_ai = c

            # 销售原始分
            best_sales = None
            for c in sales_list:
                ov = c.get('overall_score')
                if ov is not None:
                    if best_sales is None or ov > best_sales.get('overall_score', 0):
                        best_sales = c

            if best_ai is None:
                null_ai_count += 1
            if best_sales is None:
                null_sales_count += 1

            score_analysis.append({
                'case': f'{sc}-{rank}',
                'qs': qs,
                'best_ai': best_ai,
                'best_sales': best_sales,
                'ai_count': len(ai_cands),
                'sales_count': len(sales_list),
                'qst': qst,
            })
        except Exception as e:
            print(f'  {sc}-{rank} 解析错误: {e}')

    print(f'AI分为空: {null_ai_count}/60, 销售分为空: {null_sales_count}/60\n')

    # 打印90分以上详情
    print('=== 90分以上案例详情 ===')
    for item in score_analysis:
        if item['qs'] >= 90:
            ba = item['best_ai']
            print(f"\n{item['case']}: qs={item['qs']} (ai_cands={item['ai_count']})")
            if ba:
                scores = ba.get('scores') or {}
                reply_text = ba.get('reply_text', '')
                print(f"  AI最高={ba.get('overall_score')} 字数={len(reply_text)}")
                print(f"  conc={scores.get('conciseness')} low={scores.get('low_barrier')} nonrep={scores.get('non_repetition')} safe={scores.get('safety')} style={scores.get('style_match')} ctx={scores.get('context_alignment')}")
                print(f"  回复内容: {reply_text[:200]}")
                print(f"  score_note: {ba.get('score_note', '')}")
            else:
                print(f"  AI候选为空，quality_score={item['qs']} 从何而来？")
                # 检查原始reply_scores

    # 检查ai=None但qs有分的案例
    print('\n=== AI候选为空但有quality_score的案例 ===')
    for item in score_analysis:
        if item['best_ai'] is None and item['qs'] is not None:
            print(f"  {item['case']}: qs={item['qs']} qst={item['qst']} ai_cands={item['ai_count']}")

    # 检查sales_scores为空的原因
    print('\n=== 销售原始分统计 ===')
    print(f'  所有60个案例的销售分均为None: {null_sales_count == 60}')
    # Show sample reply_scores structure
    for item in score_analysis[:3]:
        sc_rank = item['case']
        break

    # 打印score分布
    print('\n=== 分数分布 ===')
    from collections import Counter
    dist = Counter(int(item['qs']) for item in score_analysis if item['qs'] is not None)
    for k in sorted(dist.keys(), reverse=True):
        print(f"  {k}分: {dist[k]}个")
