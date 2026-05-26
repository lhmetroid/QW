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
        "Re-open dialogue with a previously engaged customer through a low-pressure "
        "four-step sequence: relationship restart, relevant proof, process confidence, "
        "then a reviewed commercial next step."
    ),
    applicable_trigger=(
        "CRM or sales review confirms prior cooperation, inquiry, sampling, delivery, "
        "or meaningful business conversation, with no effective recent business contact."
    ),
    isolation_boundary=(
        "Mail-only strategy metadata. Do not write state to WeCom conversation tables, "
        "do not require WeCom callbacks, and do not send real email."
    ),
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.RE_ACTIVATION.value,
            scenario_label="old_customer_re_activation",
            suite_step=1,
            step_key="re_activation_step_1_reconnect",
            objective=(
                "Restart the relationship with a light greeting, acknowledge prior "
                "cooperation, and invite a simple update without selling."
            ),
            recommended_snippet_types=(MailSnippetType.GREETINGS.value,),
            subject_template_hints=(
                "Quick hello and a small update for your team",
                "Checking in after our previous cooperation",
                "Hope everything has been going smoothly on your side",
            ),
            cta_style=(
                "Low-pressure reply invitation. Ask whether there is anything upcoming "
                "the team should prepare for, without asking for an order or quote."
            ),
            retrieval_filter_requirements=(
                "scenario must equal re_activation.",
                "sequence_step_hint should be 1 or null; prefer exact step match.",
                "snippet_type must be greetings.",
                "retrieval_enabled, publishable, allowed_for_generation and usable_for_reply must all be true.",
                "useful_score must meet MAIL_FEWSHOT_MIN_USEFUL_SCORE, default 0.60.",
                "desensitized_status must be desensitized when present in source_snapshot.",
                "review_status must be approved when present in source_snapshot.",
                "Do not require industry or product_line for Step 1 unless request-side CRM profile provides them.",
            ),
            forbidden_boundaries=(
                "No price, discount, payment term, urgent delivery promise, or concrete SLA.",
                "No strong promotional language or pressure to place an order.",
                "No real customer name, project number, file name, phone, URL, or internal identifier from history.",
                "No claim that the customer has an active need unless CRM or the user request provides it.",
            ),
            exit_conditions=(
                "Customer replies by email.",
                "CRM stage changes to won, active opportunity, complaint, do-not-contact, or manual follow-up.",
                "Sales manually seals the sequence.",
                "Recipient or domain fails later anti-leakage checks.",
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
                "Share a closely matched, desensitized peer project or capability proof "
                "to remind the customer why the team is relevant."
            ),
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value,),
            subject_template_hints=(
                "A recent reference from a similar project",
                "Sharing a relevant example for your next localization work",
                "A quick case reference that may be useful for your team",
            ),
            cta_style=(
                "Interest-check CTA. Invite the recipient to ask for the anonymized "
                "reference details or send similar files for review."
            ),
            retrieval_filter_requirements=(
                "scenario must equal re_activation.",
                "sequence_step_hint should be 2 or null; prefer exact step match.",
                "snippet_type must be example.",
                "industry should strongly match when the CRM/request industry is known.",
                "product_line should strongly match when the CRM/request product_line is known.",
                "country may be used as a soft preference, not as a substitute for domain checks.",
                "Do not use unknown industry examples before exhausting exact industry/product matches.",
                "All Task 17 Few-Shot admission conditions still apply.",
            ),
            forbidden_boundaries=(
                "No cross-industry proof when a known industry profile exists.",
                "No real customer names, recognizable project details, unapproved metrics, or ROI claims.",
                "No implication that the recipient endorsed or requested the example.",
                "No price, discount, account term, or delivery commitment.",
            ),
            exit_conditions=(
                "Customer replies or asks for details.",
                "CRM profile shows industry mismatch or missing consent for case sharing.",
                "Customer is already assigned to manual opportunity follow-up.",
                "Sales manually seals the sequence.",
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
                "Reduce hesitation by explaining the current service process, quality "
                "checks, required inputs, and reasonable delivery boundaries."
            ),
            recommended_snippet_types=(MailSnippetType.PROCESS.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "How we now handle translation, review and formatting projects",
                "Our updated workflow for smoother project delivery",
                "A quick note on process and quality control",
            ),
            cta_style=(
                "Operational CTA. Ask whether the recipient wants the checklist, file "
                "review, or a quick feasibility confirmation."
            ),
            retrieval_filter_requirements=(
                "scenario must equal re_activation.",
                "sequence_step_hint should be 3 or null; prefer exact step match.",
                "snippet_type should be process or constraint.",
                "product_line should match the current service interest when known.",
                "industry is a weighting field; for medical or legal_finance, prefer exact matches.",
                "constraint snippets must be approved and safe_for_fewshot before retrieval.",
                "Delivery durations must come from later SLA rules, not from historical free text.",
            ),
            forbidden_boundaries=(
                "No non-standard rush promise or fixed delivery date from historical emails.",
                "No internal staffing, cost, vendor, margin, or unpublished quality-control detail.",
                "No customer-sensitive file names or document contents.",
                "No wording that bypasses future SLA calibration or manual review.",
            ),
            exit_conditions=(
                "Customer sends files, asks for feasibility, or opens a concrete project discussion.",
                "CRM marks active opportunity or manual follow-up.",
                "Later SLA guardrail would need to lock the draft for approval.",
                "Sales manually seals the sequence.",
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
                "Offer a reviewed light commercial next step such as sample review, "
                "trial, or quote conversation while preserving price and term guardrails."
            ),
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "A small next step reserved for returning clients",
                "Would a sample review help for your next project?",
                "Closing the loop with a practical option for your team",
            ),
            cta_style=(
                "Single explicit reply CTA. Ask the recipient to reply yes, send files, "
                "or confirm whether they want a reviewed quote or sample arrangement."
            ),
            retrieval_filter_requirements=(
                "scenario must equal re_activation.",
                "sequence_step_hint should be 4 or null; prefer exact step match.",
                "snippet_type should be quotation or constraint.",
                "product_line and customer_tier should match before using any commercial wording.",
                "payment_risk high, prepaid_required, blocked, or unknown should force conservative wording or manual review.",
                "Quotation snippets provide expression structure only; amounts and discounts come from later physical fields.",
                "All safety-related source_snapshot fields must be affirmative before retrieval.",
            ),
            forbidden_boundaries=(
                "No model-generated price, discount, payment term, account privilege, or bottom-line hint.",
                "No promise of free service, sample, or trial unless supplied by approved config or human input.",
                "No pressure language, scarcity claim, or auto-expiring privilege unless backed by business config.",
                "No real sending until draft review and future safety gates pass.",
            ),
            exit_conditions=(
                "Customer replies, accepts, declines, or asks not to be contacted.",
                "CRM stage changes, manual seal is applied, or sequence status becomes interrupted or blocked.",
                "A pending draft is locked or destroyed by future Task 25 rules.",
                "Any price, SLA, payment, or recipient guardrail fails.",
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
        "Introduce a relevant new product line, service bundle, or capability upgrade "
        "through a four-step sequence: light value introduction, matched proof, "
        "service-package process, then a reviewed trial or quote conversation."
    ),
    applicable_trigger=(
        "CRM, sales tagging, or manual review shows the customer has a related demand "
        "profile but has not purchased the promoted product line or service bundle."
    ),
    isolation_boundary=(
        "Mail-only strategy metadata. Do not write state to WeCom conversation tables, "
        "do not require WeCom callbacks, and do not send real email."
    ),
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_BUSINESS_PROMOTION.value,
            scenario_label="new_business_promotion",
            suite_step=1,
            step_key="new_business_promotion_step_1_value_intro",
            objective=(
                "Open with a light, profile-aware introduction to the promoted service "
                "and connect it to a plausible customer need without quoting or pushing."
            ),
            recommended_snippet_types=(MailSnippetType.GREETINGS.value, MailSnippetType.EXAMPLE.value),
            subject_template_hints=(
                "A small service update that may fit your upcoming work",
                "Sharing a new option for your localization projects",
                "A quick note on a service bundle your team may find useful",
            ),
            cta_style=(
                "Low-pressure interest check. Ask whether the recipient wants a short "
                "overview, reference, or sample workflow for the promoted service."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_business_promotion.",
                "sequence_step_hint should be 1 or null; prefer exact step match.",
                "snippet_type should be greetings or example.",
                "target product_line should match the promoted service when known.",
                "industry and country should be used as soft relevance filters when present.",
                "retrieval_enabled, publishable, allowed_for_generation and usable_for_reply must all be true.",
                "useful_score must meet MAIL_FEWSHOT_MIN_USEFUL_SCORE, default 0.60.",
                "desensitized_status must be desensitized when present in source_snapshot.",
                "review_status must be approved when present in source_snapshot.",
            ),
            forbidden_boundaries=(
                "No claim that the customer already requested, approved, or committed to the new service.",
                "No price, discount, account term, fixed delivery promise, or urgent deadline.",
                "No cold mass-mail wording when no customer profile or contact source exists.",
                "No real customer name, project number, file name, phone, URL, or internal identifier from history.",
            ),
            exit_conditions=(
                "Customer replies, asks for details, or rejects the promotion.",
                "CRM marks do-not-contact, complaint, active opportunity, or manual follow-up.",
                "Customer profile is missing or contradicts the promoted service fit.",
                "Recipient or domain fails later anti-leakage checks.",
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
                "Use a strongly matched, desensitized industry or product-line example "
                "to show why the new service is relevant to the recipient."
            ),
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value,),
            subject_template_hints=(
                "A relevant example for this service area",
                "How a similar team used this service bundle",
                "A short reference from a comparable project",
            ),
            cta_style=(
                "Relevance-check CTA. Invite the recipient to ask for the anonymized "
                "reference, compare a similar file, or confirm whether the use case fits."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_business_promotion.",
                "sequence_step_hint should be 2 or null; prefer exact step match.",
                "snippet_type must be example.",
                "industry should strongly match when the CRM/request industry is known.",
                "product_line must match the promoted product line when known.",
                "customer_tier may tune tone and depth, but must not create unsupported claims.",
                "Do not use unknown industry or unrelated product examples before exhausting exact matches.",
                "All Task 17 Few-Shot admission conditions still apply.",
            ),
            forbidden_boundaries=(
                "No obviously mismatched industry or product-line proof.",
                "No real customer names, recognizable project details, unapproved metrics, or ROI claims.",
                "No implication that the recipient endorsed the example or has the same result guaranteed.",
                "No price, discount, account term, or delivery commitment.",
            ),
            exit_conditions=(
                "Customer replies, asks for the reference, or sends a sample file.",
                "CRM profile shows industry/product mismatch or missing consent for case sharing.",
                "Customer is already assigned to manual opportunity follow-up.",
                "Sales manually seals the sequence.",
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
                "Explain the service package, collaboration flow, required inputs, and "
                "reasonable constraints so the customer can evaluate a small trial."
            ),
            recommended_snippet_types=(MailSnippetType.PROCESS.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "How this service package would work for your team",
                "A simple workflow for trying this service",
                "What we would need to review a first sample",
            ),
            cta_style=(
                "Operational CTA. Ask whether the recipient wants a checklist, sample "
                "review, scope confirmation, or a short feasibility check."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_business_promotion.",
                "sequence_step_hint should be 3 or null; prefer exact step match.",
                "snippet_type should be process or constraint.",
                "product_line must match the promoted service package when known.",
                "industry is a weighting field; for medical or legal_finance, prefer exact matches.",
                "constraint snippets must be approved and safe_for_fewshot before retrieval.",
                "Delivery durations must come from later SLA rules, not from historical free text.",
            ),
            forbidden_boundaries=(
                "No non-standard rush promise or fixed delivery date from historical emails.",
                "No internal staffing, cost, vendor, margin, or unpublished quality-control detail.",
                "No customer-sensitive file names or document contents.",
                "No wording that bypasses future SLA calibration, scope confirmation, or manual review.",
            ),
            exit_conditions=(
                "Customer asks for a checklist, sends files, or opens a concrete trial discussion.",
                "CRM marks active opportunity or manual follow-up.",
                "Later SLA guardrail would need to lock the draft for approval.",
                "Sales manually seals the sequence.",
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
                "Offer a reviewed trial, sample review, or quote conversation for the "
                "promoted service while preserving price, term, and sending guardrails."
            ),
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "Would a small trial help evaluate this service?",
                "A practical next step for reviewing this service option",
                "Checking whether a reviewed quote or sample would help",
            ),
            cta_style=(
                "Single explicit reply CTA. Ask the recipient to reply yes, send files, "
                "or confirm whether they want a reviewed quote, sample, or trial scope."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_business_promotion.",
                "sequence_step_hint should be 4 or null; prefer exact step match.",
                "snippet_type should be quotation or constraint.",
                "product_line and customer_tier should match before using any commercial wording.",
                "payment_risk high, prepaid_required, blocked, or unknown should force conservative wording or manual review.",
                "Quotation snippets provide expression structure only; amounts and discounts come from later physical fields.",
                "All safety-related source_snapshot fields must be affirmative before retrieval.",
            ),
            forbidden_boundaries=(
                "No model-generated price, discount, payment term, account privilege, or bottom-line hint.",
                "No promise of free trial, sample, bundle, or special offer unless supplied by approved config or human input.",
                "No pressure language, scarcity claim, or auto-expiring privilege unless backed by business config.",
                "No real sending until draft review and future safety gates pass.",
            ),
            exit_conditions=(
                "Customer replies, accepts, declines, or asks not to be contacted.",
                "CRM stage changes, manual seal is applied, or sequence status becomes interrupted or blocked.",
                "A pending draft is locked or destroyed by future Task 25 rules.",
                "Any price, SLA, payment, or recipient guardrail fails.",
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
        "Establish trust with a newly assigned recipient or newly assigned seller "
        "through a four-step sequence: transparent handover introduction, prior "
        "cooperation context, role-relevant service path, then a reviewed next step."
    ),
    applicable_trigger=(
        "CRM, sales handover, or manual review shows the account has a new recipient, "
        "new department owner, or new seller-owner relationship that needs a clean "
        "email introduction before business follow-up."
    ),
    isolation_boundary=(
        "Mail-only strategy metadata. Do not write state to WeCom conversation tables, "
        "do not require WeCom callbacks, and do not send real email."
    ),
    steps=(
        MailSequenceStepStrategy(
            scenario=MailScenario.NEW_CONTACT_INTRO.value,
            scenario_label="new_contact_intro",
            suite_step=1,
            step_key="new_contact_intro_step_1_handover_intro",
            objective=(
                "Introduce the current seller, explain the handover or contact reason, "
                "and make the email feel accountable rather than promotional."
            ),
            recommended_snippet_types=(MailSnippetType.GREETINGS.value,),
            subject_template_hints=(
                "A quick introduction as your new contact",
                "Introducing myself for future project coordination",
                "Following up after the account handover",
            ),
            cta_style=(
                "Permission-based reply CTA. Ask whether the recipient is the right "
                "person for future coordination or whether another colleague should be copied."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_contact_intro.",
                "sequence_step_hint should be 1 or null; prefer exact step match.",
                "snippet_type must be greetings.",
                "handover_context should come from CRM, sales handover, or manual request, not model inference alone.",
                "retrieval_enabled, publishable, allowed_for_generation and usable_for_reply must all be true.",
                "useful_score must meet MAIL_FEWSHOT_MIN_USEFUL_SCORE, default 0.60.",
                "desensitized_status must be desensitized when present in source_snapshot.",
                "review_status must be approved when present in source_snapshot.",
            ),
            forbidden_boundaries=(
                "No claim of personal relationship, prior conversation, or customer approval unless provided by CRM or request.",
                "No pressure to start a project, place an order, or provide files immediately.",
                "No real previous contact name, department, phone, project number, or internal handover note unless approved.",
                "No price, discount, payment term, or fixed delivery commitment.",
            ),
            exit_conditions=(
                "Recipient replies with the correct owner, rejection, or do-not-contact request.",
                "CRM shows the recipient is not the right contact or has left the company.",
                "Sales manually seals the sequence or assigns manual follow-up.",
                "Recipient or domain fails later anti-leakage checks.",
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
                "Provide concise, desensitized prior cooperation or department context "
                "so the new contact understands why the introduction is relevant."
            ),
            recommended_snippet_types=(MailSnippetType.EXAMPLE.value, MailSnippetType.PROCESS.value),
            subject_template_hints=(
                "A little background on how we have supported your team",
                "Context for future translation and production requests",
                "Sharing the relevant cooperation background",
            ),
            cta_style=(
                "Context-check CTA. Ask whether this background matches the recipient's "
                "current responsibilities or whether another team should be connected."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_contact_intro.",
                "sequence_step_hint should be 2 or null; prefer exact step match.",
                "snippet_type should be example or process.",
                "Known department, contact_role_hint, industry, and product_line should be used to avoid irrelevant history.",
                "Do not use real names or identifiable project references from historical snippets.",
                "All Task 17 Few-Shot admission conditions still apply.",
            ),
            forbidden_boundaries=(
                "No disclosure of previous contact personal details, direct phone, mailbox, resignation, retirement, or internal notes.",
                "No customer-sensitive project names, PO numbers, file names, or contract information.",
                "No implication that the new recipient already agreed to own this work.",
                "No unapproved claims about business volume, ranking, ROI, or strategic importance.",
            ),
            exit_conditions=(
                "Recipient confirms role fit, refers another contact, or says the context is irrelevant.",
                "CRM profile shows department or contact mismatch.",
                "Customer is already assigned to manual opportunity follow-up.",
                "Sales manually seals the sequence.",
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
                "Explain how future requests can be routed, reviewed, and scoped so "
                "the new contact has a low-friction way to cooperate."
            ),
            recommended_snippet_types=(MailSnippetType.PROCESS.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "A simple path for future translation or production requests",
                "How we can support your team when a request comes up",
                "A short coordination note for future projects",
            ),
            cta_style=(
                "Operational CTA. Offer a checklist, routing path, or file review "
                "option while asking the recipient to confirm the preferred workflow."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_contact_intro.",
                "sequence_step_hint should be 3 or null; prefer exact step match.",
                "snippet_type should be process or constraint.",
                "product_line should match the likely service path when known.",
                "contact_role_hint should shape the workflow wording but not create unsupported responsibilities.",
                "constraint snippets must be approved and safe_for_fewshot before retrieval.",
                "Delivery durations must come from later SLA rules, not from historical free text.",
            ),
            forbidden_boundaries=(
                "No non-standard rush promise or fixed delivery date from historical emails.",
                "No internal staffing, cost, vendor, margin, or unpublished quality-control detail.",
                "No customer-sensitive file names, document contents, or prior commercial terms.",
                "No wording that bypasses future SLA calibration, scope confirmation, or manual review.",
            ),
            exit_conditions=(
                "Recipient asks for the checklist, sends files, or confirms a preferred routing path.",
                "CRM marks active opportunity or manual follow-up.",
                "Later SLA guardrail would need to lock the draft for approval.",
                "Sales manually seals the sequence.",
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
                "Offer a reviewed practical next step such as a file check, sample "
                "review, or quote conversation while preserving commercial guardrails."
            ),
            recommended_snippet_types=(MailSnippetType.QUOTATION.value, MailSnippetType.CONSTRAINT.value),
            subject_template_hints=(
                "Would a small file review help your team get started?",
                "A practical next step if a request comes up",
                "Checking whether a reviewed quote or sample would help",
            ),
            cta_style=(
                "Single explicit reply CTA. Ask the recipient to reply yes, send files, "
                "or confirm whether another colleague should handle quote or sample review."
            ),
            retrieval_filter_requirements=(
                "scenario must equal new_contact_intro.",
                "sequence_step_hint should be 4 or null; prefer exact step match.",
                "snippet_type should be quotation or constraint.",
                "contact_role_hint, product_line, and customer_tier should match before using commercial wording.",
                "payment_risk high, prepaid_required, blocked, or unknown should force conservative wording or manual review.",
                "Quotation snippets provide expression structure only; amounts and discounts come from later physical fields.",
                "All safety-related source_snapshot fields must be affirmative before retrieval.",
            ),
            forbidden_boundaries=(
                "No model-generated price, discount, payment term, account privilege, or bottom-line hint.",
                "No promise of free sample, special treatment, or prior-client privilege unless supplied by approved config or human input.",
                "No pressure language, scarcity claim, or auto-expiring privilege unless backed by business config.",
                "No real sending until draft review and future safety gates pass.",
            ),
            exit_conditions=(
                "Recipient replies, refers another owner, accepts, declines, or asks not to be contacted.",
                "CRM stage changes, manual seal is applied, or sequence status becomes interrupted or blocked.",
                "A pending draft is locked or destroyed by future Task 25 rules.",
                "Any price, SLA, payment, or recipient guardrail fails.",
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


def get_re_activation_sequence() -> MailSequenceStrategy:
    return RE_ACTIVATION_SEQUENCE


def get_new_business_promotion_sequence() -> MailSequenceStrategy:
    return NEW_BUSINESS_PROMOTION_SEQUENCE


def get_new_contact_intro_sequence() -> MailSequenceStrategy:
    return NEW_CONTACT_INTRO_SEQUENCE


def get_mail_sequence_strategy(scenario: str) -> MailSequenceStrategy:
    if scenario == MailScenario.RE_ACTIVATION.value:
        return RE_ACTIVATION_SEQUENCE
    if scenario == MailScenario.NEW_BUSINESS_PROMOTION.value:
        return NEW_BUSINESS_PROMOTION_SEQUENCE
    if scenario == MailScenario.NEW_CONTACT_INTRO.value:
        return NEW_CONTACT_INTRO_SEQUENCE
    raise ValueError(f"unsupported mail sequence scenario: {scenario}")


def get_mail_sequence_step(scenario: str, suite_step: int) -> MailSequenceStepStrategy:
    strategy = get_mail_sequence_strategy(scenario)
    for step in strategy.steps:
        if step.suite_step == suite_step:
            return step
    raise ValueError(f"unsupported suite_step for {scenario}: {suite_step}")


def list_mail_sequence_strategies() -> list[dict[str, Any]]:
    return [
        RE_ACTIVATION_SEQUENCE.to_dict(),
        NEW_BUSINESS_PROMOTION_SEQUENCE.to_dict(),
        NEW_CONTACT_INTRO_SEQUENCE.to_dict(),
    ]
