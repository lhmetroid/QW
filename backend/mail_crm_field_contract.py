# -*- coding: utf-8 -*-
"""Canonical CRM/mail field contract for the isolated mail workflow.

This module documents the field names the mail workflow may exchange with CRM
context.  It is intentionally mail-specific: do not store these values in
WeCom session state or depend on WeCom external_userid/session_id as a mail key.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MailCrmFieldSpec:
    field_name: str
    source: str
    required_at_draft_boundary: bool
    pii_level: str
    description: str


MAIL_CRM_FIELD_CONTRACT_VERSION = "mail_crm_field_contract.v1"

MAIL_CRM_FIELD_CONTRACT: tuple[MailCrmFieldSpec, ...] = (
    MailCrmFieldSpec(
        field_name="customer_key",
        source="mail profile or CRM customer mapping",
        required_at_draft_boundary=True,
        pii_level="business_identifier",
        description=(
            "Stable mail-side customer or organization key. It must be a CRM/mail "
            "profile key, not a WeCom external_userid, group_, or session_id."
        ),
    ),
    MailCrmFieldSpec(
        field_name="contact_email",
        source="mail profile or CRM contact mapping",
        required_at_draft_boundary=True,
        pii_level="contact_pii",
        description="Target recipient email address used by mail recipient/domain guardrails.",
    ),
    MailCrmFieldSpec(
        field_name="company_industry",
        source="CRM profile",
        required_at_draft_boundary=False,
        pii_level="business_profile",
        description="Optional industry/profile signal for mail retrieval and wording constraints.",
    ),
    MailCrmFieldSpec(
        field_name="payment_risk_level",
        source="CRM profile or finance-approved risk rules",
        required_at_draft_boundary=False,
        pii_level="finance_risk_signal",
        description=(
            "Canonical payment risk signal. Use low, medium, high, blocked, "
            "prepaid_required, or unknown; do not pass free-form payment terms as CRM context."
        ),
    ),
    MailCrmFieldSpec(
        field_name="current_seller_name",
        source="CRM owner mapping or explicit seller input",
        required_at_draft_boundary=True,
        pii_level="seller_business_identity",
        description="Current seller owner name shown as the sender/owner for the mail draft.",
    ),
    MailCrmFieldSpec(
        field_name="current_seller_signature",
        source="CRM owner mapping or explicit seller input",
        required_at_draft_boundary=True,
        pii_level="seller_contact_pii",
        description="Current seller signature block appended to draft-only mail output.",
    ),
)

MAIL_CRM_CANONICAL_FIELD_NAMES: tuple[str, ...] = tuple(
    spec.field_name for spec in MAIL_CRM_FIELD_CONTRACT
)

MAIL_CRM_DRAFT_REQUIRED_FIELD_NAMES: tuple[str, ...] = tuple(
    spec.field_name for spec in MAIL_CRM_FIELD_CONTRACT if spec.required_at_draft_boundary
)

MAIL_CRM_OPTIONAL_PROFILE_FIELD_NAMES: tuple[str, ...] = tuple(
    spec.field_name for spec in MAIL_CRM_FIELD_CONTRACT if not spec.required_at_draft_boundary
)

MAIL_CRM_FIELD_ALIASES: dict[str, str] = {
    "industry": "company_industry",
    "seller_owner_name": "current_seller_name",
    "seller_signature": "current_seller_signature",
    "payment_terms": "payment_risk_level",
}
