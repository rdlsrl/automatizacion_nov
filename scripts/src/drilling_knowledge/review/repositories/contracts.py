"""Repository contracts for review queues and human decisions."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.review.domain import ReviewDecision, ReviewQueueItem, ReviewTargetType


class ReviewRepository(Protocol):
    def get_queue(self, queue_id: EntityId) -> ReviewQueueItem | None:
        ...

    def get_open_queue(self, target_type: ReviewTargetType, target_id: EntityId) -> ReviewQueueItem | None:
        ...

    def list_queues(self) -> tuple[ReviewQueueItem, ...]:
        ...

    def list_open_queues(self) -> tuple[ReviewQueueItem, ...]:
        ...

    def get_decision(self, decision_id: EntityId) -> ReviewDecision | None:
        ...

    def get_queue_decision(self, queue_id: EntityId) -> ReviewDecision | None:
        ...

    def list_decisions(self) -> tuple[ReviewDecision, ...]:
        ...

    def append_queue(self, queue: ReviewQueueItem) -> ReviewRepository:
        ...

    def append_decision(self, decision: ReviewDecision) -> ReviewRepository:
        ...