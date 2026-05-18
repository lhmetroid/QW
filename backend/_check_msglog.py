import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from sqlalchemy import create_engine, text

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
url = os.environ.get('DATABASE_URL','').replace('postgresql+psycopg://','postgresql+psycopg2://')
e = create_engine(url, connect_args={'connect_timeout':30})

EMP_IDS = ['alicehe','davidXiaoMeiPeng','HanHan','joycesheng','WangHuiYing']

with e.connect() as c:
    rows = c.execute(text("""
        SELECT user_id, sender_type, COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM message_logs
        WHERE is_mock = FALSE AND user_id = ANY(:ids)
        GROUP BY user_id, sender_type
        ORDER BY user_id, sender_type
    """), {'ids': EMP_IDS}).fetchall()
    print('=== 员工直接对话 ===')
    for r in rows: print(r)

    rows2 = c.execute(text("""
        SELECT user_id, COUNT(*) cnt
        FROM message_logs
        WHERE is_mock=FALSE AND user_id LIKE 'group_%'
        GROUP BY user_id ORDER BY cnt DESC LIMIT 5
    """)).fetchall()
    print('=== 群对话TOP5 ===')
    for r in rows2: print(r)

    rows3 = c.execute(text("""
        SELECT user_id, sender_type, content, timestamp
        FROM message_logs
        WHERE is_mock=FALSE AND user_id='alicehe'
        ORDER BY timestamp DESC LIMIT 3
    """)).fetchall()
    print('=== alicehe 最近3条 ===')
    for r in rows3: print(f'  [{r[1]}] {str(r[2])[:120]} @{r[3]}')
