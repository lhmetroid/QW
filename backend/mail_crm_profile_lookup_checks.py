import re
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mail_crm_mock_data import (
    MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY,
    MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
)


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class _Logger:
    def info(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def sanitize_text(value: str | None) -> str:
    return str(value or "").strip()


def _load_mail_crm_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    start = source.index("MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST")
    end = source.index("def _resolve_mail_commercial_terms", start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "HTTPException": HTTPException,
        "MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY": MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY,
        "MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY": MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
        "logger": _Logger(),
        "re": re,
        "sanitize_text": sanitize_text,
    }
    exec(source[start:end], namespace)
    namespace["_mail_crm_profile_from_sql"] = lambda customer_key, contact_email: None
    return namespace


class MailCrmProfileLookupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_mail_crm_helpers()

    def test_static_customer_key_profile_adds_profile_signals_and_domains(self):
        profile = self.helpers["_lookup_mail_crm_profile"](
            "CUST-DEMO-MULTI-DOMAIN",
            "buyer@customer-domain.mailmock.test",
        )

        self.assertEqual(profile["company_industry"], "manufacturing")
        self.assertEqual(profile["payment_risk_level"], "low")
        self.assertEqual(profile["crm_profile_lookup_status"], "matched_mail_crm_mock_customer_key")
        self.assertEqual(
            profile["customer_domains"],
            ("customer-domain-cn.mailmock.test", "customer-domain.mailmock.test"),
        )

    def test_contact_email_domain_fallback_does_not_use_wecom_identifier_as_mail_key(self):
        profile = self.helpers["_lookup_mail_crm_profile"](
            "wmS8sICwAASvXbkmC2kY5HN9fE-0gQOA",
            "buyer@fallback-customer.com",
        )

        self.assertEqual(profile["company_industry"], "unknown")
        self.assertEqual(profile["payment_risk_level"], "unknown")
        self.assertEqual(profile["customer_domains"], ("fallback-customer.com",))
        self.assertEqual(profile["crm_profile_lookup_status"], "skipped_wecom_identifier")

    def test_guardrail_allows_crm_profile_domain_fallback_for_cc(self):
        profile = self.helpers["_lookup_mail_crm_profile"](
            "CUST-DEMO-MULTI-DOMAIN",
            "buyer@customer-domain.mailmock.test",
        )
        result = self.helpers["_evaluate_mail_recipient_domain_confidentiality_guardrail"](
            customer_key="CUST-DEMO-MULTI-DOMAIN",
            contact_email="buyer@customer-domain.mailmock.test",
            cc_emails=["legal@customer-domain-cn.mailmock.test"],
            crm_profile=profile,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
