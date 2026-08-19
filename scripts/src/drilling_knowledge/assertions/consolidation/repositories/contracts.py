"""Repository contracts for fact consolidation runs."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactConsolidationRun, FactSupport
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId


class FactConsolidationRunRepository(Protocol):
    def get_run(self, run_id: RunId) -> FactConsolidationRun | None:
        ...

    def list_runs(self) -> tuple[FactConsolidationRun, ...]:
        ...

    def list_assertions(self, run_id: RunId) -> tuple[EvidenceAssertion, ...]:
        ...

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        ...

    def list_facts(self, run_id: RunId) -> tuple[ConsolidatedFact, ...]:
        ...

    def list_support_links(self, run_id: RunId) -> tuple[FactSupport, ...]:
        ...

    def get_fact(self, fact_id: EntityId) -> ConsolidatedFact | None:
        ...

    def append_run(self, run: FactConsolidationRun) -> "FactConsolidationRunRepository":
        ...