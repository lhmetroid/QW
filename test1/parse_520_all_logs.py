#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Timezone and target date
BJT = timezone(timedelta(hours=8))
TARGET_DATE = "2026-05-20"

# Directories
CLAUDE_LOGS_DIR = Path(os.path.expandvars(r"%USERPROFILE%\.claude\projects\d--items-QW"))
CODEX_LOGS_DIR = Path.home() / ".codex" / "sessions" / "2026" / "05" / "20"
GEMINI_LOGS_DIR = Path(os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity\brain"))
WORKSPACE_DIR = Path(r"d:\items\QW")

BASE64_PATTERN = re.compile(r'data:[^;]+;base64,[A-Za-z0-9+/=]{100,}')
SYSTEM_TAG_PATTERN = re.compile(
    r'^<(command-name|command-message|command-args|local-command-stdout|local-command-stderr|'
    r'system-reminder|ide_selection|ide_opened_file|user-prompt-submit-hook)\b',
    re.IGNORECASE,
)

def to_bjt(ts_str: str) -> datetime:
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return dt.astimezone(BJT)

def extract_claude_text(content) -> str:
    if isinstance(content, str):
        text = content.strip()
        if SYSTEM_TAG_PATTERN.match(text):
            return ""
        return BASE64_PATTERN.sub("[图片]", text)

    if not isinstance(content, list):
        return ""

    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type", "")
        if t == "text":
            text = item.get("text", "")
            if SYSTEM_TAG_PATTERN.match(text.lstrip()):
                continue
            text = BASE64_PATTERN.sub("[图片]", text)
            parts.append(text)
        elif t in ("image", "image_url"):
            parts.append("[图片]")
        elif t == "document":
            title = item.get("title", "")
            parts.append(f"[文档: {title}]" if title else "[文档]")
    return "\n".join(parts).strip()

def parse_claude_file(filepath: Path) -> list[dict]:
    rows = []
    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            entry_type = obj.get("type", "")
            if entry_type != "user":
                continue

            if obj.get("isMeta") or obj.get("isSidechain"):
                continue

            msg = obj.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", "")
            if role != "user":
                continue

            text = extract_claude_text(msg.get("content", ""))
            if not text:
                continue

            ts_raw = obj.get("timestamp", "")
            if not ts_raw:
                continue
            try:
                bjt_dt = to_bjt(ts_raw)
            except Exception:
                continue

            if bjt_dt.strftime("%Y-%m-%d") != TARGET_DATE:
                continue

            rows.append({
                "dt": bjt_dt,
                "time": bjt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "role": "用户",
                "text": text,
                "source": f"Claude ({filepath.name})",
            })
    return rows

# Codex
BASE64_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\r\n]+")

def is_ignored_text(text):
    stripped = text.strip()
    if not stripped:
        return True
    ignored_blocks = (
        "<environment_context>",
        "<turn_aborted>",
    )
    return any(stripped.startswith(marker) for marker in ignored_blocks)

def clean_codex_text(text):
    text = BASE64_RE.sub("[图片]", text)
    text = text.replace("<image>", "[图片]").replace("</image>", "")
    return text.strip("\n")

def extract_codex_content(content):
    if isinstance(content, str):
        text = clean_codex_text(content)
        return "" if is_ignored_text(text) else text

    if not isinstance(content, list):
        return ""

    parts = []
    image_seen = False
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {"input_image", "image", "local_image"} or "image_url" in item:
            if not image_seen:
                parts.append("[图片]")
                image_seen = True
            continue
        if item_type in {"input_text", "output_text", "text"}:
            raw_text = str(item.get("text", ""))
            if raw_text.strip() in {"<image>", "</image>"}:
                continue
            text = clean_codex_text(raw_text)
            if text == "[图片]" and image_seen:
                continue
            if text and not is_ignored_text(text):
                parts.append(text)

    return "\n".join(part for part in parts if part).strip()

