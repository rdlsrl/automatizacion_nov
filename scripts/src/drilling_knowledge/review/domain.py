"""Deterministic review queue and human decision domain."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactLifecycle
from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus, EvidenceAssertion
from drilling_knowledge.catalog.services.ontology_proposals.domain import OntologyChangeProposal, OntologyProposalStatus
from drilling_knowledge.common.ids import EntityId


def _serialize_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value") and not is_dataclass(value):
        return str(value)
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return str(value)


class ReviewTargetType(StrEnum):
    ASSERTION = "assertion"
    FACT = "fact"
    PROPOSAL = "proposal"


class ReviewQueueStatus(StrEnum):
    OPEN = "open"


class ReviewDecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    queue_type: str
    allowed_target_types: tuple[ReviewTargetType, ...]
    allowed_reasons: tuple[str, ...]
    allowed_actions: tuple[ReviewDecisionAction, ...]
    escalation_policy: str

    def __post_init__(self) -> None:
        queue_type = self.queue_type.strip().lower()
        escalation_policy = self.escalation_policy.strip()
        if not queue_type:
            raise ValueError("ReviewPolicy.queue_type cannot be empty")
        if not self.allowed_target_types:
            raise ValueError("ReviewPolicy.allowed_target_types cannot be empty")
        if len(set(self.allowed_target_types)) != len(self.allowed_target_types):
            raise ValueError("ReviewPolicy.allowed_target_types cannot contain duplicates")
        reasons = tuple(sorted({reason.strip().lower() for reason in self.allowed_reasons if reason.strip()}))
        if not reasons:
            raise ValueError("ReviewPolicy.allowed_reasons cannot be empty")
        actions = tuple(sorted(set(self.allowed_actions), key=lambda item: item.value))
        if not actions:
            raise ValueError("ReviewPolicy.allowed_actions cannot be empty")
        if not escalation_policy:
            raise ValueError("ReviewPolicy.escalation_policy cannot be empty")
        object.__setattr__(self, "queue_type", queue_type)
        object.__setattr__(self, "allowed_reasons", reasons)
        object.__setattr__(self, "allowed_actions", actions)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReviewPolicyCatalog:
    policies: tuple[ReviewPolicy, ...]

    def __post_init__(self) -> None:
        if not self.policies:
            raise ValueError("ReviewPolicyCatalog.policies cannot be empty")
        queue_types = [policy.queue_type for policy in self.policies]
        if len(set(queue_types)) != len(queue_types):
            raise ValueError("ReviewPolicyCatalog.policies cannot contain duplicate queue types")

    def policy_for(self, queue_type: str) -> ReviewPolicy:
        normalized = queue_type.strip().lower()
        for policy in self.policies:
            if policy.queue_type == normalized:
                return policy
        raise ValueError(f"Unknown review queue_type: {queue_type}")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReviewQueueItem:
    queue_id: EntityId
    queue_type: str
    target_type: ReviewTargetType
    target_id: EntityId
    reference_table: str
    priority: int
    review_reason: str
    status: ReviewQueueStatus
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str
    provenance: tuple[tuple[str, str], ...]
    policy_version: str

    def __post_init__(self) -> None:
        queue_type = self.queue_type.strip().lower()
        reference_table = self.reference_table.strip().lower()
        review_reason = self.review_reason.strip().lower()
        created_by = self.created_by.strip()
        updated_by = self.updated_by.strip()
        assigned_to = None if self.assigned_to is None else self.assigned_to.strip()
        policy_version = self.policy_version.strip()
        if not queue_type:
            raise ValueError("ReviewQueueItem.queue_type cannot be empty")
        if not reference_table:
            raise ValueError("ReviewQueueItem.reference_table cannot be empty")
        if not review_reason:
            raise ValueError("ReviewQueueItem.review_reason cannot be empty")
        if self.priority < 0:
            raise ValueError("ReviewQueueItem.priority cannot be negative")
        if not created_by:
            raise ValueError("ReviewQueueItem.created_by cannot be empty")
        if not updated_by:
            raise ValueError("ReviewQueueItem.updated_by cannot be empty")
        if self.updated_at < self.created_at:
            raise ValueError("ReviewQueueItem.updated_at cannot be before created_at")
        if not self.provenance:
            raise ValueError("ReviewQueueItem.provenance cannot be empty")
        if len(set(self.provenance)) != len(self.provenance):
            raise ValueError("ReviewQueueItem.provenance cannot contain duplicates")
        if not policy_version:
            raise ValueError("ReviewQueueItem.policy_version cannot be empty")
        object.__setattr__(self, "queue_type", queue_type)
        object.__setattr__(self, "reference_table", reference_table)
        object.__setattr__(self, "review_reason", review_reason)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "updated_by", updated_by)
        object.__setattr__(self, "assigned_to", assigned_to if assigned_to else None)
        object.__setattr__(self, "policy_version", policy_version)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: EntityId
    review_queue_id: EntityId
    target_type: ReviewTargetType
    target_id: EntityId
    action: ReviewDecisionAction
    reason: str
    decided_by: str
    decided_at: datetime
    provenance: tuple[tuple[str, str], ...]
    previous_state: str
    resulting_state: str

    def __post_init__(self) -> None:
        reason = self.reason.strip()
        decided_by = self.decided_by.strip()
        previous_state = self.previous_state.strip().lower()
        resulting_state = self.resulting_state.strip().lower()
        if not reason:
            raise ValueError("ReviewDecision.reason cannot be empty")
        if not decided_by:
            raise ValueError("ReviewDecision.decided_by cannot be empty")
        if not self.provenance:
            raise ValueError("ReviewDecision.provenance cannot be empty")
        if len(set(self.provenance)) != len(self.provenance):
            raise ValueError("ReviewDecision.provenance cannot contain duplicates")
        if not previous_state:
            raise ValueError("ReviewDecision.previous_state cannot be empty")
        if not resulting_state:
            raise ValueError("ReviewDecision.resulting_state cannot be empty")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "decided_by", decided_by)
        object.__setattr__(self, "previous_state", previous_state)
        object.__setattr__(self, "resulting_state", resulting_state)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReviewApplicationResult:
    queue: ReviewQueueItem
    decision: ReviewDecision
    updated_assertion: EvidenceAssertion | None = None
    updated_fact: ConsolidatedFact | None = None
    updated_proposal: OntologyChangeProposal | None = None

    def __post_init__(self) -> None:
        populated = sum(item is not None for item in (self.updated_assertion, self.updated_fact, self.updated_proposal))
        if populated != 1:
            raise ValueError("ReviewApplicationResult must contain exactly one updated target")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


def assertion_state(assertion: EvidenceAssertion) -> str:
    return f"{assertion.status.value}:{assertion.review_state.value}"


def fact_state(fact: ConsolidatedFact) -> str:
    return f"{fact.lifecycle.value}:{'active' if fact.active_revision else 'historical'}"


def proposal_state(proposal: OntologyChangeProposal) -> str:
    return proposal.proposal_status.value


def apply_assertion_decision(assertion: EvidenceAssertion, action: ReviewDecisionAction) -> EvidenceAssertion:
    if assertion.review_state != AssertionReviewState.PENDING_HUMAN:
        raise ValueError("Only pending-human assertions can receive manual review decisions")
    if action == ReviewDecisionAction.APPROVE:
        supported = assertion.transition_to(AssertionStatus.SUPPORTED, review_state=AssertionReviewState.APPROVED)
        return supported.transition_to(AssertionStatus.ACCEPTED, review_state=AssertionReviewState.APPROVED)
    return assertion.transition_to(
        AssertionStatus.REJECTED,
        review_state=AssertionReviewState.REJECTED,
        reason_code="human_review_rejected",
    )


def apply_fact_decision(fact: ConsolidatedFact, action: ReviewDecisionAction, *, decided_at: datetime) -> ConsolidatedFact:
    if action == ReviewDecisionAction.APPROVE:
        return fact
    if fact.lifecycle != FactLifecycle.ACTIVE or not fact.active_revision:
        raise ValueError("Only active fact revisions can be rejected by human review")
    return replace(fact, lifecycle=FactLifecycle.SUPERSEDED, active_revision=False, updated_at=decided_at)


def apply_proposal_decision(proposal: OntologyChangeProposal, action: ReviewDecisionAction) -> OntologyChangeProposal:
    if proposal.proposal_status != OntologyProposalStatus.QUEUED:
        raise ValueError("Only queued ontology proposals can receive manual review decisions")
    if action == ReviewDecisionAction.APPROVE:
        return proposal.transition_to(OntologyProposalStatus.APPROVED)
    return proposal.transition_to(OntologyProposalStatus.REJECTED)