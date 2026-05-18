import sys, os
sys.path.insert(0, os.path.dirname(__file__))
def load_env(p):
    if not os.path.exists(p): return
    for l in open(p):
        l = l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, v = l.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
n = db.execute(text("UPDATE case_iteration_run SET status='failed', error_message='aborted due to port+truncation bugs' WHERE status IN ('running','queued')")).rowcount
db.commit()
print(f'marked stuck runs as failed: {n}')
db.close()
