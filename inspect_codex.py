import sys
from pathlib import Path
sys.path.insert(0, r"d:\items\QW")
from parse_520_all_logs import parse_codex_file, CODEX_LOGS_DIR

print("\n--- CODEX RECORDS DETAIL ---")
for fp in CODEX_LOGS_DIR.glob("*.jsonl"):
    records = parse_codex_file(fp)
    print(f"File: {fp.name}, count={len(records)}")
    for r in records:
        print(f"Time: {r['time']}")
        print(f"Text: {r['text'][:500]}")
        print("-" * 50)
