import unittest
from pathlib import Path
from typing import Any


def sanitize_text(value: str | None) -> str:
    return str(value or "").strip()


class MailDraftCommercialTerms:
    pass


def _load_guardrail_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    start = source.index("MAIL_SENSITIVE_CONTENT_REDACTION")
    end = source.index("MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST", start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "MailDraftCommercialTerms": MailDraftCommercialTerms,
        "re": __import__("re"),
        "sanitize_text": sanitize_text,
    }
    exec(source[start:end], namespace)
    return namespace


class MailSensitiveContentGuardrailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_guardrail_helpers()

    def test_blocks_internal_floor_price_leak(self):
        result = self.helpers["_evaluate_mail_sensitive_content_red_card_guardrail"](
            body_html="<p>Internal floor price is USD 0.04 per word. Do not share with customer.</p>"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "red_card_hard_block")
        self.assertIn("internal_floor_price", result["blocked_categories"])
        self.assertFalse(result["real_sending_enabled"])

    def test_blocks_personal_finance_account(self):
        result = self.helpers["_evaluate_mail_sensitive_content_red_card_guardrail"](
            body_html="<p>Please pay to my personal bank account number 6222 8888 9999 0000.</p>"
        )

        self.assertIsNotNone(result)
        self.assertIn("personal_finance_account", result["blocked_categories"])
        self.assertNotIn("6222", result["matches"][0]["matched_context"])

    def test_blocks_unpublished_rebate_or_discount(self):
        result = self.helpers["_evaluate_mail_sensitive_content_red_card_guardrail"](
            subject="Private note: unpublished rebate for this buyer"
        )

        self.assertIsNotNone(result)
        self.assertIn("unpublished_rebate_discount", result["blocked_categories"])
        self.assertFalse(result["will_send_email"])

    def test_allows_backend_placeholders_and_public_terms(self):
        result = self.helpers["_evaluate_mail_sensitive_content_red_card_guardrail"](
            body_html=(
                "<p>Backend-filled commercial terms for review: "
                "Price: {{MAIL_PRICE_RESOLVED_BY_APPROVED_PRICING_RULE}}; "
                "Discount: {{MAIL_DISCOUNT_REQUIRES_APPROVAL}}; "
                "Payment terms: {{MAIL_PAYMENT_TERMS_REQUIRES_APPROVAL}}.</p>"
            )
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
