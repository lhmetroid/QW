# -*- coding: utf-8 -*-
"""Review-only CRM mock profiles for isolated mail workflow integration.

The records here are fictional and mail-specific. They let CRM/mail API
integration run without querying production CRM, mutating WeCom state, or
enabling real email sending.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mail_crm_field_contract import (
    MAIL_CRM_CANONICAL_FIELD_NAMES,
    MAIL_CRM_FIELD_CONTRACT_VERSION,
)


MAIL_CRM_MOCK_DATA_VERSION = "mail_crm_mock_data.v1"
MAIL_CRM_MOCK_SOURCE = "mail_crm_mock_review_only"


@dataclass(frozen=True)
class MailCrmMockProfile:
    customer_key: str
    contact_email: str
    company_industry: str
    payment_risk_level: str
    current_seller_name: str
    current_seller_signature: str
    customer_domains: tuple[str, ...]
    scenario: str
    suite_step: int
    cc_emails: tuple[str, ...] = ()
    crm_stage: str = "mock_open_review"
    previous_crm_stage: str = "mock_re_activation"
    mock_label: str = "review-only mock CRM profile"
    source: str = MAIL_CRM_MOCK_SOURCE
    is_mock: bool = True
    review_only: bool = True
    real_sending_enabled: bool = False
    will_query_production_crm: bool = False
    will_write_database: bool = False
    will_update_wecom_state: bool = False

    def to_profile_lookup_payload(self) -> dict[str, Any]:
        return {
            "company_industry": self.company_industry,
            "payment_risk_level": self.payment_risk_level,
            "customer_domains": set(self.customer_domains),
            "crm_profile_lookup_status": "matched_mail_crm_mock_customer_key",
            "crm_profile_source": MAIL_CRM_MOCK_SOURCE,
        }

    def to_generate_draft_payload(self) -> dict[str, Any]:
        return {
            "customer_key": self.customer_key,
            "contact_email": self.contact_email,
            "cc_emails": list(self.cc_emails),
            "scenario": self.scenario,
            "suite_step": self.suite_step,
            "current_seller_name": self.current_seller_name,
            "current_seller_signature": self.current_seller_signature,
        }

    def to_sequence_interrupt_payload(self) -> dict[str, Any]:
        return {
            "customer_key": self.customer_key,
            "contact_email": self.contact_email,
            "recipient_domain": self.customer_domains[0],
            "interrupt_reason": "crm_stage_changed_to_won",
            "operator_name": self.current_seller_name,
            "event_type": "crm_state_change",
            "crm_event_type": "CRM_STAGE_CHANGED_TO_WON",
            "crm_stage": self.crm_stage,
            "previous_crm_stage": self.previous_crm_stage,
            "crm_changed_at": "2026-05-26T00:00:00Z",
            "scenario": self.scenario,
            "suite_step": self.suite_step,
            "pending_draft_statuses": ["pending", "drafted", "approved"],
            "metadata": {
                "source": MAIL_CRM_MOCK_SOURCE,
                "is_mock": True,
                "review_only": True,
                "will_update_crm_stage": False,
                "will_update_wecom_state": False,
                "real_sending_enabled": False,
            },
        }

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["contract_version"] = MAIL_CRM_FIELD_CONTRACT_VERSION
        data["canonical_fields"] = list(MAIL_CRM_CANONICAL_FIELD_NAMES)
        data["generate_draft_payload"] = self.to_generate_draft_payload()
        data["sequence_interrupt_payload"] = self.to_sequence_interrupt_payload()
        return data


MAIL_CRM_MOCK_PROFILES: tuple[MailCrmMockProfile, ...] = (
    MailCrmMockProfile(
        customer_key="CUST-DEMO-MULTI-DOMAIN",
        contact_email="buyer@customer-domain.mailmock.test",
        cc_emails=("legal@customer-domain-cn.mailmock.test",),
        company_industry="manufacturing",
        payment_risk_level="low",
        current_seller_name="Mock Sales Owner",
        current_seller_signature=(
            "Mock Sales Owner\n"
            "Mail Workflow Review Sandbox\n"
            "mock-sales-owner@mailmock.test"
        ),
        customer_domains=(
            "customer-domain-cn.mailmock.test",
            "customer-domain.mailmock.test",
        ),
        scenario="re_activation",
        suite_step=1,
    ),
    MailCrmMockProfile(
        customer_key="CUST-HIGH-RISK-DEMO",
        contact_email="buyer@risk-customer.mailmock.test",
        company_industry="legal",
        payment_risk_level="high",
        current_seller_name="Mock Finance Reviewer",
        current_seller_signature=(
            "Mock Finance Reviewer\n"
            "Mail Workflow Review Sandbox\n"
            "mock-finance-reviewer@mailmock.test"
        ),
        customer_domains=("risk-customer.mailmock.test",),
        scenario="new_business_promotion",
        suite_step=2,
        crm_stage="mock_finance_review_required",
        previous_crm_stage="mock_open_review",
    ),
)

MAIL_CRM_MOCK_PROFILE_BY_CUSTOMER_KEY: dict[str, dict[str, Any]] = {
    profile.customer_key: profile.to_profile_lookup_payload()
    for profile in MAIL_CRM_MOCK_PROFILES
}

MAIL_CRM_MOCK_DOMAIN_WHITELIST_BY_CUSTOMER_KEY: dict[str, set[str]] = {
    profile.customer_key: set(profile.customer_domains)
    for profile in MAIL_CRM_MOCK_PROFILES
}


def get_mail_crm_mock_profile(customer_key: str | None) -> MailCrmMockProfile | None:
    normalized = (customer_key or "").strip().upper()
    for profile in MAIL_CRM_MOCK_PROFILES:
        if profile.customer_key == normalized:
            return profile
    return None


def list_mail_crm_mock_profiles() -> list[dict[str, Any]]:
    return [profile.to_public_dict() for profile in MAIL_CRM_MOCK_PROFILES]


def build_mail_crm_mock_catalog() -> dict[str, Any]:
    return {
        "mock_data_version": MAIL_CRM_MOCK_DATA_VERSION,
        "source": MAIL_CRM_MOCK_SOURCE,
        "contract_version": MAIL_CRM_FIELD_CONTRACT_VERSION,
        "canonical_fields": list(MAIL_CRM_CANONICAL_FIELD_NAMES),
        "is_mock": True,
        "review_only": True,
        "real_sending_enabled": False,
        "will_query_production_crm": False,
        "will_write_database": False,
        "will_update_wecom_state": False,
        "wecom_state_change": "none",
        "profile_count": len(MAIL_CRM_MOCK_PROFILES),
        "profiles": list_mail_crm_mock_profiles(),
    }
