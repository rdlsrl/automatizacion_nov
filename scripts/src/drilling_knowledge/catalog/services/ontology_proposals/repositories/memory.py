"""In-memory append-only repository for ontology proposal runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from drilling_knowledge.catalog.services.ontology_proposals.domain import OntologyChangeProposal, OntologyProposalEvidence, OntologyProposalRun
from drilling_knowledge.catalog.services.ontology_proposals.repositories.contracts import OntologyProposalRunRepository
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId


@dataclass(frozen=True, slots=True)
class InMemoryOntologyProposalRunRepository(OntologyProposalRunRepository):
    runs: tuple[OntologyProposalRun, ...] = ()
    _runs_by_id: dict[RunId, OntologyProposalRun] = field(init=False, default_factory=dict)
    _proposals_by_run: dict[RunId, tuple[OntologyChangeProposal, ...]] = field(init=False, default_factory=dict)
    _evidences_by_run: dict[RunId, tuple[OntologyProposalEvidence, ...]] = field(init=False, default_factory=dict)
    _proposals_by_id: dict[EntityId, OntologyChangeProposal] = field(init=False, default_factory=dict)
    _evidences_by_id: dict[EntityId, OntologyProposalEvidence] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, OntologyProposalRun] = {}
        proposals_by_run: dict[RunId, tuple[OntologyChangeProposal, ...]] = {}
        evidences_by_run: dict[RunId, tuple[OntologyProposalEvidence, ...]] = {}
        proposals_by_id: dict[EntityId, OntologyChangeProposal] = {}
        evidences_by_id: dict[EntityId, OntologyProposalEvidence] = {}
        for run in self.runs:
            existing_run = runs_by_id.get(run.run_id)
            if existing_run is not None and existing_run != run:
                raise ConflictError(
                    code="duplicate_ontology_proposal_run",
                    message="A different ontology proposal run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            self._validate_references(run)
            runs_by_id[run.run_id] = run
            proposals_by_run[run.run_id] = run.proposals
            evidences_by_run[run.run_id] = run.proposal_evidences
            for proposal in run.proposals:
                existing = proposals_by_id.get(proposal.proposal_id)
                if existing is not None and existing != proposal:
                    raise ConflictError(
                        code="duplicate_ontology_change_proposal",
                        message="A different ontology change proposal already exists for the same proposal id",
                        context={"proposal_id": str(proposal.proposal_id)},
                    )
                proposals_by_id[proposal.proposal_id] = proposal
            for evidence in run.proposal_evidences:
                existing = evidences_by_id.get(evidence.proposal_evidence_id)
                if existing is not None and existing != evidence:
                    raise ConflictError(
                        code="duplicate_ontology_proposal_evidence",
                        message="A different ontology proposal evidence already exists for the same proposal_evidence_id",
                        context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                    )
                evidences_by_id[evidence.proposal_evidence_id] = evidence
        object.__setattr__(self, "runs", self.runs)
        object.__setattr__(self, "_runs_by_id", runs_by_id)
        object.__setattr__(self, "_proposals_by_run", proposals_by_run)
        object.__setattr__(self, "_evidences_by_run", evidences_by_run)
        object.__setattr__(self, "_proposals_by_id", proposals_by_id)
        object.__setattr__(self, "_evidences_by_id", evidences_by_id)

    def get_run(self, run_id: RunId) -> OntologyProposalRun | None:
        return self._runs_by_id.get(run_id)

    def list_runs(self) -> tuple[OntologyProposalRun, ...]:
        return self.runs

    def list_proposals(self, run_id: RunId) -> tuple[OntologyChangeProposal, ...]:
        return self._proposals_by_run.get(run_id, ())

    def list_proposal_evidences(self, run_id: RunId) -> tuple[OntologyProposalEvidence, ...]:
        return self._evidences_by_run.get(run_id, ())

    def get_proposal(self, proposal_id: EntityId) -> OntologyChangeProposal | None:
        return self._proposals_by_id.get(proposal_id)

    def append_run(self, run: OntologyProposalRun) -> "InMemoryOntologyProposalRunRepository":
        existing = self._runs_by_id.get(run.run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_ontology_proposal_run",
                    message="A different ontology proposal run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            return self
        return InMemoryOntologyProposalRunRepository(self.runs + (run,))

    def _validate_references(self, run: OntologyProposalRun) -> None:
        fact_ids = {fact.fact_id for fact in run.facts}
        support_by_id = {support.fact_support_id: support for support in run.fact_supports}
        assertion_ids = {assertion.assertion_id for assertion in run.assertions}
        evidence_links_by_id = {link.link_id: link for link in run.evidence_links}
        normalization_candidates_by_id = {candidate.candidate_id: candidate for candidate in run.normalization_candidates}
        conflict_ids = {conflict_set.conflict_set_id for conflict_set in run.conflict_sets}
        proposal_ids = {proposal.proposal_id for proposal in run.proposals}
        evidence_ids_by_proposal: dict[EntityId, list[EntityId]] = defaultdict(list)
        seen_evidence_ids: set[EntityId] = set()

        for evidence in run.proposal_evidences:
            if evidence.proposal_id not in proposal_ids:
                raise ConflictError(
                    code="proposal_evidence_missing_proposal",
                    message="Ontology proposal evidence references an unknown proposal id",
                    context={"proposal_id": str(evidence.proposal_id)},
                )
            if evidence.proposal_evidence_id in seen_evidence_ids:
                raise ConflictError(
                    code="duplicate_proposal_evidence",
                    message="Ontology proposal evidence cannot reuse the same proposal_evidence_id",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            seen_evidence_ids.add(evidence.proposal_evidence_id)
            if not set(evidence.consolidated_fact_ids).issubset(fact_ids):
                raise ConflictError(
                    code="proposal_evidence_missing_fact",
                    message="Ontology proposal evidence references an unknown consolidated fact id",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            if not set(evidence.fact_support_ids).issubset(support_by_id):
                raise ConflictError(
                    code="proposal_evidence_missing_support",
                    message="Ontology proposal evidence references an unknown fact support id",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            if not set(evidence.assertion_ids).issubset(assertion_ids):
                raise ConflictError(
                    code="proposal_evidence_missing_assertion",
                    message="Ontology proposal evidence references an unknown assertion id",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            if not set(evidence.conflict_set_ids).issubset(conflict_ids):
                raise ConflictError(
                    code="proposal_evidence_missing_conflict_set",
                    message="Ontology proposal evidence references an unknown conflict set id",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            if not set(evidence.evidence_bundle).issubset(set(evidence_links_by_id) | set(normalization_candidates_by_id)):
                raise ConflictError(
                    code="proposal_evidence_missing_link",
                    message="Ontology proposal evidence references an unknown evidence bundle id",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            expected_provenance = {
                self._provenance_tuple(link_id, evidence_links_by_id, normalization_candidates_by_id)
                for link_id in evidence.evidence_bundle
            }
            actual_provenance = {
                (item.document_id, item.document_version_id, item.fragment_id)
                for item in evidence.provenance
            }
            if actual_provenance != expected_provenance:
                raise ConflictError(
                    code="proposal_evidence_provenance_mismatch",
                    message="Ontology proposal provenance must match the linked assertion evidence provenance",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            support_fact_ids = {support_by_id[support_id].fact_id for support_id in evidence.fact_support_ids}
            if evidence.fact_support_ids and support_fact_ids != set(evidence.consolidated_fact_ids):
                raise ConflictError(
                    code="proposal_evidence_fact_support_mismatch",
                    message="Ontology proposal evidence must preserve the exact fact-to-support linkage",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            support_assertion_ids = {support_by_id[support_id].assertion_id for support_id in evidence.fact_support_ids}
            if evidence.fact_support_ids and support_assertion_ids != set(evidence.assertion_ids):
                raise ConflictError(
                    code="proposal_evidence_assertion_mismatch",
                    message="Ontology proposal evidence must preserve the exact support-to-assertion linkage",
                    context={"proposal_evidence_id": str(evidence.proposal_evidence_id)},
                )
            evidence_ids_by_proposal[evidence.proposal_id].append(evidence.proposal_evidence_id)

        for proposal in run.proposals:
            linked_evidence_ids = tuple(sorted(evidence_ids_by_proposal.get(proposal.proposal_id, ()), key=str))
            if not linked_evidence_ids:
                raise ConflictError(
                    code="proposal_missing_evidence",
                    message="Ontology change proposals must reference at least one evidence bundle",
                    context={"proposal_id": str(proposal.proposal_id)},
                )
            if linked_evidence_ids != tuple(sorted(proposal.evidence_ids, key=str)):
                raise ConflictError(
                    code="proposal_evidence_set_mismatch",
                    message="Ontology change proposals must match the persisted evidence collection",
                    context={"proposal_id": str(proposal.proposal_id)},
                )

    @staticmethod
    def _provenance_tuple(
        bundle_id: EntityId,
        evidence_links_by_id: dict[EntityId, object],
        normalization_candidates_by_id: dict[EntityId, object],
    ) -> tuple[EntityId, EntityId, EntityId]:
        link = evidence_links_by_id.get(bundle_id)
        if link is not None:
            return (link.document_id, link.document_version_id, link.fragment_id)
        candidate = normalization_candidates_by_id[bundle_id]
        return (candidate.source_mention.document_id, candidate.source_mention.version_id, candidate.source_mention.fragment_id)