"""Repository contracts for ontology proposal runs."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.catalog.services.ontology_proposals.domain import OntologyChangeProposal, OntologyProposalEvidence, OntologyProposalRun
from drilling_knowledge.common.ids import EntityId, RunId


class OntologyProposalRunRepository(Protocol):
    def get_run(self, run_id: RunId) -> OntologyProposalRun | None:
        ...

    def list_runs(self) -> tuple[OntologyProposalRun, ...]:
        ...

    def list_proposals(self, run_id: RunId) -> tuple[OntologyChangeProposal, ...]:
        ...

    def list_proposal_evidences(self, run_id: RunId) -> tuple[OntologyProposalEvidence, ...]:
        ...

    def get_proposal(self, proposal_id: EntityId) -> OntologyChangeProposal | None:
        ...

    def append_run(self, run: OntologyProposalRun) -> "OntologyProposalRunRepository":
        ...