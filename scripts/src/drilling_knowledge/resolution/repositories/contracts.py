"""Repository contracts for semantic resolution runs."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.resolution.domain import HypothesisSupport, RuleExecutionLog, SemanticHypothesis, SemanticResolutionRun


class SemanticResolutionRunRepository(Protocol):
    def get_run(self, run_id: RunId) -> SemanticResolutionRun | None:
        ...

    def list_runs(self) -> tuple[SemanticResolutionRun, ...]:
        ...

    def list_hypotheses(self, run_id: RunId) -> tuple[SemanticHypothesis, ...]:
        ...

    def list_supports(self, run_id: RunId) -> tuple[HypothesisSupport, ...]:
        ...

    def list_execution_logs(self, run_id: RunId) -> tuple[RuleExecutionLog, ...]:
        ...

    def get_hypothesis(self, hypothesis_id: EntityId) -> SemanticHypothesis | None:
        ...

    def append_run(self, run: SemanticResolutionRun) -> "SemanticResolutionRunRepository":
        ...