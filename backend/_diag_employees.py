import io, sys, os
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

SALES_IDS      = ('alicehe', 'davidXiaoMeiPeng', 'HanHan', 'joycesheng')
SALES_SENDERS  = ('销售:何珺', '销售:肖美鹏', '销售:韩瑾', '销售:盛晔',
                  '销售:alicehe', '销售:davidXiaoMeiPeng', '销售:HanHan', '销售:joycesheng')

EMP_MAP = [
    ('何珺',  'alicehe',           '销售:何珺'),
    ('肖美鹏', 'davidXiaoMeiPeng',  '销售:肖美鹏'),
    ('韩瑾',  'HanHan',            '销售:韩瑾'),
    ('盛晔',  'joycesheng',        '销售:盛晔'),
]

with e.connect() as c:
    # 各员工对话组数
    print('=== 各员工对话组数 ===')
    for cn, fid, sender in EMP_MAP:
        r = c.execute(text(
            "SELECT COUNT(DISTINCT group_key) FROM wecom_raw_import "
            "WHERE from_id=:fid OR sender=:sender"
        ), {'fid': fid, 'sender': sender}).fetchone()
        print(f'  {cn}/{fid}: {r[0]} 组')

    # 5员工整体规模（group_key去重）
    r2 = c.execute(text("""
        WITH emp_gk AS (
            SELECT DISTINCT group_key FROM wecom_raw_import
            WHERE from_id = ANY(:ids) OR sender = ANY(:senders)
        ),
        stats AS (
            SELECT g.group_key,
                   COUNT(*) as total,
                   COUNT(CASE WHEN role='customer' THEN 1 END) as cust_cnt,
                   COUNT(CASE WHEN role='sales' THEN 1 END) as sales_cnt
            FROM emp_gk g
            JOIN wecom_raw_import w ON w.group_key = g.group_key
            GROUP BY g.group_key
        )
        SELECT COUNT(*) total_gk,
               COUNT(CASE WHEN cust_cnt>=2 AND sales_cnt>=2 THEN 1 END) bidir_gk,
               SUM(total) total_msgs
        FROM stats
    """), {'ids': list(SALES_IDS), 'senders': list(SALES_SENDERS)}).fetchone()
    print(f'\n5员工总计: {r2[0]}组对话, 双向有效组(≥2条各方){r2[1]}组, 总消息{r2[2]}条')

    # message_logs 结构
    r3 = c.execute(text(
        "SELECT COUNT(DISTINCT user_id), MAX(timestamp) FROM message_logs WHERE is_mock=false"
    )).fetchone()
    print(f'\nmessage_logs: {r3[0]}个会话, 最新={str(r3[1])[:19]}')
    samples = c.execute(text(
        "SELECT DISTINCT user_id FROM message_logs WHERE is_mock=false LIMIT 6"
    )).fetchall()
    print('user_id 样本:', [r[0] for r in samples])

    # 肖美鹏对话组里，找有价格/比价内容的对话
    print('\n=== 肖美鹏含价格竞争内容的对话 (取3个) ===')
    rows = c.execute(text("""
        WITH emp_gk AS (
            SELECT DISTINCT group_key FROM wecom_raw_import
            WHERE from_id='davidXiaoMeiPeng' OR sender='销售:肖美鹏'
        )
        SELECT w.group_key,
               COUNT(*) as cnt,
               COUNT(CASE WHEN role='customer' THEN 1 END) as cust,
               MIN(w.msg_time)::date as day
        FROM emp_gk g JOIN wecom_raw_import w ON w.group_key=g.group_key
        WHERE w.content ILIKE '%比价%' OR w.content ILIKE '%比你们便宜%'
           OR w.content ILIKE '%别家%' OR w.content ILIKE '%其他家%'
           OR w.content ILIKE '%价格能不能%' OR w.content ILIKE '%比我们低%'
        GROUP BY w.group_key
        HAVING COUNT(CASE WHEN role='customer' THEN 1 END)>=2
        ORDER BY cnt DESC LIMIT 3
    """)).fetchall()
    for r in rows:
        print(f'  group={r[0]}, cnt={r[1]}, cust_msgs={r[2]}, date={r[3]}')
