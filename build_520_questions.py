#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import escape

# Timezone and target date
BJT = timezone(timedelta(hours=8))
TARGET_DATE = "2026-05-20"

# Directories
CLAUDE_LOGS_DIR = Path(os.path.expandvars(r"%USERPROFILE%\.claude\projects\d--items-QW"))
CODEX_LOGS_DIR = Path.home() / ".codex" / "sessions" / "2026" / "05" / "20"
GEMINI_LOGS_DIR = Path(os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity\brain"))
WORKSPACE_DIR = Path(r"d:\items\QW")
OUTPUT_HTML_PATH = WORKSPACE_DIR / f"claude-code-{TARGET_DATE}-questions-only.html"

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
                "source": "Claude",
                "detail_source": f"Claude Code ({filepath.name})",
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
    
    # Try to extract the user query after the IDE context block
    match = re.search(r"## My request for (?:Codex|AI|assistant):\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            return extracted
            
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
                "source": "Codex",
                "detail_source": f"Codex ({filepath.name})",
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
                
                gemini_records.append({
                    "dt": bjt_dt,
                    "time": bjt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "role": "用户",
                    "text": text,
                    "source": "Gemini",
                    "detail_source": f"Gemini Agent ({folder.name})",
                })
    return gemini_records

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>2026-05-20 智能助手多端提问汇总记录</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-primary: #0f172a;
      --bg-secondary: #1e293b;
      --bg-tertiary: #0f172a;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --accent-claude: #8b5cf6;
      --accent-claude-bg: rgba(139, 92, 246, 0.15);
      --accent-codex: #f97316;
      --accent-codex-bg: rgba(249, 115, 22, 0.15);
      --accent-gemini: #0ea5e9;
      --accent-gemini-bg: rgba(14, 165, 233, 0.15);
      --border-color: rgba(255, 255, 255, 0.08);
      --card-border-hover: rgba(99, 102, 241, 0.4);
      --shadow-color: rgba(0, 0, 0, 0.3);
      --glow-color: rgba(99, 102, 241, 0.15);
    }}

    [data-theme="light"] {{
      --bg-primary: #f8fafc;
      --bg-secondary: #ffffff;
      --bg-tertiary: #f1f5f9;
      --text-primary: #0f172a;
      --text-secondary: #64748b;
      --accent-claude-bg: rgba(139, 92, 246, 0.1);
      --accent-codex-bg: rgba(249, 115, 22, 0.1);
      --accent-gemini-bg: rgba(14, 165, 233, 0.1);
      --border-color: rgba(0, 0, 0, 0.08);
      --card-border-hover: rgba(99, 102, 241, 0.3);
      --shadow-color: rgba(0, 0, 0, 0.05);
      --glow-color: rgba(99, 102, 241, 0.05);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg-primary);
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      line-height: 1.6;
      transition: background-color 0.3s, color 0.3s;
      padding-bottom: 60px;
    }}

    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 20px;
    }}

    /* Header section */
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 28px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 24px;
    }}

    .header-left h1 {{
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.025em;
      margin-bottom: 8px;
      background: linear-gradient(to right, #818cf8, #c084fc, #60a5fa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .header-left p {{
      font-size: 13px;
      color: var(--text-secondary);
    }}

    /* Theme Toggle */
    .theme-toggle-btn {{
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 500;
      transition: all 0.2s;
    }}
    .theme-toggle-btn:hover {{
      transform: translateY(-1px);
      box-shadow: 0 4px 12px var(--shadow-color);
    }}

    /* Stats Dashboard */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 28px;
    }}

    .stat-card {{
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      position: relative;
      overflow: hidden;
      transition: all 0.2s;
    }}
    .stat-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 8px 24px var(--shadow-color);
    }}
    .stat-card::before {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
    }}
    .stat-card.total::before {{ background: linear-gradient(to bottom, #818cf8, #c084fc); }}
    .stat-card.claude::before {{ background-color: var(--accent-claude); }}
    .stat-card.codex::before {{ background-color: var(--accent-codex); }}
    .stat-card.gemini::before {{ background-color: var(--accent-gemini); }}

    .stat-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-secondary);
      margin-bottom: 4px;
      font-weight: 600;
    }}
    .stat-value {{
      font-size: 26px;
      font-weight: 700;
      color: var(--text-primary);
    }}

    /* Controls bar (Tabs & Search) */
    .controls-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      gap: 16px;
      flex-wrap: wrap;
    }}

    .filter-tabs {{
      display: flex;
      background-color: var(--bg-secondary);
      padding: 4px;
      border-radius: 10px;
      border: 1px solid var(--border-color);
      gap: 2px;
    }}

    .filter-btn {{
      background: transparent;
      border: none;
      color: var(--text-secondary);
      padding: 6px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 500;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .filter-btn:hover {{
      color: var(--text-primary);
    }}
    .filter-btn.active {{
      background-color: var(--bg-primary);
      color: var(--text-primary);
      box-shadow: 0 2px 6px var(--shadow-color);
    }}

    .search-box {{
      position: relative;
      flex: 1;
      max-width: 320px;
    }}
    .search-input {{
      width: 100%;
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 8px 12px 8px 34px;
      border-radius: 8px;
      font-size: 12px;
      outline: none;
      transition: all 0.2s;
    }}
    .search-input:focus {{
      border-color: var(--card-border-hover);
      box-shadow: 0 0 0 3px var(--glow-color);
    }}
    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-secondary);
      pointer-events: none;
    }}

    /* Table styles */
    .table-container {{
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 20px var(--shadow-color);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}

    th, td {{
      padding: 12px 16px;
      vertical-align: top;
      border-bottom: 1px solid var(--border-color);
      text-align: left;
    }}

    th {{
      background-color: var(--bg-tertiary);
      font-weight: 600;
      color: var(--text-secondary);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-bottom: 2px solid var(--border-color);
    }}

    .col-time {{ width: 150px; text-align: center; }}
    .col-source {{ width: 140px; text-align: center; }}
    .col-content {{ width: auto; }}

    tbody tr {{
      transition: all 0.15s;
    }}
    tbody tr:hover {{
      background-color: rgba(99, 102, 241, 0.03);
    }}

    .time-cell {{
      font-family: 'Fira Code', monospace;
      color: var(--text-secondary);
      font-size: 12px;
      white-space: nowrap;
      text-align: center;
    }}

    .source-cell {{
      text-align: center;
    }}

    /* Source Badge */
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .badge.claude {{
      background-color: var(--accent-claude-bg);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.2);
    }}
    .badge.codex {{
      background-color: var(--accent-codex-bg);
      color: #fdba74;
      border: 1px solid rgba(249, 115, 22, 0.2);
    }}
    .badge.gemini {{
      background-color: var(--accent-gemini-bg);
      color: #7dd3fc;
      border: 1px solid rgba(14, 165, 233, 0.2);
    }}

    /* Content Rendering */
    .content-cell {{
      position: relative;
    }}
    
    .col-content-text {{
      word-wrap: break-word;
      overflow-wrap: break-word;
      white-space: pre-wrap;
      padding-right: 40px;
    }}

    .col-content-text pre {{
      background: rgba(0, 0, 0, 0.15);
      padding: 10px 14px;
      border-radius: 8px;
      border: 1px solid var(--border-color);
      overflow-x: auto;
      margin: 8px 0;
      font-family: 'Fira Code', monospace;
      font-size: 12px;
    }}

    .col-content-text code {{
      background: rgba(255, 255, 255, 0.08);
      padding: 2px 4px;
      border-radius: 4px;
      font-family: 'Fira Code', monospace;
      font-size: 12px;
    }}

    /* Copy Button */
    .copy-btn {{
      position: absolute;
      right: 12px;
      top: 10px;
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      color: var(--text-secondary);
      width: 28px;
      height: 28px;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: all 0.2s;
    }}
    .content-cell:hover .copy-btn {{
      opacity: 1;
    }}
    .copy-btn:hover {{
      color: var(--text-primary);
      border-color: var(--card-border-hover);
      background-color: var(--bg-primary);
    }}

    /* Tooltip */
    .tooltip {{
      position: absolute;
      bottom: 100%;
      right: 0;
      background-color: #1e293b;
      color: #f8fafc;
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 11px;
      white-space: nowrap;
      pointer-events: none;
      opacity: 0;
      transform: translateY(4px);
      transition: all 0.15s;
      box-shadow: 0 4px 10px rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.1);
    }}
    .copy-btn:hover .tooltip {{
      opacity: 1;
      transform: translateY(-4px);
    }}
    .tooltip.show {{
      opacity: 1;
      transform: translateY(-4px);
      background-color: #10b981;
      border-color: rgba(16, 185, 129, 0.3);
    }}

    /* Back to top */
    .back-to-top {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      width: 36px;
      height: 36px;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      opacity: 0;
      visibility: hidden;
      transition: all 0.3s;
      z-index: 99;
    }}
    .back-to-top.show {{
      opacity: 1;
      visibility: visible;
    }}
    .back-to-top:hover {{
      transform: translateY(-2px);
      border-color: var(--card-border-hover);
    }}

    @media (max-width: 768px) {{
      .stats-grid {{
        grid-template-columns: repeat(2, 1fr);
      }}
      .controls-bar {{
        flex-direction: column;
        align-items: stretch;
      }}
      .search-box {{
        max-width: none;
      }}
      .col-time {{ width: 120px; }}
      .col-source {{ width: 100px; }}
    }}
  </style>
