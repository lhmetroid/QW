import unittest
import re
from pathlib import Path
from typing import Any


from mail_crm_mock_data import (
    MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY,
    MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
)


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def sanitize_text(value: str | None) -> str:
    return str(value or "").strip()


def _load_guardrail_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    start = source.index("MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST")
    end = source.index("def _resolve_mail_commercial_terms", start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "HTTPException": HTTPException,
        "re": re,
        "sanitize_text": sanitize_text,
        "Session": Any,
        "MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY": MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY,
        "MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY": MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
    }
    exec(source[start:end], namespace)
    return namespace


class MailRecipientDomainGuardrailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_guardrail_helpers()

    def test_blocks_competitor_recipient_domain(self):
        result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
            customer_key="CUST-NORMAL",
            contact_email="buyer@transperfect.com",
            cc_emails=[],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "red_card_hard_block")
        self.assertFalse(result["real_sending_enabled"])
        self.assertEqual(result["blocked_recipients"][0]["field"], "recipient")
        self.assertEqual(result["blocked_recipients"][0]["risk_type"], "competitor_domain")
        self.assertIn("transperfect.com", result["competitor_domain_blacklist"])

    def test_blocks_risky_cc_domain(self):
        result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
            customer_key="CUST-NORMAL",
            contact_email="buyer@customer-domain.com",
            cc_emails=["audit@mailinator.com"],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["blocked_recipients"][0]["field"], "cc")
        self.assertEqual(result["blocked_recipients"][0]["risk_type"], "risky_recipient_domain")
        self.assertFalse(result["will_send_email"])

    def test_blocks_non_whitelisted_customer_domain(self):
        result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
            customer_key="CUST-NORMAL",
            contact_email="buyer@customer-domain.com",
            cc_emails=["shared@outside-domain.com"],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["blocked_recipients"][0]["risk_type"], "non_whitelisted_customer_domain")
        self.assertEqual(result["customer_domain_whitelist"], ["customer-domain.com"])

    def test_allows_normal_customer_domains(self):
        result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
            customer_key="CUST-NORMAL",
            contact_email="buyer@customer-domain.com",
            cc_emails=["legal@sub.customer-domain.com"],
        )

        self.assertIsNone(result)

    def test_allows_customer_key_whitelisted_alias_domain(self):
        result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
            customer_key="CUST-DEMO-MULTI-DOMAIN",
            contact_email="buyer@customer-domain.com",
            cc_emails=["ops@customer-domain-cn.mailmock.test"],
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
