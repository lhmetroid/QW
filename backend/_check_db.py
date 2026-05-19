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
    # 1. 当前连的数据库主机
    info = c.execute(text("SELECT current_database(), inet_server_addr()::text, inet_server_port()")).fetchone()
    print(f"connected_database = {info[0]}")
    print(f"server_addr        = {info[1]}")
    print(f"server_port        = {info[2]}")
    print()

    # 2. 新增的 3 张表是否存在
    print("=== 3 张新增表存在性检查 ===")
    for t in ['case_library_case', 'case_iteration_run', 'case_iteration_result']:
        exists = c.execute(text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"
        ), {"t": t}).scalar()
        n = 0
        sz = "?"
        if exists:
            n = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            sz = c.execute(text(f"SELECT pg_size_pretty(pg_total_relation_size('public.{t}'))")).scalar()
        flag = "✓" if exists else "✗"
        print(f"  {flag} {t:30s} 存在={exists} 行数={n:>4} 大小={sz}")
    print()

    # 3. 列定义
    print("=== case_iteration_run 列结构 ===")
    cols = c.execute(text(
        "SELECT column_name, data_type, character_maximum_length, is_nullable "
        "FROM information_schema.columns WHERE table_schema='public' AND table_name='case_iteration_run' ORDER BY ordinal_position"
    )).fetchall()
    for col in cols:
        print(f"  {col[0]:32s} {col[1]:25s} max_len={col[2]} null={col[3]}")
    print()

    # 4. 全库总表数（确认没建库，只是建表）
    total = c.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    print(f"public schema 总表数 = {total}（我新增 3 张，其余为既有表）")