</head>
<body>

<div class="container">
  <header>
    <div class="header-left">
      <h1>2026-05-20 智能助手多端提问汇总记录</h1>
      <p>汇聚当天所有的用户提问记录（北京时间），用于评估及追溯各智能体的实际交互场景</p>
    </div>
    <button class="theme-toggle-btn" id="theme-toggle">
      <svg id="theme-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
      </svg>
      <span id="theme-text">浅色模式</span>
    </button>
  </header>

  <!-- Stats Grid -->
  <div class="stats-grid">
    <div class="stat-card total">
      <span class="stat-label">总提问记录</span>
      <span class="stat-value">{total_count}</span>
    </div>
    <div class="stat-card claude">
      <span class="stat-label">Claude Code</span>
      <span class="stat-value">{claude_count}</span>
    </div>
    <div class="stat-card codex">
      <span class="stat-label">Codex 终端</span>
      <span class="stat-value">{codex_count}</span>
    </div>
    <div class="stat-card gemini">
      <span class="stat-label">Gemini Agent</span>
      <span class="stat-value">{gemini_count}</span>
    </div>
  </div>

  <!-- Controls Bar -->
  <div class="controls-bar">
    <div class="filter-tabs">
      <button class="filter-btn active" data-filter="all">全部 ({total_count})</button>
      <button class="filter-btn" data-filter="Claude">Claude Code ({claude_count})</button>
      <button class="filter-btn" data-filter="Codex">Codex ({codex_count})</button>
      <button class="filter-btn" data-filter="Gemini">Gemini Agent ({gemini_count})</button>
    </div>
    <div class="search-box">
      <span class="search-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
        </svg>
      </span>
      <input type="text" class="search-input" id="search-input" placeholder="搜索提问内容...">
    </div>
  </div>

  <!-- Table Container -->
  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th class="col-time">时间</th>
          <th class="col-source">来源端</th>
          <th class="col-content">提问内容</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
