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

def analyze():
    with engine.connect() as c:
        print("=== 空 main_text 邮件的来源类型分布 ===")
        rows = c.execute(text("""
            SELECT ru.source_type, COUNT(*)
            FROM mail_cleaned mc
            JOIN mail_raw_unified ru ON mc.mail_uid = ru.mail_uid
            WHERE mc.body_main_text IS NULL OR TRIM(mc.body_main_text) = ''
            GROUP BY ru.source_type
        """)).fetchall()
        for r in rows:
            print(f"  {r[0]}: {r[1]}")
            
        print("\n=== 空 main_text 邮件的主题关键词统计 ===")
        rows_sub = c.execute(text("""
            SELECT ru.subject, COUNT(*)
            FROM mail_cleaned mc
            JOIN mail_raw_unified ru ON mc.mail_uid = ru.mail_uid
            WHERE mc.body_main_text IS NULL OR TRIM(mc.body_main_text) = ''
            GROUP BY ru.subject
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)).fetchall()
        for r in rows_sub:
            print(f"  {r[0]}: {r[1]}")

if __name__ == "__main__":
    analyze()
