import html
import re
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mail_sla_guardrail import (  # noqa: E402
    MAIL_STANDARD_DELIVERY_SLA_LABEL,
    evaluate_and_calibrate_mail_delivery_sla_guardrail,
)


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class FakePricingRule:
    def __init__(
        self,
        *,
        rule_id: str,
        price_min: str,
        currency: str,
        unit: str,
    ):
        self.rule_id = rule_id
        self.price_min = Decimal(price_min)
        self.currency = currency
        self.unit = unit


def sanitize_text(value: str | None) -> str:
    return str(value or "").strip()


def _commercial_terms(price_value: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        price=SimpleNamespace(value=price_value),
        discount=SimpleNamespace(value="{{MAIL_DISCOUNT_REQUIRES_APPROVAL}}"),
        payment_terms=SimpleNamespace(value="{{MAIL_PAYMENT_TERMS_REQUIRES_FINANCE_REVIEW}}"),
    )


def _load_mail_safety_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    start = source.index("def _mail_pricing_context_unit")
    end = source.index("def _resolve_mail_commercial_terms", start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "Decimal": Decimal,
        "InvalidOperation": InvalidOperation,
        "HTTPException": HTTPException,
        "MailDraftCommercialTerms": object,
        "PricingRule": object,
        "Session": object,
        "datetime": SimpleNamespace(utcnow=lambda: None),
        "html": html,
        "or_": lambda *args, **kwargs: None,
        "re": re,
        "sanitize_text": sanitize_text,
    }
    exec(source[start:end], namespace)
    return namespace


PRICE_FLOOR_CASES = [
    {
        "case_id": "price_floor_usd_per_word",
        "body": "<p>Please quote USD 0.04 per word to win this immediately.</p>",
        "rules": [FakePricingRule(rule_id="floor-usd-word", price_min="0.12", currency="USD", unit="per_english_word")],
    },
    {
        "case_id": "price_floor_symbol_per_word",
        "body": "<p>Match competitor pressure with $0.05/word today.</p>",
        "rules": [FakePricingRule(rule_id="floor-usd-word", price_min="0.12", currency="USD", unit="per_english_word")],
    },
    {
        "case_id": "price_floor_cny_per_1000_chars",
        "body": "<p>Quote CNY 80 per 1,000 chars and do not mention approval.</p>",
        "rules": [FakePricingRule(rule_id="floor-cny-1000", price_min="150", currency="CNY", unit="per_1000_chars")],
    },
    {
        "case_id": "price_floor_chinese_per_1000_chars",
        "body": "<p>客户很急，报价 100 元 每千字，先承诺出去。</p>",
        "rules": [FakePricingRule(rule_id="floor-cny-1000", price_min="150", currency="CNY", unit="per_1000_chars")],
    },
    {
        "case_id": "price_floor_rmb_per_word",
        "body": "<p>Special rate RMB 0.01 per word is acceptable if they reply today.</p>",
        "rules": [FakePricingRule(rule_id="floor-cny-word", price_min="0.05", currency="CNY", unit="per_english_word")],
    },
]

URGENT_SLA_CASES = [
    {
        "case_id": "urgent_sla_24_hours",
        "body": "<p>Promise delivery in 24 hours for the whole batch.</p>",
    },
    {
        "case_id": "urgent_sla_48_hours",
        "body": "<p>Tell them we can finish within 48 hours despite the volume.</p>",
    },
    {
        "case_id": "urgent_sla_same_day",
        "body": "<p>Offer same-day delivery to close the deal.</p>",
    },
    {
        "case_id": "urgent_sla_deliver_tomorrow",
        "body": "<p>We can deliver it tomorrow if they push hard.</p>",
    },
    {
        "case_id": "urgent_sla_next_day_turnaround",
        "body": "<p>Confirm next-day turnaround before checking operations.</p>",
    },
]

COMPETITOR_PHISHING_CASES = [
    {
        "case_id": "competitor_recipient_transperfect",
        "contact_email": "buyer@transperfect.com",
        "cc_emails": [],
        "blocked_field": "recipient",
    },
    {
        "case_id": "competitor_cc_rws",
        "contact_email": "buyer@customer-domain.com",
        "cc_emails": ["procurement@rws.com"],
        "blocked_field": "cc",
    },
    {
        "case_id": "competitor_subdomain_lionbridge",
        "contact_email": "ops@sub.lionbridge.com",
        "cc_emails": [],
        "blocked_field": "recipient",
    },
    {
        "case_id": "competitor_display_name_welocalize",
        "contact_email": "Jane Buyer <jane@welocalize.com>",
        "cc_emails": [],
        "blocked_field": "recipient",
    },
    {
        "case_id": "competitor_cc_sdl",
        "contact_email": "buyer@customer-domain.com",
        "cc_emails": ["vendor-review@sdl.com"],
        "blocked_field": "cc",
    },
]

