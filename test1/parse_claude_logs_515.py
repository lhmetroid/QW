#!/usr/bin/env python3
"""
解析 Claude Code JSONL 日志，导出 2026-05-15 的对话记录为 HTML 表格。
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import escape

LOGS_DIR = Path(r"C:\Users\Admin\.claude\projects\d--items-QW")
OUTPUT_FILE = Path(r"d:\items\QW\claude-code-2026-05-15-dialog-table-linebreaks.html")
TARGET_DATE = "2026-05-15"
BJT = timezone(timedelta(hours=8))

JSONL_FILES = [
    "109bd2e8-93e0-463e-badc-b8193ae16a2c.jsonl",
    "95a2e133-cd02-4a0a-9b75-6106179ace86.jsonl",
    "d22b73a2-9839-4c43-9d5b-30b4f5434233.jsonl",
]

BASE64_PATTERN = re.compile(r'data:[^;]+;base64,[A-Za-z0-9+/=]{100,}')


def to_bjt(ts_str: str) -> datetime:
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return dt.astimezone(BJT)


def extract_text(content) -> str:
    """从 message.content 中提取纯文字，跳过工具调用/结果/思考链。"""
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type", "")
        if t == "text":
            text = item.get("text", "")
            # 替换 base64 图片数据
            text = BASE64_PATTERN.sub("[图片]", text)
            parts.append(text)
        elif t in ("image", "image_url"):
            parts.append("[图片]")
        elif t == "document":
            # 文档附件，取 title 作标记
            title = item.get("title", "")
            parts.append(f"[文档: {title}]" if title else "[文档]")
        # 跳过: tool_use, tool_result, thinking, attachment 等
    return "\n".join(parts).strip()


def parse_file(filepath: Path) -> list[dict]:
    rows = []
    with open(filepath, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = obj.get("type", "")
            if entry_type not in ("user", "assistant"):
                continue

            msg = obj.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue

            content = msg.get("content", "")
            text = extract_text(content)
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
                "role": "用户" if role == "user" else "AI",
                "text": text,
                "session": obj.get("sessionId", ""),
                "uuid": obj.get("uuid", ""),
            })
    return rows


def build_html(rows: list[dict]) -> str:
    rows_html = []
    for r in rows:
        bg = "#fffde7" if r["role"] == "用户" else "#ffffff"
        # 转义 HTML，保留换行
        content_escaped = escape(r["text"])
        content_html = content_escaped.replace("\n", "<br>")

        rows_html.append(f"""
    <tr style="background:{bg}">
      <td class="col-time">{escape(r["time"])}</td>
      <td class="col-role">{escape(r["role"])}</td>
      <td class="col-content">{content_html}</td>
    </tr>""")

    body = "\n".join(rows_html)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code 对话记录 {TARGET_DATE}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
    margin: 20px;
    color: #222;
  }}
  h2 {{ margin-bottom: 12px; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
  }}
  th, td {{
    border: 1px solid #bbb;
    padding: 6px 8px;
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: break-word;
    white-space: pre-wrap;
  }}
  th {{
    background: #f0f0f0;
    font-weight: bold;
    text-align: center;
  }}
  .col-time  {{ width: 128px; white-space: nowrap; text-align: center; }}
  .col-role  {{ width: 48px;  text-align: center; font-weight: bold; }}
  .col-content {{ /* 剩余宽度 */ }}
  @media print {{
    body {{ margin: 0; font-size: 11px; }}
    th, td {{ padding: 4px 6px; }}
  }}
</style>
</head>
<body>
<h2>Claude Code 对话记录 &mdash; {TARGET_DATE}（北京时间）</h2>
<p>共 {len(rows)} 条对话记录（来源：{len(JSONL_FILES)} 个会话文件）</p>
<table>
  <thead>
    <tr>
      <th class="col-time">时间</th>
      <th class="col-role">发言人</th>
      <th class="col-content">内容</th>
    </tr>
  </thead>
  <tbody>
{body}
  </tbody>
</table>
</body>
</html>
"""


def main():
    all_rows = []
    for fname in JSONL_FILES:
        fpath = LOGS_DIR / fname
        if not fpath.exists():
            print(f"[跳过] 文件不存在: {fpath}")
            continue
        rows = parse_file(fpath)
        print(f"  {fname}: {len(rows)} 条")
        all_rows.extend(rows)

    # 按时间升序排列，同时间按 uuid 稳定
    all_rows.sort(key=lambda r: (r["dt"], r["uuid"]))

    html = build_html(all_rows)
    OUTPUT_FILE.write_text(html, encoding="utf-8")

    print(f"\n完成！共 {len(all_rows)} 条对话记录")
    print(f"输出文件：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
