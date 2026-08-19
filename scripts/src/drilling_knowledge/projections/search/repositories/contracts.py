"""Repository contracts for search projection batches."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.search.domain import SearchProjectionBatch


class SearchProjectionBatchRepository(Protocol):
    def get_batch(self, projection_batch_id: EntityId) -> SearchProjectionBatch | None:
        ...

    def list_batches(self) -> tuple[SearchProjectionBatch, ...]:
        ...

    def append_batch(self, batch: SearchProjectionBatch) -> "SearchProjectionBatchRepository":
        ...