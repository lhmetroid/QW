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
    print("--- Distinct subject values for source_type = 'wecom' ---")
    rows = c.execute(text("SELECT subject, COUNT(*) FROM mail_raw_unified WHERE source_type = 'wecom' GROUP BY subject")).fetchall()
    for row in rows:
        print(f"  {row[0]} : {row[1]:,}")
        
    print("\n--- Distinct subject values for non-wecom source_types ---")
    rows2 = c.execute(text("SELECT source_type, subject, COUNT(*) FROM mail_raw_unified WHERE source_type != 'wecom' GROUP BY source_type, subject ORDER BY count DESC LIMIT 10")).fetchall()
    for row in rows2:
        print(f"  [{row[0]}] {row[1]} : {row[2]:,}")