</div>

<button class="back-to-top" id="back-to-top">
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="m18 15-6-6-6 6"/>
  </svg>
</button>

<script>
  // Filter & Search Logic
  const filterButtons = document.querySelectorAll('.filter-btn');
  const searchInput = document.getElementById('search-input');
  const rows = document.querySelectorAll('tbody tr');

  let activeSource = 'all';
  let searchQuery = '';

  function updateFilter() {{
    rows.forEach(row => {{
      const source = row.getAttribute('data-source');
      const content = row.querySelector('.col-content-text').textContent.toLowerCase();
      
      const matchesSource = (activeSource === 'all' || source === activeSource);
      const matchesSearch = content.includes(searchQuery);
      
      if (matchesSource && matchesSearch) {{
        row.style.display = '';
      }} else {{
        row.style.display = 'none';
      }}
    }});
  }}

  filterButtons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      filterButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeSource = btn.getAttribute('data-filter');
      updateFilter();
    }});
  }});

  searchInput.addEventListener('input', (e) => {{
    searchQuery = e.target.value.toLowerCase();
    updateFilter();
  }});

  // Theme Toggle
  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = document.getElementById('theme-icon');
  const themeText = document.getElementById('theme-text');
  const html = document.documentElement;

  themeToggle.addEventListener('click', () => {{
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    
    if (newTheme === 'light') {{
      themeText.textContent = '深色模式';
      themeIcon.innerHTML = `
        <circle cx="12" cy="12" r="4"/>
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" stroke-linecap="round"/>
      `;
    }} else {{
      themeText.textContent = '浅色模式';
      themeIcon.innerHTML = `<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>`;
    }}
  }});

  // Copy to Clipboard
  function copyText(btn, elementId) {{
    const textElement = document.getElementById(elementId);
    const text = textElement.textContent;
    navigator.clipboard.writeText(text).then(() => {{
      const tooltip = btn.querySelector('.tooltip');
      tooltip.textContent = '已复制!';
      tooltip.classList.add('show');
      setTimeout(() => {{
        tooltip.classList.remove('show');
        tooltip.textContent = '复制内容';
      }}, 1500);
    }});
  }}

  // Back to Top Button
  const backToTop = document.getElementById('back-to-top');
  window.addEventListener('scroll', () => {{
    if (window.scrollY > 300) {{
      backToTop.classList.add('show');
    }} else {{
      backToTop.classList.remove('show');
    }}
  }});
  backToTop.addEventListener('click', () => {{
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }});
</script>
</body>
</html>
"""

def main():
    print(f"--- 启动 2026-05-20 提问记录生成服务 ---")
    
    # 1. Parse Claude
    claude_rows = []
    if CLAUDE_LOGS_DIR.exists():
        for fp in sorted(CLAUDE_LOGS_DIR.glob("*.jsonl")):
            try:
                rows = parse_claude_file(fp)
                if rows:
                    claude_rows.extend(rows)
            except Exception as e:
                print(f"[错误] 解析 Claude 文件 {fp.name}: {e}")
    
    # 2. Parse Codex
    codex_rows = []
    if CODEX_LOGS_DIR.exists():
        for fp in sorted(CODEX_LOGS_DIR.glob("*.jsonl")):
            try:
                rows = parse_codex_file(fp)
                if rows:
                    codex_rows.extend(rows)
            except Exception as e:
                print(f"[错误] 解析 Codex 文件 {fp.name}: {e}")
    for fp in sorted(WORKSPACE_DIR.glob(f"*{TARGET_DATE}*.jsonl")):
        try:
            rows = parse_codex_file(fp)
            if rows:
                codex_rows.extend(rows)
        except Exception as e:
            print(f"[错误] 解析 Workspace Codex 文件 {fp.name}: {e}")
            
    # 3. Parse Gemini
    gemini_rows = parse_gemini_logs()
    
    all_records = claude_rows + codex_rows + gemini_rows
    # Sort chronologically by datetime
    all_records.sort(key=lambda r: (r["dt"], r["source"]))
    
    total_count = len(all_records)
    claude_count = len(claude_rows)
    codex_count = len(codex_rows)
    gemini_count = len(gemini_rows)
    
    print(f"解析完成！共有 {total_count} 条记录：")
    print(f"  Claude Code: {claude_count} 条")
    print(f"  Codex 终端:  {codex_count} 条")
    print(f"  Gemini Agent: {gemini_count} 条")
    
    # Generate Rows HTML
    rows_html_list = []
    for idx, r in enumerate(all_records):
        source = r["source"]
        badge_class = "claude" if source == "Claude" else ("codex" if source == "Codex" else "gemini")
        
        # HTML Escape the text
        escaped_text = escape(r["text"])
        
        # Format code blocks neatly if any
        # (Replace triple backticks with <pre><code> and single backticks with <code>)
        # Note: We need a basic parser for markdown snippets to make it look even more premium!
        text_html = escaped_text
        
        # Replace code blocks: ```lang\ncode\n```
        def repl_pre(match):
            code_content = match.group(2)
            return f"<pre><code>{code_content}</code></pre>"
        text_html = re.sub(r"```([a-zA-Z0-9_-]*)\n(.*?)\n```", repl_pre, text_html, flags=re.DOTALL)
        
        # Replace inline code: `code`
        text_html = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text_html)
        
        element_id = f"content-text-{idx}"
        
        row_str = f"""        <tr class="question-row" data-source="{source}">
          <td class="col-time">
            <div class="time-cell">{r['time']}</div>
          </td>
          <td class="col-source">
            <div class="source-cell">
              <span class="badge {badge_class}" title="{escape(r['detail_source'])}">{source}</span>
            </div>
          </td>
          <td class="col-content content-cell">
            <div class="col-content-text" id="{element_id}">{text_html}</div>
            <button class="copy-btn" onclick="copyText(this, '{element_id}')" title="复制内容">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
              </svg>
              <span class="tooltip">复制内容</span>
            </button>
          </td>
        </tr>"""
        rows_html_list.append(row_str)
        
    rows_html = "\n".join(rows_html_list)
    
    # Render final page
    final_html = HTML_TEMPLATE.format(
        total_count=total_count,
        claude_count=claude_count,
        codex_count=codex_count,
        gemini_count=gemini_count,
        rows_html=rows_html
    )
    
    OUTPUT_HTML_PATH.write_text(final_html, encoding="utf-8")
    print(f"完美生成！HTML 页面已保存至: {OUTPUT_HTML_PATH}")

if __name__ == "__main__":
    main()
