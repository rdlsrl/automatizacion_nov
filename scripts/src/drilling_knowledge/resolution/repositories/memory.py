"""In-memory repositories for semantic resolution runs."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.resolution.domain import HypothesisSupport, RuleExecutionLog, SemanticHypothesis, SemanticResolutionRun
from drilling_knowledge.resolution.repositories.contracts import SemanticResolutionRunRepository


@dataclass(frozen=True, slots=True)
class InMemorySemanticResolutionRunRepository(SemanticResolutionRunRepository):
    runs: tuple[SemanticResolutionRun, ...] = ()
    _runs_by_id: dict[RunId, SemanticResolutionRun] = field(init=False, default_factory=dict)
    _hypotheses_by_run: dict[RunId, tuple[SemanticHypothesis, ...]] = field(init=False, default_factory=dict)
    _supports_by_run: dict[RunId, tuple[HypothesisSupport, ...]] = field(init=False, default_factory=dict)
    _logs_by_run: dict[RunId, tuple[RuleExecutionLog, ...]] = field(init=False, default_factory=dict)
    _hypotheses_by_id: dict[EntityId, SemanticHypothesis] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, SemanticResolutionRun] = {}
        hypotheses_by_run: dict[RunId, tuple[SemanticHypothesis, ...]] = {}
        supports_by_run: dict[RunId, tuple[HypothesisSupport, ...]] = {}
        logs_by_run: dict[RunId, tuple[RuleExecutionLog, ...]] = {}
        hypotheses_by_id: dict[EntityId, SemanticHypothesis] = {}
        ordered = tuple(sorted(self.runs, key=self._sort_key))
        for run in ordered:
            existing = runs_by_id.get(run.run_id)
            if existing is not None and existing != run:
                raise ConflictError(
                    code="duplicate_semantic_resolution_run",
                    message="A different semantic resolution run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            self._validate_references(run)
            runs_by_id[run.run_id] = run
            hypotheses_by_run[run.run_id] = run.hypotheses
            supports_by_run[run.run_id] = run.supports
            logs_by_run[run.run_id] = run.execution_logs
            for hypothesis in run.hypotheses:
                existing_hypothesis = hypotheses_by_id.get(hypothesis.hypothesis_id)
                if existing_hypothesis is not None and existing_hypothesis != hypothesis:
                    raise ConflictError(
                        code="duplicate_semantic_hypothesis",
                        message="A different semantic hypothesis already exists for the same hypothesis id",
                        context={"hypothesis_id": str(hypothesis.hypothesis_id)},
                    )
                hypotheses_by_id[hypothesis.hypothesis_id] = hypothesis
        object.__setattr__(self, "runs", ordered)
        object.__setattr__(self, "_runs_by_id", runs_by_id)
        object.__setattr__(self, "_hypotheses_by_run", hypotheses_by_run)
        object.__setattr__(self, "_supports_by_run", supports_by_run)
        object.__setattr__(self, "_logs_by_run", logs_by_run)
        object.__setattr__(self, "_hypotheses_by_id", hypotheses_by_id)

    def get_run(self, run_id: RunId) -> SemanticResolutionRun | None:
        return self._runs_by_id.get(run_id)

    def list_runs(self) -> tuple[SemanticResolutionRun, ...]:
        return self.runs

    def list_hypotheses(self, run_id: RunId) -> tuple[SemanticHypothesis, ...]:
        return self._hypotheses_by_run.get(run_id, ())

    def list_supports(self, run_id: RunId) -> tuple[HypothesisSupport, ...]:
        return self._supports_by_run.get(run_id, ())

    def list_execution_logs(self, run_id: RunId) -> tuple[RuleExecutionLog, ...]:
        return self._logs_by_run.get(run_id, ())

    def get_hypothesis(self, hypothesis_id: EntityId) -> SemanticHypothesis | None:
        return self._hypotheses_by_id.get(hypothesis_id)

    def append_run(self, run: SemanticResolutionRun) -> "InMemorySemanticResolutionRunRepository":
        existing = self._runs_by_id.get(run.run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_semantic_resolution_run",
                    message="A different semantic resolution run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            return self
        return InMemorySemanticResolutionRunRepository(self.runs + (run,))

    def _validate_references(self, run: SemanticResolutionRun) -> None:
        hypothesis_ids = {hypothesis.hypothesis_id for hypothesis in run.hypotheses}
        candidate_ids = {hypothesis.source_candidate_id for hypothesis in run.hypotheses}
        for support in run.supports:
            if support.hypothesis_id not in hypothesis_ids:
                raise ConflictError(
                    code="semantic_support_missing_hypothesis",
                    message="Hypothesis support references an unknown hypothesis id",
                    context={"run_id": str(run.run_id), "hypothesis_id": str(support.hypothesis_id)},
                )
            if support.source_candidate_id not in candidate_ids:
                raise ConflictError(
                    code="semantic_support_missing_candidate",
                    message="Hypothesis support references an unknown source candidate id",
                    context={"run_id": str(run.run_id), "source_candidate_id": str(support.source_candidate_id)},
                )
        for log in run.execution_logs:
            if log.hypothesis_id is not None and log.hypothesis_id not in hypothesis_ids:
                raise ConflictError(
                    code="semantic_log_missing_hypothesis",
                    message="Rule execution log references an unknown hypothesis id",
                    context={"run_id": str(run.run_id), "hypothesis_id": str(log.hypothesis_id)},
                )

    @staticmethod
    def _sort_key(run: SemanticResolutionRun) -> tuple[str, str]:
        return (run.finished_at.isoformat(), str(run.run_id))