import json
import re
from datetime import datetime, timezone, timedelta
from html import escape
from pathlib import Path


TARGET_DATE = "2026-05-15"
BEIJING = timezone(timedelta(hours=8))
WORKSPACE = Path(__file__).resolve().parent
CODEX_SESSIONS = Path.home() / ".codex" / "sessions" / "2026" / "05" / "15"
OUTPUT = WORKSPACE / "codex-2026-05-15-dialog-table-linebreaks.html"
OUTPUT_QUESTIONS = WORKSPACE / "codex-2026-05-15-questions-only.html"


BASE64_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\r\n]+")


def parse_time(value):
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING)


def is_ignored_text(text):
    stripped = text.strip()
    if not stripped:
        return True
    ignored_blocks = (
        "<environment_context>",
        "<turn_aborted>",
    )
    return any(stripped.startswith(marker) for marker in ignored_blocks)


def clean_text(text):
    text = BASE64_RE.sub("[图片]", text)
    text = text.replace("<image>", "[图片]").replace("</image>", "")
    return text.strip("\n")


def extract_content(content):
    if isinstance(content, str):
        text = clean_text(content)
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
            text = clean_text(raw_text)
            if text == "[图片]" and image_seen:
                continue
            if text and not is_ignored_text(text):
                parts.append(text)

    return "\n".join(part for part in parts if part).strip()


def iter_log_files():
    if CODEX_SESSIONS.exists():
        yield from sorted(CODEX_SESSIONS.glob("*.jsonl"))
    yield from sorted(WORKSPACE.glob(f"*{TARGET_DATE}*.jsonl"))
    yield from sorted((WORKSPACE / "logs").glob(f"*{TARGET_DATE.replace('-', '')}*.jsonl")) if (WORKSPACE / "logs").exists() else ()


def collect_records():
    records = []
    seen_files = set()
    for path in iter_log_files():
        resolved = path.resolve()
        if resolved in seen_files or path.stat().st_size == 0:
            continue
        seen_files.add(resolved)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("type") != "response_item":
                    continue

                payload = event.get("payload") or {}
                if payload.get("type") != "message":
                    continue

                role = payload.get("role")
                if role == "user":
                    speaker = "用户"
                elif role == "assistant":
                    speaker = "AI"
                else:
                    continue

                content = extract_content(payload.get("content"))
                if not content:
                    continue

                timestamp = parse_time(event.get("timestamp"))
                if not timestamp or timestamp.strftime("%Y-%m-%d") != TARGET_DATE:
                    continue

                records.append(
                    {
                        "time": timestamp,
                        "speaker": speaker,
                        "content": content,
                        "source": str(path),
                        "line": line_number,
                    }
                )

    records.sort(key=lambda item: (item["time"], item["source"], item["line"]))
    return records


def render_html(records, title, subtitle):
    generated_at = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for record in records:
        css_class = "user-row" if record["speaker"] == "用户" else "ai-row"
        rows.append(
            "      <tr class=\"{css_class}\">\n"
            "        <td class=\"time\">{time}</td>\n"
            "        <td class=\"speaker\">{speaker}</td>\n"
            "        <td class=\"content\">{content}</td>\n"
            "      </tr>".format(
                css_class=css_class,
                time=escape(record["time"].strftime("%Y-%m-%d %H:%M:%S")),
                speaker=escape(record["speaker"]),
                content=escape(record["content"]),
            )
        )

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{
      margin: 24px;
      color: #111827;
      background: #ffffff;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      font-size: 13px;
      line-height: 1.55;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 20px;
      font-weight: 700;
    }}
    .meta {{
      margin: 0 0 16px;
      color: #4b5563;
      font-size: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      border: 1px solid #9ca3af;
    }}
    th, td {{
      border: 1px solid #9ca3af;
      padding: 6px 8px;
      vertical-align: top;
    }}
    th {{
      background: #e5e7eb;
      text-align: left;
      font-weight: 700;
    }}
    .time {{
      width: 126px;
      white-space: nowrap;
      color: #374151;
    }}
    .speaker {{
      width: 46px;
      text-align: center;
      white-space: nowrap;
      font-weight: 700;
    }}
    .content {{
      width: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .user-row {{
      background: #fff7cc;
    }}
    .ai-row {{
      background: #ffffff;
    }}
    @media print {{
      body {{
        margin: 10mm;
      }}
      table {{
        page-break-inside: auto;
      }}
      tr {{
        page-break-inside: avoid;
        page-break-after: auto;
      }}
    }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">{subtitle}；生成时间：{generated_at}（北京时间）；记录数：{count}</p>
  <table>
    <thead>
      <tr>
        <th class="time">时间</th>
        <th class="speaker">发言人</th>
        <th class="content">内容</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
""".format(
        title=escape(title),
        subtitle=escape(subtitle),
        generated_at=escape(generated_at),
        count=len(records),
        rows="\n".join(rows),
    )


def main():
    records = collect_records()
    questions = [record for record in records if record["speaker"] == "用户"]

    OUTPUT.write_text(
        render_html(records, "Codex 2026-05-15 对话记录", "问 + 答"),
        encoding="utf-8",
    )
    OUTPUT_QUESTIONS.write_text(
        render_html(questions, "Codex 2026-05-15 提问记录", "仅用户提问"),
        encoding="utf-8",
    )

    print(f"records={len(records)}")
    print(f"questions={len(questions)}")
    print(f"output_full={OUTPUT}")
    print(f"output_questions={OUTPUT_QUESTIONS}")


if __name__ == "__main__":
    main()
