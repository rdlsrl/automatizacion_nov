"""In-memory append-only repository for search projection batches."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.search.domain import SearchProjectionBatch
from drilling_knowledge.projections.search.repositories.contracts import SearchProjectionBatchRepository


@dataclass(frozen=True, slots=True)
class InMemorySearchProjectionBatchRepository(SearchProjectionBatchRepository):
    batches: tuple[SearchProjectionBatch, ...] = ()
    _batches_by_id: dict[EntityId, SearchProjectionBatch] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        batches_by_id: dict[EntityId, SearchProjectionBatch] = {}
        for batch in self.batches:
            existing = batches_by_id.get(batch.projection_batch_id)
            if existing is not None and existing != batch:
                raise ConflictError(
                    code="duplicate_search_projection_batch",
                    message="A different search projection batch already exists for the same projection batch id",
                    context={"projection_batch_id": str(batch.projection_batch_id)},
                )
            batches_by_id[batch.projection_batch_id] = batch
        object.__setattr__(self, "_batches_by_id", batches_by_id)

    def get_batch(self, projection_batch_id: EntityId) -> SearchProjectionBatch | None:
        return self._batches_by_id.get(projection_batch_id)

    def list_batches(self) -> tuple[SearchProjectionBatch, ...]:
        return self.batches

    def append_batch(self, batch: SearchProjectionBatch) -> "InMemorySearchProjectionBatchRepository":
        existing = self._batches_by_id.get(batch.projection_batch_id)
        if existing is not None:
            if existing != batch:
                raise ConflictError(
                    code="duplicate_search_projection_batch",
                    message="A different search projection batch already exists for the same projection batch id",
                    context={"projection_batch_id": str(batch.projection_batch_id)},
                )
            return self
        return InMemorySearchProjectionBatchRepository(self.batches + (batch,))