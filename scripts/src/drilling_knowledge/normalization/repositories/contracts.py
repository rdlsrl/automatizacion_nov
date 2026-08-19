"""Repository contracts for normalization runs."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import RunId
from drilling_knowledge.normalization.domain import NormalizationRun


class NormalizationRunRepository(Protocol):
    def get_run(self, run_id: RunId) -> NormalizationRun | None:
        ...

    def list_runs(self) -> tuple[NormalizationRun, ...]:
        ...

    def append_run(self, run: NormalizationRun) -> "NormalizationRunRepository":
        ...
