"""In-memory normalization repositories."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import RunId
from drilling_knowledge.normalization.domain import NormalizationRun
from drilling_knowledge.normalization.repositories.contracts import NormalizationRunRepository


@dataclass(frozen=True, slots=True)
class InMemoryNormalizationRunRepository(NormalizationRunRepository):
    runs: tuple[NormalizationRun, ...] = ()
    _runs_by_id: dict[RunId, NormalizationRun] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, NormalizationRun] = {}
        ordered = tuple(sorted(self.runs, key=self._sort_key))
        for run in ordered:
            existing = runs_by_id.get(run.run_id)
            if existing is not None and existing != run:
                raise ConflictError(
                    code="duplicate_normalization_run",
                    message="A different normalization run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            runs_by_id[run.run_id] = run
        object.__setattr__(self, "runs", ordered)
        object.__setattr__(self, "_runs_by_id", runs_by_id)

    def get_run(self, run_id: RunId) -> NormalizationRun | None:
        return self._runs_by_id.get(run_id)

    def list_runs(self) -> tuple[NormalizationRun, ...]:
        return self.runs

    def append_run(self, run: NormalizationRun) -> "InMemoryNormalizationRunRepository":
        existing = self._runs_by_id.get(run.run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_normalization_run",
                    message="A different normalization run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            return self
        return InMemoryNormalizationRunRepository(self.runs + (run,))

    @staticmethod
    def _sort_key(run: NormalizationRun) -> tuple[str, str]:
        return (run.finished_at.isoformat(), str(run.run_id))
