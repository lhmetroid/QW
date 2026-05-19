# -*- coding: utf-8 -*-
"""用正确的 UTF-8 client_encoding 写入分析"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    with open(p) as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith('#') or '=' not in l: continue
            k, v = l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

import sqlalchemy
from sqlalchemy import create_engine, text

db_url = os.environ['DATABASE_URL']

# 强制 client_encoding=utf8
engine = create_engine(
    db_url,
    connect_args={
        'connect_timeout': 15,
        'options': '-c client_encoding=UTF8',
    },
    pool_pre_ping=True,
)

run_id = 'caf54fdf-21d4-4732-8963-d548d2d0da2c'

# 读取分析文本文件（避免py源文件编码问题）
analysis_file = os.path.join(os.path.dirname(__file__), '_cc_analysis.txt')
summary_file = os.path.join(os.path.dirname(__file__), '_summary.txt')

with open(analysis_file, encoding='utf-8') as f:
    cc_analysis = f.read()
with open(summary_file, encoding='utf-8') as f:
    summary = f.read()

with engine.connect() as conn:
    # 验证当前 claude_code 内容
    row = conn.execute(text(
        "SELECT LEFT(analysis_claude_code, 20) FROM case_iteration_run WHERE run_id = :rid"
    ), {'rid': run_id}).fetchone()
    print(f'当前 claude_code 前20字: {row[0] if row else "空"}')

    # 更新
    conn.execute(text(
        "UPDATE case_iteration_run SET analysis_claude_code = :c, analysis_summary = :s WHERE run_id = :rid"
    ), {'c': cc_analysis, 's': summary, 'rid': run_id})
    conn.commit()

    # 验证
    row2 = conn.execute(text(
        "SELECT LEFT(analysis_claude_code, 20), LEFT(analysis_summary, 20) FROM case_iteration_run WHERE run_id = :rid"
    ), {'rid': run_id}).fetchone()
    print(f'写入后 claude_code 前20字: {row2[0] if row2 else "空"}')
    print(f'写入后 summary 前20字: {row2[1] if row2 else "空"}')
    print('完成！')
