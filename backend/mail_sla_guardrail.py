"""Mail delivery SLA guardrail helpers.

This module is mail-only and has no sender integration. It only detects and
calibrates draft text before human review.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


MAIL_STANDARD_DELIVERY_SLA_DAYS = 3
MAIL_STANDARD_DELIVERY_SLA_LABEL = f"{MAIL_STANDARD_DELIVERY_SLA_DAYS} 个工作日"


def delivery_days_from_match(match: re.Match) -> Decimal | None:
    raw_value = str(match.group("value") or "").strip().lower()
    unit = str(match.group("unit") or "").strip().lower()
    word_numbers = {
        "one": Decimal("1"),
        "two": Decimal("2"),
        "three": Decimal("3"),
    }
    if raw_value in word_numbers:
        amount = word_numbers[raw_value]
    else:
        try:
            amount = Decimal(raw_value)
        except (InvalidOperation, ValueError):
            return None
    if "hour" in unit or unit in {"hr", "hrs"}:
        return amount / Decimal("24")
    return amount


def calibrate_mail_delivery_sla_text(
    text_value: str | None,
    *,
    standard_days: int = MAIL_STANDARD_DELIVERY_SLA_DAYS,
    standard_label: str = MAIL_STANDARD_DELIVERY_SLA_LABEL,
) -> dict[str, Any]:
    source_text = str(text_value or "")
    if not source_text:
        return {"text": source_text, "triggered": False, "matches": []}

    matches: list[dict[str, Any]] = []
    numeric_pattern = re.compile(
        r"\b(?:within\s+|in\s+)?(?P<value>\d+(?:\.\d+)?|one|two|three)\s*"
        r"(?P<unit>hours?|hrs?|business\s+days?|working\s+days?|days?)\b",
        flags=re.IGNORECASE,
    )

    def replace_numeric(match: re.Match) -> str:
        extracted_days = delivery_days_from_match(match)
        if extracted_days is None or extracted_days >= Decimal(str(standard_days)):
            return match.group(0)
        matched_text = match.group(0)
        matches.append(
            {
                "matched_text": matched_text,
                "extracted_days": float(extracted_days),
                "standard_sla_days": standard_days,
                "replacement": standard_label,
            }
        )
        return standard_label

    calibrated_text = numeric_pattern.sub(replace_numeric, source_text)
    phrase_patterns = [
        (re.compile(r"\b(?:same[-\s]?day|next[-\s]?day|tomorrow)\s+(?:delivery|turnaround|dispatch)\b", re.IGNORECASE), Decimal("1")),
        (re.compile(r"\b(?:deliver|dispatch|turn\s*around)\s+(?:it\s+|them\s+|the\s+\w+\s+)?(?:today|tomorrow)\b", re.IGNORECASE), Decimal("1")),
    ]
    for pattern, extracted_days in phrase_patterns:
        def replace_phrase(match: re.Match, *, days: Decimal = extracted_days) -> str:
            matched_text = match.group(0)
            matches.append(
                {
                    "matched_text": matched_text,
                    "extracted_days": float(days),
                    "standard_sla_days": standard_days,
                    "replacement": standard_label,
                }
            )
            return standard_label

        calibrated_text = pattern.sub(replace_phrase, calibrated_text)

    return {
        "text": calibrated_text,
        "triggered": bool(matches),
        "matches": matches,
        "standard_sla_days": standard_days,
        "standard_sla_label": standard_label,
    }


def evaluate_and_calibrate_mail_delivery_sla_guardrail(body_html: str | None) -> dict[str, Any] | None:
    calibration = calibrate_mail_delivery_sla_text(body_html)
    if not calibration["triggered"]:
        return None
    return {
        "status": "yellow_card_calibrated_and_locked",
        "reason": "explicit_delivery_promise_faster_than_standard_sla",
        "calibrated_body_html": calibration["text"],
        "standard_sla_days": calibration["standard_sla_days"],
        "standard_sla_label": calibration["standard_sla_label"],
        "matches": calibration["matches"],
        "review_only": True,
        "real_sending_enabled": False,
    }
