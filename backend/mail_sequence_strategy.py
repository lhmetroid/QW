"""Reusable mail sequence strategy definitions.

This module is intentionally isolated from WeCom reply flows and mail sending.
It only exposes deterministic strategy metadata that later mail APIs and
sequence state-machine tasks can reuse.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class MailScenario(str, Enum):
    RE_ACTIVATION = "re_activation"
    NEW_BUSINESS_PROMOTION = "new_business_promotion"
    NEW_CONTACT_INTRO = "new_contact_intro"
    PRINT_QUOTE_FOLLOWUP = "print_quote_followup"


class MailSnippetType(str, Enum):
    GREETINGS = "greetings"
    EXAMPLE = "example"
    PROCESS = "process"
    CONSTRAINT = "constraint"
    QUOTATION = "quotation"


class MailSequenceStatus(str, Enum):
    PENDING = "pending"
    DRAFTED = "drafted"
    APPROVED = "approved"
    SENT = "sent"
    REPLIED = "replied"
    INTERRUPTED = "interrupted"
    BLOCKED = "blocked"


class MailSequenceTriggerAnchor(str, Enum):
    SEQUENCE_START = "sequence_start"
    PREVIOUS_STEP_COMPLETED = "previous_step_completed"


class MailSequenceCutoffEventType(str, Enum):
    CUSTOMER_REPLY = "customer_reply"
    CRM_STATE_CHANGE = "crm_state_change"
    MANUAL_SEAL = "manual_seal"


class MailSequenceInterruptionReason(str, Enum):
    CUSTOMER_REPLIED_BY_EMAIL = "customer_replied_by_email"
    CUSTOMER_REPLIED_SAME_DOMAIN = "customer_replied_same_domain"
    CUSTOMER_REPLIED_OTHER_CHANNEL = "customer_replied_other_channel"
    CRM_STAGE_CHANGED_TO_WON = "crm_stage_changed_to_won"
    CRM_STAGE_CHANGED_TO_LOST = "crm_stage_changed_to_lost"
    CRM_STAGE_CHANGED_TO_ACTIVE_OPPORTUNITY = "crm_stage_changed_to_active_opportunity"
    CRM_STAGE_CHANGED_TO_COMPLAINT = "crm_stage_changed_to_complaint"
    CRM_MARKED_DO_NOT_CONTACT = "crm_marked_do_not_contact"
    CRM_ASSIGNED_MANUAL_FOLLOW_UP = "crm_assigned_manual_follow_up"
    CRM_CONTACT_INVALID_OR_LEFT = "crm_contact_invalid_or_left"
    MANUAL_SEALED_BY_SALES = "manual_sealed_by_sales"
    MANUAL_SEALED_BY_OPERATIONS = "manual_sealed_by_operations"
    MANUAL_SEALED_BY_SUPERVISOR = "manual_sealed_by_supervisor"


class MailPendingDraftDispositionAction(str, Enum):
    DESTROY = "destroy"
    LOCK = "lock"
    KEEP = "keep"


@dataclass(frozen=True)
class MailSequenceStepStrategy:
    scenario: str
    scenario_label: str
    suite_step: int
    step_key: str
    objective: str
    recommended_snippet_types: tuple[str, ...]
    subject_template_hints: tuple[str, ...]
    cta_style: str
    retrieval_filter_requirements: tuple[str, ...]
    forbidden_boundaries: tuple[str, ...]
    exit_conditions: tuple[str, ...]
    data_structure_fields: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MailSequenceStepInterval:
    scenario: str
    suite_step: int
    trigger_anchor: str
    delay_days: int
    cumulative_min_days_from_sequence_start: int
    default_status_to_create: str
    generation_policy: str
    interrupt_before_generation: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MailSequenceStrategy:
    scenario: str
    scenario_label: str
    objective: str
    applicable_trigger: str
    isolation_boundary: str
    steps: tuple[MailSequenceStepStrategy, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MailSequenceStatusMetadata:
    status: str
    label: str
    category: str
    description: str
    terminal: bool
    allows_draft_generation: bool
    allows_manual_approval: bool
    allows_real_sending: bool
    owner: str
    next_task_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MailSequenceCutoffRule:
    event_type: str
    interruption_reason: str
    label: str
    description: str
    terminal_status: str
    physically_stops_sequence: bool
    applies_to_scenarios: tuple[str, ...]
    applies_to_steps: tuple[int, ...]
    cutoff_scope: str
    source_system: str
    required_metadata_keys: tuple[str, ...]
    draft_disposition: str
    audit_metadata: dict[str, str]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MailPendingDraftDispositionRule:
    event_type: str
    interruption_reason: str
    draft_status: str
    disposition_action: str
    disposition_label: str
    description: str
    applies_to_scenarios: tuple[str, ...]
    applies_to_steps: tuple[int, ...]
    preserve_audit_record: bool
    blocks_real_sending: bool
    removes_body_content: bool
    audit_metadata: dict[str, str]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MAIL_SEQUENCE_STATUS_METADATA: dict[MailSequenceStatus, MailSequenceStatusMetadata] = {
    MailSequenceStatus.PENDING: MailSequenceStatusMetadata(
        status=MailSequenceStatus.PENDING.value,
        label="Pending",
        category="active",
        description=(
            "Sequence step is queued or waiting for draft creation. No customer-facing "
            "content has been generated for this step yet."
        ),
        terminal=False,
        allows_draft_generation=True,
        allows_manual_approval=False,
        allows_real_sending=False,
        owner="mail_sequence",
        next_task_notes=(
            "Task 23 may attach scheduled trigger intervals to this status.",
            "Task 25 may destroy or lock pending drafts when a sequence is cut off.",
        ),
    ),
    MailSequenceStatus.DRAFTED: MailSequenceStatusMetadata(
        status=MailSequenceStatus.DRAFTED.value,
        label="Drafted",
        category="review",
        description=(
            "A draft exists for the step and is waiting for sales, operations, or "
            "future safety-gate review."
        ),
        terminal=False,
        allows_draft_generation=False,
        allows_manual_approval=True,
        allows_real_sending=False,
        owner="mail_draft_review",
        next_task_notes=(
            "Task 26-31 should create drafts in this status by default.",
            "Price, SLA, payment, and recipient safety gates must still run before approval.",
        ),
    ),
    MailSequenceStatus.APPROVED: MailSequenceStatusMetadata(
        status=MailSequenceStatus.APPROVED.value,
        label="Approved",
        category="review",
        description=(
            "A human or later explicit approval workflow has accepted the draft for "
            "the next controlled action."
        ),
        terminal=False,
        allows_draft_generation=False,
        allows_manual_approval=False,
        allows_real_sending=False,
        owner="mail_draft_review",
        next_task_notes=(
            "This metadata does not enable real sending.",
            "A separate mail sender integration must still remain disabled by default.",
        ),
    ),
    MailSequenceStatus.SENT: MailSequenceStatusMetadata(
        status=MailSequenceStatus.SENT.value,
        label="Sent",
        category="outbound",
        description=(
            "A future controlled sender has recorded the step as sent. The current "
            "strategy module only defines the status value and never sends email."
        ),
        terminal=False,
        allows_draft_generation=False,
        allows_manual_approval=False,
        allows_real_sending=False,
        owner="future_mail_sender",
        next_task_notes=(
            "Real sending must stay behind a separate disabled-by-default integration.",
            "Task 24 should stop later steps if a reply or CRM state change is detected.",
        ),
    ),
    MailSequenceStatus.REPLIED: MailSequenceStatusMetadata(
        status=MailSequenceStatus.REPLIED.value,
        label="Replied",
        category="terminal",
        description=(
            "Customer replied or otherwise engaged, so automated follow-up steps "
            "should stop and move to manual or CRM-owned handling."
        ),
        terminal=True,
        allows_draft_generation=False,
        allows_manual_approval=False,
        allows_real_sending=False,
        owner="mail_inbound_or_crm",
        next_task_notes=(
            "Task 24 should treat this as a physical cut-off state.",
            "Task 25 should lock or remove unsent follow-up drafts.",
        ),
    ),
    MailSequenceStatus.INTERRUPTED: MailSequenceStatusMetadata(
        status=MailSequenceStatus.INTERRUPTED.value,
        label="Interrupted",
        category="terminal",
        description=(
            "Manual seal, CRM stage change, do-not-contact, or another explicit "
            "business event stopped the sequence before completion."
        ),
        terminal=True,
        allows_draft_generation=False,
        allows_manual_approval=False,
        allows_real_sending=False,
        owner="mail_sequence_interrupt",
        next_task_notes=(
            "Task 24 should define the concrete interruption events.",
            "Task 32-37 should expose interrupt APIs and operation logging.",
        ),
    ),
    MailSequenceStatus.BLOCKED: MailSequenceStatusMetadata(
        status=MailSequenceStatus.BLOCKED.value,
        label="Blocked",
        category="terminal",
        description=(
            "Safety, compliance, payment-risk, recipient-domain, or manual guardrail "
            "blocked the sequence from proceeding."
        ),
        terminal=True,
        allows_draft_generation=False,
        allows_manual_approval=False,
        allows_real_sending=False,
        owner="mail_safety_guardrail",
        next_task_notes=(
            "Task 38-45 should map red/yellow safety results to this status where appropriate.",
            "Blocked status must not be inferred by free-form model text alone.",
        ),
    ),
}

MAIL_SEQUENCE_STATUSES: tuple[str, ...] = tuple(status.value for status in MailSequenceStatus)
MAIL_SEQUENCE_TERMINAL_STATUSES: tuple[str, ...] = tuple(
    metadata.status
    for metadata in MAIL_SEQUENCE_STATUS_METADATA.values()
    if metadata.terminal
)
MAIL_SEQUENCE_ACTIVE_STATUSES: tuple[str, ...] = tuple(
    metadata.status
    for metadata in MAIL_SEQUENCE_STATUS_METADATA.values()
    if not metadata.terminal
)
MAIL_SEQUENCE_REVIEW_STATUSES: tuple[str, ...] = tuple(
    metadata.status
    for metadata in MAIL_SEQUENCE_STATUS_METADATA.values()
    if metadata.category == "review"
)
MAIL_SEQUENCE_OUTBOUND_STATUSES: tuple[str, ...] = tuple(
    metadata.status
    for metadata in MAIL_SEQUENCE_STATUS_METADATA.values()
    if metadata.category == "outbound"
)

ALL_MAIL_SEQUENCE_SCENARIOS: tuple[str, ...] = tuple(scenario.value for scenario in MailScenario)
ALL_MAIL_SEQUENCE_STEPS: tuple[int, ...] = (1, 2, 3, 4)

MAIL_SEQUENCE_CUTOFF_RULES: dict[MailSequenceInterruptionReason, MailSequenceCutoffRule] = {
    MailSequenceInterruptionReason.CUSTOMER_REPLIED_BY_EMAIL: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CUSTOMER_REPLY.value,
        interruption_reason=MailSequenceInterruptionReason.CUSTOMER_REPLIED_BY_EMAIL.value,
        label="Customer replied by email",
        description=(
            "A new non-automatic inbound email from the target contact means the activation "
            "sequence has achieved engagement and all later automated follow-up must stop."
        ),
        terminal_status=MailSequenceStatus.REPLIED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="contact",
        source_system="mail_inbound_sync",
        required_metadata_keys=("customer_key", "contact_email", "message_id", "received_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={
            "reply_channel": "email",
            "auto_mail_policy": "ignore_auto_replies_and_bounces",
            "matching_policy": "exact_contact_email",
        },
        notes=(
            "Auto replies, bounces, advertisements, and quoted historical text must not trigger this rule.",
            "This module only defines the cut-off decision; Task 25/API work performs draft cleanup.",
        ),
    ),
    MailSequenceInterruptionReason.CUSTOMER_REPLIED_SAME_DOMAIN: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CUSTOMER_REPLY.value,
        interruption_reason=MailSequenceInterruptionReason.CUSTOMER_REPLIED_SAME_DOMAIN.value,
        label="Customer domain replied",
        description=(
            "A new non-automatic inbound email from the same customer domain indicates "
            "the account is active, even if a different colleague replied."
        ),
        terminal_status=MailSequenceStatus.REPLIED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="domain",
        source_system="mail_inbound_sync",
        required_metadata_keys=("customer_key", "recipient_domain", "sender_email", "message_id", "received_at"),
        draft_disposition="lock_or_delete_pending_domain_followup_drafts",
        audit_metadata={
            "reply_channel": "email",
            "auto_mail_policy": "ignore_auto_replies_and_bounces",
            "matching_policy": "same_customer_domain",
        },
        notes=(
            "Free-mail and competitor domains must be handled by later recipient-domain safety rules.",
            "Domain-level stop prevents continued automated chasing after any real account engagement.",
        ),
    ),
    MailSequenceInterruptionReason.CUSTOMER_REPLIED_OTHER_CHANNEL: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CUSTOMER_REPLY.value,
        interruption_reason=MailSequenceInterruptionReason.CUSTOMER_REPLIED_OTHER_CHANNEL.value,
        label="Customer replied through another channel",
        description=(
            "Sales or CRM recorded a real customer response by phone, meeting, chat, or "
            "another non-email channel, so mail automation must hand off to manual handling."
        ),
        terminal_status=MailSequenceStatus.REPLIED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer",
        source_system="crm_or_manual_activity",
        required_metadata_keys=("customer_key", "channel", "recorded_at", "operator_id"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={
            "reply_channel": "non_email",
            "matching_policy": "crm_activity_or_manual_record",
        },
        notes=(
            "This covers the documented phone, chat, meeting, or offline reply double-stop path.",
        ),
    ),
    MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_WON: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_WON.value,
        label="CRM stage changed to won",
        description="The customer has won business recorded in CRM; activation follow-up is no longer appropriate.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer",
        source_system="crm",
        required_metadata_keys=("customer_key", "crm_stage", "changed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"terminal_crm_stage": "deal_won"},
        notes=("Future conversion tracking may read this reason, but it must not keep the sequence active.",),
    ),
    MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_LOST: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_LOST.value,
        label="CRM stage changed to lost",
        description="CRM marked the opportunity or account as lost, so automated activation must stop.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer",
        source_system="crm",
        required_metadata_keys=("customer_key", "crm_stage", "changed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"terminal_crm_stage": "lost"},
        notes=("Restarting later requires an explicit new sequence, not continuation of this one.",),
    ),
    MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_ACTIVE_OPPORTUNITY: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_ACTIVE_OPPORTUNITY.value,
        label="CRM stage changed to active opportunity",
        description="CRM now has an active opportunity, quote, sample, or project discussion for this customer.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer",
        source_system="crm",
        required_metadata_keys=("customer_key", "crm_stage", "changed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"terminal_crm_stage": "active_opportunity"},
        notes=("Manual opportunity handling owns follow-up after this event.",),
    ),
    MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_COMPLAINT: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_STAGE_CHANGED_TO_COMPLAINT.value,
        label="CRM stage changed to complaint",
        description="CRM indicates complaint, dispute, or escalation handling; activation content must stop.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer",
        source_system="crm",
        required_metadata_keys=("customer_key", "crm_stage", "changed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"terminal_crm_stage": "complaint"},
        notes=("Complaint handling must be manual or safety-owned, never sequence-owned.",),
    ),
    MailSequenceInterruptionReason.CRM_MARKED_DO_NOT_CONTACT: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_MARKED_DO_NOT_CONTACT.value,
        label="CRM marked do-not-contact",
        description="CRM or compliance data marks the customer/contact/domain as not contactable.",
        terminal_status=MailSequenceStatus.BLOCKED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer_or_contact_or_domain",
        source_system="crm",
        required_metadata_keys=("customer_key", "do_not_contact_scope", "changed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"guardrail": "do_not_contact"},
        notes=("This maps to blocked because it is a contactability guardrail, not normal engagement.",),
    ),
    MailSequenceInterruptionReason.CRM_ASSIGNED_MANUAL_FOLLOW_UP: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_ASSIGNED_MANUAL_FOLLOW_UP.value,
        label="CRM assigned manual follow-up",
        description="CRM assigns the customer to an owner, task, or queue that should handle follow-up manually.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer",
        source_system="crm",
        required_metadata_keys=("customer_key", "owner_id", "changed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"terminal_crm_stage": "manual_follow_up"},
        notes=("This avoids competing automated and human follow-up.",),
    ),
    MailSequenceInterruptionReason.CRM_CONTACT_INVALID_OR_LEFT: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.CRM_STATE_CHANGE.value,
        interruption_reason=MailSequenceInterruptionReason.CRM_CONTACT_INVALID_OR_LEFT.value,
        label="CRM contact invalid or left",
        description="CRM shows the selected recipient is invalid, has left, or is not the right contact.",
        terminal_status=MailSequenceStatus.BLOCKED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="contact",
        source_system="crm",
        required_metadata_keys=("customer_key", "contact_email", "changed_at"),
        draft_disposition="lock_or_delete_pending_contact_drafts",
        audit_metadata={"guardrail": "invalid_contact"},
        notes=("A new contact introduction sequence may be opened only after a validated replacement contact exists.",),
    ),
    MailSequenceInterruptionReason.MANUAL_SEALED_BY_SALES: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.MANUAL_SEAL.value,
        interruption_reason=MailSequenceInterruptionReason.MANUAL_SEALED_BY_SALES.value,
        label="Manually sealed by sales",
        description="A salesperson explicitly sealed the activation sequence after taking over follow-up.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer_or_contact",
        source_system="mail_workbench",
        required_metadata_keys=("customer_key", "operator_id", "sealed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"manual_seal_actor": "sales"},
        notes=("Manual seal is an explicit physical stop and must win over scheduled generation.",),
    ),
    MailSequenceInterruptionReason.MANUAL_SEALED_BY_OPERATIONS: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.MANUAL_SEAL.value,
        interruption_reason=MailSequenceInterruptionReason.MANUAL_SEALED_BY_OPERATIONS.value,
        label="Manually sealed by operations",
        description="Operations explicitly sealed the activation sequence because handling moved outside automation.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer_or_contact",
        source_system="mail_workbench",
        required_metadata_keys=("customer_key", "operator_id", "sealed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"manual_seal_actor": "operations"},
        notes=("This is for process ownership handoff, not safety override.",),
    ),
    MailSequenceInterruptionReason.MANUAL_SEALED_BY_SUPERVISOR: MailSequenceCutoffRule(
        event_type=MailSequenceCutoffEventType.MANUAL_SEAL.value,
        interruption_reason=MailSequenceInterruptionReason.MANUAL_SEALED_BY_SUPERVISOR.value,
        label="Manually sealed by supervisor",
        description="A supervisor explicitly sealed the activation sequence for business, safety, or quality reasons.",
        terminal_status=MailSequenceStatus.INTERRUPTED.value,
        physically_stops_sequence=True,
        applies_to_scenarios=ALL_MAIL_SEQUENCE_SCENARIOS,
        applies_to_steps=ALL_MAIL_SEQUENCE_STEPS,
        cutoff_scope="customer_or_contact_or_domain",
        source_system="mail_workbench",
        required_metadata_keys=("customer_key", "operator_id", "sealed_at"),
        draft_disposition="lock_or_delete_pending_followup_drafts",
        audit_metadata={"manual_seal_actor": "supervisor"},
        notes=("Supervisor seal should be preserved in audit logs for later review.",),
    ),
}

MAIL_SEQUENCE_CUTOFF_EVENT_TERMINAL_STATUS: dict[MailSequenceInterruptionReason, MailSequenceStatus] = {
    reason: MailSequenceStatus(rule.terminal_status)
    for reason, rule in MAIL_SEQUENCE_CUTOFF_RULES.items()
}
MAIL_SEQUENCE_CUTOFF_REASONS: tuple[str, ...] = tuple(reason.value for reason in MailSequenceInterruptionReason)
MAIL_SEQUENCE_CUTOFF_EVENT_TYPES: tuple[str, ...] = tuple(event_type.value for event_type in MailSequenceCutoffEventType)

MAIL_UNSENT_DRAFT_STATUSES: tuple[str, ...] = (
    MailSequenceStatus.PENDING.value,
    MailSequenceStatus.DRAFTED.value,
    MailSequenceStatus.APPROVED.value,
)

MAIL_SENT_OR_TERMINAL_DRAFT_STATUSES: tuple[str, ...] = (
    MailSequenceStatus.SENT.value,
    *MAIL_SEQUENCE_TERMINAL_STATUSES,
)

MAIL_PENDING_DRAFT_DISPOSITION_ACTIONS: tuple[str, ...] = tuple(
    action.value for action in MailPendingDraftDispositionAction
)

_CUSTOMER_REPLY_PENDING_DRAFT_ACTION_BY_STATUS: dict[str, MailPendingDraftDispositionAction] = {
    MailSequenceStatus.PENDING.value: MailPendingDraftDispositionAction.DESTROY,
    MailSequenceStatus.DRAFTED.value: MailPendingDraftDispositionAction.DESTROY,
    MailSequenceStatus.APPROVED.value: MailPendingDraftDispositionAction.LOCK,
}

_CRM_PENDING_DRAFT_ACTION_BY_STATUS: dict[str, MailPendingDraftDispositionAction] = {
    MailSequenceStatus.PENDING.value: MailPendingDraftDispositionAction.DESTROY,
    MailSequenceStatus.DRAFTED.value: MailPendingDraftDispositionAction.DESTROY,
    MailSequenceStatus.APPROVED.value: MailPendingDraftDispositionAction.LOCK,
}

_CRM_STRICT_DESTROY_REASONS: frozenset[MailSequenceInterruptionReason] = frozenset(
    {
        MailSequenceInterruptionReason.CRM_MARKED_DO_NOT_CONTACT,
        MailSequenceInterruptionReason.CRM_CONTACT_INVALID_OR_LEFT,
    }
)

_MANUAL_SEAL_PENDING_DRAFT_ACTION_BY_STATUS: dict[str, MailPendingDraftDispositionAction] = {
    MailSequenceStatus.PENDING.value: MailPendingDraftDispositionAction.LOCK,
    MailSequenceStatus.DRAFTED.value: MailPendingDraftDispositionAction.LOCK,
    MailSequenceStatus.APPROVED.value: MailPendingDraftDispositionAction.LOCK,
}


def _pending_draft_action_by_status_for_reason(
    reason: MailSequenceInterruptionReason,
) -> dict[str, MailPendingDraftDispositionAction]:
    rule = MAIL_SEQUENCE_CUTOFF_RULES[reason]
    event_type = MailSequenceCutoffEventType(rule.event_type)
    if event_type == MailSequenceCutoffEventType.CUSTOMER_REPLY:
        return _CUSTOMER_REPLY_PENDING_DRAFT_ACTION_BY_STATUS
    if event_type == MailSequenceCutoffEventType.MANUAL_SEAL:
        return _MANUAL_SEAL_PENDING_DRAFT_ACTION_BY_STATUS
    if reason in _CRM_STRICT_DESTROY_REASONS:
        return {
            status: MailPendingDraftDispositionAction.DESTROY
            for status in MAIL_UNSENT_DRAFT_STATUSES
        }
    return _CRM_PENDING_DRAFT_ACTION_BY_STATUS


def _pending_draft_disposition_description(
    reason: MailSequenceInterruptionReason,
    draft_status: str,
    action: MailPendingDraftDispositionAction,
) -> str:
    rule = MAIL_SEQUENCE_CUTOFF_RULES[reason]
    if action == MailPendingDraftDispositionAction.DESTROY:
        return (
            f"After {rule.label}, unsent {draft_status} draft content must be destroyed "
            "or the pending generation record must be cancelled before any send path can use it."
        )
    if action == MailPendingDraftDispositionAction.LOCK:
        return (
            f"After {rule.label}, unsent {draft_status} drafts must be locked so they "
            "remain available for audit or manual review but cannot be approved or sent."
        )
    return f"After {rule.label}, {draft_status} records are retained without draft cleanup."


def _build_pending_draft_disposition_rules() -> dict[
    tuple[MailSequenceInterruptionReason, str],
    MailPendingDraftDispositionRule,
]:
    disposition_rules: dict[tuple[MailSequenceInterruptionReason, str], MailPendingDraftDispositionRule] = {}
    for reason, cutoff_rule in MAIL_SEQUENCE_CUTOFF_RULES.items():
        action_by_status = _pending_draft_action_by_status_for_reason(reason)
        for draft_status, action in action_by_status.items():
            disposition_rules[(reason, draft_status)] = MailPendingDraftDispositionRule(
                event_type=cutoff_rule.event_type,
                interruption_reason=reason.value,
                draft_status=draft_status,
                disposition_action=action.value,
                disposition_label=(
                    "Destroy unsent draft"
                    if action == MailPendingDraftDispositionAction.DESTROY
                    else "Lock unsent draft"
                    if action == MailPendingDraftDispositionAction.LOCK
                    else "Keep draft record"
                ),
                description=_pending_draft_disposition_description(reason, draft_status, action),
                applies_to_scenarios=cutoff_rule.applies_to_scenarios,
                applies_to_steps=cutoff_rule.applies_to_steps,
                preserve_audit_record=True,
                blocks_real_sending=action != MailPendingDraftDispositionAction.KEEP,
                removes_body_content=action == MailPendingDraftDispositionAction.DESTROY,
                audit_metadata={
                    "cutoff_scope": cutoff_rule.cutoff_scope,
                    "source_system": cutoff_rule.source_system,
                    "terminal_status": cutoff_rule.terminal_status,
                    "draft_disposition": cutoff_rule.draft_disposition,
                },
                notes=(
                    "These rules are mail-only metadata and do not execute database deletes or locks.",
                    "A destroy action should remove customer-facing body content while retaining an audit shell.",
                    "A lock action must make the draft impossible to approve or send unless a later manual workflow opens a new sequence.",
                ),
            )
    return disposition_rules


MAIL_PENDING_DRAFT_DISPOSITION_RULES: dict[
    tuple[MailSequenceInterruptionReason, str],
    MailPendingDraftDispositionRule,
] = _build_pending_draft_disposition_rules()

DEFAULT_MAIL_SEQUENCE_STEP_DELAYS_DAYS: dict[int, int] = {
    1: 0,
    2: 7,
    3: 10,
    4: 10,
}

DEFAULT_MAIL_SEQUENCE_STEP_CUMULATIVE_MIN_DAYS: dict[int, int] = {
    1: 0,
    2: 7,
    3: 17,
    4: 27,
}

MAIL_SEQUENCE_STEP_INTERVALS: dict[tuple[MailScenario, int], MailSequenceStepInterval] = {
    (scenario, suite_step): MailSequenceStepInterval(
        scenario=scenario.value,
        suite_step=suite_step,
        trigger_anchor=(
            MailSequenceTriggerAnchor.SEQUENCE_START.value
            if suite_step == 1
            else MailSequenceTriggerAnchor.PREVIOUS_STEP_COMPLETED.value
        ),
        delay_days=delay_days,
        cumulative_min_days_from_sequence_start=DEFAULT_MAIL_SEQUENCE_STEP_CUMULATIVE_MIN_DAYS[suite_step],
        default_status_to_create=MailSequenceStatus.PENDING.value,
        generation_policy=(
            "Generate Step 1 draft on the same day the sequence is opened; generate "
            "later step drafts only after the configured delay has elapsed and Task 24/25 "
            "interruption or draft-lock rules have not stopped the sequence."
        ),
        interrupt_before_generation=True,
        notes=(
            "This metadata defines draft-generation timing only and never enables real sending.",
            "Step 2 waits 7 days after the previous step is completed.",
            "Step 3 waits 10 days after the previous step is completed.",
            "Step 4 waits 10 days after the previous step is completed.",
            "Future Task 54 may expose these defaults through mail-only configuration.",
        ),
    )
    for scenario in MailScenario
    for suite_step, delay_days in DEFAULT_MAIL_SEQUENCE_STEP_DELAYS_DAYS.items()
}


def normalize_mail_sequence_status(status: str | MailSequenceStatus) -> str:
    try:
        status_enum = MailSequenceStatus(status)
    except ValueError as exc:
        raise ValueError(f"unsupported mail sequence status: {status}") from exc
    return status_enum.value


def normalize_mail_sequence_cutoff_event_type(
    event_type: str | MailSequenceCutoffEventType,
) -> str:
    if isinstance(event_type, MailSequenceCutoffEventType):
        return event_type.value
    event_type = event_type.lower()
    try:
        event_type_enum = MailSequenceCutoffEventType(event_type)
    except ValueError as exc:
        raise ValueError(f"unsupported mail sequence cut-off event type: {event_type}") from exc
    return event_type_enum.value


def normalize_mail_sequence_interruption_reason(
    interruption_reason: str | MailSequenceInterruptionReason,
) -> str:
    if isinstance(interruption_reason, MailSequenceInterruptionReason):
        return interruption_reason.value
    interruption_reason = interruption_reason.lower()
    try:
        reason_enum = MailSequenceInterruptionReason(interruption_reason)
    except ValueError as exc:
        raise ValueError(f"unsupported mail sequence interruption reason: {interruption_reason}") from exc
    return reason_enum.value


def normalize_mail_pending_draft_disposition_action(
    disposition_action: str | MailPendingDraftDispositionAction,
) -> str:
    if isinstance(disposition_action, MailPendingDraftDispositionAction):
        return disposition_action.value
    disposition_action = disposition_action.lower()
    try:
        action_enum = MailPendingDraftDispositionAction(disposition_action)
    except ValueError as exc:
        raise ValueError(f"unsupported mail pending-draft disposition action: {disposition_action}") from exc
    return action_enum.value


def get_mail_sequence_status_metadata(status: str | MailSequenceStatus) -> MailSequenceStatusMetadata:
    status_enum = MailSequenceStatus(normalize_mail_sequence_status(status))
    return MAIL_SEQUENCE_STATUS_METADATA[status_enum]


def list_mail_sequence_status_metadata() -> list[dict[str, Any]]:
    return [metadata.to_dict() for metadata in MAIL_SEQUENCE_STATUS_METADATA.values()]


def list_mail_sequence_statuses_by_category(category: str) -> tuple[str, ...]:
    return tuple(
        metadata.status
        for metadata in MAIL_SEQUENCE_STATUS_METADATA.values()
        if metadata.category == category
    )


def get_mail_sequence_step_interval(
    scenario: str | MailScenario,
    suite_step: int,
) -> MailSequenceStepInterval:
    try:
        scenario_enum = MailScenario(scenario)
    except ValueError as exc:
        raise ValueError(f"unsupported mail sequence scenario: {scenario}") from exc

    try:
        return MAIL_SEQUENCE_STEP_INTERVALS[(scenario_enum, suite_step)]
    except KeyError as exc:
        raise ValueError(f"unsupported suite_step for {scenario_enum.value}: {suite_step}") from exc


def list_mail_sequence_step_intervals(scenario: str | MailScenario | None = None) -> list[dict[str, Any]]:
    if scenario is None:
        intervals = MAIL_SEQUENCE_STEP_INTERVALS.values()
    else:
        scenario_enum = MailScenario(scenario)
        intervals = (
            interval
            for key, interval in MAIL_SEQUENCE_STEP_INTERVALS.items()
            if key[0] == scenario_enum
        )
    return [interval.to_dict() for interval in intervals]


def is_known_mail_sequence_status(status: str | MailSequenceStatus) -> bool:
    try:
        normalize_mail_sequence_status(status)
    except ValueError:
        return False
    return True


def is_terminal_mail_sequence_status(status: str | MailSequenceStatus) -> bool:
    return get_mail_sequence_status_metadata(status).terminal


def get_mail_sequence_cutoff_rule(
    interruption_reason: str | MailSequenceInterruptionReason,
) -> MailSequenceCutoffRule:
    reason_enum = MailSequenceInterruptionReason(normalize_mail_sequence_interruption_reason(interruption_reason))
    return MAIL_SEQUENCE_CUTOFF_RULES[reason_enum]


def get_mail_sequence_cutoff_terminal_status(
    interruption_reason: str | MailSequenceInterruptionReason,
) -> str:
    reason_enum = MailSequenceInterruptionReason(normalize_mail_sequence_interruption_reason(interruption_reason))
    return MAIL_SEQUENCE_CUTOFF_EVENT_TERMINAL_STATUS[reason_enum].value


def should_physically_stop_mail_sequence(
    interruption_reason: str | MailSequenceInterruptionReason,
    current_status: str | MailSequenceStatus | None = None,
) -> bool:
    rule = get_mail_sequence_cutoff_rule(interruption_reason)
    if not rule.physically_stops_sequence:
        return False
    if current_status is None:
        return True
    return not is_terminal_mail_sequence_status(current_status)


def should_cutoff_event_physically_stop_sequence(
    event_type: str | MailSequenceCutoffEventType,
    interruption_reason: str | MailSequenceInterruptionReason,
    current_status: str | MailSequenceStatus | None = None,
) -> bool:
    event_type_value = normalize_mail_sequence_cutoff_event_type(event_type)
    rule = get_mail_sequence_cutoff_rule(interruption_reason)
    if rule.event_type != event_type_value:
        return False
    return should_physically_stop_mail_sequence(interruption_reason, current_status=current_status)


def list_mail_sequence_cutoff_rules(
    scenario: str | MailScenario | None = None,
    suite_step: int | None = None,
    event_type: str | MailSequenceCutoffEventType | None = None,
) -> list[dict[str, Any]]:
    scenario_value = MailScenario(scenario).value if scenario is not None else None
    event_type_value = (
        normalize_mail_sequence_cutoff_event_type(event_type)
        if event_type is not None
        else None
    )
    if suite_step is not None and suite_step not in ALL_MAIL_SEQUENCE_STEPS:
        raise ValueError(f"unsupported suite_step for mail sequence cut-off rules: {suite_step}")

    rules = []
    for rule in MAIL_SEQUENCE_CUTOFF_RULES.values():
        if scenario_value is not None and scenario_value not in rule.applies_to_scenarios:
            continue
        if suite_step is not None and suite_step not in rule.applies_to_steps:
            continue
        if event_type_value is not None and rule.event_type != event_type_value:
            continue
        rules.append(rule.to_dict())
    return rules


def list_mail_sequence_cutoff_rules_for_step(
    scenario: str | MailScenario,
    suite_step: int,
) -> list[dict[str, Any]]:
    return list_mail_sequence_cutoff_rules(scenario=scenario, suite_step=suite_step)


def get_mail_pending_draft_disposition_rule(
    interruption_reason: str | MailSequenceInterruptionReason,
    draft_status: str | MailSequenceStatus,
) -> MailPendingDraftDispositionRule:
    reason_enum = MailSequenceInterruptionReason(normalize_mail_sequence_interruption_reason(interruption_reason))
    draft_status_value = normalize_mail_sequence_status(draft_status)
    try:
        return MAIL_PENDING_DRAFT_DISPOSITION_RULES[(reason_enum, draft_status_value)]
    except KeyError as exc:
        raise ValueError(
            "no pending-draft disposition rule for "
            f"{reason_enum.value} with draft_status={draft_status_value}"
        ) from exc


def resolve_mail_pending_draft_disposition(
    interruption_reason: str | MailSequenceInterruptionReason,
    draft_status: str | MailSequenceStatus,
    event_type: str | MailSequenceCutoffEventType | None = None,
    scenario: str | MailScenario | None = None,
    suite_step: int | None = None,
) -> dict[str, Any]:
    reason_enum = MailSequenceInterruptionReason(normalize_mail_sequence_interruption_reason(interruption_reason))
    draft_status_value = normalize_mail_sequence_status(draft_status)

    if event_type is not None:
        event_type_value = normalize_mail_sequence_cutoff_event_type(event_type)
        cutoff_rule = MAIL_SEQUENCE_CUTOFF_RULES[reason_enum]
        if cutoff_rule.event_type != event_type_value:
            raise ValueError(
                f"event_type={event_type_value} does not match interruption_reason={reason_enum.value}"
            )

    if draft_status_value in MAIL_SENT_OR_TERMINAL_DRAFT_STATUSES:
        return {
            "interruption_reason": reason_enum.value,
            "draft_status": draft_status_value,
            "disposition_action": MailPendingDraftDispositionAction.KEEP.value,
            "blocks_real_sending": False,
            "removes_body_content": False,
            "preserve_audit_record": True,
            "reason": "sent_or_terminal_records_are_not_pending_unsent_drafts",
        }

    rule = get_mail_pending_draft_disposition_rule(reason_enum, draft_status_value)
    if scenario is not None:
        scenario_value = MailScenario(scenario).value
        if scenario_value not in rule.applies_to_scenarios:
            raise ValueError(
                f"scenario={scenario_value} is not covered by disposition rule {reason_enum.value}"
            )
    if suite_step is not None:
        if suite_step not in ALL_MAIL_SEQUENCE_STEPS:
            raise ValueError(f"unsupported suite_step for pending-draft disposition: {suite_step}")
        if suite_step not in rule.applies_to_steps:
            raise ValueError(
                f"suite_step={suite_step} is not covered by disposition rule {reason_enum.value}"
            )
    return rule.to_dict()


def list_mail_pending_draft_disposition_rules(
    scenario: str | MailScenario | None = None,
    suite_step: int | None = None,
    event_type: str | MailSequenceCutoffEventType | None = None,
    disposition_action: str | MailPendingDraftDispositionAction | None = None,
) -> list[dict[str, Any]]:
    scenario_value = MailScenario(scenario).value if scenario is not None else None
    event_type_value = (
        normalize_mail_sequence_cutoff_event_type(event_type)
        if event_type is not None
        else None
    )
    disposition_action_value = (
        normalize_mail_pending_draft_disposition_action(disposition_action)
        if disposition_action is not None
        else None
    )
    if suite_step is not None and suite_step not in ALL_MAIL_SEQUENCE_STEPS:
        raise ValueError(f"unsupported suite_step for pending-draft disposition: {suite_step}")

    rules = []
    for rule in MAIL_PENDING_DRAFT_DISPOSITION_RULES.values():
        if scenario_value is not None and scenario_value not in rule.applies_to_scenarios:
            continue
        if suite_step is not None and suite_step not in rule.applies_to_steps:
            continue
        if event_type_value is not None and rule.event_type != event_type_value:
            continue
        if disposition_action_value is not None and rule.disposition_action != disposition_action_value:
            continue
        rules.append(rule.to_dict())
    return rules


COMMON_RE_ACTIVATION_FIELDS: dict[str, str] = {
    "scenario": "Fixed value re_activation.",
    "scenario_label": "Human label, fixed as old customer re-activation.",
    "suite_step": "Integer 1-4. Used by generate-draft and sequence state tasks.",
    "step_key": "Stable machine key for strategy lookup and diagnostics.",
    "customer_key": "Desensitized customer or organization key from CRM/mail profile.",
    "contact_email": "Target recipient address, validated later by domain guardrails.",
    "current_seller_name": "Current seller name injected by request or CRM profile.",
    "current_seller_signature": "Seller signature injected by request or CRM profile.",
    "retrieval_filters": "Scenario, step, snippet types, score, review and profile filters.",
    "retrieved_fewshot_id": "Future draft API field for the selected approved snippet.",
    "fewshot_match_score": "Future draft API field for retrieval score diagnostics.",
    "safety_guardrail": "Future draft API field for price, SLA and recipient guardrails.",
    "sequence_status": "One of MailSequenceStatus values; mail-only and never stored in WeCom state.",
    "exit_reason": "Future Task 24/25 interruption or draft lock reason.",
}


COMMON_NEW_BUSINESS_PROMOTION_FIELDS: dict[str, str] = {
    "scenario": "Fixed value new_business_promotion.",
    "scenario_label": "Human label, fixed as new business promotion.",
    "suite_step": "Integer 1-4. Used by generate-draft and sequence state tasks.",
    "step_key": "Stable machine key for strategy lookup and diagnostics.",
    "customer_key": "Desensitized customer or organization key from CRM/mail profile.",
    "contact_email": "Target recipient address, validated later by domain guardrails.",
    "current_seller_name": "Current seller name injected by request or CRM profile.",
    "current_seller_signature": "Seller signature injected by request or CRM profile.",
    "target_product_line": "The promoted product line or service bundle selected by CRM or sales input.",
    "known_customer_profile": "Desensitized profile signals such as industry, country, tier, and prior service usage.",
    "retrieval_filters": "Scenario, step, snippet types, score, review and profile filters.",
    "retrieved_fewshot_id": "Future draft API field for the selected approved snippet.",
    "fewshot_match_score": "Future draft API field for retrieval score diagnostics.",
    "safety_guardrail": "Future draft API field for price, SLA and recipient guardrails.",
    "sequence_status": "One of MailSequenceStatus values; mail-only and never stored in WeCom state.",
    "exit_reason": "Future Task 24/25 interruption or draft lock reason.",
}


COMMON_NEW_CONTACT_INTRO_FIELDS: dict[str, str] = {
    "scenario": "Fixed value new_contact_intro.",
    "scenario_label": "Human label, fixed as new contact intro.",
    "suite_step": "Integer 1-4. Used by generate-draft and sequence state tasks.",
    "step_key": "Stable machine key for strategy lookup and diagnostics.",
    "customer_key": "Desensitized customer or organization key from CRM/mail profile.",
    "contact_email": "Target recipient address, validated later by domain guardrails.",
    "current_seller_name": "Current seller name injected by request or CRM profile.",
    "current_seller_signature": "Seller signature injected by request or CRM profile.",
    "handover_context": "CRM or sales-provided reason for the new seller or contact introduction.",
    "known_previous_contact": "Optional desensitized previous contact or department signal used only when approved.",
    "contact_role_hint": "Recipient role, department, or responsibility signal from CRM or manual input.",
    "retrieval_filters": "Scenario, step, snippet types, score, review and profile filters.",
    "retrieved_fewshot_id": "Future draft API field for the selected approved snippet.",
    "fewshot_match_score": "Future draft API field for retrieval score diagnostics.",
    "safety_guardrail": "Future draft API field for price, SLA and recipient guardrails.",
    "sequence_status": "One of MailSequenceStatus values; mail-only and never stored in WeCom state.",
    "exit_reason": "Future Task 24/25 interruption or draft lock reason.",
}


RE_ACTIVATION_SEQUENCE = MailSequenceStrategy(
    scenario=MailScenario.RE_ACTIVATION.value,
    scenario_label="old_customer_re_activation",
    objective=(
        "通过轻量级问候、提供相关证明、建立流程信心以及提供经过人工审核的商业下一步，"
        "分四步重新建立与过往客户的对话：关系重新连接、相关案例证明、流程信心确认，以及商业跟进。"
    ),
    applicable_trigger=(
        "CRM 或销售复核确认该客户过往曾有合作、询价、打样、交付或深入业务交流，"
        "且近期没有活跃的业务往来记录。"
    ),
    isolation_boundary=(
        "仅邮件侧策略元数据。不向企微会话表写入状态，不需要企微回调，默认关闭真实发送。"
    ),
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.RE_ACTIVATION.value,
            scenario_label="old_customer_re_activation",
            suite_step=1,
            step_key="re_activation_step_1_reconnect",
            objective=(
                "通过轻量问候重新建立联系，确认过往合作，在不推销的情况下邀请客户简单更新近况。"
            ),
            recommended_snippet_types=(MailSnippetType.GREETINGS.value,),
            subject_template_hints=(
                "好久不见 想跟您聊聊最近的项目动向",
                "关于我们过往合作项目的后续跟进",
                "希望您最近一切顺利，顺便向您问个好",
            ),
            cta_style=(
                "低压力问候，邀请客户简单更新近况，不强推业务。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 re_activation。",
                "sequence_step_hint 建议为 1 或空；优先精确步骤匹配。",
                "snippet_type 必须为 greetings。",
                "retrieval_enabled, publishable, allowed_for_generation 和 usable_for_reply 必须均为 true。",
                "useful_score 必须满足 MAIL_FEWSHOT_MIN_USEFUL_SCORE（默认 0.60）。",
                "当 source_snapshot 中存在 desensitized_status 时必须为 desensitized。",
                "当 source_snapshot 中存在 review_status 时必须为 approved。",
                "对于步骤 1，除非请求侧 CRM 画像明确提供，否则不需要行业或产品线限制。",
            ),
            forbidden_boundaries=(
                "不能提及价格、折扣、账期、加急交期承诺或具体 SLA。",
                "不要使用强推销的语气或催促下单的措辞。",
                "不能出现历史邮件中的真实客户名、项目号、文件名称、电话、URL 或内部 ID。",
                "除非 CRM 或用户请求明确给出，否则不要假设客户目前有特定需求。",
            ),
            exit_conditions=(
                "客户通过邮件进行了回复。",
                "CRM 阶段变更为赢单、进行中商机、投诉、勿扰或销售手动跟进。",
                "销售手动封印（手动强中断）。",
                "收件人或域名未通过安全防泄密校验。",
            ),
            data_structure_fields={
                **COMMON_RE_ACTIVATION_FIELDS,
                "subject_hint": "Step 1 subject should read as a personal check-in, not a campaign.",
                "body_intent": "reconnect_greeting",
                "cta_type": "soft_reply_invitation",
                "required_snippet_types": "greetings only.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.RE_ACTIVATION.value,
            scenario_label="old_customer_re_activation",
            suite_step=2,
            step_key="re_activation_step_2_relevant_proof",
            objective=(
                "分享高度匹配且已脱敏的同行业成功服务案例，唤醒客户对我们专业度的记忆。"
            ),
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value,),
            subject_template_hints=(
                "为您分享一个我们近期完成的同行业案例",
                "关于我们近期在您所在行业完成的项目参考",
                "一个可供您团队参考的近期本地化案例",
            ),
            cta_style=(
                "分享一个同行业的合作案例，引出可类比的项目机会。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 re_activation。",
                "sequence_step_hint 建议为 2 或空；优先精确步骤匹配。",
                "snippet_type 必须为 example。",
                "当 CRM/请求行业已知时，行业字段应当强匹配。",
                "当 CRM/请求产品线已知时，产品线字段应当强匹配。",
                "国家字段可用作软相关性过滤，但不能代替域名安全校验。",
                "在用尽精确行业/产品匹配前，不要使用未识别行业的案例。",
                "所有 Task 17 Few-Shot 准入条件依然适用。",
            ),
            forbidden_boundaries=(
                "如果已知客户行业画像，不要提供跨行业的案例证明。",
                "绝不能出现真实客户名、可识别的项目细节、未经核准的度量指标或投资回报率承诺。",
                "不要暗示收件人认可该案例，或承诺其必然能达到完全相同的效果。",
                "不能提及具体报价、折扣、账期或交付时间承诺。",
            ),
            exit_conditions=(
                "客户回复邮件、索取案例详情或发送文件。",
                "CRM 画像显示行业不匹配或未获得客户分享许可。",
                "客户已在 CRM 中被分配到人工销售跟进阶段。",
                "销售手动封印了该邮件序列。",
            ),
            data_structure_fields={
                **COMMON_RE_ACTIVATION_FIELDS,
                "subject_hint": "Step 2 subject should signal relevant proof without exposing a client.",
                "body_intent": "peer_case_reference",
                "cta_type": "ask_if_reference_is_relevant",
                "required_snippet_types": "example only.",
                "profile_filter_priority": "industry, product_line, country, customer_tier.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.RE_ACTIVATION.value,
            scenario_label="old_customer_re_activation",
            suite_step=3,
            step_key="re_activation_step_3_process_confidence",
            objective=(
                "通过介绍当前的服务流程、质量把控机制、必要输入和合理的工期边界，建立客户的流程信心并降低顾虑。"
            ),
            recommended_snippet_types=(MailSnippetType.PROCESS.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "向您简要介绍我们目前采用的多流程质量把控机制",
                "为您整理的翻译与排版交付流程规范说明",
                "关于我们如何保障复杂项目按时高质量交付的几点说明",
            ),
            cta_style=(
                "展示标准服务流程与工期 SLA，给客户安全感。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 re_activation。",
                "sequence_step_hint 建议为 3 或空；优先精确步骤匹配。",
                "snippet_type 应当为 process 或 constraint。",
                "当已知当前服务兴趣时，产品线必须匹配。",
                "行业是加权字段；对于医疗医药或法律服务，优先匹配相同行业。",
                "constraint 类型的切片在检索前必须已审核且 safe_for_fewshot 标记为 true。",
                "交付工期必须来自后续的物理 SLA 规则，而非历史切片中的自由文本。",
            ),
            forbidden_boundaries=(
                "不能使用历史邮件中非标的加急承诺或固定交付日期。",
                "不要暴露公司内部人员配备、底线成本、供应商选择、毛利及未公开的质控细节。",
                "不要泄露任何带有敏感客户信息的文件名或内容。",
                "不要使用任何试图绕过后续 SLA 校准或人工审核的措辞。",
            ),
            exit_conditions=(
                "客户发送待评估文件、索取流程清单或开启具体的项目讨论。",
                "CRM 中出现活跃商机或被标记为销售手动跟进。",
                "后续 SLA 拦截器触发并将该草稿锁定到人工审批队列。",
                "销售手动封印了该序列。",
            ),
            data_structure_fields={
                **COMMON_RE_ACTIVATION_FIELDS,
                "subject_hint": "Step 3 subject should emphasize process confidence.",
                "body_intent": "process_and_quality_reassurance",
                "cta_type": "request_file_review_or_checklist",
                "required_snippet_types": "process plus constraint.",
                "sla_source": "future physical SLA guardrail, not historical snippet text.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.RE_ACTIVATION.value,
            scenario_label="old_customer_re_activation",
            suite_step=4,
            step_key="re_activation_step_4_reviewed_commercial_next_step",
            objective=(
                "在遵循价格和条款安全门的前提下，向客户提供经过审核的轻量商业下一步动作，如样稿评估、试用或报价沟通。"
            ),
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "针对老客户回归我们为您准备的合作优选路径",
                "近期是否有我们可协助的试译或样稿评估安排？",
                "关于我们合作项目可行性方案及报价的初步探讨",
            ),
            cta_style=(
                "提供小批量试用样稿邀约，降低客户决策门槛。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 re_activation。",
                "sequence_step_hint 建议为 4 或空；优先精确步骤匹配。",
                "snippet_type 应当为 quotation 或 constraint。",
                "在采用任何商业化措辞前，产品线和客户级别应当匹配。",
                "对于高欠款风险（high, prepaid_required, blocked）或未识别状态，强制采用保守表达或进行人工复核。",
                "quotation 类型的切片仅提供句式结构；具体金额与折扣由后续的物理字段填充。",
                "检索前所有与安全相关的 source_snapshot 字段必须均已确认通过。",
            ),
            forbidden_boundaries=(
                "绝对不能在邮件正文中由大模型自由生成底线价格、具体折扣或特权账期天数。",
                "除非有已核准的配置或人工显式设定，否则不要在邮件中承诺免费试用、试译或特殊优惠额度。",
                "不要使用强迫性促销语言、紧迫性宣传或虚假的到期限制措辞。",
                "在通过草稿人工审核及三重物理安全门前，严禁启用真实发送。",
            ),
            exit_conditions=(
                "客户回复、接受、明确拒绝或退信/退阅。",
                "CRM 中出现阶段变化、销售手动封印，或序列被安全拦截器中断。",
                "该待发草稿被物理销毁或锁定（符合 Task 25 规则）。",
                "任意价格、SLA、欠款风险或域名黑名单校验未通过。",
            ),
            data_structure_fields={
                **COMMON_RE_ACTIVATION_FIELDS,
                "subject_hint": "Step 4 subject may name a practical next step but not an unapproved discount.",
                "body_intent": "reviewed_commercial_followup",
                "cta_type": "explicit_yes_or_file_request",
                "required_snippet_types": "quotation plus constraint.",
                "commercial_value_source": "future pricing/config placeholders and manual review.",
            },
        ),
    ),
)


NEW_BUSINESS_PROMOTION_SEQUENCE = MailSequenceStrategy(
    scenario=MailScenario.NEW_BUSINESS_PROMOTION.value,
    scenario_label="new_business_promotion",
    objective=(
        "通过轻量级价值引介、同业匹配证明、服务方案流程说明以及最后的试用/报价邀约，"
        "分四步向客户推广相关的新业务线或新能力，以发掘增量业务机会。"
    ),
    applicable_trigger=(
        "CRM、销售标记或人工复核表明该客户存在相关业务需求，"
        "且尚未采购过我们拟推广的新业务线或服务组合。"
    ),
    isolation_boundary=(
        "仅邮件侧策略元数据。不向企微会话表写入状态，不需要企微回调，默认关闭真实发送。"
    ),
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_BUSINESS_PROMOTION.value,
            scenario_label="new_business_promotion",
            suite_step=1,
            step_key="new_business_promotion_step_1_value_intro",
            objective=(
                "针对客户行业画像对所推广的新业务进行轻量引介，并将其与客户可能存在的痛点相结合，不急于报价或催促。"
            ),
            recommended_snippet_types=(MailSnippetType.GREETINGS.value, MailSnippetType.EXAMPLE.value),
            subject_template_hints=(
                "向您介绍我们近期新增的本地化与多语种服务能力",
                "分享一个或许契合贵司团队近期项目需求的新服务选项",
                "关于我们新增服务组合对贵司项目效率提升的简明引介",
            ),
            cta_style=(
                "低门槛价值提示：用一两句话讲清新业务能为对方解决什么具体问题。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_business_promotion。",
                "sequence_step_hint 建议为 1 或空；优先精确步骤匹配。",
                "snippet_type 应当为 greetings 或 example。",
                "拟推广的产品线应当匹配所推广的新服务（当已知时）。",
                "当存在行业和国家画像时，应当作为软相关性过滤条件。",
                "retrieval_enabled, publishable, allowed_for_generation 和 usable_for_reply 必须均为 true。",
                "useful_score 必须满足 MAIL_FEWSHOT_MIN_USEFUL_SCORE（默认 0.60）。",
                "当 source_snapshot 中存在 desensitized_status 时必须为 desensitized。",
                "当 source_snapshot 中存在 review_status 时必须为 approved。",
            ),
            forbidden_boundaries=(
                "不要声称客户已经请求、批准或承诺了该新服务。",
                "不能提及具体报价、折扣、账期天数、固定交期或紧急时限要求。",
                "在没有明确的客户画像或联系人来源时，不要使用冰冷死板的群发推广措辞。",
                "绝对不能出现历史邮件中的真实客户名、项目号、文件名称、电话、URL 或内部 ID。",
            ),
            exit_conditions=(
                "客户进行了回复、索取详情或明确拒绝该业务推广。",
                "CRM 中被标记为勿扰、投诉、活跃商机，或转为销售手动跟进。",
                "客户画像缺失或与所推广的服务不匹配。",
                "收件人或域名未通过安全防泄密校验。",
            ),
            data_structure_fields={
                **COMMON_NEW_BUSINESS_PROMOTION_FIELDS,
                "subject_hint": "Step 1 subject should signal a relevant service update, not a campaign blast.",
                "body_intent": "new_service_value_intro",
                "cta_type": "soft_interest_check",
                "required_snippet_types": "greetings plus optional example.",
                "promotion_fit_source": "CRM, sales tag, or manual request; not inferred from model text alone.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_BUSINESS_PROMOTION.value,
            scenario_label="new_business_promotion",
            suite_step=2,
            step_key="new_business_promotion_step_2_industry_proof",
            objective=(
                "使用高度匹配且已脱敏的同行业或同产品线案例，向收件人展示该新业务的实用价值与相关性。"
            ),
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value,),
            subject_template_hints=(
                "为您分享一个我们近期在相同行业完成的服务案例",
                "同行业团队如何利用我们这项新业务提升项目成效",
                "一个可供贵司团队参考的同类产品线近期成功案例",
            ),
            cta_style=(
                "引用一两个行业案例，强化新业务的可靠性。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_business_promotion。",
                "sequence_step_hint 建议为 2 或空；优先精确步骤匹配。",
                "snippet_type 必须为 example。",
                "当 CRM/请求行业已知时，行业字段应当强匹配。",
                "产品线必须匹配拟推广的新产品线（当已知时）。",
                "客户级别可用于调整语气深度，但不能用于伪造未经证实的承诺。",
                "在精确匹配用尽前，不要使用行业或产品线不相关的案例。",
                "所有 Task 17 Few-Shot 准入条件依然适用。",
            ),
            forbidden_boundaries=(
                "不要提供行业或产品线明显不匹配的案例证明。",
                "绝对不能出现真实客户名、可识别的项目细节、未经核准的度量指标或投资回报率承诺。",
                "不要暗示收件人认可该案例，或承诺其必然能达到完全相同的效果。",
                "不能提及具体报价、折扣、账期或交付时间承诺。",
            ),
            exit_conditions=(
                "客户回复、索取案例详情或发送试用样本文件。",
                "CRM 画像显示行业或拟推广产品线不匹配，或未获得客户分享许可。",
                "客户已在 CRM 中被分配到人工销售跟进阶段。",
                "销售手动封印了该邮件序列。",
            ),
            data_structure_fields={
                **COMMON_NEW_BUSINESS_PROMOTION_FIELDS,
                "subject_hint": "Step 2 subject should name relevance without exposing a client.",
                "body_intent": "industry_or_product_line_proof",
                "cta_type": "ask_if_case_matches_need",
                "required_snippet_types": "example only.",
                "profile_filter_priority": "product_line, industry, country, customer_tier.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_BUSINESS_PROMOTION.value,
            scenario_label="new_business_promotion",
            suite_step=3,
            step_key="new_business_promotion_step_3_service_package_process",
            objective=(
                "向客户阐明该服务方案的流程、协作细节、必要输入及合理限制，以便客户对小批量测试进行评估。"
            ),
            recommended_snippet_types=(MailSnippetType.PROCESS.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "关于这项新服务包在贵司项目中的具体协作流程",
                "一个便于贵司快速开启小批量试用测试的简明工作流",
                "我们在开展该项新服务前所需的分析及准备工作说明",
            ),
            cta_style=(
                "邀请客户试用方案或小批量测试，作为决策前的低成本验证。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_business_promotion。",
                "sequence_step_hint 建议为 3 或空；优先精确步骤匹配。",
                "snippet_type 应当为 process 或 constraint。",
                "产品线必须匹配拟推广的新产品线（当已知时）。",
                "行业是加权字段；对于医疗医药或法律服务，优先匹配相同行业。",
                "constraint 类型的切片在检索前必须已审核且 safe_for_fewshot 标记为 true。",
                "交付工期必须来自后续的物理 SLA 规则，而非历史切片中的自由文本。",
            ),
            forbidden_boundaries=(
                "不能使用历史邮件中非标的加急承诺或固定交付日期。",
                "不要暴露公司内部人员配备、底线成本、供应商选择、毛利及未公开的质控细节。",
                "不要泄露任何带有敏感客户信息的文件名或内容。",
                "不要使用任何试图绕过后续 SLA 校准、范围确认或人工审核的措辞。",
            ),
            exit_conditions=(
                "客户索取流程清单、发送试用样本文件或开启具体的合作测试讨论。",
                "CRM 中出现活跃商机或被标记为销售手动跟进。",
                "后续 SLA 拦截器触发并将该草稿锁定到人工审批队列。",
                "销售手动封印了该序列。",
            ),
            data_structure_fields={
                **COMMON_NEW_BUSINESS_PROMOTION_FIELDS,
                "subject_hint": "Step 3 subject should emphasize a clear service-package workflow.",
                "body_intent": "service_package_process_and_constraints",
                "cta_type": "request_sample_review_or_checklist",
                "required_snippet_types": "process plus constraint.",
                "sla_source": "future physical SLA guardrail, not historical snippet text.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_BUSINESS_PROMOTION.value,
            scenario_label="new_business_promotion",
            suite_step=4,
            step_key="new_business_promotion_step_4_reviewed_trial_or_quote",
            objective=(
                "在价格、条款和发件安全门审查的前提下，为所推广的新业务提供试用、试译或报价机会。"
            ),
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "是否可以为您安排一个小型试用以评估这项新服务？",
                "针对贵司近期项目的方案评估及初步报价说明",
                "确认是否可以为贵司定制一份新服务试用方案与预算建议",
            ),
            cta_style=(
                "给出报价邀约，附带工期、账期、折扣等结构化商业条款（由后端占位符替换）。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_business_promotion。",
                "sequence_step_hint 建议为 4 或空；优先精确步骤匹配。",
                "snippet_type 应当为 quotation 或 constraint。",
                "在采用任何商业化措辞前，产品线和客户级别应当匹配。",
                "对于高欠款风险（high, prepaid_required, blocked）或未识别状态，强制采用保守表达或进行人工复核。",
                "quotation 类型的切片仅提供句式结构；具体金额与折扣由后续的物理字段填充。",
                "检索前所有与安全相关的 source_snapshot 字段必须均已确认通过。",
            ),
            forbidden_boundaries=(
                "绝对不能在邮件正文中由大模型自由生成底线价格、具体折扣或特权账期天数。",
                "除非有已核准的配置或人工显式设定，否则不要在邮件中承诺免费试用、试译、打包优惠或特权。",
                "不要使用强迫性促销语言、紧迫性宣传或虚假的到期限制措辞。",
                "在通过草稿人工审核及三重物理安全门前，严禁启用真实发送。",
            ),
            exit_conditions=(
                "客户回复、接受、明确拒绝或退信/退阅。",
                "CRM 中出现阶段变化、销售手动封印，或序列被安全拦截器中断。",
                "该待发草稿被物理销毁或锁定（符合 Task 25 规则）。",
                "任意价格、SLA、欠款风险或域名黑名单校验未通过。",
            ),
            data_structure_fields={
                **COMMON_NEW_BUSINESS_PROMOTION_FIELDS,
                "subject_hint": "Step 4 subject may name a practical trial or quote next step but not an unapproved offer.",
                "body_intent": "reviewed_trial_or_quote_followup",
                "cta_type": "explicit_yes_file_or_quote_request",
                "required_snippet_types": "quotation plus constraint.",
                "commercial_value_source": "future pricing/config placeholders and manual review.",
            },
        ),
    ),
)


NEW_CONTACT_INTRO_SEQUENCE = MailSequenceStrategy(
    scenario=MailScenario.NEW_CONTACT_INTRO.value,
    scenario_label="new_contact_intro",
    objective=(
        "通过透明的交接介绍、过往合作背景确认、角色相关的服务路径阐述以及最后的务实下一步，"
        "分四步在新指派的销售人员与客户新负责人之间建立信任，为后续的顺畅沟通打下基础。"
    ),
    applicable_trigger=(
        "CRM、销售交接或人工复核确认该账户存在新对接人、新部门负责人，"
        "或新指派的销售负责关系，需要在正式跟进业务前进行一次正式的邮件引介。"
    ),
    isolation_boundary=(
        "仅邮件侧策略元数据。不向企微会话表写入状态，不需要企微回调，默认关闭真实发送。"
    ),
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_CONTACT_INTRO.value,
            scenario_label="new_contact_intro",
            suite_step=1,
            step_key="new_contact_intro_step_1_handover_intro",
            objective=(
                "介绍当前的销售对接人，说明交接背景或联系原因，使邮件显得认真负责而非推销性质。"
            ),
            recommended_snippet_types=(MailSnippetType.GREETINGS.value,),
            subject_template_hints=(
                "您好！我是您本次项目合作的新对接人",
                "关于贵司项目对接人变更及未来协作的沟通",
                "SpeedAsia 翻译与本地化对接人交接说明",
            ),
            cta_style=(
                "自我介绍新接手身份，询问对方是否还有其他同事需要抄送。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_contact_intro。",
                "sequence_step_hint 建议为 1 或空；优先精确步骤匹配。",
                "snippet_type 必须为 greetings。",
                "交接背景应当来自 CRM、销售交接或人工请求，而非模型凭空臆断。",
                "retrieval_enabled, publishable, allowed_for_generation 和 usable_for_reply 必须均为 true。",
                "useful_score 必须满足 MAIL_FEWSHOT_MIN_USEFUL_SCORE（默认 0.60）。",
                "当 source_snapshot 中存在 desensitized_status 时必须为 desensitized。",
                "当 source_snapshot 中存在 review_status 时必须为 approved。",
            ),
            forbidden_boundaries=(
                "不要虚构个人私交、过往聊天记录或客户已批准对接的假象。",
                "不要催促客户立即提供项目、下单或发送文件。",
                "不能在未经核准前透露前任对接人的真实姓名、部门、私人电话或内部交接备注。",
                "不能提及具体价格、折扣、账期或固定交付承诺。",
            ),
            exit_conditions=(
                "收件人回复了正确的对接负责人、明确拒绝或提出退阅要求。",
                "CRM 中表明收件人已离职或联系邮箱失效。",
                "销售手动封印了该序列，或标记为人工手动跟进。",
                "收件人或域名未通过安全防泄密校验。",
            ),
            data_structure_fields={
                **COMMON_NEW_CONTACT_INTRO_FIELDS,
                "subject_hint": "Step 1 subject should read as a direct introduction, not a marketing campaign.",
                "body_intent": "handover_intro_and_permission_check",
                "cta_type": "confirm_right_contact_or_referral",
                "required_snippet_types": "greetings only.",
                "handover_source": "CRM owner change, sales handover, or manual request.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_CONTACT_INTRO.value,
            scenario_label="new_contact_intro",
            suite_step=2,
            step_key="new_contact_intro_step_2_prior_context",
            objective=(
                "提供简明且脱敏的过往合作或部门对接背景，让新联系人明白此次引介的必要性与相关性。"
            ),
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value, MailSnippetType.PROCESS.value),
            subject_template_hints=(
                "向您同步我们过往为贵司团队提供服务的一些背景",
                "关于我们此前项目合作的历史概况与交付总结",
                "为您整理的过往本地化项目合作参考信息",
            ),
            cta_style=(
                "请客户分享当前在进行的项目背景或近期需要协助的点。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_contact_intro。",
                "sequence_step_hint 建议为 2 或空；优先精确步骤匹配。",
                "snippet_type 应当为 example 或 process。",
                "应当使用已知部门、联系人角色、行业和产品线画像以过滤掉无关的历史信息。",
                "绝不能在历史切片中使用真实人名或可识别的项目引用。",
                "所有 Task 17 Few-Shot 准入条件依然适用。",
            ),
            forbidden_boundaries=(
                "不要泄露前任对接人的私人信息、直呼电话、邮箱、离职/退休原因或任何内部负面备注。",
                "绝对不能泄露任何客户敏感的项目名、PO单号、文件名称或具体的合同条款明细。",
                "不要暗示新收件人已经同意承接这些工作。",
                "不要发表关于业务量、客户评级、投资回报率或战略重要性的未经证实的断言。",
            ),
            exit_conditions=(
                "收件人确认其职责范围、推荐了其他对接人，或指出背景信息不相关。",
                "CRM 画像表明客户部门或联系职责不匹配。",
                "客户已被分配到 CRM 的销售手动跟进状态。",
                "销售手动封印了该序列。",
            ),
            data_structure_fields={
                **COMMON_NEW_CONTACT_INTRO_FIELDS,
                "subject_hint": "Step 2 subject should signal context without exposing sensitive history.",
                "body_intent": "prior_context_and_role_fit_check",
                "cta_type": "confirm_responsibility_or_referral",
                "required_snippet_types": "example plus optional process.",
                "profile_filter_priority": "contact_role_hint, department, product_line, industry, country.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_CONTACT_INTRO.value,
            scenario_label="new_contact_intro",
            suite_step=3,
            step_key="new_contact_intro_step_3_service_path",
            objective=(
                "说明未来的项目如何提交、审核和评估，为新联系人提供一种低摩擦的顺畅协作路径。"
            ),
            recommended_snippet_types=(MailSnippetType.PROCESS.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "为您说明未来项目协作中的文件提交与交付路径",
                "如果后续有项目需求，这是推荐的对接与处理流程",
                "关于我们协作规范及沟通时限要求的简要说明",
            ),
            cta_style=(
                "介绍标准协作路径（接稿、审稿、交付、复盘），给客户专业感。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_contact_intro。",
                "sequence_step_hint 建议为 3 或空；优先精确步骤匹配。",
                "snippet_type 应当为 process 或 constraint。",
                "产品线应当匹配可能的服务兴趣领域（当已知时）。",
                "收件人角色画像应当塑造工作流措辞，但不能创设未经确认的职责。",
                "constraint 类型的切片在检索前必须已审核且 safe_for_fewshot 标记为 true。",
                "交付工期必须来自后续的物理 SLA 规则，而非历史切片中的自由文本。",
            ),
            forbidden_boundaries=(
                "不能使用历史邮件中非标的加急承诺或固定交付日期。",
                "不要暴露公司内部人员配备、底线成本、供应商选择、毛利及未公开的质控细节。",
                "不要泄露任何带有敏感客户信息的文件名、文档内容或过往商业条款。",
                "不要使用任何试图绕过后续 SLA 校准、范围确认或人工审核的措辞。",
            ),
            exit_conditions=(
                "收件人索取流程清单、发送项目文件或确认了首选的对接协作路径。",
                "CRM 中出现活跃商机或被标记为销售手动跟进。",
                "后续 SLA 拦截器触发并将该草稿锁定到人工审批队列。",
                "销售手动封印了该序列。",
            ),
            data_structure_fields={
                **COMMON_NEW_CONTACT_INTRO_FIELDS,
                "subject_hint": "Step 3 subject should emphasize an easy coordination path.",
                "body_intent": "service_path_and_process_reassurance",
                "cta_type": "request_workflow_confirmation_or_file_review",
                "required_snippet_types": "process plus constraint.",
                "sla_source": "future physical SLA guardrail, not historical snippet text.",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_CONTACT_INTRO.value,
            scenario_label="new_contact_intro",
            suite_step=4,
            step_key="new_contact_intro_step_4_reviewed_next_step",
            objective=(
                "在遵循商业安全门的前提下，提供经过审核的务实下一步，如文件评估、样稿测试或报价沟通。"
            ),
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "确认是否可以为贵司近期的项目提供试用或报价参考？",
                "如果近期有项目机会，我们为您准备的协作测试建议",
                "关于我们首次对接合作的实操流程与预算建议",
            ),
            cta_style=(
                "确认下一步协作切入点（试稿、会议、小项目），形成具体动作。"
            ),
            retrieval_filter_requirements=(
                "scenario 必须为 new_contact_intro。",
                "sequence_step_hint 建议为 4 或空；优先精确步骤匹配。",
                "snippet_type 应当为 quotation 或 constraint。",
                "在采用任何商业化措辞前，联系人角色、产品线和客户级别应当匹配。",
                "对于高欠款风险（high, prepaid_required, blocked）或未识别状态，强制采用保守表达或进行人工复核。",
                "quotation 类型的切片仅提供句式结构；具体金额与折扣由后续的物理字段填充。",
                "检索前所有与安全相关的 source_snapshot 字段必须均已确认通过。",
            ),
            forbidden_boundaries=(
                "绝对不能在邮件正文中由大模型自由生成底线价格、具体折扣或特权账期天数。",
                "除非有已核准的配置或人工显式设定，否则不要在邮件中承诺免费样稿、特殊待遇或过往特权限制。",
                "不要使用强迫性促销语言、紧迫性宣传或虚假的到期限制措辞。",
                "在通过草稿人工审核及三重物理安全门前，严禁启用真实发送。",
            ),
            exit_conditions=(
                "收件人回复、推荐了其他负责人、接受、明确拒绝或退信/退阅。",
                "CRM 中出现阶段变化、销售手动封印，或序列被安全拦截器中断。",
                "该待发草稿被物理销毁或锁定（符合 Task 25 规则）。",
                "任意价格、SLA、欠款风险或域名白名单校验未通过。",
            ),
            data_structure_fields={
                **COMMON_NEW_CONTACT_INTRO_FIELDS,
                "subject_hint": "Step 4 subject may name a practical next step but not an unapproved commercial offer.",
                "body_intent": "reviewed_intro_next_step",
                "cta_type": "explicit_yes_file_or_referral_request",
                "required_snippet_types": "quotation plus constraint.",
                "commercial_value_source": "future pricing/config placeholders and manual review.",
            },
        ),
    ),
)


PRINT_QUOTE_FOLLOWUP_SEQUENCE = MailSequenceStrategy(
    scenario=MailScenario.PRINT_QUOTE_FOLLOWUP.value,
    scenario_label="print_quote_followup",
    objective=(
        "印刷报价发出后的四步跟进：确认收件→样稿/工艺跟进→异议处理与价值强化→促成下单或转介绍收口。"
        "使用人工填写的 AI 指令模板生成正文，不依赖案例库少样本检索。"
    ),
    applicable_trigger="销售已向客户发送印刷报价，客户尚未回复或未明确表态。",
    isolation_boundary="仅邮件侧独立模板，不绑定具体客户案例，内容由 ai_instruction_script 模板驱动。",
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.PRINT_QUOTE_FOLLOWUP.value,
            scenario_label="print_quote_followup",
            suite_step=1,
            step_key="print_quote_followup_step_1_delivery_confirm",
            objective="确认报价已送达，邀请客户反馈疑问或安排进一步沟通。",
            recommended_snippet_types=(MailSnippetType.GREETINGS.value,),
            subject_template_hints=(
                "关于我们刚发出的印刷报价，请您确认收到",
                "印刷报价确认——期待您的反馈",
                "您好，请问收到我们的报价了吗",
            ),
            cta_style="轻量确认，邀请客户告知是否收到并提出疑问。",
            retrieval_filter_requirements=(
                "scenario 为 print_quote_followup，优先使用 ai_instruction_script 模板内容。",
                "不强制要求 snippet_type 匹配，模板驱动优先。",
            ),
            forbidden_boundaries=(
                "不能擅自更改报价中的价格、数量或交期。",
                "不能施压催单，保持专业礼貌语气。",
            ),
            exit_conditions=(
                "客户回复确认或提出具体问题。",
                "销售手动跟进或封印。",
            ),
            data_structure_fields={
                "body_intent": "delivery_confirm",
                "cta_type": "soft_reply_invitation",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.PRINT_QUOTE_FOLLOWUP.value,
            scenario_label="print_quote_followup",
            suite_step=2,
            step_key="print_quote_followup_step_2_sample_process",
            objective="跟进样稿或工艺方案，提供额外参考资料，推进客户决策。",
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value,),
            subject_template_hints=(
                "关于印刷方案的工艺细节——补充说明",
                "样稿跟进：提供更多参考供您决策",
                "附上工艺说明，期待您的进一步反馈",
            ),
            cta_style="提供增值信息，推动客户进入下一步决策。",
            retrieval_filter_requirements=(
                "scenario 为 print_quote_followup，优先使用 ai_instruction_script 模板内容。",
            ),
            forbidden_boundaries=(
                "不能主动降价或承诺未经确认的 SLA。",
                "不能虚构样品或工艺参数。",
            ),
            exit_conditions=(
                "客户回复或进入打样/下单流程。",
                "销售手动跟进或封印。",
            ),
            data_structure_fields={
                "body_intent": "sample_process_followup",
                "cta_type": "info_share_and_next_step",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.PRINT_QUOTE_FOLLOWUP.value,
            scenario_label="print_quote_followup",
            suite_step=3,
            step_key="print_quote_followup_step_3_objection_value",
            objective="主动处理可能的价格或交期异议，强化整体服务价值。",
            recommended_snippet_types=(MailSnippetType.CONSTRAINT.value, MailSnippetType.EXAMPLE.value),
            subject_template_hints=(
                "关于报价中您可能关注的问题——我们的说明",
                "价值再确认：为什么选择我们的印刷方案",
                "解答疑问，期待推进合作",
            ),
            cta_style="主动化解顾虑，重申价值，邀请客户告知障碍点。",
            retrieval_filter_requirements=(
                "scenario 为 print_quote_followup，优先使用 ai_instruction_script 模板内容。",
            ),
            forbidden_boundaries=(
                "不能擅自承诺额外折扣或超出报价范围的条款。",
                "不能贬低竞争对手。",
            ),
            exit_conditions=(
                "客户提出具体异议或表示有意推进。",
                "销售手动跟进或封印。",
            ),
            data_structure_fields={
                "body_intent": "objection_handling_value_reinforcement",
                "cta_type": "objection_resolution_invitation",
            },
        ),
        MailSequenceStepStrategy(
            scenario=MailScenario.PRINT_QUOTE_FOLLOWUP.value,
            scenario_label="print_quote_followup",
            suite_step=4,
            step_key="print_quote_followup_step_4_close_or_referral",
            objective="促成下单决策或请求转介绍，礼貌收口本轮跟进序列。",
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "期待您的最终决定——随时为您服务",
                "关于合作的最后一次跟进",
                "如果时机不合适，欢迎推荐有需要的同事或伙伴",
            ),
            cta_style="温和催单或请求转介绍，礼貌结束序列。",
            retrieval_filter_requirements=(
                "scenario 为 print_quote_followup，优先使用 ai_instruction_script 模板内容。",
            ),
            forbidden_boundaries=(
                "不能施加过度压力或发出最后通牒语气。",
                "不能承诺报价之外的任何条款。",
            ),
            exit_conditions=(
                "客户确认下单、明确拒绝或被销售手动封印。",
                "本步骤为序列终止步骤，之后不再自动生成草稿。",
            ),
            data_structure_fields={
                "body_intent": "close_or_referral",
                "cta_type": "close_or_referral_request",
            },
        ),
    ),
)


# 新增套装场景只需在这里加一行，其余函数自动覆盖
_STRATEGY_REGISTRY: dict[str, MailSequenceStrategy] = {
    MailScenario.RE_ACTIVATION.value: RE_ACTIVATION_SEQUENCE,
    MailScenario.NEW_BUSINESS_PROMOTION.value: NEW_BUSINESS_PROMOTION_SEQUENCE,
    MailScenario.NEW_CONTACT_INTRO.value: NEW_CONTACT_INTRO_SEQUENCE,
    MailScenario.PRINT_QUOTE_FOLLOWUP.value: PRINT_QUOTE_FOLLOWUP_SEQUENCE,
}


def get_re_activation_sequence() -> MailSequenceStrategy:
    return RE_ACTIVATION_SEQUENCE


def get_new_business_promotion_sequence() -> MailSequenceStrategy:
    return NEW_BUSINESS_PROMOTION_SEQUENCE


def get_new_contact_intro_sequence() -> MailSequenceStrategy:
    return NEW_CONTACT_INTRO_SEQUENCE


def get_mail_sequence_strategy(scenario: str) -> MailSequenceStrategy:
    if scenario not in _STRATEGY_REGISTRY:
        raise ValueError(f"unsupported mail sequence scenario: {scenario}")
    return _STRATEGY_REGISTRY[scenario]


def get_mail_sequence_step(scenario: str, suite_step: int) -> MailSequenceStepStrategy:
    strategy = get_mail_sequence_strategy(scenario)
    for step in strategy.steps:
        if step.suite_step == suite_step:
            return step
    raise ValueError(f"unsupported suite_step for {scenario}: {suite_step}")


def list_mail_sequence_strategies() -> list[dict[str, Any]]:
    return [s.to_dict() for s in _STRATEGY_REGISTRY.values()]
