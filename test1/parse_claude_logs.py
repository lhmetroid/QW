#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 Claude Code JSONL 日志，生成对话记录 HTML 表格"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

TARGET_DATE = "2026-05-14"
LOG_DIR = Path(r"C:\Users\Admin\.claude\projects\d--items-QW")
OUTPUT_FILE = Path(r"d:\items\QW") / f"claude-code-{TARGET_DATE}-dialog-table.html"
BEIJING_TZ = timezone(timedelta(hours=8))


def to_beijing_time(ts_str: str) -> datetime:
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return dt.astimezone(BEIJING_TZ)


def strip_injected_tags(text: str) -> str:
    """移除 IDE 注入的 <ide_selection> 和 <system-reminder> 标签块"""
    text = re.sub(r"<ide_selection>.*?</ide_selection>", "", text, flags=re.DOTALL)
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL)
    return text.strip()


def extract_user_text(content) -> str | None:
    """从 user 消息 content 数组中提取真实用户文本"""
    if isinstance(content, str):
        cleaned = strip_injected_tags(content)
        return cleaned if cleaned else None

    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "")
        if item_type == "text":
            cleaned = strip_injected_tags(item.get("text", ""))
            if cleaned:
                parts.append(cleaned)
        elif item_type in ("image", "image_url"):
            parts.append("[图片]")
        elif item_type == "tool_result":
            pass  # 忽略工具返回
    result = "\n".join(parts).strip()
    return result if result else None


def extract_assistant_text(content) -> str | None:
    """从 assistant 消息 content 数组中提取文本块（忽略 thinking/tool_use）"""
    if isinstance(content, str):
        return content.strip() if content.strip() else None

    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "")
        if item_type == "text":
            text = item.get("text", "").strip()
            if text:
                parts.append(text)
        elif item_type in ("image", "image_url"):
            parts.append("[图片]")
        # 忽略 thinking / tool_use / tool_result
    result = "\n".join(parts).strip()
    return result if result else None


def collect_messages():
    messages = []
    # 找到当天修改的所有 jsonl 文件（含子目录 subagents）
    for jsonl_file in LOG_DIR.rglob("*.jsonl"):
        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=BEIJING_TZ)
        if mtime.strftime("%Y-%m-%d") != TARGET_DATE:
            continue

        session_id = jsonl_file.stem[:8]  # 前8位作标识
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    entry_type = obj.get("type", "")
                    timestamp_str = obj.get("timestamp", "")
                    if not timestamp_str:
                        continue

                    try:
                        dt = to_beijing_time(timestamp_str)
                    except Exception:
                        continue

                    # 只在当天范围内
                    if dt.strftime("%Y-%m-%d") != TARGET_DATE:
                        continue

                    msg = obj.get("message", {})
                    role = msg.get("role", "")
                    content = msg.get("content", [])

                    if entry_type == "user" and role == "user":
                        text = extract_user_text(content)
                        if text:
                            messages.append({
                                "dt": dt,
                                "speaker": "用户",
                                "text": text,
                                "session": session_id,
                            })
                    elif entry_type == "assistant" and role == "assistant":
                        text = extract_assistant_text(content)
                        if text:
                            messages.append({
                                "dt": dt,
                                "speaker": "AI",
                                "text": text,
                                "session": session_id,
                            })
        except Exception as e:
            print(f"  跳过文件 {jsonl_file.name}：{e}")

    # 按时间升序排列
    messages.sort(key=lambda x: x["dt"])
    return messages


def escape_html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def generate_html(messages: list) -> str:
    rows = []
    for msg in messages:
        time_str = msg["dt"].strftime("%Y-%m-%d\n%H:%M:%S")
        speaker = msg["speaker"]
        text = escape_html(msg["text"])
        row_style = 'style="background:#fffbe6;"' if speaker == "用户" else ""
        rows.append(f"""  <tr {row_style}>
    <td class="col-time">{time_str.replace(chr(10), '<br>')}</td>
    <td class="col-speaker">{speaker}</td>
    <td class="col-content"><pre>{text}</pre></td>
  </tr>""")

    rows_html = "\n".join(rows)
    total = len(messages)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code 对话记录 {TARGET_DATE}</title>
<style>
  body {{
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    margin: 20px;
    color: #222;
  }}
  h2 {{ margin-bottom: 6px; }}
  .meta {{ color: #666; margin-bottom: 12px; font-size: 12px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  th, td {{
    border: 1px solid #c8c8c8;
    padding: 6px 8px;
    vertical-align: top;
  }}
  th {{
    background: #f0f0f0;
    text-align: center;
    font-weight: 600;
  }}
  .col-time {{
    width: 125px;
    text-align: center;
    white-space: nowrap;
    font-size: 12px;
    color: #555;
  }}
  .col-speaker {{
    width: 48px;
    text-align: center;
    font-weight: bold;
  }}
  .col-content {{
    word-break: break-word;
    overflow-wrap: break-word;
  }}
  .col-content pre {{
    margin: 0;
    font-family: inherit;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  @media print {{
    body {{ margin: 8px; font-size: 11px; }}
    .col-time {{ width: 100px; }}
  }}
</style>
</head>
<body>
<h2>Claude Code 对话记录 &nbsp; {TARGET_DATE}</h2>
<p class="meta">共 {total} 条对话记录 &nbsp;|&nbsp; 导出时间：{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")} (北京时间)</p>
<table>
  <thead>
    <tr>
      <th class="col-time">时间</th>
      <th class="col-speaker">发言人</th>
      <th class="col-content">内容</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>
</body>
</html>"""


def main():
    print(f"扫描目录：{LOG_DIR}")
    print(f"目标日期：{TARGET_DATE}")
    print("正在解析日志文件（大文件可能需要几秒钟）...")
    messages = collect_messages()
    print(f"共提取到 {len(messages)} 条对话记录")

    html = generate_html(messages)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"已生成文件：{OUTPUT_FILE}")
    return len(messages)


if __name__ == "__main__":
    main()
