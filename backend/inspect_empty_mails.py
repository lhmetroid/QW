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
        print("=== 检查 body_main_text 为空的邮件 (前10条) ===")
        rows_empty = c.execute(text("""
            SELECT mc.mail_uid, ru.subject, ru.body_text
            FROM mail_cleaned mc
            JOIN mail_raw_unified ru ON mc.mail_uid = ru.mail_uid
            WHERE mc.body_main_text IS NULL OR TRIM(mc.body_main_text) = ''
            LIMIT 10
        """)).fetchall()
        for i, r in enumerate(rows_empty):
            print(f"[{i+1}] UID: {r[0]}")
            print(f"Subject: {r[1]}")
            print(f"Raw body (first 150 chars): {repr((r[2] or '')[:150])}")
            print("-" * 50)
            
        print("\n=== 检查包含 'test' 噪音且在 mail_cleaned 中的邮件 (前10条) ===")
        rows_test = c.execute(text("""
            SELECT mc.mail_uid, ru.subject, mc.body_main_text
            FROM mail_cleaned mc
            JOIN mail_raw_unified ru ON mc.mail_uid = ru.mail_uid
            WHERE mc.normalized_subject ILIKE '%test%' 
               OR mc.body_main_text ILIKE '%test%'
            LIMIT 10
        """)).fetchall()
        for i, r in enumerate(rows_test):
            print(f"[{i+1}] UID: {r[0]}")
            print(f"Subject: {r[1]}")
            print(f"Cleaned main body: {repr(r[2])}")
            print("-" * 50)

if __name__ == "__main__":
    inspect()
