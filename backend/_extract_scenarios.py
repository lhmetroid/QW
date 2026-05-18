"""提取各场景典型案例脚本"""
import os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
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
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', '').replace('postgresql+psycopg://', 'postgresql+psycopg2://')
e = create_engine(url, connect_args={'connect_timeout': 30})

TARGET_SCENARIOS = [
    '方案确认与正式报价',
    '新客激活',
    '节气/开工问候',
    '产品/服务细节对标',
    '紧急响应/确定性交付',
    '价格竞争/比价',
    '业务深度介绍',
    '预算收紧',
    '售后纠偏/客诉处理',
    '案例分享',
]

with e.connect() as c:
    from collections import defaultdict

    # 统计各场景对话组
    rows = c.execute(text("""
        SELECT business_scenario_name, group_key, COUNT(*) as msg_cnt,
               MIN(msg_time) as start_time, MAX(msg_time) as end_time,
               MIN(slice_title) as title,
               MIN(quality_score) as q_score,
               MIN(process_result) as proc_result
        FROM wecom_raw_import
        WHERE business_scenario_name = ANY(:scenarios)
        AND content IS NOT NULL AND content != ''
        GROUP BY business_scenario_name, group_key
        HAVING COUNT(*) >= 2
        ORDER BY business_scenario_name, COUNT(*) DESC
    """), {'scenarios': TARGET_SCENARIOS}).fetchall()

    scenario_groups = defaultdict(list)
    for r in rows:
        scenario_groups[r[0]].append({
            'group_key': r[1], 'msg_cnt': r[2],
            'start': str(r[3]), 'end': str(r[4]),
            'title': r[5],
            'q': float(r[6]) if r[6] else None,
            'proc': r[7]
        })

    for sc in TARGET_SCENARIOS:
        groups = scenario_groups.get(sc, [])
        if not groups:
            print(f'{sc}: 无数据')
            continue
        max_cnt = max(g['msg_cnt'] for g in groups)
        print(f'{sc}: {len(groups)} 个对话组，最大消息数={max_cnt}')
        for g in groups[:3]:
            print(f'   group={g["group_key"]}, msgs={g["msg_cnt"]}, title={str(g["title"])[:40]}')
