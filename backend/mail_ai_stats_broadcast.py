# -*- coding: utf-8 -*-
"""邮件统计企微群播报。"""
from __future__ import annotations

import html
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, date
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from qywx_utils import QYWXUtils

logger = logging.getLogger(__name__)

BJ_OFFSET = timedelta(hours=8)
_METRICS = (
    ("generated_count", "AI生成邮件数"),
    ("sent_count", "AI实际发送数"),
    ("reply_count", "回信邮件数"),
    ("valuable_count", "有价值邮件数"),
    ("feedback_count", "反馈邮件数"),
)
_scheduler_started = False
_scheduler_lock = threading.Lock()
_last_sent_keys: set[str] = set()


def bj_now() -> datetime:
    return datetime.utcnow() + BJ_OFFSET


def parse_stat_day(value: str | None = None) -> date:
    if value:
        return date.fromisoformat(str(value).strip()[:10])
    return bj_now().date()


def parse_broadcast_times(raw: str | None = None) -> set[str]:
    source = raw if raw is not None else settings.MAIL_AI_STATS_BROADCAST_TIMES
    out: set[str] = set()
    for part in str(source or "").replace("，", ",").split(","):
        item = part.strip()
        if not item:
            continue
        hhmm = item[:5]
        try:
            hh, mm = hhmm.split(":", 1)
            hhi = int(hh)
            mmi = int(mm)
        except Exception:
            continue
        if 0 <= hhi <= 23 and 0 <= mmi <= 59:
            out.add(f"{hhi:02d}:{mmi:02d}")
    return out


def is_workday(day_value: date) -> bool:
    return day_value.weekday() < 5


def _resolve_staff_names(staff_ids: list[str]) -> dict[str, str]:
    ids = sorted({(s or "").strip() for s in staff_ids if (s or "").strip()})
    if not ids:
        return {}
    from crm_database import CRMSessionLocal
    crm = CRMSessionLocal()
    out: dict[str, str] = {}
    try:
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            params = {f"s{j}": v for j, v in enumerate(chunk)}
            ph = ",".join(f":s{j}" for j in range(len(chunk)))
            rows = crm.execute(text(
                f"SELECT StaffId, ISNULL(CAST(StaffName AS NVARCHAR(120)),'') FROM usrStaff WHERE StaffId IN ({ph})"
            ), params).fetchall()
            for row in rows:
                sid = str(row[0] or "").strip()
                name = str(row[1] or "").strip()
                if sid:
                    out[sid] = name or sid
    except Exception:
        logger.warning("MAIL_STATS_BROADCAST_STAFF_NAME_FAILED", exc_info=True)
    finally:
        crm.close()
    return out


def _total_row(rows: list[dict]) -> dict:
    total = {key: 0 for key, _ in _METRICS}
    for row in rows:
        for key, _ in _METRICS:
            total[key] += int(row.get(key) or 0)
    return total


def _row_name(row: dict) -> str:
    return str(row.get("staff_name") or row.get("staff_id") or "未分配")


def format_stats_message(day_value: date, rows: list[dict], refreshed: bool = True) -> str:
    total = _total_row(rows)
    display_day = day_value.strftime("%Y/%m/%d")
    iso_day = day_value.isoformat()
    lines = [
        "按销售单日统计",
        f"日期 {display_day}",
        f"{iso_day} · 合计 生成{total['generated_count']} / 实发{total['sent_count']} / 回信{total['reply_count']} / 有价值{total['valuable_count']} / 反馈{total['feedback_count']}",
        "",
        "销售 | AI生成邮件数 | AI实际发送数 | 回信邮件数 | 有价值邮件数 | 反馈邮件数",
        f"合计 | {total['generated_count']} | {total['sent_count']} | {total['reply_count']} | {total['valuable_count']} | {total['feedback_count']}",
    ]
    for row in rows:
        lines.append(
            f"{_row_name(row)} | {int(row.get('generated_count') or 0)} | {int(row.get('sent_count') or 0)} | "
            f"{int(row.get('reply_count') or 0)} | {int(row.get('valuable_count') or 0)} | {int(row.get('feedback_count') or 0)}"
        )
    lines.append("")
    lines.append(f"数据状态：{'已从CRM刷新' if refreshed else '未刷新'}；播报时间：{bj_now().strftime('%H:%M')}")
    return "\n".join(lines)


