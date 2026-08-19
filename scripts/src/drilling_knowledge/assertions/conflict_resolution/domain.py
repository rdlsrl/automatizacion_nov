"""Conflict detection and resolution domain for evidence assertions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId


class ConflictSetStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ConflictType(StrEnum):
    INCOMPATIBLE_ASSERTION = "incompatible_assertion"


class ConflictDecisionType(StrEnum):
    ACCEPTED_MEMBER = "accepted_member"
    REJECTED_MEMBER = "rejected_member"
    COEXISTENCE_SPLIT = "coexistence_split"
    REVIEW_REQUIRED = "review_required"


class ConflictMemberRole(StrEnum):
    ACCEPTED_MEMBER = "accepted_member"
    REJECTED_MEMBER = "rejected_member"
    SPLIT_CONTEXT = "split_context"
    REVIEW_CANDIDATE = "review_candidate"


@dataclass(frozen=True, slots=True)
class ConflictReviewQueueItem:
    review_item_id: EntityId
    conflict_set_id: EntityId
    queue_type: str
    review_reason: str
    created_at: datetime

    def __post_init__(self) -> None:
        queue_type = self.queue_type.strip().lower()
        review_reason = self.review_reason.strip()
        if not queue_type:
            raise ValueError("ConflictReviewQueueItem.queue_type cannot be empty")
        if not review_reason:
            raise ValueError("ConflictReviewQueueItem.review_reason cannot be empty")
        object.__setattr__(self, "queue_type", queue_type)
        object.__setattr__(self, "review_reason", review_reason)


@dataclass(frozen=True, slots=True)
class AssertionConflictMember:
    member_id: EntityId
    conflict_set_id: EntityId
    assertion_id: EntityId
    member_role: ConflictMemberRole
    member_score: float
    scope_key: str
    value_key: str
    created_at: datetime
    source_assertion: EvidenceAssertion

    def __post_init__(self) -> None:
        scope_key = self.scope_key.strip()
        value_key = self.value_key.strip()
        if not 0.0 <= self.member_score <= 1.0:
            raise ValueError("AssertionConflictMember.member_score must be between 0 and 1")
        if self.assertion_id != self.source_assertion.assertion_id:
            raise ValueError("AssertionConflictMember.assertion_id must match source_assertion.assertion_id")
        if not scope_key:
            raise ValueError("AssertionConflictMember.scope_key cannot be empty")
        if not value_key:
            raise ValueError("AssertionConflictMember.value_key cannot be empty")
        object.__setattr__(self, "scope_key", scope_key)
        object.__setattr__(self, "value_key", value_key)


@dataclass(frozen=True, slots=True)
class AssertionConflictContext:
    context_id: EntityId
    conflict_set_id: EntityId
    scope_key: str
    document_id: EntityId
    document_version_id: EntityId
    member_ids: tuple[EntityId, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        scope_key = self.scope_key.strip()
        if not scope_key:
            raise ValueError("AssertionConflictContext.scope_key cannot be empty")
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("AssertionConflictContext.member_ids cannot contain duplicates")
        if not self.member_ids:
            raise ValueError("AssertionConflictContext.member_ids cannot be empty")
        object.__setattr__(self, "scope_key", scope_key)


@dataclass(frozen=True, slots=True)
class AssertionConflictSet:
    conflict_set_id: EntityId
    claim_key: str
    scope_key: str
    conflict_type: ConflictType
    status: ConflictSetStatus
    decision_type: ConflictDecisionType | None
    decision_reason: str | None
    requires_human_review: bool
    opened_at: datetime
    closed_at: datetime | None
    members: tuple[AssertionConflictMember, ...] = ()
    contexts: tuple[AssertionConflictContext, ...] = ()
    review_item: ConflictReviewQueueItem | None = None

    def __post_init__(self) -> None:
        claim_key = self.claim_key.strip()
        scope_key = self.scope_key.strip()
        if not claim_key:
            raise ValueError("AssertionConflictSet.claim_key cannot be empty")
        if not scope_key:
            raise ValueError("AssertionConflictSet.scope_key cannot be empty")
        if len({member.assertion_id for member in self.members}) != len(self.members):
            raise ValueError("AssertionConflictSet.members cannot contain duplicate assertion ids")
        if len({context.context_id for context in self.contexts}) != len(self.contexts):
            raise ValueError("AssertionConflictSet.contexts cannot contain duplicate context ids")
        if self.status == ConflictSetStatus.CLOSED and (self.decision_type is None or self.closed_at is None):
            raise ValueError("Closed conflict sets must define decision_type and closed_at")
        if self.requires_human_review and self.review_item is None:
            raise ValueError("Conflict sets requiring human review must define a review_item")
        if not self.requires_human_review and self.review_item is not None:
            raise ValueError("Conflict sets without review escalation cannot define a review_item")
        if self.decision_reason is not None and not self.decision_reason.strip():
            raise ValueError("AssertionConflictSet.decision_reason cannot be blank")
        if self.decision_type == ConflictDecisionType.COEXISTENCE_SPLIT and len(self.contexts) < 2:
            raise ValueError("Split-by-context conflict sets must define two or more contexts")
        object.__setattr__(self, "claim_key", claim_key)
        object.__setattr__(self, "scope_key", scope_key)


@dataclass(frozen=True, slots=True)
class ConflictResolutionRun:
    run_id: RunId
    assertion_run_id: RunId
    rule_pack_version: str
    started_at: datetime
    finished_at: datetime
    conflict_sets: tuple[AssertionConflictSet, ...] = ()
    members: tuple[AssertionConflictMember, ...] = ()
    contexts: tuple[AssertionConflictContext, ...] = ()
    review_queue_items: tuple[ConflictReviewQueueItem, ...] = ()
    evidence_links: tuple[AssertionEvidenceLink, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rule_pack_version = self.rule_pack_version.strip()
        if not rule_pack_version:
            raise ValueError("ConflictResolutionRun.rule_pack_version cannot be empty")
        if self.finished_at < self.started_at:
            raise ValueError("ConflictResolutionRun.finished_at cannot be before started_at")
        object.__setattr__(self, "rule_pack_version", rule_pack_version)