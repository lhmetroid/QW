# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mail_crm_field_contract import (
    MAIL_CRM_CANONICAL_FIELD_NAMES,
    MAIL_CRM_FIELD_CONTRACT_VERSION,
)
from mail_crm_mock_data import (
    MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
    MAIL_CRM_MOCK_PROFILES,
    build_mail_crm_mock_catalog,
)


class MailCrmMockDataTest(unittest.TestCase):
    def test_mock_catalog_is_explicitly_review_only(self):
        catalog = build_mail_crm_mock_catalog()

        self.assertTrue(catalog["is_mock"])
        self.assertTrue(catalog["review_only"])
        self.assertFalse(catalog["real_sending_enabled"])
        self.assertFalse(catalog["will_query_production_crm"])
        self.assertFalse(catalog["will_write_database"])
        self.assertFalse(catalog["will_update_wecom_state"])
        self.assertEqual(catalog["wecom_state_change"], "none")
        self.assertEqual(catalog["contract_version"], MAIL_CRM_FIELD_CONTRACT_VERSION)

    def test_mock_profiles_reuse_mail_crm_field_contract(self):
        canonical = set(MAIL_CRM_CANONICAL_FIELD_NAMES)
        required = {
            "customer_key",
            "contact_email",
            "company_industry",
            "payment_risk_level",
            "current_seller_name",
            "current_seller_signature",
        }
        self.assertTrue(required.issubset(canonical))

        for profile in MAIL_CRM_MOCK_PROFILES:
            public = profile.to_public_dict()
            draft_payload = public["generate_draft_payload"]
            for field_name in required:
                if field_name in {"company_industry", "payment_risk_level"}:
                    self.assertTrue(public[field_name])
                else:
                    self.assertTrue(draft_payload[field_name])
            self.assertTrue(public["is_mock"])
            self.assertTrue(public["review_only"])
            self.assertFalse(public["real_sending_enabled"])
            self.assertFalse(public["will_query_production_crm"])
            self.assertFalse(public["will_update_wecom_state"])

    def test_mock_lookup_payload_matches_existing_mail_profile_shape(self):
        low_risk = MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY["CUST-DEMO-MULTI-DOMAIN"]
        high_risk = MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY["CUST-HIGH-RISK-DEMO"]

        self.assertEqual(low_risk["company_industry"], "manufacturing")
        self.assertEqual(low_risk["payment_risk_level"], "low")
        self.assertEqual(
            low_risk["crm_profile_lookup_status"],
            "matched_mail_crm_mock_customer_key",
        )
        self.assertIn("customer-domain.mailmock.test", low_risk["customer_domains"])
        self.assertEqual(high_risk["payment_risk_level"], "high")
        self.assertIn("risk-customer.mailmock.test", high_risk["customer_domains"])

    def test_mock_payloads_cover_draft_and_sequence_interrupt_without_real_effects(self):
        for profile in MAIL_CRM_MOCK_PROFILES:
            draft_payload = profile.to_generate_draft_payload()
            interrupt_payload = profile.to_sequence_interrupt_payload()

            self.assertEqual(draft_payload["customer_key"], profile.customer_key)
            self.assertEqual(draft_payload["contact_email"], profile.contact_email)
            self.assertIn("scenario", draft_payload)
            self.assertIn("suite_step", draft_payload)
            self.assertEqual(interrupt_payload["event_type"], "crm_state_change")
            self.assertEqual(interrupt_payload["crm_event_type"], "CRM_STAGE_CHANGED_TO_WON")
            self.assertTrue(interrupt_payload["metadata"]["is_mock"])
            self.assertTrue(interrupt_payload["metadata"]["review_only"])
            self.assertFalse(interrupt_payload["metadata"]["will_update_crm_stage"])
            self.assertFalse(interrupt_payload["metadata"]["will_update_wecom_state"])
            self.assertFalse(interrupt_payload["metadata"]["real_sending_enabled"])


if __name__ == "__main__":
    unittest.main()
