import unittest
from pathlib import Path
from typing import Any


def sanitize_text(value: str | None) -> str:
    return str(value or "").strip()


def _load_safety_result_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    start = source.index("MAIL_SAFETY_GATE_RESULT_SCHEMA_VERSION")
    end = source.index("def _resolve_mail_commercial_terms", start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "sanitize_text": sanitize_text,
    }
    exec(source[start:end], namespace)
    return namespace


class MailGenerateDraftSafetyResultStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_safety_result_helpers()

    def test_passed_results_use_same_shape_for_all_gates(self):
        results = self.helpers["_build_mail_safety_gate_results"]()

        self.assertEqual(self.helpers["_mail_safety_overall_outcome"](results), "passed")
        self.assertEqual({item["outcome"] for item in results}, {"passed"})
        self.assertEqual(len({tuple(item.keys()) for item in results}), 1)
        for item in results:
            self.assertEqual(item["schema_version"], "mail_safety_gate_result.v1")
            self.assertTrue(item["passed"])
            self.assertFalse(item["hard_block"])
            self.assertFalse(item["real_sending_enabled"])
            self.assertIn("details", item)
            self.assertIsNone(item["details"])

    def test_yellow_card_result_keeps_same_shape_and_overall_outcome(self):
        yellow_details = {
            "status": "yellow_card_sla_calibrated_locked",
            "standard_sla_label": "3 business days",
        }
        results = self.helpers["_build_mail_safety_gate_results"](
            delivery_sla_guardrail=yellow_details,
        )
        delivery_result = next(item for item in results if item["gate_key"] == "delivery_sla")

        self.assertEqual(self.helpers["_mail_safety_overall_outcome"](results), "yellow_card")
        self.assertEqual(len({tuple(item.keys()) for item in results}), 1)
        self.assertEqual(delivery_result["outcome"], "yellow_card")
        self.assertFalse(delivery_result["passed"])
        self.assertFalse(delivery_result["hard_block"])
        self.assertEqual(delivery_result["action"], "calibrate_and_lock_for_review")
        self.assertEqual(delivery_result["details"], yellow_details)

    def test_red_card_result_keeps_same_shape_and_takes_priority(self):
        red_details = {
            "status": "red_card_hard_block",
            "reason": "recipient_or_cc_domain_confidentiality_risk",
        }
        yellow_details = {
            "status": "yellow_card_sla_calibrated_locked",
            "standard_sla_label": "3 business days",
        }
        results = self.helpers["_build_mail_safety_gate_results"](
            recipient_domain_confidentiality_block=red_details,
            delivery_sla_guardrail=yellow_details,
        )
        recipient_result = next(
            item for item in results
            if item["gate_key"] == "recipient_domain_confidentiality"
        )

        self.assertEqual(self.helpers["_mail_safety_overall_outcome"](results), "red_card")
        self.assertEqual(len({tuple(item.keys()) for item in results}), 1)
        self.assertEqual(recipient_result["outcome"], "red_card")
        self.assertFalse(recipient_result["passed"])
        self.assertTrue(recipient_result["hard_block"])
        self.assertEqual(recipient_result["action"], "block_send")
        self.assertEqual(recipient_result["details"], red_details)


if __name__ == "__main__":
    unittest.main()
