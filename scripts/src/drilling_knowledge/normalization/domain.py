"""Deterministic normalization domain over extracted mentions and observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractedEntity, ExtractedEntityType, ExtractedObservation


class NormalizationRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class NormalizationCandidateStatus(StrEnum):
    RESOLVED = "resolved"
    ALTERNATIVE = "alternative"
    PROPOSED = "proposed"


class NormalizationMatchMethod(StrEnum):
    EXACT_NAME = "exact_name"
    EXACT_CODE = "exact_code"
    EXACT_SYMBOL = "exact_symbol"
    EXPLICIT_ALIAS = "explicit_alias"
    MNEMONIC_ALIAS = "mnemonic_alias"
    TAG_PATTERN = "tag_pattern"
    MODEL_SCOPE = "model_scope"
    VENDOR_SCOPE = "vendor_scope"
    NO_CATALOG_MATCH = "no_catalog_match"
    UNSUPPORTED_ENTITY_TYPE = "unsupported_entity_type"
    COMPATIBLE_QUANTITY_UNIT = "compatible_quantity_unit"
    INCOMPATIBLE_QUANTITY_UNIT = "incompatible_quantity_unit"
    EXPLICIT_SCALING_LITERAL = "explicit_scaling_literal"
    EXPLICIT_RELATION = "explicit_relation"


@dataclass(frozen=True, slots=True)
class NormalizationEvidence:
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
            raise ValueError("NormalizationEvidence.matched_text cannot be empty")
        if not normalized_matched_text:
            raise ValueError("NormalizationEvidence.normalized_matched_text cannot be empty")
        if not source_field:
            raise ValueError("NormalizationEvidence.source_field cannot be empty")
        if not explanation:
            raise ValueError("NormalizationEvidence.explanation cannot be empty")
        object.__setattr__(self, "matched_text", matched_text)
        object.__setattr__(self, "normalized_matched_text", normalized_matched_text)
        object.__setattr__(self, "source_field", source_field)
        object.__setattr__(self, "explanation", explanation)


@dataclass(frozen=True, slots=True)
class NormalizedEntityCandidate:
    candidate_id: EntityId
    extraction_run_id: RunId
    candidate_mention_id: EntityId
    entity_type: ExtractedEntityType
    mention_text: str
    matched_table: str | None
    matched_id: EntityId | None
    canonical_text: str
    match_method: NormalizationMatchMethod
    normalization_score: float
    is_new_concept_proposal: bool
    status: NormalizationCandidateStatus
    created_at: datetime
    source_mention: ExtractedEntity
    evidence: NormalizationEvidence
    supporting_evidences: tuple[NormalizationEvidence, ...] = ()

    def __post_init__(self) -> None:
        mention_text = self.mention_text.strip()
        canonical_text = self.canonical_text.strip()
        if not mention_text:
            raise ValueError("NormalizedEntityCandidate.mention_text cannot be empty")
        if not canonical_text:
            raise ValueError("NormalizedEntityCandidate.canonical_text cannot be empty")
        if self.candidate_mention_id != self.source_mention.entity_id:
            raise ValueError("NormalizedEntityCandidate.candidate_mention_id must match source_mention.entity_id")
        if not 0.0 <= self.normalization_score <= 1.0:
            raise ValueError("NormalizedEntityCandidate.normalization_score must be between 0 and 1")
        if (self.matched_table is None) != (self.matched_id is None):
            raise ValueError("NormalizedEntityCandidate.matched_table and matched_id must both be set or both be null")
        if self.status == NormalizationCandidateStatus.PROPOSED:
            if self.matched_table is not None or self.matched_id is not None:
                raise ValueError("Proposed candidates cannot point to a matched catalog record")
            if not self.is_new_concept_proposal:
                raise ValueError("Proposed candidates must be marked as new concept proposals")
        if self.status != NormalizationCandidateStatus.PROPOSED and self.matched_id is None:
            raise ValueError("Resolved or alternative candidates must point to a matched catalog record")
        object.__setattr__(self, "mention_text", mention_text)
        object.__setattr__(self, "canonical_text", canonical_text)


@dataclass(frozen=True, slots=True)
class NormalizedRelationCandidate:
    candidate_id: EntityId
    extraction_run_id: RunId
    candidate_relation_id: EntityId
    predicate_code: str
    normalized_subject_table: str
    normalized_subject_id: EntityId
    normalized_object_table: str | None
    normalized_object_id: EntityId | None
    normalization_score: float
    status: NormalizationCandidateStatus
    created_at: datetime
    source_observation: ExtractedObservation
    attributes: tuple[tuple[str, str], ...] = ()
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        predicate_code = self.predicate_code.strip().lower()
        normalized_subject_table = self.normalized_subject_table.strip()
        if not predicate_code:
            raise ValueError("NormalizedRelationCandidate.predicate_code cannot be empty")
        if not normalized_subject_table:
            raise ValueError("NormalizedRelationCandidate.normalized_subject_table cannot be empty")
        if self.candidate_relation_id != self.source_observation.observation_id:
            raise ValueError("NormalizedRelationCandidate.candidate_relation_id must match source_observation.observation_id")
        if not 0.0 <= self.normalization_score <= 1.0:
            raise ValueError("NormalizedRelationCandidate.normalization_score must be between 0 and 1")
        if (self.normalized_object_table is None) != (self.normalized_object_id is None):
            raise ValueError(
                "NormalizedRelationCandidate.normalized_object_table and normalized_object_id must both be set or both be null"
            )
        object.__setattr__(self, "predicate_code", predicate_code)
        object.__setattr__(self, "normalized_subject_table", normalized_subject_table)


@dataclass(frozen=True, slots=True)
class NormalizationRun:
    run_id: RunId
    extraction_run_id: RunId
    ontology_version: str
    rule_pack_version: str
    started_at: datetime
    finished_at: datetime
    status: NormalizationRunStatus
    entity_candidates: tuple[NormalizedEntityCandidate, ...] = ()
    relation_candidates: tuple[NormalizedRelationCandidate, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ontology_version = self.ontology_version.strip()
        rule_pack_version = self.rule_pack_version.strip()
        if not ontology_version:
            raise ValueError("NormalizationRun.ontology_version cannot be empty")
        if not rule_pack_version:
            raise ValueError("NormalizationRun.rule_pack_version cannot be empty")
        object.__setattr__(self, "ontology_version", ontology_version)
        object.__setattr__(self, "rule_pack_version", rule_pack_version)
