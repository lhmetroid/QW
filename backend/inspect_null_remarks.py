# -*- coding: utf-8 -*-
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

def inspect():
    with engine.connect() as c:
        print("=== 检查 mail_raw_unified 中的空 body_text ===")
        total_raw_empty = c.execute(text("""
            SELECT COUNT(*) FROM mail_raw_unified
            WHERE body_text IS NULL OR TRIM(body_text) = ''
        """)).scalar()
        print(f"mail_raw_unified 中 body_text 为空的数量: {total_raw_empty}")
        
        print("\n=== 检查 mail_raw_unified 中的空 body_text 按 source_type 分布 ===")
        rows = c.execute(text("""
            SELECT source_type, COUNT(*)
            FROM mail_raw_unified
            WHERE body_text IS NULL OR TRIM(body_text) = ''
            GROUP BY source_type
        """)).fetchall()
        for r in rows:
            print(f"  {r[0]}: {r[1]}")

if __name__ == "__main__":
    inspect()