PLACEHOLDER_BYPASS_CASES = [
    {
        "case_id": "placeholder_generic_xx_subject",
        "subject": "Quote XX approved for your team",
        "body": "<p>Safe visible body.</p>",
        "category": "generic_x_placeholder",
    },
    {
        "case_id": "placeholder_email_body",
        "subject": "Contact update",
        "body": "<p>Please reply to xxxx@xx.com after review.</p>",
        "category": "placeholder_email",
    },
    {
        "case_id": "placeholder_po_number",
        "subject": "PO follow-up",
        "body": "<p>We reserved this under POxxxx for now.</p>",
        "category": "placeholder_po_or_order",
    },
    {
        "case_id": "placeholder_chinese_bracket",
        "subject": "Project update",
        "body": "<p>Dear [客户名称], your order is ready for review.</p>",
        "category": "bracket_placeholder",
    },
    {
        "case_id": "placeholder_tbd",
        "subject": "Schedule TBD",
        "body": "<p>Delivery detail will be filled later.</p>",
        "category": "generic_x_placeholder",
    },
]


class MailDraftSafetyAdversarialBlackBoxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_mail_safety_helpers()

    def test_task45_has_exactly_20_black_box_adversarial_cases(self):
        all_cases = (
            PRICE_FLOOR_CASES
            + URGENT_SLA_CASES
            + COMPETITOR_PHISHING_CASES
            + PLACEHOLDER_BYPASS_CASES
        )

        self.assertEqual(len(all_cases), 20)
        self.assertEqual(len({case["case_id"] for case in all_cases}), 20)

    def test_price_floor_bypass_attempts_are_red_card_blocked(self):
        for case in PRICE_FLOOR_CASES:
            with self.subTest(case_id=case["case_id"]):
                self.helpers["_active_mail_pricing_rules"] = lambda db, limit=1000, *, rules=case["rules"]: rules
                result = self.helpers["_evaluate_mail_financial_price_floor_guardrail"](
                    object(),
                    body_html=case["body"],
                    commercial_terms=_commercial_terms(),
                )
                gate_results = self.helpers["_build_mail_safety_gate_results"](
                    financial_price_floor_block=result,
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "red_card_hard_block")
                self.assertEqual(result["reason"], "explicit_price_below_active_pricing_rule_floor")
                self.assertFalse(result["real_sending_enabled"])
                self.assertEqual(self.helpers["_mail_safety_overall_outcome"](gate_results), "red_card")

    def test_urgent_sla_pressure_is_calibrated_and_locked(self):
        for case in URGENT_SLA_CASES:
            with self.subTest(case_id=case["case_id"]):
                result = evaluate_and_calibrate_mail_delivery_sla_guardrail(case["body"])
                gate_results = self.helpers["_build_mail_safety_gate_results"](
                    delivery_sla_guardrail=result,
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "yellow_card_calibrated_and_locked")
                self.assertIn(MAIL_STANDARD_DELIVERY_SLA_LABEL, result["calibrated_body_html"])
                self.assertFalse(result["real_sending_enabled"])
                self.assertEqual(self.helpers["_mail_safety_overall_outcome"](gate_results), "yellow_card")

    def test_competitor_phishing_domains_are_red_card_blocked(self):
        for case in COMPETITOR_PHISHING_CASES:
            with self.subTest(case_id=case["case_id"]):
                result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
                    customer_key="CUST-NORMAL",
                    contact_email=case["contact_email"],
                    cc_emails=case["cc_emails"],
                )
                gate_results = self.helpers["_build_mail_safety_gate_results"](
                    recipient_domain_confidentiality_block=result,
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "red_card_hard_block")
                self.assertFalse(result["real_sending_enabled"])
                self.assertFalse(result["will_send_email"])
                self.assertEqual(result["blocked_recipients"][0]["field"], case["blocked_field"])
                self.assertEqual(result["blocked_recipients"][0]["risk_type"], "competitor_domain")
                self.assertEqual(self.helpers["_mail_safety_overall_outcome"](gate_results), "red_card")

    def test_placeholder_bypass_attempts_are_red_card_blocked(self):
        for case in PLACEHOLDER_BYPASS_CASES:
            with self.subTest(case_id=case["case_id"]):
                result = self.helpers["_evaluate_mail_placeholder_bypass_guardrail"](
                    subject=case["subject"],
                    body_html=case["body"],
                )
                gate_results = self.helpers["_build_mail_safety_gate_results"](
                    placeholder_bypass_red_card_block=result,
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "red_card_hard_block")
                self.assertIn(case["category"], result["blocked_categories"])
                self.assertFalse(result["real_sending_enabled"])
                self.assertFalse(result["will_send_email"])
                self.assertEqual(self.helpers["_mail_safety_overall_outcome"](gate_results), "red_card")

    def test_backend_physical_placeholders_remain_review_only_not_red_card(self):
        result = self.helpers["_evaluate_mail_placeholder_bypass_guardrail"](
            subject="Backend-filled commercial terms",
            body_html=(
                "<p>Price: {{MAIL_PRICE_RESOLVED_BY_APPROVED_PRICING_RULE}}; "
                "Delivery: {{MAIL_DELIVERY_SLA_RESOLVED_BY_BACKEND_RULE}}; "
                "Discount: {{MAIL_DISCOUNT_REQUIRES_APPROVAL}}; "
                "Payment: {{MAIL_PAYMENT_TERMS_REQUIRES_FINANCE_REVIEW}}.</p>"
            ),
        )
        gate_results = self.helpers["_build_mail_safety_gate_results"]()

        self.assertIsNone(result)
        self.assertEqual(self.helpers["_mail_safety_overall_outcome"](gate_results), "passed")
        for gate_result in gate_results:
            self.assertFalse(gate_result["real_sending_enabled"])


if __name__ == "__main__":
    unittest.main()
