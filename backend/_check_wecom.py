import os, sys, urllib.parse
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_env(path):
    if not os.path.exists(path): return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
_load_env(os.path.join(_ROOT, ".env"))

from sqlalchemy import create_engine, text
db_url = (os.environ.get("DATABASE_URL") or "").replace("postgresql+psycopg://", "postgresql+psycopg2://")

engine = create_engine(db_url)
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM wecom_raw_import")).scalar()
    unique = conn.execute(text("SELECT COUNT(*) FROM (SELECT MIN(id) FROM wecom_raw_import GROUP BY import_batch_id, row_index) t")).scalar()
    print(f"总行数: {total}")
    print(f"去重后应有: {unique}")
    print(f"重复行: {total - unique}")
