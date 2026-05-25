#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export first-batch mail gold snippet candidates.

The exporter is intentionally read-only: it does not create tables, migrate
schema, or write back to PostgreSQL. It reads mail_raw_unified/mail_cleaned,
scores sales-side cleaned messages, redacts sensitive fields, and writes
candidate files for human review.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "mail_gold_candidates"

SCENARIO_LABELS = {
    "re_activation": "老客户唤醒",
    "new_business_promotion": "新业务推广",
    "new_contact_intro": "新接手联系人介绍",
}

SCENARIO_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "new_contact_intro",
        [
            r"接手", r"交接", r"新同事", r"新联系人", r"介绍.*负责", r"后续.*负责",
            r"take over", r"handover", r"introduc(?:e|ing|tion)", r"new contact",
            r"my colleague", r"will be responsible",
        ],
    ),
    (
        "new_business_promotion",
        [
            r"推广", r"新业务", r"新服务", r"新品", r"印刷", r"口译", r"同传", r"本地化",
            r"translation", r"locali[sz]ation", r"printing", r"interpreting",
            r"transcreation", r"subtitl", r"voice[- ]?over", r"service",
        ],
    ),
    (
        "re_activation",
        [
            r"好久", r"近期", r"最近", r"回访", r"跟进", r"问候", r"还需要", r"有需要",
            r"long time", r"checking in", r"follow(?:ing)? up", r"hope you are well",
            r"touch base", r"any update", r"would like to ask",
        ],
    ),
]

BUSINESS_SIGNAL_PATTERNS = [
    r"报价", r"费用", r"价格", r"单价", r"工期", r"交期", r"排期", r"样稿", r"打样",
    r"翻译", r"校对", r"排版", r"印刷", r"发票", r"合同", r"PO", r"项目",
    r"quote", r"quotation", r"price", r"rate", r"timeline", r"turnaround",
    r"delivery", r"sample", r"proof", r"invoice", r"contract", r"project",
    r"translation", r"review", r"layout", r"typesetting", r"printing",
]

AUTO_OR_LOW_VALUE_PATTERNS = [
    r"\btest\b", r"测试", r"退信", r"自动回复", r"out of office", r"undeliver",
    r"delivery status notification", r"unsubscribe", r"newsletter",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
LONG_ID_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9_-]{10,}\b")
MONEY_RE = re.compile(r"(?:[$￥¥]\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*(?:RMB|USD|CNY|元|美元))", re.I)


@dataclass
class MailGoldCandidate:
    rank: int
    candidate_id: str
    source_type: str
    source_ref: str
    source_batch_id: int | None
    raw_payload_path: str
    subject: str
    sent_at: str
    customer_key: str
    sender_side: str
    scenario: str
    scenario_label: str
    scenario_reason: str
    useful_score: float
    score_source: str
    desensitized_status: str
    desensitized_fields: list[str]
    body_preview: str
    body_text: str


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _collapse(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _infer_scenario(subject: str, body: str) -> tuple[str, str]:
    haystack = f"{subject}\n{body}"
    for scenario, patterns in SCENARIO_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, haystack, re.I):
                return scenario, f"matched:{pattern}"
    return "re_activation", "fallback:general_sales_followup"


def _score_candidate(row: dict[str, Any], scenario_reason: str) -> tuple[float, str]:
    text = _collapse(row.get("body_main_text"))
    subject = _collapse(row.get("subject") or row.get("normalized_subject"))
    sender_side = _collapse(row.get("sender_side")).lower()
    clean_status = _collapse(row.get("clean_status")).lower()
    is_auto_mail = bool(row.get("is_auto_mail"))
    text_len = len(text)

    score = 0.35
    reasons: list[str] = ["base=0.35"]
    if sender_side in ("sales", "seller"):
        score += 0.20
        reasons.append("sales_sender=+0.20")
    if clean_status == "completed":
        score += 0.10
        reasons.append("clean_completed=+0.10")
    if not is_auto_mail:
        score += 0.10
        reasons.append("not_auto=+0.10")
    if 80 <= text_len <= 1200:
        score += 0.15
        reasons.append("length_fit=+0.15")
    elif text_len >= 40:
        score += 0.08
        reasons.append("length_partial=+0.08")
    if _matches_any(f"{subject}\n{text}", BUSINESS_SIGNAL_PATTERNS):
        score += 0.12
        reasons.append("business_signal=+0.12")
    if scenario_reason.startswith("matched:"):
        score += 0.06
        reasons.append("scenario_signal=+0.06")
    if _matches_any(f"{subject}\n{text}", AUTO_OR_LOW_VALUE_PATTERNS):
        score -= 0.25
        reasons.append("low_value_pattern=-0.25")
    if text_len < 30:
        score -= 0.20
        reasons.append("too_short=-0.20")
    if re.search(r"\b(?:xx+|xxx+|待补|todo)\b", text, re.I):
        score -= 0.08
        reasons.append("placeholder_penalty=-0.08")
    score = max(0.0, min(0.99, round(score, 4)))
    return score, ";".join(reasons)


