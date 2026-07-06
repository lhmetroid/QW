import sys, os, io
def load_env(p):
    if not os.path.exists(p): return
    for l in open(p, encoding='utf-8'):
        l = l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, v = l.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import engine
from sqlalchemy import text

with engine.connect() as c:
    exts = c.execute(text("SELECT extname FROM pg_extension")).fetchall()
    print("Installed extensions:")
    for (ext,) in exts:
        print(f"  {ext}")
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
    
    print("\n--- Columns of llm_service_knowledge_unit ---")
    try:
        cols = c.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='llm_service_knowledge_unit' ORDER BY ordinal_position"
        )).fetchall()
        for col_name, data_type in cols:
            print(f"  {col_name:30s} : {data_type}")
    except Exception as e:
        print(f"Error: {e}")
