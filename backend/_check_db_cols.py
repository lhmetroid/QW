import os, sys
sys.path.insert(0, '.')

def load_env(p):
    if not os.path.exists(p): return
    with open(p) as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith('#') or '=' not in l: continue
            k, v = l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

load_env('../.env')
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', '').replace('postgresql+psycopg://', 'postgresql+psycopg2://')
e = create_engine(url, connect_args={'connect_timeout': 15})

with e.connect() as c:
    cols = [r[0] for r in c.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='wecom_raw_import' ORDER BY ordinal_position"
    )).fetchall()]
    print('COLS:', cols)

    rows = c.execute(text(
        "SELECT id, role, group_key, stage, section, process_result, quality_score, content "
        "FROM wecom_raw_import ORDER BY id ASC LIMIT 5"
    )).fetchall()
    for r in rows:
        print(r[:7], '|', str(r[7])[:50] if r[7] else '')
