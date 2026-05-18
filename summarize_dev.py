#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从今日对话日志中提取开发活动摘要"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

TARGET_DATE = "2026-05-14"
LOG_DIR = Path(r"C:\Users\Admin\.claude\projects\d--items-QW")
BEIJING_TZ = timezone(timedelta(hours=8))


def to_beijing(ts_str):
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return dt.astimezone(BEIJING_TZ)


def strip_tags(text):
    text = re.sub(r"<ide_selection>.*?</ide_selection>", "", text, flags=re.DOTALL)
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL)
    return text.strip()


def collect_all():
    entries = []
    for jsonl_file in LOG_DIR.rglob("*.jsonl"):
        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=BEIJING_TZ)
        if mtime.strftime("%Y-%m-%d") != TARGET_DATE:
            continue
        if "subagent" in str(jsonl_file):
            continue
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except:
                        continue
                    ts = obj.get("timestamp", "")
                    if not ts:
                        continue
                    try:
                        dt = to_beijing(ts)
                    except:
                        continue
                    if dt.strftime("%Y-%m-%d") != TARGET_DATE:
                        continue

                    entry_type = obj.get("type", "")
                    msg = obj.get("message", {})
                    role = msg.get("role", "")
                    content = msg.get("content", [])

                    # 提取用户消息
                    if entry_type == "user" and role == "user":
                        texts = []
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    cleaned = strip_tags(item.get("text", ""))
                                    if cleaned:
                                        texts.append(cleaned)
                        elif isinstance(content, str):
                            cleaned = strip_tags(content)
                            if cleaned:
                                texts.append(cleaned)
                        text = "\n".join(texts).strip()
                        if text:
                            entries.append({"dt": dt, "role": "用户", "text": text})

                    # 提取工具调用（了解操作了哪些文件/命令）
                    elif entry_type == "assistant" and role == "assistant":
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "tool_use":
                                    tool_name = item.get("name", "")
                                    tool_input = item.get("input", {})
                                    entries.append({
                                        "dt": dt,
                                        "role": "TOOL",
                                        "tool": tool_name,
                                        "input": tool_input,
                                    })
                            # AI 文本回复
                            ai_texts = []
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    t = item.get("text", "").strip()
                                    if t:
                                        ai_texts.append(t)
                            if ai_texts:
                                entries.append({"dt": dt, "role": "AI", "text": "\n".join(ai_texts)})

        except Exception as e:
            pass

    entries.sort(key=lambda x: x["dt"])
    return entries


def main():
    entries = collect_all()

    # 收集用户请求
    user_msgs = [e for e in entries if e["role"] == "用户"]
    # 收集文件操作
    file_edits = []
    file_writes = []
    bash_cmds = []
    for e in entries:
        if e["role"] != "TOOL":
            continue
        tool = e.get("tool", "")
        inp = e.get("input", {})
        if tool in ("Edit", "MultiEdit"):
            fp = inp.get("file_path", "")
            if fp:
                file_edits.append((e["dt"], fp))
        elif tool == "Write":
            fp = inp.get("file_path", "")
            if fp:
                file_writes.append((e["dt"], fp))
        elif tool in ("Bash", "PowerShell"):
            cmd = inp.get("command", "") or inp.get("script", "")
            desc = inp.get("description", "")
            if cmd:
                bash_cmds.append((e["dt"], desc or cmd[:100]))

    # 统计被修改的文件
    all_modified = {}
    for dt, fp in file_edits + file_writes:
        fname = Path(fp).name
        all_modified[fname] = all_modified.get(fname, 0) + 1

    print("=" * 60)
    print(f"[{TARGET_DATE} Claude Code 开发活动摘要]")
    print("=" * 60)

    print(f"\n[统计]")
    print(f"  用户发送消息：{len(user_msgs)} 条")
    print(f"  文件编辑操作：{len(file_edits)} 次 (Edit)")
    print(f"  文件写入操作：{len(file_writes)} 次 (Write)")
    print(f"  命令执行次数：{len(bash_cmds)} 次 (Bash/PowerShell)")

    print(f"\n[被修改的文件（按操作次数）]")
    for fname, cnt in sorted(all_modified.items(), key=lambda x: -x[1]):
        print(f"  {fname}  ({cnt} 次)")

    print(f"\n[用户主要请求]")
    for i, msg in enumerate(user_msgs, 1):
        first_line = msg["text"].split("\n")[0][:100]
        time_str = msg["dt"].strftime("%H:%M")
        print(f"  [{time_str}] {first_line}")

    print(f"\n[主要命令执行（前40条）]")
    for dt, desc in bash_cmds[:40]:
        print(f"  [{dt.strftime('%H:%M')}] {desc[:80]}")


if __name__ == "__main__":
    main()
