"""去除 wecom_raw_import 中因重复导入产生的重复行，保留每组 (import_batch_id, row_index) 最小 id。"""
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

engine = create_engine(db_url, connect_args={"connect_timeout": 30})
with engine.connect() as conn:
    before = conn.execute(text("SELECT COUNT(*) FROM wecom_raw_import")).scalar()
    print(f"[INFO] 去重前: {before} 条")

    # 高效删除重复行（PostgreSQL DELETE USING 语法）
    result = conn.execute(text("""
        DELETE FROM wecom_raw_import a
        USING wecom_raw_import b
        WHERE a.id > b.id
          AND a.import_batch_id = b.import_batch_id
          AND a.row_index = b.row_index
    """))
    conn.commit()
    deleted = result.rowcount
    print(f"[INFO] 删除重复: {deleted} 条")

    after = conn.execute(text("SELECT COUNT(*) FROM wecom_raw_import")).scalar()
    print(f"[INFO] 去重后: {after} 条")
