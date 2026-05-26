import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mail_sla_guardrail import (
    MAIL_STANDARD_DELIVERY_SLA_LABEL,
    calibrate_mail_delivery_sla_text,
    evaluate_and_calibrate_mail_delivery_sla_guardrail,
)


class MailSlaGuardrailTest(unittest.TestCase):
    def test_calibrates_fast_hour_promise_to_standard_sla(self):
        result = calibrate_mail_delivery_sla_text("<p>We can deliver the files in 24 hours.</p>")

        self.assertTrue(result["triggered"])
        self.assertIn(MAIL_STANDARD_DELIVERY_SLA_LABEL, result["text"])
        self.assertNotIn("24 hours", result["text"])
        self.assertEqual(result["matches"][0]["standard_sla_days"], 3)

    def test_leaves_standard_or_slower_sla_unchanged(self):
        body = "<p>We will deliver in 3 business days, or 5 days for complex formatting.</p>"
        result = calibrate_mail_delivery_sla_text(body)

        self.assertFalse(result["triggered"])
        self.assertEqual(result["text"], body)

    def test_guardrail_returns_yellow_lock_without_real_sending(self):
        result = evaluate_and_calibrate_mail_delivery_sla_guardrail(
            "<p>We promise next-day delivery for this batch.</p>"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "yellow_card_calibrated_and_locked")
        self.assertFalse(result["real_sending_enabled"])
        self.assertIn(MAIL_STANDARD_DELIVERY_SLA_LABEL, result["calibrated_body_html"])


if __name__ == "__main__":
    unittest.main()
