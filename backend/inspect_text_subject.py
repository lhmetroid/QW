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
    # Let's inspect rows where subject = 'text'
    print("--- Querying 5 rows where subject = 'text' ---")
    rows = c.execute(text("SELECT id, mail_uid, direction, from_email, sent_at, body_text FROM mail_raw_unified WHERE subject = 'text' LIMIT 5")).fetchall()
    
    for i, row in enumerate(rows):
        body = row[5] or ""
        body_safe = body.encode('utf-8', 'replace').decode('utf-8')
        print(f"Row {i+1}:")
        print(f"  ID: {row[0]}")
        print(f"  UID: {row[1]}")
        print(f"  Direction: {row[2]}")
        print(f"  From: {row[3]}")
        print(f"  Sent At: {row[4]}")
        print(f"  Body length: {len(body)}")
        print(f"  Body snippet: {body_safe[:200]}")
        print("-" * 40)
