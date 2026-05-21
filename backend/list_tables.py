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
    tables = c.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' ORDER BY table_name"
    )).fetchall()
    
    print(f"Total tables: {len(tables)}")
    
    table_counts = []
    for (t,) in tables:
        try:
            count = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            table_counts.append((t, count))
        except Exception as e:
            print(f"Error reading {t}: {e}")
            
    # Sort by count descending
    table_counts.sort(key=lambda x: x[1], reverse=True)
    
    print("\n--- Tables sorted by row count ---")
    for t, count in table_counts[:30]:
        print(f"  {t:40s} : {count:,} rows")
