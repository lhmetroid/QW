# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mail_crm_field_contract import (
    MAIL_CRM_CANONICAL_FIELD_NAMES,
    MAIL_CRM_DRAFT_REQUIRED_FIELD_NAMES,
    MAIL_CRM_FIELD_ALIASES,
    MAIL_CRM_FIELD_CONTRACT,
    MAIL_CRM_FIELD_CONTRACT_VERSION,
    MAIL_CRM_OPTIONAL_PROFILE_FIELD_NAMES,
)


class MailCrmFieldContractTest(unittest.TestCase):
    def test_canonical_mail_crm_fields_are_locked(self):
        self.assertEqual(MAIL_CRM_FIELD_CONTRACT_VERSION, "mail_crm_field_contract.v1")
        self.assertEqual(
            MAIL_CRM_CANONICAL_FIELD_NAMES,
            (
                "customer_key",
                "contact_email",
                "company_industry",
                "payment_risk_level",
                "current_seller_name",
                "current_seller_signature",
            ),
        )

    def test_draft_boundary_requires_only_mail_api_inputs(self):
        self.assertEqual(
            MAIL_CRM_DRAFT_REQUIRED_FIELD_NAMES,
            (
                "customer_key",
                "contact_email",
                "current_seller_name",
                "current_seller_signature",
            ),
        )
        self.assertEqual(
            MAIL_CRM_OPTIONAL_PROFILE_FIELD_NAMES,
            (
                "company_industry",
                "payment_risk_level",
            ),
        )

    def test_human_terms_have_explicit_canonical_fields(self):
        self.assertEqual(MAIL_CRM_FIELD_ALIASES["industry"], "company_industry")
        self.assertEqual(MAIL_CRM_FIELD_ALIASES["seller_owner_name"], "current_seller_name")
        self.assertEqual(MAIL_CRM_FIELD_ALIASES["seller_signature"], "current_seller_signature")
        self.assertEqual(MAIL_CRM_FIELD_ALIASES["payment_terms"], "payment_risk_level")

    def test_contract_keeps_mail_and_wecom_isolated(self):
        forbidden_fragments = ("external_userid", "session_id", "group_")
        for spec in MAIL_CRM_FIELD_CONTRACT:
            self.assertNotIn(spec.field_name, forbidden_fragments)
            self.assertTrue(spec.source)
            self.assertTrue(spec.pii_level)
            if spec.field_name == "customer_key":
                for fragment in forbidden_fragments:
                    self.assertIn(fragment, spec.description)


if __name__ == "__main__":
    unittest.main()
