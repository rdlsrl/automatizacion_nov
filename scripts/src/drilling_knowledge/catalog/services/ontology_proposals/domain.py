"""Domain objects for deterministic ontology change proposal generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactSupport
from drilling_knowledge.assertions.conflict_resolution.domain import AssertionConflictSet
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.normalization.domain import NormalizedEntityCandidate, NormalizationRun


class OntologyProposalStatus(StrEnum):
    QUEUED = "queued"
    APPROVED = "approved"
    REJECTED = "rejected"


class OntologyProposalRunOutcome(StrEnum):
    PROPOSAL_QUEUED = "proposal_queued"
    NO_OP = "no_op"


@dataclass(frozen=True, slots=True)
class OntologyProposalProvenance:
    document_id: EntityId
    document_version_id: EntityId
    fragment_id: EntityId


@dataclass(frozen=True, slots=True)
class OntologyChangeProposal:
    proposal_id: EntityId
    proposal_type: str
    proposal_status: OntologyProposalStatus
    target_entity: tuple[tuple[str, str], ...]
    proposed_change: tuple[tuple[str, str], ...]
    rationale: str
    impact_summary: tuple[tuple[str, str], ...]
    created_at: datetime
    revision: int
    evidence_ids: tuple[EntityId, ...] = ()

    def __post_init__(self) -> None:
        proposal_type = self.proposal_type.strip().lower()
        rationale = self.rationale.strip()
        if not proposal_type:
            raise ValueError("OntologyChangeProposal.proposal_type cannot be empty")
        if not self.target_entity:
            raise ValueError("OntologyChangeProposal.target_entity cannot be empty")
        if len(set(self.target_entity)) != len(self.target_entity):
            raise ValueError("OntologyChangeProposal.target_entity cannot contain duplicates")
        if not self.proposed_change:
            raise ValueError("OntologyChangeProposal.proposed_change cannot be empty")
        if len(set(self.proposed_change)) != len(self.proposed_change):
            raise ValueError("OntologyChangeProposal.proposed_change cannot contain duplicates")
        if not rationale:
            raise ValueError("OntologyChangeProposal.rationale cannot be empty")
        if not self.impact_summary:
            raise ValueError("OntologyChangeProposal.impact_summary cannot be empty")
        if len(set(self.impact_summary)) != len(self.impact_summary):
            raise ValueError("OntologyChangeProposal.impact_summary cannot contain duplicates")
        if self.revision < 1:
            raise ValueError("OntologyChangeProposal.revision must be >= 1")
        if not self.evidence_ids:
            raise ValueError("OntologyChangeProposal.evidence_ids cannot be empty")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("OntologyChangeProposal.evidence_ids cannot contain duplicates")
        object.__setattr__(self, "proposal_type", proposal_type)
        object.__setattr__(self, "rationale", rationale)

    def transition_to(self, status: OntologyProposalStatus) -> "OntologyChangeProposal":
        if status == self.proposal_status:
            return self
        if self.proposal_status != OntologyProposalStatus.QUEUED:
            raise ValueError("Ontology proposals can only transition from queued state")
        return replace(self, proposal_status=status)


@dataclass(frozen=True, slots=True)
class OntologyProposalEvidence:
    proposal_evidence_id: EntityId
    proposal_id: EntityId
    consolidated_fact_ids: tuple[EntityId, ...]
    fact_support_ids: tuple[EntityId, ...]
    conflict_set_ids: tuple[EntityId, ...]
    assertion_ids: tuple[EntityId, ...]
    evidence_bundle: tuple[EntityId, ...]
    provenance: tuple[OntologyProposalProvenance, ...]

    def __post_init__(self) -> None:
        for field_name in ("evidence_bundle", "provenance"):
            values = getattr(self, field_name)
            if not values:
                raise ValueError(f"OntologyProposalEvidence.{field_name} cannot be empty")
            if len(set(values)) != len(values):
                raise ValueError(f"OntologyProposalEvidence.{field_name} cannot contain duplicates")
        if len(set(self.conflict_set_ids)) != len(self.conflict_set_ids):
            raise ValueError("OntologyProposalEvidence.conflict_set_ids cannot contain duplicates")
        for field_name in ("consolidated_fact_ids", "fact_support_ids", "assertion_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"OntologyProposalEvidence.{field_name} cannot contain duplicates")


@dataclass(frozen=True, slots=True)
class OntologyProposalMetrics:
    proposed_normalization_candidates: int
    recurring_pattern_groups: int
    recurring_conflict_groups: int
    repeated_manual_decision_groups: int
    proposals_created: int
    proposals_reused: int
    no_op_outputs: int

    def __post_init__(self) -> None:
        for field_name in (
            "proposed_normalization_candidates",
            "recurring_pattern_groups",
            "recurring_conflict_groups",
            "repeated_manual_decision_groups",
            "proposals_created",
            "proposals_reused",
            "no_op_outputs",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"OntologyProposalMetrics.{field_name} cannot be negative")


@dataclass(frozen=True, slots=True)
class OntologyProposalRun:
    run_id: RunId
    fact_consolidation_run_id: RunId
    conflict_resolution_run_id: RunId
    normalization_run_id: RunId | None
    rule_pack_version: str
    started_at: datetime
    finished_at: datetime
    outcome: OntologyProposalRunOutcome
    normalization_run: NormalizationRun | None
    normalization_candidates: tuple[NormalizedEntityCandidate, ...]
    assertions: tuple[EvidenceAssertion, ...]
    evidence_links: tuple[AssertionEvidenceLink, ...]
    facts: tuple[ConsolidatedFact, ...]
    fact_supports: tuple[FactSupport, ...]
    conflict_sets: tuple[AssertionConflictSet, ...]
    proposals: tuple[OntologyChangeProposal, ...]
    proposal_evidences: tuple[OntologyProposalEvidence, ...]
    metrics: OntologyProposalMetrics
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rule_pack_version = self.rule_pack_version.strip()
        if not rule_pack_version:
            raise ValueError("OntologyProposalRun.rule_pack_version cannot be empty")
        if self.finished_at < self.started_at:
            raise ValueError("OntologyProposalRun.finished_at cannot be before started_at")
        if self.normalization_run is None and self.normalization_run_id is not None:
            raise ValueError("OntologyProposalRun.normalization_run_id requires normalization_run")
        if self.normalization_run is not None and self.normalization_run_id != self.normalization_run.run_id:
            raise ValueError("OntologyProposalRun.normalization_run_id must match normalization_run.run_id")
        object.__setattr__(self, "rule_pack_version", rule_pack_version)