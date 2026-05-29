import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mail_sequence_strategy import (
    MAIL_UNSENT_DRAFT_STATUSES,
    MailSequenceCutoffEventType,
    MailSequenceInterruptionReason,
    get_mail_sequence_cutoff_rule,
    get_mail_sequence_cutoff_terminal_status,
    resolve_mail_pending_draft_disposition,
    should_cutoff_event_physically_stop_sequence,
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


def _load_mail_sequence_interrupt_helpers() -> dict[str, Any]:
    source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
    model_start = source.index("class MailSequenceInterruptRequest")
    model_end = source.index("class MailDraftResolvedTerm", model_start)
    helper_start = source.index("CRM_STATE_CHANGE_INTERRUPT_REASON_ALIASES")
    helper_end = source.index("def _email_effect_feedback_to_dict", helper_start)
    namespace: dict[str, Any] = {
        "Any": Any,
        "BaseModel": BaseModel,
        "datetime": datetime,
        "HTTPException": HTTPException,
        "MAIL_UNSENT_DRAFT_STATUSES": MAIL_UNSENT_DRAFT_STATUSES,
        "MailSequenceCutoffEventType": MailSequenceCutoffEventType,
        "MailSequenceInterruptionReason": MailSequenceInterruptionReason,
        "get_mail_sequence_cutoff_rule": get_mail_sequence_cutoff_rule,
        "get_mail_sequence_cutoff_terminal_status": get_mail_sequence_cutoff_terminal_status,
        "json": json,
        "logger": _Logger(),
        "re": re,
        "resolve_mail_pending_draft_disposition": resolve_mail_pending_draft_disposition,
        "sanitize_text": sanitize_text,
        "should_cutoff_event_physically_stop_sequence": should_cutoff_event_physically_stop_sequence,
    }
    exec(source[model_start:model_end], namespace)
    exec(source[helper_start:helper_end], namespace)
    return namespace


class MailSequenceInterruptChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.helpers = _load_mail_sequence_interrupt_helpers()
        cls.request_model = cls.helpers["MailSequenceInterruptRequest"]
        cls.build_response = staticmethod(cls.helpers["_build_mail_sequence_interrupt_response"])

    def test_customer_email_reply_preview_stays_review_only(self) -> None:
        payload = self.request_model(
            customer_key="CUST-EMAIL-DEMO",
            contact_email="buyer@example.com",
            interrupt_reason="customer_reply",
            operator_name="Alice",
            reply_channel="email",
            reply_message_id="mail-msg-001",
            reply_sender_email="buyer@example.com",
            reply_received_at="2026-05-26T20:01:00Z",
            pending_draft_statuses=["drafted"],
        )

        response = self.build_response(payload)

        self.assertEqual(
            response.interrupt_reason,
            MailSequenceInterruptionReason.CUSTOMER_REPLIED_BY_EMAIL.value,
        )
        self.assertEqual(response.event_type, MailSequenceCutoffEventType.CUSTOMER_REPLY.value)
        self.assertTrue(response.review_only)
        self.assertFalse(response.real_sending_enabled)
        self.assertEqual(response.customer_reply_trigger["reply_channel"], "email")
        self.assertEqual(response.customer_reply_trigger["reply_message_id"], "mail-msg-001")
        self.assertFalse(response.customer_reply_trigger["is_other_channel_deal_closure"])
        self.assertFalse(response.audit_preview["will_update_wecom_state"])
        self.assertEqual(response.audit_preview["wecom_state_change"], "none")

    def test_wechat_or_phone_deal_closure_maps_to_other_channel_reply(self) -> None:
        for channel in ("wechat", "phone"):
            with self.subTest(channel=channel):
                payload = self.request_model(
                    customer_key="CUST-DEAL-DEMO",
                    interrupt_reason="customer_reply",
                    operator_name="Alice",
                    reply_channel=channel,
                    deal_closure_channel=channel,
                    deal_closure_status="won",
                    activity_summary="Customer confirmed the deal off-email.",
                    pending_draft_statuses=["approved"],
                )

                response = self.build_response(payload)

                self.assertEqual(
                    response.interrupt_reason,
                    MailSequenceInterruptionReason.CUSTOMER_REPLIED_OTHER_CHANNEL.value,
                )
                self.assertEqual(response.customer_reply_trigger["reply_channel"], channel)
                self.assertTrue(response.customer_reply_trigger["is_other_channel_deal_closure"])
                self.assertEqual(
                    response.customer_reply_trigger["review_only_validation"]["validation_status"],
                    "passed",
                )
                self.assertFalse(
                    response.customer_reply_trigger["review_only_validation"]["will_update_wecom_state"]
                )

    def test_crm_stage_change_preview_exposes_review_only_validation(self) -> None:
        payload = self.request_model(
            customer_key="CUST-CRM-DEMO",
            interrupt_reason="crm_state_change",
            operator_name="Alice",
            crm_event_type="CRM_STAGE_CHANGED_TO_WON",
            crm_stage="won",
            previous_crm_stage="proposal",
            crm_changed_at="2026-05-26T20:05:00Z",
            pending_draft_statuses=["drafted", "approved"],
        )

        response = self.build_response(payload)

        self.assertEqual(
            response.interrupt_reason,
            MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_WON.value,
        )
        self.assertEqual(response.event_type, MailSequenceCutoffEventType.CRM_STATE_CHANGE.value)
        self.assertEqual(
            response.crm_state_change_trigger["review_only_validation"]["validation_status"],
            "passed",
        )
        self.assertFalse(
            response.crm_state_change_trigger["review_only_validation"]["will_update_crm_stage"]
        )
        self.assertFalse(
            response.crm_state_change_trigger["review_only_validation"]["will_update_wecom_state"]
        )
        self.assertEqual(response.crm_state_change_trigger["review_only"], True)
        self.assertEqual(response.audit_preview["crm_state_change_trigger"]["crm_stage"], "won")

    def test_customer_reply_requires_reply_channel(self) -> None:
        payload = self.request_model(
            customer_key="CUST-MISSING-CHANNEL",
            interrupt_reason="customer_reply",
            operator_name="Alice",
        )

        with self.assertRaises(HTTPException) as exc:
            self.build_response(payload)

        self.assertEqual(exc.exception.status_code, 422)
        self.assertIn("reply_channel is required", exc.exception.detail)


if __name__ == "__main__":
    unittest.main()