def parse_codex_file(filepath: Path) -> list[dict]:
    rows = []
    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue

            if event.get("type") != "response_item":
                continue

            payload = event.get("payload") or {}
            if payload.get("type") != "message":
                continue

            role = payload.get("role")
            if role != "user":
                continue

            content = extract_codex_content(payload.get("content"))
            if not content:
                continue

            ts_raw = event.get("timestamp")
            if not ts_raw:
                continue
            
            try:
                bjt_dt = to_bjt(ts_raw)
            except Exception:
                continue

            if bjt_dt.strftime("%Y-%m-%d") != TARGET_DATE:
                continue

            rows.append({
                "dt": bjt_dt,
                "time": bjt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "role": "用户",
                "text": content,
                "source": f"Codex ({filepath.name})",
            })
    return rows

def parse_gemini_logs() -> list[dict]:
    gemini_records = []
    if not GEMINI_LOGS_DIR.exists():
        return gemini_records
    
    user_request_pattern = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
    
    for folder in GEMINI_LOGS_DIR.iterdir():
        if not folder.is_dir():
            continue
        log_file = folder / ".system_generated" / "logs" / "overview.txt"
        if not log_file.exists():
            continue
        
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                
                if obj.get("type") != "USER_INPUT":
                    continue
                
                content = obj.get("content", "")
                if not content:
                    continue
                
                # Extract user request content
                match = user_request_pattern.search(content)
                if match:
                    text = match.group(1).strip()
                else:
                    text = content.strip()
                
                ts_raw = obj.get("created_at", "")
                if not ts_raw:
                    continue
                
                try:
                    dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    bjt_dt = dt.astimezone(BJT)
                except Exception:
                    continue
                
                if bjt_dt.strftime("%Y-%m-%d") != TARGET_DATE:
                    continue
                
                # Check for model changes or settings change to exclude or clean up
                # (usually user request handles that)
                gemini_records.append({
                    "dt": bjt_dt,
                    "time": bjt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "role": "用户",
                    "text": text,
                    "source": f"Gemini ({folder.name})",
                })
    return gemini_records

def main():
    print(f"--- 正在解析 {TARGET_DATE} 的所有聊天日志 ---")
    
    # 1. Claude
    claude_rows = []
    if CLAUDE_LOGS_DIR.exists():
        for fp in sorted(CLAUDE_LOGS_DIR.glob("*.jsonl")):
            try:
                rows = parse_claude_file(fp)
                if rows:
                    claude_rows.extend(rows)
            except Exception as e:
                print(f"解析 Claude 文件出错 {fp.name}: {e}")
    print(f"发现 {len(claude_rows)} 条 Claude 记录")
    
    # 2. Codex
    codex_rows = []
    # Check both the session dir and the workspace
    if CODEX_LOGS_DIR.exists():
        for fp in sorted(CODEX_LOGS_DIR.glob("*.jsonl")):
            try:
                rows = parse_codex_file(fp)
                if rows:
                    codex_rows.extend(rows)
            except Exception as e:
                print(f"解析 Codex 目录文件出错 {fp.name}: {e}")
    # Also check workspace
    for fp in sorted(WORKSPACE_DIR.glob(f"*{TARGET_DATE}*.jsonl")):
        try:
            rows = parse_codex_file(fp)
            if rows:
                codex_rows.extend(rows)
        except Exception as e:
            print(f"解析 Workspace Codex 文件出错 {fp.name}: {e}")
            
    print(f"发现 {len(codex_rows)} 条 Codex 记录")
    
    # 3. Gemini
    gemini_rows = parse_gemini_logs()
    print(f"发现 {len(gemini_rows)} 条 Gemini 记录")
    
    all_records = claude_rows + codex_rows + gemini_rows
    # Sort chronologically by datetime, then by source
    all_records.sort(key=lambda r: (r["dt"], r["source"]))
    
    print(f"总计找到 {len(all_records)} 条记录")
    
    # Print the first few and last few to verify
    if all_records:
        print("\n--- 首 5 条记录 ---")
        for r in all_records[:5]:
            print(f"[{r['time']}] ({r['source']}): {r['text'][:60]}...")
            
        print("\n--- 尾 5 条记录 ---")
        for r in all_records[-5:]:
            print(f"[{r['time']}] ({r['source']}): {r['text'][:60]}...")

if __name__ == "__main__":
    main()
