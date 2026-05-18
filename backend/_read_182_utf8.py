import os, sys, json, codecs
sys.path.insert(0, '.')
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

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
e = create_engine(url, connect_args={'connect_timeout': 15, 'client_encoding': 'utf8'})

with e.connect() as c:
    rows = c.execute(text(
        "SELECT id, role, group_key, msg_time, content, stage, section, quality_score, process_result, process_note, row_status "
        "FROM wecom_raw_import ORDER BY id ASC LIMIT 182"
    )).fetchall()

    data = []
    for r in rows:
        data.append({
            'id': r[0],
            'role': r[1],
            'group_key': r[2],
            'msg_time': str(r[3]) if r[3] else None,
            'content': r[4],
            'stage': r[5],
            'section': r[6],
            'quality_score': float(r[7]) if r[7] else None,
            'process_result': r[8],
            'process_note': r[9],
            'row_status': r[10],
        })

    print(json.dumps(data, ensure_ascii=False, indent=2))