def format_stats_html(day_value: date, rows: list[dict], refreshed: bool = True) -> str:
    total = _total_row(rows)
    subtitle = f"{day_value.isoformat()} 的自动邮件数据播报"
    generated_at = bj_now().strftime("%H:%M")
    headers = ["员工", "AI生成邮件数", "AI实际发送数", "回信邮件数", "有价值邮件数", "反馈邮件数"]
    body_rows = [{"staff_name": "合计", **total}] + rows
    tr_html = []
    for row in body_rows:
        tr_html.append(
            "<tr>"
            f"<td>{html.escape(_row_name(row))}</td>"
            f"<td>{int(row.get('generated_count') or 0)}</td>"
            f"<td>{int(row.get('sent_count') or 0)}</td>"
            f"<td>{int(row.get('reply_count') or 0)}</td>"
            f"<td>{int(row.get('valuable_count') or 0)}</td>"
            f"<td>{int(row.get('feedback_count') or 0)}</td>"
            "</tr>"
        )
    th_html = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><style>
body{{margin:0;background:#f3f6fb;font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;color:#111827;}}
.card{{width:920px;min-height:520px;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:28px 32px;box-sizing:border-box;}}
h1{{display:none;}}
.sub{{text-align:center;margin:4px 0 24px;font-size:18px;color:#d11b2d;font-weight:700;}}
table{{width:100%;border-collapse:collapse;font-size:15px;}}
th{{background:#fff7f7;color:#d11b2d;font-weight:700;border:1px solid #f1d7dc;padding:11px 8px;text-align:center;}}
td{{border:1px solid #edf0f4;padding:10px 8px;text-align:center;}}
td:first-child,th:first-child{{text-align:left;width:120px;}}
tr:nth-child(even) td{{background:#fbfcfe;}}
</style></head><body><div class=\"card\">
<div class=\"sub\">{html.escape(subtitle)}</div>
<table><thead><tr>{th_html}</tr></thead><tbody>{''.join(tr_html)}</tbody></table>
</div></body></html>"""


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_stats_image(day_value: date, rows: list[dict], refreshed: bool = True) -> str:
    """把 HTML 同款数据渲染为 PNG 图片，返回临时文件路径。"""
    from PIL import Image, ImageDraw

    total = _total_row(rows)
    body_rows = [{"staff_name": "合计", **total}] + rows
    width = 1080
    height = 610
    margin_x = 46
    img = Image.new("RGB", (width, height), "#f3f6fb")
    draw = ImageDraw.Draw(img)
    card = (28, 28, width - 28, height - 28)
    draw.rounded_rectangle(card, radius=12, fill="#ffffff", outline="#e5e7eb", width=1)

    sub_font = _font(17, bold=True)
    head_font = _font(15, bold=True)
    cell_font = _font(15)

    subtitle = f"{day_value.isoformat()} 的自动邮件数据播报"
    bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    draw.text(((width - (bbox[2] - bbox[0])) / 2, 58), subtitle, fill="#d11b2d", font=sub_font)

    headers = ["员工", "AI生成邮件数", "AI实际发送数", "回信邮件数", "有价值邮件数", "反馈邮件数"]
    col_widths = [150, 170, 170, 150, 165, 165]
    table_x = margin_x
    table_y = 118
    row_h = 46
    x = table_x
    for idx, h in enumerate(headers):
        w = col_widths[idx]
        draw.rectangle((x, table_y, x + w, table_y + row_h), fill="#fff7f7", outline="#f1d7dc")
        draw.text((x + 12, table_y + 13), h, fill="#d11b2d", font=head_font)
        x += w
    for r_idx, row in enumerate(body_rows):
        y = table_y + row_h * (r_idx + 1)
        fill = "#ffffff" if r_idx % 2 == 0 else "#fbfcfe"
        values = [
            _row_name(row),
            str(int(row.get("generated_count") or 0)),
            str(int(row.get("sent_count") or 0)),
            str(int(row.get("reply_count") or 0)),
            str(int(row.get("valuable_count") or 0)),
            str(int(row.get("feedback_count") or 0)),
        ]
        x = table_x
        for c_idx, value in enumerate(values):
            w = col_widths[c_idx]
            draw.rectangle((x, y, x + w, y + row_h), fill=fill, outline="#edf0f4")
            color = "#111827"
            font = head_font if r_idx == 0 else cell_font
            if c_idx == 0:
                draw.text((x + 12, y + 13), value, fill=color, font=font)
            else:
                bbox = draw.textbbox((0, 0), value, font=font)
                draw.text((x + (w - (bbox[2] - bbox[0])) / 2, y + 13), value, fill=color, font=font)
            x += w

    fd, path = tempfile.mkstemp(prefix="mail_ai_stats_", suffix=".png")
    os.close(fd)
    img.save(path, format="PNG", optimize=True)
    return path


def build_stats_payload(db: Session, llm_call: Callable[[str], dict], day_value: date, refresh: bool = True) -> dict:
    import mail_ai_stats as stats
    today = bj_now().date()
    refresh_result = None
    if refresh:
        refresh_result = stats.refresh_all(db, llm_call, lookback_days=max(1, (today - day_value).days + 1))
    else:
        stats.compute_and_store_daily(db, day_value, day_value)
    rows = stats.query_daily_by_staff(db, day_value)
    name_map = _resolve_staff_names([r["staff_id"] for r in rows])
    for row in rows:
        row["staff_name"] = name_map.get(row["staff_id"], "") or row["staff_id"]
    message = format_stats_message(day_value, rows, refreshed=refresh)
    html_body = format_stats_html(day_value, rows, refreshed=refresh)
    return {
        "day": day_value.isoformat(),
        "rows": rows,
        "totals": _total_row(rows),
        "message": message,
        "html": html_body,
        "refreshed": bool(refresh),
        "refresh_result": refresh_result,
    }


def broadcast_stats(day_value: date, llm_call: Callable[[str], dict], *, refresh: bool = True,
                    chat_id: str | None = None, dry_run: bool = False, message_type: str = "image") -> dict:
    db = SessionLocal()
    try:
        payload = build_stats_payload(db, llm_call, day_value, refresh=refresh)
    finally:
        db.close()
    target_chat = (chat_id or settings.MAIL_AI_STATS_BROADCAST_CHAT_ID or "").strip()
    kind = (message_type or "image").strip().lower()
    image_path = None
    if kind == "image":
        image_path = render_stats_image(day_value, payload["rows"], refreshed=refresh)
        payload["image_path"] = image_path
    if dry_run:
        return {**payload, "sent": False, "dry_run": True, "chat_id": target_chat, "message_type": kind}
    if not target_chat:
        return {**payload, "sent": False, "error": "MAIL_AI_STATS_BROADCAST_CHAT_ID 未配置", "message_type": kind}
    try:
        if kind == "text":
            send_result = QYWXUtils.send_appchat_text(target_chat, payload["message"])
        else:
            send_result = QYWXUtils.send_appchat_image(target_chat, image_path)
    finally:
        if image_path:
            try:
                os.remove(image_path)
            except Exception:
                pass
    return {**payload, "sent": bool(send_result.get("ok")), "chat_id": target_chat,
            "message_type": kind, "send_result": send_result}


def start_scheduler(llm_call: Callable[[str], dict]) -> bool:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return False
        if not bool(getattr(settings, "MAIL_AI_STATS_BROADCAST_ENABLED", True)):
            logger.info("邮件统计企微群自动播报未启用")
            return False
        if not str(getattr(settings, "MAIL_AI_STATS_BROADCAST_CHAT_ID", "") or "").strip():
            logger.warning("邮件统计企微群自动播报未启动: chat_id 未配置")
            return False
        _scheduler_started = True

    def loop() -> None:
        logger.info("邮件统计企微群自动播报已启动: times=%s", sorted(parse_broadcast_times()))
        while True:
            now = bj_now()
            key = f"{now.date().isoformat()} {now.strftime('%H:%M')}"
            try:
                if (not settings.MAIL_AI_STATS_BROADCAST_WORKDAYS_ONLY or is_workday(now.date())):
                    if now.strftime("%H:%M") in parse_broadcast_times() and key not in _last_sent_keys:
                        _last_sent_keys.add(key)
                        result = broadcast_stats(now.date(), llm_call, refresh=True, message_type="image")
                        logger.info("MAIL_STATS_WECOM_BROADCAST_DONE day=%s sent=%s type=%s",
                                    result.get("day"), result.get("sent"), result.get("message_type"))
            except Exception:
                logger.exception("MAIL_STATS_WECOM_BROADCAST_FAILED")
            time.sleep(20)

    threading.Thread(target=loop, daemon=True, name="mail_stats_wecom_broadcast").start()
    return True
