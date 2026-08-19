"""Evidence assertion domain for atomic, auditable semantic claims."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import math

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace
from drilling_knowledge.resolution.domain import HypothesisSupport, SemanticHypothesis


class AssertionStatus(StrEnum):
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


class AssertionReviewState(StrEnum):
    AUTO = "auto"
    PENDING_HUMAN = "pending_human"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class AssertionEvidenceLink:
    link_id: EntityId
    assertion_id: EntityId
    hypothesis_id: EntityId
    support_id: EntityId
    document_id: EntityId
    document_version_id: EntityId
    fragment_id: EntityId
    evidence_role: str
    weight: float | None
    source_trace: ExtractionSourceTrace
    original_text: str
    normalized_text: str

    def __post_init__(self) -> None:
        original_text = self.original_text.strip()
        normalized_text = self.normalized_text.strip()
        evidence_role = self.evidence_role.strip().lower()
        if not original_text:
            raise ValueError("AssertionEvidenceLink.original_text cannot be empty")
        if not normalized_text:
            raise ValueError("AssertionEvidenceLink.normalized_text cannot be empty")
        if not evidence_role:
            raise ValueError("AssertionEvidenceLink.evidence_role cannot be empty")
        if self.document_id is None:
            raise ValueError("AssertionEvidenceLink.document_id cannot be null")
        if self.document_version_id is None:
            raise ValueError("AssertionEvidenceLink.document_version_id cannot be null")
        if self.fragment_id is None:
            raise ValueError("AssertionEvidenceLink.fragment_id cannot be null")
        if self.weight is not None and (not math.isfinite(self.weight) or self.weight < 0.0):
            raise ValueError("AssertionEvidenceLink.weight must be finite and non-negative when present")
        if evidence_role == "candidate" and self.weight is None:
            raise ValueError("AssertionEvidenceLink.weight is required for candidate evidence")
        object.__setattr__(self, "original_text", original_text)
        object.__setattr__(self, "normalized_text", normalized_text)
        object.__setattr__(self, "evidence_role", evidence_role)


@dataclass(frozen=True, slots=True)
class AssertionValidationLog:
    log_id: EntityId
    assertion_id: EntityId
    rule_code: str
    outcome: str
    reason_code: str
    detail: str

    def __post_init__(self) -> None:
        rule_code = self.rule_code.strip()
        outcome = self.outcome.strip().lower()
        reason_code = self.reason_code.strip()
        detail = self.detail.strip()
        if not rule_code:
            raise ValueError("AssertionValidationLog.rule_code cannot be empty")
        if not outcome:
            raise ValueError("AssertionValidationLog.outcome cannot be empty")
        if not reason_code:
            raise ValueError("AssertionValidationLog.reason_code cannot be empty")
        if not detail:
            raise ValueError("AssertionValidationLog.detail cannot be empty")
        object.__setattr__(self, "rule_code", rule_code)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "detail", detail)


@dataclass(frozen=True, slots=True)
class EvidenceAssertion:
    assertion_id: EntityId
    source_hypothesis_id: EntityId
    source_candidate_id: EntityId
    evidence_link_ids: tuple[EntityId, ...]
    subject_table: str
    subject_id: EntityId
    predicate_code: str
    object_table: str | None
    object_id: EntityId | None
    literal_value: tuple[tuple[str, str], ...]
    status: AssertionStatus
    review_state: AssertionReviewState
    score: float
    score_breakdown: tuple[tuple[str, float], ...]
    reason_codes: tuple[str, ...]
    supersedes_id: EntityId | None
    invalidates_id: EntityId | None
    created_at: datetime
    source_hypothesis: SemanticHypothesis
    source_supports: tuple[HypothesisSupport, ...]

    def __post_init__(self) -> None:
        subject_table = self.subject_table.strip()
        predicate_code = self.predicate_code.strip().lower()
        if not subject_table:
            raise ValueError("EvidenceAssertion.subject_table cannot be empty")
        if not predicate_code:
            raise ValueError("EvidenceAssertion.predicate_code cannot be empty")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("EvidenceAssertion.score must be between 0 and 1")
        if (self.object_table is None) != (self.object_id is None):
            raise ValueError("EvidenceAssertion.object_table and object_id must both be set or both be null")
        if self.object_id is None and not self.literal_value:
            raise ValueError("EvidenceAssertion must contain an object reference or a literal value")
        if not self.evidence_link_ids:
            raise ValueError("EvidenceAssertion.evidence_link_ids cannot be empty")
        if not self.source_supports:
            raise ValueError("EvidenceAssertion.source_supports cannot be empty")
        if self.source_hypothesis_id != self.source_hypothesis.hypothesis_id:
            raise ValueError("EvidenceAssertion.source_hypothesis_id must match source_hypothesis.hypothesis_id")
        if self.source_candidate_id != self.source_hypothesis.source_candidate_id:
            raise ValueError("EvidenceAssertion.source_candidate_id must match source_hypothesis.source_candidate_id")
        if len(set(self.evidence_link_ids)) != len(self.evidence_link_ids):
            raise ValueError("EvidenceAssertion.evidence_link_ids cannot contain duplicates")
        support_ids = {support.support_id for support in self.source_supports}
        if len(support_ids) != len(self.source_supports):
            raise ValueError("EvidenceAssertion.source_supports cannot contain duplicate support ids")
        for support in self.source_supports:
            if support.hypothesis_id != self.source_hypothesis_id:
                raise ValueError("EvidenceAssertion.source_supports must belong to source_hypothesis_id")
            if support.source_candidate_id != self.source_candidate_id:
                raise ValueError("EvidenceAssertion.source_supports must belong to source_candidate_id")
        if self.status in {AssertionStatus.SUPPORTED, AssertionStatus.ACCEPTED} and self.review_state == AssertionReviewState.PENDING_HUMAN:
            raise ValueError("EvidenceAssertion pending human review cannot be supported or accepted")
        if self.status == AssertionStatus.SUPERSEDED and self.supersedes_id is None:
            raise ValueError("EvidenceAssertion.superseded assertions must define supersedes_id")
        if self.status == AssertionStatus.INVALIDATED and self.invalidates_id is None:
            raise ValueError("EvidenceAssertion.invalidated assertions must define invalidates_id")
        if self.supersedes_id == self.assertion_id:
            raise ValueError("EvidenceAssertion.supersedes_id cannot point to the assertion itself")
        if self.invalidates_id == self.assertion_id:
            raise ValueError("EvidenceAssertion.invalidates_id cannot point to the assertion itself")
        object.__setattr__(self, "subject_table", subject_table)
        object.__setattr__(self, "predicate_code", predicate_code)

    def transition_to(
        self,
        status: AssertionStatus,
        *,
        review_state: AssertionReviewState | None = None,
        supersedes_id: EntityId | None = None,
        invalidates_id: EntityId | None = None,
        reason_code: str | None = None,
    ) -> "EvidenceAssertion":
        transitions = {
            AssertionStatus.CANDIDATE: {AssertionStatus.SUPPORTED, AssertionStatus.REJECTED},
            AssertionStatus.SUPPORTED: {AssertionStatus.ACCEPTED, AssertionStatus.REJECTED, AssertionStatus.INVALIDATED, AssertionStatus.SUPERSEDED},
            AssertionStatus.ACCEPTED: {AssertionStatus.INVALIDATED, AssertionStatus.SUPERSEDED},
            AssertionStatus.REJECTED: set(),
            AssertionStatus.INVALIDATED: set(),
            AssertionStatus.SUPERSEDED: set(),
        }
        if status == self.status:
            return self
        allowed = transitions[self.status]
        if status not in allowed:
            raise ValueError(f"Invalid assertion lifecycle transition: {self.status.value} -> {status.value}")
        next_review_state = review_state if review_state is not None else self.review_state
        next_reason_codes = self.reason_codes if reason_code is None else self.reason_codes + (reason_code,)
        return replace(
            self,
            status=status,
            review_state=next_review_state,
            supersedes_id=supersedes_id,
            invalidates_id=invalidates_id,
            reason_codes=next_reason_codes,
        )


@dataclass(frozen=True, slots=True)
class AssertionGenerationRun:
    run_id: RunId
    semantic_run_id: RunId
    rule_pack_version: str
    threshold: float
    started_at: datetime
    finished_at: datetime
    assertions: tuple[EvidenceAssertion, ...] = ()
    evidence_links: tuple[AssertionEvidenceLink, ...] = ()
    validation_logs: tuple[AssertionValidationLog, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rule_pack_version = self.rule_pack_version.strip()
        if not rule_pack_version:
            raise ValueError("AssertionGenerationRun.rule_pack_version cannot be empty")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("AssertionGenerationRun.threshold must be between 0 and 1")
        if self.finished_at < self.started_at:
            raise ValueError("AssertionGenerationRun.finished_at cannot be before started_at")
        object.__setattr__(self, "rule_pack_version", rule_pack_version)