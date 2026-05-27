#!/usr/bin/env python3
"""
解析 Claude Code JSONL 日志，导出 2026-05-18 当天的对话记录为 HTML 表格。

自动扫描 ~/.claude/projects/d--items-QW/*.jsonl，按消息 timestamp 过滤当天数据，
分别输出两份 HTML：
  1) 完整版（问+答）
  2) 仅用户提问版
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import escape

LOGS_DIR = Path(os.path.expandvars(r"%USERPROFILE%\.claude\projects\d--items-QW"))
OUT_DIR = Path(r"d:\items\QW")
TARGET_DATE = "2026-05-18"
BJT = timezone(timedelta(hours=8))

OUT_FULL = OUT_DIR / f"claude-code-{TARGET_DATE}-dialog-table-linebreaks.html"
OUT_QONLY = OUT_DIR / f"claude-code-{TARGET_DATE}-questions-only.html"

BASE64_PATTERN = re.compile(r'data:[^;]+;base64,[A-Za-z0-9+/=]{100,}')
# 常见的工具/系统消息前缀（如 <command-name>、<local-command-stdout> 等也算系统噪音）
SYSTEM_TAG_PATTERN = re.compile(
    r'^<(command-name|command-message|command-args|local-command-stdout|local-command-stderr|'
    r'system-reminder|ide_selection|ide_opened_file|user-prompt-submit-hook)\b',
    re.IGNORECASE,
)


def to_bjt(ts_str: str) -> datetime:
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return dt.astimezone(BJT)


def extract_text(content) -> str:
    """从 message.content 中提取纯文字，跳过工具调用/结果/思考链/系统注入。"""
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

            # 忽略 isMeta / isSidechain 等元信息条目
            if obj.get("isMeta") or obj.get("isSidechain"):
                continue

            msg = obj.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue

            text = extract_text(msg.get("content", ""))
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


CSS = """
  * { box-sizing: border-box; }
  body {
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
    margin: 20px;
    color: #222;
  }
  h2 { margin-bottom: 12px; }
  table {
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
  }
  th, td {
    border: 1px solid #bbb;
    padding: 6px 8px;
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: break-word;
    white-space: pre-wrap;
  }
  th {
    background: #f0f0f0;
    font-weight: bold;
    text-align: center;
  }
  .col-time   { width: 128px; white-space: nowrap; text-align: center; }
  .col-role   { width: 48px;  text-align: center; font-weight: bold; }
  .col-content { /* 剩余宽度 */ }
  @media print {
    body { margin: 0; font-size: 11px; }
    th, td { padding: 4px 6px; }
  }
"""


def build_html(rows: list[dict], title: str, source_count: int, qonly: bool) -> str:
    rows_html = []
    for r in rows:
        bg = "#fffde7" if r["role"] == "用户" else "#ffffff"
        content_html = escape(r["text"])  # white-space: pre-wrap 已保留换行，无需 <br>
        rows_html.append(
            f'    <tr style="background:{bg}">'
            f'<td class="col-time">{escape(r["time"])}</td>'
            f'<td class="col-role">{escape(r["role"])}</td>'
            f'<td class="col-content">{content_html}</td></tr>'
        )
    body = "\n".join(rows_html)
    subtitle = "（仅用户提问）" if qonly else "（问 + 答）"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<h2>{escape(title)} &mdash; {TARGET_DATE}（北京时间）{subtitle}</h2>
<p>共 {len(rows)} 条记录（来源：{source_count} 个会话文件）</p>
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
    if not LOGS_DIR.exists():
        raise SystemExit(f"日志目录不存在: {LOGS_DIR}")

    files = sorted(LOGS_DIR.glob("*.jsonl"))
    print(f"扫描目录: {LOGS_DIR}")
    print(f"发现 {len(files)} 个 jsonl 文件\n")

    all_rows = []
    used_files = 0
    for fp in files:
        try:
            rows = parse_file(fp)
        except Exception as e:
            print(f"  [跳过] {fp.name}: {e}")
            continue
        if rows:
            used_files += 1
            print(f"  {fp.name}: {len(rows)} 条（{TARGET_DATE}）")
            all_rows.extend(rows)

    all_rows.sort(key=lambda r: (r["dt"], r["uuid"]))

    # 完整版（问 + 答）
    html_full = build_html(all_rows, "Claude Code 对话记录", used_files, qonly=False)
    OUT_FULL.write_text(html_full, encoding="utf-8")

    # 仅提问版
    questions = [r for r in all_rows if r["role"] == "用户"]
    html_q = build_html(questions, "Claude Code 提问记录", used_files, qonly=True)
    OUT_QONLY.write_text(html_q, encoding="utf-8")

    print(f"\n完成！")
    print(f"  全部对话: {len(all_rows)} 条（含用户 {len(questions)} 条 + AI {len(all_rows)-len(questions)} 条）")
    print(f"  来源会话: {used_files} 个文件")
    print(f"  完整版:   {OUT_FULL}")
    print(f"  仅提问版: {OUT_QONLY}")


if __name__ == "__main__":
    main()
