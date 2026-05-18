"""
直接导入企微原始数据到 wecom_raw_import 表。
用法：python backend/import_wecom_raw_direct.py
"""
import csv
import hashlib
import os
import sys
from datetime import datetime

# ─── 加载 .env ─────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_ROOT, ".env")

def _load_env(path):
    if not os.path.exists(path):
        print(f"[WARN] .env 文件不存在: {path}")
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env(_ENV_PATH)

# ─── DB 连接 ───────────────────────────────────────────────────────────────────
import urllib.parse
from sqlalchemy import create_engine, text as sa_text

DATABASE_URL = os.environ.get("DATABASE_URL") or ""
if not DATABASE_URL:
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "")
    user = os.environ.get("DB_USER", "")
    pw   = urllib.parse.quote_plus(os.environ.get("DB_PASSWORD", ""))
    DATABASE_URL = f"postgresql://{user}:{pw}@{host}:{port}/{name}"

# SQLAlchemy dialect fix: psycopg2 driver
db_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg2://")
if db_url.startswith("postgresql://"):
    db_url = db_url  # already fine for psycopg2

print(f"[INFO] DB: {db_url.split('@')[-1]}")  # 不打印密码

engine = create_engine(db_url, connect_args={"connect_timeout": 30})
conn = engine.connect()

# ─── 建表（若不存在）─────────────────────────────────────────────────────────
conn.execute(sa_text("""
CREATE TABLE IF NOT EXISTS wecom_raw_import (
    id SERIAL PRIMARY KEY,
    import_batch_id VARCHAR(40) NOT NULL,
    sender VARCHAR(200),
    receiver VARCHAR(200),
    group_id VARCHAR(200),
    msg_time TIMESTAMP,
    content TEXT,
    from_id VARCHAR(200),
    to_id VARCHAR(200),
    stage VARCHAR(50),
    section VARCHAR(100),
    quality_score NUMERIC(5,2),
    process_note TEXT,
    process_result VARCHAR(50),
    row_status VARCHAR(30) DEFAULT 'pending',
    group_key VARCHAR(80),
    role VARCHAR(20),
    row_index INTEGER,
    created_at TIMESTAMP DEFAULT now()
)
"""))
conn.commit()
print("[INFO] 表 wecom_raw_import 已就绪")

# ─── 文件路径 ──────────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(_ROOT, "docs", "企微提取内容_20260509111157.csv")
if not os.path.exists(CSV_PATH):
    print(f"[ERROR] 文件不存在: {CSV_PATH}")
    sys.exit(1)

file_size = os.path.getsize(CSV_PATH)
print(f"[INFO] 文件: {CSV_PATH}")
print(f"[INFO] 大小: {file_size/1024/1024:.1f} MB")

# ─── 流式 MD5 ─────────────────────────────────────────────────────────────────
h = hashlib.md5()
with open(CSV_PATH, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        h.update(chunk)
file_hash = h.hexdigest()[:12]
batch_id = f"wri_{file_hash}"
print(f"[INFO] batch_id: {batch_id}")

# ─── 检查是否已导入 ────────────────────────────────────────────────────────────
existing = conn.execute(sa_text("SELECT COUNT(*) FROM wecom_raw_import WHERE import_batch_id = :bid"), {"bid": batch_id}).scalar()
if existing:
    ans = input(f"[WARN] 该文件已导入 {existing} 条（batch={batch_id}）。输入 y 强制覆盖，其他键跳过: ").strip().lower()
    if ans != "y":
        print("[INFO] 跳过，退出。")
        sys.exit(0)
    conn.execute(sa_text("DELETE FROM wecom_raw_import WHERE import_batch_id = :bid"), {"bid": batch_id})
    conn.commit()
    print(f"[INFO] 已删除旧数据 {existing} 条")

# ─── 编码检测 ──────────────────────────────────────────────────────────────────
detected_enc = "utf-8-sig"
for enc in ["utf-8-sig", "utf-8", "gbk", "gb18030"]:
    try:
        with open(CSV_PATH, encoding=enc, newline="") as f:
            sample = f.read(4096)
        if "发件人" in sample or "收件人" in sample:
            detected_enc = enc
            break
    except Exception:
        continue
print(f"[INFO] 编码: {detected_enc}")

# ─── 角色检测 ──────────────────────────────────────────────────────────────────
def detect_role(sender):
    if not sender:
        return "unknown"
    if sender.startswith("客户"):
        return "customer"
    if sender.startswith("销售"):
        return "sales"
    return "unknown"

# ─── 时间解析 ──────────────────────────────────────────────────────────────────
def parse_time(s):
    if not s:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

# ─── 流式插入 ──────────────────────────────────────────────────────────────────
INSERT_SQL = sa_text("""
INSERT INTO wecom_raw_import
  (import_batch_id, sender, receiver, group_id, msg_time, content, from_id, to_id,
   stage, section, quality_score, process_note, process_result,
   row_status, group_key, role, row_index)
VALUES (:batch_id,:sender,:receiver,:group_id,:msg_time,:content,:from_id,:to_id,
        NULL,NULL,NULL,NULL,NULL,'pending',:group_key,:role,:row_index)
""")

BATCH_SIZE = 500
dialogue_counter = 0
total_inserted = 0
total_skipped = 0
batch_buf = []
parse_errors = []

def flush_batch(buf):
    if not buf:
        return
    conn.execute(INSERT_SQL, buf)
    conn.commit()

with open(CSV_PATH, encoding=detected_enc, newline="", errors="replace") as fh:
    reader = csv.DictReader(fh)
    print(f"[INFO] CSV 列头: {reader.fieldnames}")

    for idx, row in enumerate(reader):
        try:
            sender   = (row.get("发件人") or "").strip()
            receiver = (row.get("收件人") or "").strip()
            group_id = (row.get("群ID")  or "").strip()
            time_str = (row.get("时间")   or "").strip()
            content  = (row.get("内容")   or "").strip()
            from_id  = (row.get("from")   or "").strip()
            to_id    = (row.get("tolist") or "").strip()

            if not sender and not content:
                dialogue_counter += 1
                total_skipped += 1
                continue

            role      = detect_role(sender)
            msg_time  = parse_time(time_str)
            group_key = f"{batch_id}_d{dialogue_counter}"

            batch_buf.append({
                "batch_id": batch_id,
                "sender": sender[:200] or None,
                "receiver": receiver[:200] or None,
                "group_id": group_id[:200] or None,
                "msg_time": msg_time,
                "content": content or None,
                "from_id": from_id[:200] or None,
                "to_id": to_id[:200] or None,
                "group_key": group_key,
                "role": role,
                "row_index": idx,
            })

            if len(batch_buf) >= BATCH_SIZE:
                flush_batch(batch_buf)
                total_inserted += len(batch_buf)
                print(f"[INFO] 已插入 {total_inserted} 条 (行 {idx})")
                batch_buf = []

        except Exception as e:
            parse_errors.append(f"row {idx}: {e}")
            if len(parse_errors) <= 5:
                print(f"[WARN] 行解析异常 idx={idx}: {e}")

# 尾批
if batch_buf:
    flush_batch(batch_buf)
    total_inserted += len(batch_buf)

conn.close()

print()
print("=" * 50)
print(f"[DONE] 导入完成")
print(f"  batch_id : {batch_id}")
print(f"  已插入   : {total_inserted} 条")
print(f"  跳过分隔  : {total_skipped} 行")
print(f"  解析错误  : {len(parse_errors)} 行")
if parse_errors:
    for e in parse_errors[:5]:
        print(f"    {e}")
