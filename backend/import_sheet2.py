"""
导入企微提取内容_第二个sheet数据.csv 到 wecom_raw_import
与原脚本完全相同逻辑，只更改文件路径
"""
import csv, hashlib, os, sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def _load_env(path):
    if not os.path.exists(path): return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env(os.path.join(_ROOT, ".env"))

import urllib.parse
from sqlalchemy import create_engine, text as sa_text

DATABASE_URL = os.environ.get("DATABASE_URL") or ""
db_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg2://")
print(f"[INFO] DB: {db_url.split('@')[-1]}")

engine = create_engine(db_url, connect_args={"connect_timeout": 30})
conn = engine.connect()

CSV_PATH = os.path.join(_ROOT, "docs", "企微提取内容_第二个sheet数据.csv")
if not os.path.exists(CSV_PATH):
    print(f"[ERROR] 文件不存在: {CSV_PATH}")
    sys.exit(1)

file_size = os.path.getsize(CSV_PATH)
print(f"[INFO] 文件: {CSV_PATH}")
print(f"[INFO] 大小: {file_size/1024/1024:.1f} MB")

# MD5 批次ID
h = hashlib.md5()
with open(CSV_PATH, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        h.update(chunk)
file_hash = h.hexdigest()[:12]
batch_id = f"wri_{file_hash}"
print(f"[INFO] batch_id: {batch_id}")

existing = conn.execute(sa_text("SELECT COUNT(*) FROM wecom_raw_import WHERE import_batch_id = :bid"), {"bid": batch_id}).scalar()
if existing:
    print(f"[WARN] 该文件已导入 {existing} 条（batch={batch_id}），跳过。")
    sys.exit(0)

# 编码检测
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

# 员工中英文对照（发件人字段有时是中文名）
CN_TO_EN = {
    '何珺': 'alicehe',
    '肖美鹏': 'davidXiaoMeiPeng',
    '韩瑾': 'HanHan',
    '盛晔': 'joycesheng',
    '王慧莹': 'WangHuiYing',
}

def detect_role(sender):
    if not sender: return "unknown"
    if sender.startswith("客户"): return "customer"
    if sender.startswith("销售"): return "sales"
    return "unknown"

def normalize_from_id(from_id, sender):
    """from_id 可能是英文ID或中文名（极少数情况），统一成英文"""
    if not from_id: return from_id
    return CN_TO_EN.get(from_id, from_id)

def parse_time(s):
    if not s: return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

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

def flush(buf):
    if not buf: return
    conn.execute(INSERT_SQL, buf)
    conn.commit()

with open(CSV_PATH, encoding=detected_enc, newline="", errors="replace") as fh:
    reader = csv.DictReader(fh)
    print(f"[INFO] CSV列头: {reader.fieldnames}")

    for idx, row in enumerate(reader):
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

        from_id = normalize_from_id(from_id, sender)
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
            "row_index": idx + 1,
        })
        total_inserted += 1

        if len(batch_buf) >= BATCH_SIZE:
            flush(batch_buf)
            batch_buf.clear()
            if total_inserted % 10000 == 0:
                print(f"[INFO] 已插入 {total_inserted:,} 行，对话组 {dialogue_counter}")

    flush(batch_buf)

print(f"\n[完成] 插入 {total_inserted:,} 行，跳过空行 {total_skipped}，对话组 {dialogue_counter + 1}")
conn.close()
