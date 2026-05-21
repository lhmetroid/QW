import sys, os, io
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

from database import engine
from sqlalchemy import text

with engine.connect() as c:
    for table in ['mail_raw_unified', 'mail_cleaned']:
        print(f"\n=== Columns of {table} ===")
        cols = c.execute(text(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema='public' AND table_name='{table}'
            ORDER BY ordinal_position
        """)).fetchall()
        for col in cols:
            print(f"  {col[0]:30s} : {col[1]}")
            
        # Get count
        cnt = c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        print(f"Total rows: {cnt}")
