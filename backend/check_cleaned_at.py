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
        row = c.execute(text("""
            SELECT cleaned_at FROM mail_cleaned
            WHERE mail_uid = '84c10b83c2d1578ce45a1aad2f33c4572213a842208bb46ab2a207d0fffbaa37'
        """)).fetchone()
        print(f"cleaned_at: {row[0]}")

if __name__ == "__main__":
    inspect()
