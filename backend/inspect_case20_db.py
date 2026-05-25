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
            SELECT mc.body_main_text, mc.signature_text, mc.disclaimer_text, mc.body_quoted_text, mc.clean_status, mc.clean_error
            FROM mail_cleaned mc
            WHERE mc.mail_uid = '84c10b83c2d1578ce45a1aad2f33c4572213a842208bb46ab2a207d0fffbaa37'
        """)).fetchone()
        if row:
            print("Database values for 84c10b83c2d1578ce45a1aad2f33c4572213a842208bb46ab2a207d0fffbaa37:")
            print(f"  body_main_text: {repr(row[0])}")
            print(f"  signature_text: {repr(row[1])}")
            print(f"  disclaimer_text: {repr(row[2])}")
            print(f"  body_quoted_text: {repr(row[3])}")
            print(f"  clean_status: {repr(row[4])}")
            print(f"  clean_error: {repr(row[5])}")
        else:
            print("Row not found in database!")

if __name__ == "__main__":
    inspect()
