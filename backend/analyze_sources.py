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
    print("--- Group by source_type in mail_raw_unified ---")
    sources = c.execute(text("SELECT source_type, COUNT(*) FROM mail_raw_unified GROUP BY source_type")).fetchall()
    for row in sources:
        print(f"  {row[0]} : {row[1]:,}")
        
    print("\n--- Group by clean_status in mail_cleaned ---")
    statuses = c.execute(text("SELECT clean_status, COUNT(*) FROM mail_cleaned GROUP BY clean_status")).fetchall()
    for row in statuses:
        print(f"  {row[0]} : {row[1]:,}")

    print("\n--- Count of is_auto_mail in mail_cleaned ---")
    auto_mails = c.execute(text("SELECT is_auto_mail, COUNT(*) FROM mail_cleaned GROUP BY is_auto_mail")).fetchall()
    for row in auto_mails:
        print(f"  {row[0]} : {row[1]:,}")
