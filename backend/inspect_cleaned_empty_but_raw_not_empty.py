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
        print("=== 检查 body_text 非空但 body_main_text 为空的邮件 (前20条) ===")
        rows = c.execute(text("""
            SELECT mc.mail_uid, ru.subject, ru.body_text
            FROM mail_cleaned mc
            JOIN mail_raw_unified ru ON mc.mail_uid = ru.mail_uid
            WHERE (ru.body_text IS NOT NULL AND TRIM(ru.body_text) <> '')
              AND (mc.body_main_text IS NULL OR TRIM(mc.body_main_text) = '')
            LIMIT 20
        """)).fetchall()
        for i, r in enumerate(rows):
            print(f"[{i+1}] UID: {r[0]}")
            print(f"Subject: {r[1]}")
            print(f"Raw body (first 250 chars): {repr(r[2])}")
            print("-" * 60)

if __name__ == "__main__":
    inspect()
