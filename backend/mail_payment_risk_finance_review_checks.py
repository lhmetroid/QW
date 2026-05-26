import re
import unittest
from pathlib import Path
from typing import Any


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


def _load_mail_payment_risk_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    start = source.index("MAIL_CONFIDENTIALITY_COMPETITOR_DOMAIN_BLACKLIST")
    end = source.index("def _resolve_mail_commercial_terms", start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "HTTPException": HTTPException,
        "logger": _Logger(),
        "re": re,
        "sanitize_text": sanitize_text,
    }
    exec(source[start:end], namespace)
    namespace["_mail_crm_profile_from_sql"] = lambda customer_key, contact_email: None
    return namespace


class MailPaymentRiskFinanceReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_mail_payment_risk_helpers()

    def test_high_payment_risk_from_crm_locks_manual_finance_review(self):
        profile = self.helpers["_lookup_mail_crm_profile"](
            "CUST-HIGH-RISK-DEMO",
            "buyer@risk-customer.com",
        )
        guardrail = self.helpers["_evaluate_mail_payment_risk_finance_review_guardrail"](
            payment_risk_level=profile["payment_risk_level"],
            crm_profile_lookup_status=profile["crm_profile_lookup_status"],
            crm_profile_source=profile["crm_profile_source"],
        )

        self.assertIsNotNone(guardrail)
        self.assertEqual(guardrail["status"], "yellow_card_manual_finance_review_locked")
        self.assertEqual(guardrail["review_mode"], "manual_finance_review_required")
        self.assertEqual(guardrail["payment_risk_level"], "high")
        self.assertTrue(guardrail["review_only"])
        self.assertFalse(guardrail["real_sending_enabled"])
        self.assertFalse(guardrail["will_send_email"])

    def test_low_and_unknown_payment_risk_do_not_trigger_finance_lock(self):
        for risk_level in ("low", "medium", "unknown", ""):
            with self.subTest(risk_level=risk_level):
                guardrail = self.helpers["_evaluate_mail_payment_risk_finance_review_guardrail"](
                    payment_risk_level=risk_level,
                )
                self.assertIsNone(guardrail)

    def test_payment_risk_gate_reports_yellow_card_without_hard_block(self):
        guardrail = self.helpers["_evaluate_mail_payment_risk_finance_review_guardrail"](
            payment_risk_level="overdue",
        )
        results = self.helpers["_build_mail_safety_gate_results"](
            payment_risk_finance_review_guardrail=guardrail,
        )
        payment_result = next(
            item for item in results
            if item["gate_key"] == "payment_risk_finance_review"
        )

        self.assertEqual(self.helpers["_mail_safety_overall_outcome"](results), "yellow_card")
        self.assertEqual(payment_result["outcome"], "yellow_card")
        self.assertFalse(payment_result["passed"])
        self.assertFalse(payment_result["hard_block"])
        self.assertEqual(payment_result["action"], "lock_for_manual_finance_review")
        self.assertEqual(payment_result["details"], guardrail)


if __name__ == "__main__":
    unittest.main()
