"""Fact consolidation domain for versioned, append-only semantic facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId


class FactLifecycle(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class FactSupportRole(StrEnum):
    ACCEPTED_ASSERTION = "accepted_assertion"
    COEXISTENCE_CONTEXT = "coexistence_context"


@dataclass(frozen=True, slots=True)
class FactProvenance:
    document_id: EntityId
    document_version_id: EntityId
    fragment_id: EntityId


@dataclass(frozen=True, slots=True)
class ConsolidatedFact:
    fact_id: EntityId
    claim_key: str
    scope: str
    lifecycle: FactLifecycle
    version: int
    active_revision: bool
    supersedes_fact_id: EntityId | None
    created_at: datetime
    updated_at: datetime
    value_key: str
    subject_table: str
    subject_id: EntityId
    predicate_code: str
    object_table: str | None
    object_id: EntityId | None
    literal_value: tuple[tuple[str, str], ...]
    support_link_ids: tuple[EntityId, ...] = ()

    def __post_init__(self) -> None:
        claim_key = self.claim_key.strip()
        scope = self.scope.strip()
        subject_table = self.subject_table.strip()
        predicate_code = self.predicate_code.strip().lower()
        value_key = self.value_key.strip()
        if not claim_key:
            raise ValueError("ConsolidatedFact.claim_key cannot be empty")
        if not scope:
            raise ValueError("ConsolidatedFact.scope cannot be empty")
        if not subject_table:
            raise ValueError("ConsolidatedFact.subject_table cannot be empty")
        if not predicate_code:
            raise ValueError("ConsolidatedFact.predicate_code cannot be empty")
        if not value_key:
            raise ValueError("ConsolidatedFact.value_key cannot be empty")
        if self.version < 1:
            raise ValueError("ConsolidatedFact.version must be >= 1")
        if self.updated_at < self.created_at:
            raise ValueError("ConsolidatedFact.updated_at cannot be before created_at")
        if (self.object_table is None) != (self.object_id is None):
            raise ValueError("ConsolidatedFact.object_table and object_id must both be set or both be null")
        if self.object_id is None and not self.literal_value:
            raise ValueError("ConsolidatedFact must contain an object reference or a literal value")
        if len(set(self.support_link_ids)) != len(self.support_link_ids):
            raise ValueError("ConsolidatedFact.support_link_ids cannot contain duplicates")
        if not self.support_link_ids:
            raise ValueError("ConsolidatedFact.support_link_ids cannot be empty")
        if self.active_revision and self.lifecycle != FactLifecycle.ACTIVE:
            raise ValueError("Active revisions must have active lifecycle")
        if self.lifecycle == FactLifecycle.SUPERSEDED and self.active_revision:
            raise ValueError("Superseded revisions cannot remain active")
        if self.version == 1 and self.supersedes_fact_id is not None:
            raise ValueError("Version 1 facts cannot supersede a previous revision")
        if self.version > 1 and self.supersedes_fact_id is None:
            raise ValueError("Versioned fact revisions after v1 must reference supersedes_fact_id")
        if self.supersedes_fact_id == self.fact_id:
            raise ValueError("ConsolidatedFact.supersedes_fact_id cannot point to itself")
        object.__setattr__(self, "claim_key", claim_key)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "subject_table", subject_table)
        object.__setattr__(self, "predicate_code", predicate_code)
        object.__setattr__(self, "value_key", value_key)


@dataclass(frozen=True, slots=True)
class FactSupport:
    fact_support_id: EntityId
    fact_id: EntityId
    assertion_id: EntityId
    evidence_assertion_id: EntityId
    assertion_evidence_link_ids: tuple[EntityId, ...]
    hypothesis_support_ids: tuple[EntityId, ...]
    provenance: tuple[FactProvenance, ...]
    support_role: FactSupportRole
    created_at: datetime
    source_assertion: EvidenceAssertion

    def __post_init__(self) -> None:
        if self.assertion_id != self.evidence_assertion_id:
            raise ValueError("FactSupport.assertion_id and evidence_assertion_id must match")
        if self.assertion_id != self.source_assertion.assertion_id:
            raise ValueError("FactSupport.assertion_id must match source_assertion.assertion_id")
        if len(set(self.assertion_evidence_link_ids)) != len(self.assertion_evidence_link_ids):
            raise ValueError("FactSupport.assertion_evidence_link_ids cannot contain duplicates")
        if len(set(self.hypothesis_support_ids)) != len(self.hypothesis_support_ids):
            raise ValueError("FactSupport.hypothesis_support_ids cannot contain duplicates")
        if len(set(self.provenance)) != len(self.provenance):
            raise ValueError("FactSupport.provenance cannot contain duplicates")
        if not self.assertion_evidence_link_ids:
            raise ValueError("FactSupport.assertion_evidence_link_ids cannot be empty")
        if not self.hypothesis_support_ids:
            raise ValueError("FactSupport.hypothesis_support_ids cannot be empty")
        if not self.provenance:
            raise ValueError("FactSupport.provenance cannot be empty")


@dataclass(frozen=True, slots=True)
class FactConsolidationMetrics:
    candidate_assertions: int
    split_contexts: int
    facts_created: int
    facts_reused: int
    supports_created: int
    superseded_facts: int
    skipped_assertions: int

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_assertions",
            "split_contexts",
            "facts_created",
            "facts_reused",
            "supports_created",
            "superseded_facts",
            "skipped_assertions",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"FactConsolidationMetrics.{field_name} cannot be negative")


@dataclass(frozen=True, slots=True)
class FactConsolidationRun:
    run_id: RunId
    assertion_run_id: RunId
    conflict_resolution_run_id: RunId
    rule_pack_version: str
    started_at: datetime
    finished_at: datetime
    assertions: tuple[EvidenceAssertion, ...]
    evidence_links: tuple[AssertionEvidenceLink, ...]
    facts: tuple[ConsolidatedFact, ...]
    support_links: tuple[FactSupport, ...]
    metrics: FactConsolidationMetrics
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rule_pack_version = self.rule_pack_version.strip()
        if not rule_pack_version:
            raise ValueError("FactConsolidationRun.rule_pack_version cannot be empty")
        if self.finished_at < self.started_at:
            raise ValueError("FactConsolidationRun.finished_at cannot be before started_at")
        object.__setattr__(self, "rule_pack_version", rule_pack_version)