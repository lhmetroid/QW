# -*- coding: utf-8 -*-
import html
import json
import re
import sys
import unittest
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mail_crm_mock_data import (
    MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY,
    MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
    build_mail_crm_mock_catalog,
)
from mail_sequence_strategy import (
    MAIL_UNSENT_DRAFT_STATUSES,
    MailSequenceCutoffEventType,
    MailSequenceInterruptionReason,
    MailSequenceStatus,
    get_mail_sequence_cutoff_rule,
    get_mail_sequence_cutoff_terminal_status,
    get_mail_sequence_step,
    get_mail_sequence_step_interval,
    resolve_mail_pending_draft_disposition,
    should_cutoff_event_physically_stop_sequence,
)
from mail_sla_guardrail import (
    MAIL_STANDARD_DELIVERY_SLA_LABEL,
    evaluate_and_calibrate_mail_delivery_sla_guardrail as _evaluate_and_calibrate_mail_delivery_sla_guardrail,
)


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class Session:
    pass


class PricingRule:
    pass


class _Logger:
    def info(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _NoPricingRulesDb:
    pass


def sanitize_text(value: str | None) -> str:
    return str(value or "").strip()


def _load_mail_review_api_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    model_start = source.index("class MailGenerateDraftRequest")
    model_end = source.index("class KnowledgeChunkCreate", model_start)
    draft_helper_start = source.index("def _first_mail_subject_hint")
    draft_helper_end = source.index("CRM_STATE_CHANGE_INTERRUPT_REASON_ALIASES", draft_helper_start)
    sequence_helper_start = source.index("CRM_STATE_CHANGE_INTERRUPT_REASON_ALIASES")
    sequence_helper_end = source.index("def _email_effect_feedback_to_dict", sequence_helper_start)

    namespace: dict[str, Any] = {
        "Any": Any,
        "BaseModel": BaseModel,
        "Decimal": Decimal,
        "HTTPException": HTTPException,
        "InvalidOperation": InvalidOperation,
        "MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY": MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY,
        "MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY": MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY,
        "MAIL_STANDARD_DELIVERY_SLA_LABEL": MAIL_STANDARD_DELIVERY_SLA_LABEL,
        "MAIL_UNSENT_DRAFT_STATUSES": MAIL_UNSENT_DRAFT_STATUSES,
        "MailSequenceCutoffEventType": MailSequenceCutoffEventType,
        "MailSequenceInterruptionReason": MailSequenceInterruptionReason,
        "MailSequenceStatus": MailSequenceStatus,
        "PricingRule": PricingRule,
        "Session": Session,
        "datetime": datetime,
        "get_mail_sequence_cutoff_rule": get_mail_sequence_cutoff_rule,
        "get_mail_sequence_cutoff_terminal_status": get_mail_sequence_cutoff_terminal_status,
        "get_mail_sequence_step": get_mail_sequence_step,
        "get_mail_sequence_step_interval": get_mail_sequence_step_interval,
        "html": html,
        "json": json,
        "logger": _Logger(),
        "re": re,
        "resolve_mail_pending_draft_disposition": resolve_mail_pending_draft_disposition,
        "sanitize_text": sanitize_text,
        "should_cutoff_event_physically_stop_sequence": should_cutoff_event_physically_stop_sequence,
        "uuid": uuid,
        "_evaluate_and_calibrate_mail_delivery_sla_guardrail": _evaluate_and_calibrate_mail_delivery_sla_guardrail,
    }
    exec(source[model_start:model_end], namespace)
    exec(source[draft_helper_start:draft_helper_end], namespace)
    exec(source[sequence_helper_start:sequence_helper_end], namespace)

    namespace["_active_mail_pricing_rules"] = lambda _db, limit=1000: []
    namespace["_active_mail_pricing_rules_by_line"] = lambda _db, business_line=None, limit=50: []
    namespace["_recall_kb_term_phrase"] = lambda _db, function_fragment, keyword_any=(), business_line=None: ("", "mock_phrase")
    namespace["_mail_fewshot_min_score"] = lambda: 0.60
    namespace["_mail_generate_draft_fewshot"] = (
        lambda _db, scenario, function_fragments, min_score: None
    )
    namespace["_get_mail_sequence_template_for_prompt"] = lambda _db, scenario, suite_step: {
        "template_id": "mock_id",
        "scenario": scenario,
        "suite_step": suite_step,
        "scenario_label_cn": "Mock Scenario",
        "step_label_cn": "Mock Step",
        "purpose_cn": "Mock Purpose",
        "send_timing_cn": "Mock Timing",
        "variable_notes": {},
        "script_template": "Mock Script Template",
        "ai_instruction_script": "Mock AI Instruction",
        "version_no": 1,
        "is_active": True,
        "updated_by": "mock_user",
        "created_at": None,
    }
    namespace["_mail_crm_profile_from_sql"] = (
        lambda customer_key, contact_email: MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY.get(customer_key)
    )
    namespace["_llm_generate_mail_intro_paragraphs"] = lambda profile: {
        "status": "success",
        "model": "gpt-4o-mini",
        "subject": "Mock Subject",
        "paragraphs": ["Mock Paragraph 1", "Mock Paragraph 2", "Mock Paragraph 3", "not enabled for real sending"],
        "error": None,
        "prompt": "Mock Prompt",
    }
    return namespace


class MailReviewApiInterfaceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
        cls.helpers = _load_mail_review_api_helpers()
        cls.draft_request_model = cls.helpers["MailGenerateDraftRequest"]
        cls.sequence_request_model = cls.helpers["MailSequenceInterruptRequest"]
        cls.build_draft_response = staticmethod(cls.helpers["_build_mail_generate_draft_response"])
        cls.build_interrupt_response = staticmethod(cls.helpers["_build_mail_sequence_interrupt_response"])

    def test_mail_review_only_routes_are_registered_with_expected_methods(self) -> None:
        route_expectations = {
            '@app.post("/api/v1/mail/generate-draft", response_model=MailGenerateDraftResponse)': "generate_mail_draft",
            '@app.post("/api/v1/sequence/interrupt", response_model=MailSequenceInterruptResponse)': "interrupt_mail_sequence",
            '@app.get("/api/v1/mail/crm/mock-profiles")': "get_mail_crm_mock_profiles",
        }
        for decorator, function_name in route_expectations.items():
            with self.subTest(function_name=function_name):
                self.assertIn(decorator, self.source)
                self.assertIn(f"async def {function_name}", self.source)

    def test_generate_draft_post_contract_stays_review_only(self) -> None:
        payload = self.draft_request_model(
            customer_key="CUST-DEMO-MULTI-DOMAIN",
            contact_email="buyer@customer-domain.mailmock.test",
            cc_emails=["legal@customer-domain-cn.mailmock.test"],
            scenario="re_activation",
            suite_step=1,
            current_seller_name="Mock Sales Owner",
            current_seller_signature=(
                "Mock Sales Owner\n"
                "Mail Workflow Review Sandbox\n"
                "mock-sales-owner@mailmock.test"
            ),
        )

        response = self.build_draft_response(_NoPricingRulesDb(), payload)

        self.assertEqual(response.status, "drafted")
        self.assertEqual(response.draft_status, MailSequenceStatus.DRAFTED.value)
        self.assertTrue(response.review_required)
        self.assertEqual(response.review_mode, "human_review_required")
        self.assertFalse(response.real_sending_enabled)
        self.assertTrue(response.mail_uid.startswith("mail_draft_"))
        self.assertIn("not enabled for real sending", response.final_body_html)
        self.assertEqual(response.safety_guardrail.overall_outcome, "passed")
        self.assertEqual(response.safety_guardrail.status, "locked_for_approval")
        self.assertTrue(response.safety_guardrail.is_locked_for_approval)
        self.assertFalse(response.safety_guardrail.real_sending_enabled)
        self.assertFalse(response.safety_guardrail.hard_block)
        self.assertTrue(
            all(
                item["real_sending_enabled"] is False
                for item in response.safety_guardrail.gate_results
            )
        )

    def test_sequence_interrupt_post_contract_stays_review_only(self) -> None:
        payload = self.sequence_request_model(
            customer_key="CUST-DEMO-MULTI-DOMAIN",
            contact_email="buyer@customer-domain.mailmock.test",
            recipient_domain="customer-domain.mailmock.test",
            interrupt_reason="crm_stage_changed_to_won",
            operator_name="Mock Sales Owner",
            event_type="crm_state_change",
            crm_event_type="CRM_STAGE_CHANGED_TO_WON",
            crm_stage="won",
            previous_crm_stage="proposal",
            pending_draft_statuses=["pending", "drafted", "approved"],
            metadata={
                "source": "mail_crm_mock_review_only",
                "review_only": True,
            },
        )

        response = self.build_interrupt_response(payload)

        self.assertEqual(response.status, MailSequenceStatus.INTERRUPTED.value)
        self.assertTrue(response.review_only)
        self.assertTrue(response.review_required)
        self.assertFalse(response.real_sending_enabled)
        self.assertEqual(response.interruption_scope, "multi_scope")
        self.assertIn("contact", response.scope_targets)
        self.assertIn("domain", response.scope_targets)
        self.assertIn("customer", response.scope_targets)
        self.assertEqual(
            response.interrupt_reason,
            MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_WON.value,
        )
        self.assertEqual(
            response.event_type,
            MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        )
        self.assertEqual(
            response.deleted_pending_drafts_count,
            response.planned_destroy_pending_drafts_count,
        )
        self.assertEqual(
            response.locked_pending_drafts_count,
            response.planned_lock_pending_drafts_count,
        )
        self.assertFalse(response.operation_log_entry.will_write_database)
        self.assertFalse(response.operation_log_entry.will_delete_pending_drafts)
        self.assertFalse(response.operation_log_entry.will_lock_pending_drafts)
        self.assertFalse(response.operation_log_entry.will_send_email)
        self.assertFalse(response.audit_preview["will_write_database"])
        self.assertFalse(response.audit_preview["will_update_wecom_state"])
        self.assertFalse(
            response.crm_state_change_trigger["review_only_validation"]["will_update_crm_stage"]
        )

    def test_mock_profiles_get_contract_is_read_only_and_uses_mock_payloads(self) -> None:
        catalog = build_mail_crm_mock_catalog()

        self.assertTrue(catalog["is_mock"])
        self.assertTrue(catalog["review_only"])
        self.assertFalse(catalog["real_sending_enabled"])
        self.assertFalse(catalog["will_query_production_crm"])
        self.assertFalse(catalog["will_write_database"])
        self.assertFalse(catalog["will_update_wecom_state"])
        self.assertGreaterEqual(catalog["profile_count"], 2)
        for profile in catalog["profiles"]:
            draft_payload = profile["generate_draft_payload"]
            interrupt_payload = profile["sequence_interrupt_payload"]

            self.draft_request_model(**draft_payload)
            self.sequence_request_model(**interrupt_payload)
            self.assertTrue(profile["is_mock"])
            self.assertTrue(profile["review_only"])
            self.assertFalse(profile["real_sending_enabled"])
            self.assertTrue(interrupt_payload["metadata"]["review_only"])
            self.assertFalse(interrupt_payload["metadata"]["will_update_crm_stage"])
            self.assertFalse(interrupt_payload["metadata"]["will_update_wecom_state"])


if __name__ == "__main__":
    unittest.main()
