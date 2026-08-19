"""Repository contracts for evidence assertion runs."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionGenerationRun, AssertionValidationLog, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId


class AssertionGenerationRunRepository(Protocol):
    def get_run(self, run_id: RunId) -> AssertionGenerationRun | None:
        ...

    def list_runs(self) -> tuple[AssertionGenerationRun, ...]:
        ...

    def list_assertions(self, run_id: RunId) -> tuple[EvidenceAssertion, ...]:
        ...

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        ...

    def list_validation_logs(self, run_id: RunId) -> tuple[AssertionValidationLog, ...]:
        ...

    def get_assertion(self, assertion_id: EntityId) -> EvidenceAssertion | None:
        ...

    def append_run(self, run: AssertionGenerationRun) -> "AssertionGenerationRunRepository":
        ...