def _redact_text(value: Any) -> tuple[str, list[str]]:
    text = str(value or "")
    fields: list[str] = []

    def repl_email(_: re.Match[str]) -> str:
        fields.append("email")
        return "[EMAIL]"

    def repl_url(_: re.Match[str]) -> str:
        fields.append("url")
        return "[URL]"

    def repl_phone(_: re.Match[str]) -> str:
        fields.append("phone")
        return "[PHONE]"

    def repl_money(_: re.Match[str]) -> str:
        fields.append("money")
        return "[AMOUNT]"

    def repl_long_id(_: re.Match[str]) -> str:
        fields.append("long_id")
        return "[ID]"

    text = EMAIL_RE.sub(repl_email, text)
    text = URL_RE.sub(repl_url, text)
    text = PHONE_RE.sub(repl_phone, text)
    text = MONEY_RE.sub(repl_money, text)
    text = LONG_ID_RE.sub(repl_long_id, text)
    return _collapse(text), sorted(set(fields))


def _redact_key(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if "@" in text:
        domain = text.split("@", 1)[1]
        return f"customer@{domain}"
    return "[CUSTOMER_KEY]"


def _import_db_tools():
    _load_env()
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    try:
        from database import SessionLocal  # type: ignore
        from sqlalchemy import text  # type: ignore
    except ModuleNotFoundError as exc:
        missing = exc.name or str(exc)
        raise RuntimeError(
            f"Missing Python dependency: {missing}. Install declared backend requirements first."
        ) from exc
    return SessionLocal, text


def _table_exists(db: Any, text: Any, table_name: str) -> bool:
    return bool(db.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:table_name)"
    ), {"table_name": table_name}).scalar())


def _table_columns(db: Any, text: Any, table_name: str) -> set[str]:
    rows = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:table_name"
    ), {"table_name": table_name}).fetchall()
    return {str(row[0]) for row in rows}


def fetch_candidates(limit: int, min_score: float) -> tuple[list[MailGoldCandidate], dict[str, Any]]:
    SessionLocal, text = _import_db_tools()
    db = SessionLocal()
    try:
        for table_name in ("mail_raw_unified", "mail_cleaned"):
            if not _table_exists(db, text, table_name):
                raise RuntimeError(f"Required table does not exist: {table_name}")

        raw_cols = _table_columns(db, text, "mail_raw_unified")
        clean_cols = _table_columns(db, text, "mail_cleaned")
        useful_expr = "mc.useful_score" if "useful_score" in clean_cols else "NULL"
        raw_selects = {
            "source_type": "m.source_type",
            "import_batch_id": "m.import_batch_id" if "import_batch_id" in raw_cols else "NULL",
            "raw_payload_path": "m.raw_payload_path" if "raw_payload_path" in raw_cols else "''",
            "subject": "m.subject",
            "sent_at": "m.sent_at" if "sent_at" in raw_cols else "NULL",
        }
        clean_selects = {
            "normalized_subject": "mc.normalized_subject" if "normalized_subject" in clean_cols else "''",
            "body_main_text": "mc.body_main_text",
            "sender_side": "mc.sender_side" if "sender_side" in clean_cols else "''",
            "customer_key": "mc.customer_key" if "customer_key" in clean_cols else "''",
            "clean_status": "mc.clean_status" if "clean_status" in clean_cols else "''",
            "is_auto_mail": "mc.is_auto_mail" if "is_auto_mail" in clean_cols else "FALSE",
        }
        select_sql = ",\n            ".join(
            [
                "m.mail_uid",
                *(f"{expr} AS {alias}" for alias, expr in raw_selects.items()),
                *(f"{expr} AS {alias}" for alias, expr in clean_selects.items()),
                f"{useful_expr} AS stored_useful_score",
            ]
        )
        sender_expr = "COALESCE(mc.sender_side, '')" if "sender_side" in clean_cols else "''"
        clean_status_expr = "COALESCE(mc.clean_status, '')" if "clean_status" in clean_cols else "''"
        is_auto_expr = "COALESCE(mc.is_auto_mail, FALSE)" if "is_auto_mail" in clean_cols else "FALSE"
        body_expr = "COALESCE(BTRIM(mc.body_main_text), '')"
        order_expr = (
            "COALESCE(m.sent_at, m.received_at) DESC NULLS LAST, m.id DESC"
            if "sent_at" in raw_cols and "received_at" in raw_cols
            else "m.id DESC"
        )
        rows = db.execute(text(f"""
            SELECT
                {select_sql}
            FROM mail_raw_unified m
            JOIN mail_cleaned mc ON mc.mail_uid = m.mail_uid
            WHERE {clean_status_expr} = 'completed'
              AND {sender_expr} IN ('seller', 'sales')
              AND {is_auto_expr} = FALSE
              AND {body_expr} <> ''
            ORDER BY {order_expr}
            LIMIT :scan_limit
        """), {"scan_limit": max(limit * 20, 500)}).mappings().all()

        candidates: list[MailGoldCandidate] = []
        for row_map in rows:
            row = dict(row_map)
            scenario, scenario_reason = _infer_scenario(row.get("subject") or row.get("normalized_subject") or "", row.get("body_main_text") or "")
            computed_score, score_source = _score_candidate(row, scenario_reason)
            stored_score = row.get("stored_useful_score")
            if stored_score is not None:
                try:
                    useful_score = round(float(stored_score), 4)
                    score_source = "stored:mail_cleaned.useful_score"
                except Exception:
                    useful_score = computed_score
            else:
                useful_score = computed_score
            if useful_score < min_score:
                continue

            body_text, body_fields = _redact_text(row.get("body_main_text"))
            subject_text, subject_fields = _redact_text(row.get("subject") or row.get("normalized_subject"))
            raw_path, path_fields = _redact_text(row.get("raw_payload_path"))
            customer_key = _redact_key(row.get("customer_key"))
            fields = sorted(set(body_fields + subject_fields + path_fields + (["customer_key"] if customer_key else [])))
            candidate = MailGoldCandidate(
                rank=0,
                candidate_id=f"mail_gold_candidate_{len(candidates) + 1:03d}",
                source_type=str(row.get("source_type") or ""),
                source_ref=str(row.get("mail_uid") or ""),
                source_batch_id=row.get("import_batch_id"),
                raw_payload_path=raw_path,
                subject=subject_text,
                sent_at=str(row.get("sent_at") or ""),
                customer_key=customer_key,
                sender_side=str(row.get("sender_side") or ""),
                scenario=scenario,
                scenario_label=SCENARIO_LABELS[scenario],
                scenario_reason=scenario_reason,
                useful_score=useful_score,
                score_source=score_source,
                desensitized_status="desensitized",
                desensitized_fields=fields,
                body_preview=body_text[:220],
                body_text=body_text,
            )
            candidates.append(candidate)
            if len(candidates) >= limit:
                break

        candidates.sort(key=lambda item: item.useful_score, reverse=True)
        for index, candidate in enumerate(candidates, start=1):
            candidate.rank = index
        meta = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_score": min_score,
            "limit": limit,
            "scanned_rows": len(rows),
            "exported_rows": len(candidates),
            "score_field_checked": "mail_cleaned.useful_score" if "useful_score" in clean_cols else "computed_export_score",
            "source_tables": ["mail_raw_unified", "mail_cleaned"],
        }
        return candidates, meta
    finally:
        db.close()


