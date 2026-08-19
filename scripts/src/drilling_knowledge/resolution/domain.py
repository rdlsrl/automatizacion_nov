"""Deterministic candidate resolution domain over extracted mentions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractedEntity
from drilling_knowledge.normalization.domain import NormalizedEntityCandidate, NormalizedRelationCandidate


class ResolutionStatus(StrEnum):
    RESOLVED_CANDIDATE = "RESOLVED_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class ResolutionEvidenceType(StrEnum):
    EXACT_NAME = "EXACT_NAME"
    EXACT_CODE = "EXACT_CODE"
    EXACT_SYMBOL = "EXACT_SYMBOL"
    EXPLICIT_ALIAS = "EXPLICIT_ALIAS"


class SemanticHypothesisStatus(StrEnum):
    SUPPORTED = "supported"
    REJECTED = "rejected"


class HypothesisSupportKind(StrEnum):
    RULE = "rule"
    FILTER = "filter"
    CANDIDATE = "candidate"


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    evidence_type: ResolutionEvidenceType
    matched_text: str
    normalized_matched_text: str
    source_field: str
    explanation: str

    def __post_init__(self) -> None:
        matched_text = self.matched_text.strip()
        normalized_matched_text = self.normalized_matched_text.strip()
        source_field = self.source_field.strip()
        explanation = self.explanation.strip()
        if not matched_text:
            raise ValueError("CandidateEvidence.matched_text cannot be empty")
        if not normalized_matched_text:
            raise ValueError("CandidateEvidence.normalized_matched_text cannot be empty")
        if not source_field:
            raise ValueError("CandidateEvidence.source_field cannot be empty")
        if not explanation:
            raise ValueError("CandidateEvidence.explanation cannot be empty")
        object.__setattr__(self, "matched_text", matched_text)
        object.__setattr__(self, "normalized_matched_text", normalized_matched_text)
        object.__setattr__(self, "source_field", source_field)
        object.__setattr__(self, "explanation", explanation)


@dataclass(frozen=True, slots=True)
class CandidateConcept:
    candidate_id: EntityId
    catalog_entity_id: EntityId
    catalog_entity_type: str
    catalog_code: str
    canonical_name: str
    rank: int
    evidence: CandidateEvidence
    supporting_evidences: tuple[CandidateEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class MentionResolution:
    resolution_id: EntityId
    mention: ExtractedEntity
    status: ResolutionStatus
    candidates: tuple[CandidateConcept, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolutionRun:
    run_id: RunId
    started_at: datetime
    finished_at: datetime
    mention_resolutions: tuple[MentionResolution, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HypothesisSupport:
    support_id: EntityId
    hypothesis_id: EntityId
    support_kind: HypothesisSupportKind
    source_candidate_id: EntityId
    rule_code: str
    reason_code: str
    detail: str

    def __post_init__(self) -> None:
        rule_code = self.rule_code.strip()
        reason_code = self.reason_code.strip()
        detail = self.detail.strip()
        if not rule_code:
            raise ValueError("HypothesisSupport.rule_code cannot be empty")
        if not reason_code:
            raise ValueError("HypothesisSupport.reason_code cannot be empty")
        if not detail:
            raise ValueError("HypothesisSupport.detail cannot be empty")
        object.__setattr__(self, "rule_code", rule_code)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "detail", detail)


@dataclass(frozen=True, slots=True)
class RuleExecutionLog:
    execution_id: EntityId
    rule_code: str
    rule_name: str
    priority: int
    input_candidate_id: EntityId
    input_candidate_kind: str
    outcome: str
    reason_codes: tuple[str, ...] = ()
    details: tuple[tuple[str, str], ...] = ()
    hypothesis_id: EntityId | None = None

    def __post_init__(self) -> None:
        rule_code = self.rule_code.strip()
        rule_name = self.rule_name.strip()
        input_candidate_kind = self.input_candidate_kind.strip()
        outcome = self.outcome.strip().lower()
        if not rule_code:
            raise ValueError("RuleExecutionLog.rule_code cannot be empty")
        if not rule_name:
            raise ValueError("RuleExecutionLog.rule_name cannot be empty")
        if self.priority < 0:
            raise ValueError("RuleExecutionLog.priority cannot be negative")
        if not input_candidate_kind:
            raise ValueError("RuleExecutionLog.input_candidate_kind cannot be empty")
        if not outcome:
            raise ValueError("RuleExecutionLog.outcome cannot be empty")
        object.__setattr__(self, "rule_code", rule_code)
        object.__setattr__(self, "rule_name", rule_name)
        object.__setattr__(self, "input_candidate_kind", input_candidate_kind)
        object.__setattr__(self, "outcome", outcome)


@dataclass(frozen=True, slots=True)
class SemanticHypothesis:
    hypothesis_id: EntityId
    source_candidate_id: EntityId
    source_candidate_kind: str
    subject_table: str
    subject_id: EntityId
    predicate_code: str
    object_table: str | None
    object_id: EntityId | None
    status: SemanticHypothesisStatus
    score: float
    score_breakdown: tuple[tuple[str, float], ...]
    reason_codes: tuple[str, ...]
    created_at: datetime
    source_entity_candidate: NormalizedEntityCandidate | None = None
    source_relation_candidate: NormalizedRelationCandidate | None = None

    def __post_init__(self) -> None:
        source_candidate_kind = self.source_candidate_kind.strip()
        subject_table = self.subject_table.strip()
        predicate_code = self.predicate_code.strip().lower()
        if not source_candidate_kind:
            raise ValueError("SemanticHypothesis.source_candidate_kind cannot be empty")
        if not subject_table:
            raise ValueError("SemanticHypothesis.subject_table cannot be empty")
        if not predicate_code:
            raise ValueError("SemanticHypothesis.predicate_code cannot be empty")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("SemanticHypothesis.score must be between 0 and 1")
        if (self.object_table is None) != (self.object_id is None):
            raise ValueError("SemanticHypothesis.object_table and object_id must both be set or both be null")
        if (self.source_entity_candidate is None) == (self.source_relation_candidate is None):
            raise ValueError("SemanticHypothesis must reference exactly one source candidate object")
        source_candidate = self.source_entity_candidate or self.source_relation_candidate
        if source_candidate is None or source_candidate.candidate_id != self.source_candidate_id:
            raise ValueError("SemanticHypothesis.source_candidate_id must match the referenced source candidate")
        object.__setattr__(self, "source_candidate_kind", source_candidate_kind)
        object.__setattr__(self, "subject_table", subject_table)
        object.__setattr__(self, "predicate_code", predicate_code)


@dataclass(frozen=True, slots=True)
class SemanticResolutionRun:
    run_id: RunId
    normalization_run_id: RunId
    rule_pack_version: str
    started_at: datetime
    finished_at: datetime
    hypotheses: tuple[SemanticHypothesis, ...] = ()
    supports: tuple[HypothesisSupport, ...] = ()
    execution_logs: tuple[RuleExecutionLog, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rule_pack_version = self.rule_pack_version.strip()
        if not rule_pack_version:
            raise ValueError("SemanticResolutionRun.rule_pack_version cannot be empty")
        object.__setattr__(self, "rule_pack_version", rule_pack_version)