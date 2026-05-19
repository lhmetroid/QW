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
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
print('=== case_iteration_run (本地DB) ===')
for r in db.execute(text("SELECT version_no, status, total_cases, success_cases, avg_quality_score, git_short_sha FROM case_iteration_run ORDER BY version_no")).fetchall():
    print(f'  v{r[0]} status={r[1]} cases={r[2]}/{r[3]} avg={r[4]} git={r[5]}')
print()
print('=== case_iteration_result v3 抽3行（最低分） ===')
for r in db.execute(text("SELECT scenario_code, scenario_rank, quality_status, quality_score, latency_ms, LEFT(step6_sales_advice, 60) FROM case_iteration_result WHERE run_id IN (SELECT run_id FROM case_iteration_run WHERE version_no=3) ORDER BY quality_score LIMIT 3")).fetchall():
    print(f'  {r[0]}-{r[1]} status={r[2]} score={r[3]} latency={r[4]}ms advice="{r[5]}"')
db.close()