def write_outputs(candidates: list[MailGoldCandidate], meta: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"mail_gold_candidates_{stamp}.json"
    csv_path = output_dir / f"mail_gold_candidates_{stamp}.csv"
    md_path = output_dir / f"mail_gold_candidates_{stamp}.md"
    latest_json = output_dir / "latest_mail_gold_candidates.json"
    latest_csv = output_dir / "latest_mail_gold_candidates.csv"
    latest_md = output_dir / "latest_mail_gold_candidates.md"

    payload = {
        "meta": meta,
        "candidates": [asdict(item) for item in candidates],
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")

    fieldnames = list(asdict(candidates[0]).keys()) if candidates else list(MailGoldCandidate.__dataclass_fields__.keys())
    for path in (csv_path, latest_csv):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for item in candidates:
                row = asdict(item)
                row["desensitized_fields"] = "|".join(row["desensitized_fields"])
                writer.writerow(row)

    lines = [
        "# 首批邮件黄金候选切片",
        "",
        f"- 生成时间：{meta['generated_at']}",
        f"- 来源表：{', '.join(meta['source_tables'])}",
        f"- 评分来源：{meta['score_field_checked']}",
        f"- 阈值：useful_score >= {meta['min_score']}",
        f"- 扫描行数：{meta['scanned_rows']}",
        f"- 导出数量：{meta['exported_rows']}",
        f"- 脱敏状态：所有正文、主题、路径、客户标识均已按导出规则脱敏",
        "",
        "| rank | candidate_id | source_type | source_ref | scenario | useful_score | desensitized_status | subject | preview |",
        "|---:|---|---|---|---|---:|---|---|---|",
    ]
    for item in candidates:
        preview = item.body_preview.replace("|", "\\|")
        subject = item.subject.replace("|", "\\|")
        lines.append(
            f"| {item.rank} | {item.candidate_id} | {item.source_type} | {item.source_ref} | "
            f"{item.scenario} | {item.useful_score:.4f} | {item.desensitized_status} | {subject} | {preview} |"
        )
    md_text = "\n".join(lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_csv": str(latest_csv),
        "latest_markdown": str(latest_md),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export mail gold snippet candidates.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum exported candidates.")
    parser.add_argument("--min-score", type=float, default=0.60, help="Minimum useful_score threshold.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        candidates, meta = fetch_candidates(limit=max(1, args.limit), min_score=max(0.0, min(args.min_score, 0.99)))
        paths = write_outputs(candidates, meta, Path(args.output_dir))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", "exported": len(candidates), "paths": paths}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
