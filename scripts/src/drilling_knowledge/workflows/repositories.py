"""Append-only workflow run repository."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import RunId
from drilling_knowledge.workflows.domain import PipelineRun


@dataclass(frozen=True, slots=True)
class InMemoryWorkflowRunRepository:
    runs: tuple[PipelineRun, ...] = ()
    _runs_by_id: dict[RunId, PipelineRun] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, PipelineRun] = {}
        ordered = tuple(sorted(self.runs, key=lambda run: (run.finished_at.isoformat(), str(run.pipeline_run_id))))
        for run in ordered:
            existing = runs_by_id.get(run.pipeline_run_id)
            if existing is not None and existing != run:
                raise ConflictError(
                    code="duplicate_workflow_run",
                    message="A different workflow run already exists for the same pipeline_run_id",
                    context={"pipeline_run_id": str(run.pipeline_run_id)},
                )
            runs_by_id[run.pipeline_run_id] = run
        object.__setattr__(self, "runs", ordered)
        object.__setattr__(self, "_runs_by_id", runs_by_id)

    @classmethod
    def empty(cls) -> "InMemoryWorkflowRunRepository":
        return cls(())

    def get_run(self, pipeline_run_id: RunId) -> PipelineRun | None:
        return self._runs_by_id.get(pipeline_run_id)

    def list_runs(self) -> tuple[PipelineRun, ...]:
        return self.runs

    def append_run(self, run: PipelineRun) -> "InMemoryWorkflowRunRepository":
        existing = self._runs_by_id.get(run.pipeline_run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_workflow_run",
                    message="A different workflow run already exists for the same pipeline_run_id",
                    context={"pipeline_run_id": str(run.pipeline_run_id)},
                )
            return self
        return InMemoryWorkflowRunRepository(self.runs + (run,))