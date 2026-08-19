"""In-memory append-only repository for review operations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.review.domain import ReviewDecision, ReviewQueueItem, ReviewQueueStatus, ReviewTargetType
from drilling_knowledge.review.repositories.contracts import ReviewRepository


@dataclass(frozen=True, slots=True)
class InMemoryReviewRepository(ReviewRepository):
    queues: tuple[ReviewQueueItem, ...] | Iterable[ReviewQueueItem] = ()
    decisions: tuple[ReviewDecision, ...] | Iterable[ReviewDecision] = ()
    _queues_by_id: dict[EntityId, ReviewQueueItem] = field(init=False, default_factory=dict)
    _open_queue_by_target: dict[tuple[ReviewTargetType, EntityId], ReviewQueueItem] = field(init=False, default_factory=dict)
    _decisions_by_id: dict[EntityId, ReviewDecision] = field(init=False, default_factory=dict)
    _decision_by_queue: dict[EntityId, ReviewDecision] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        normalized_queues = tuple(sorted(tuple(self.queues), key=self._queue_sort_key))
        normalized_decisions = tuple(sorted(tuple(self.decisions), key=self._decision_sort_key))
        queues_by_id: dict[EntityId, ReviewQueueItem] = {}
        decisions_by_id: dict[EntityId, ReviewDecision] = {}
        decision_by_queue: dict[EntityId, ReviewDecision] = {}

        for queue in normalized_queues:
            existing = queues_by_id.get(queue.queue_id)
            if existing is not None and existing != queue:
                raise ConflictError(
                    code="duplicate_review_queue",
                    message="A different review queue item already exists for the same queue id",
                    context={"queue_id": str(queue.queue_id)},
                )
            if queue.status != ReviewQueueStatus.OPEN:
                raise ConflictError(
                    code="invalid_review_queue_status",
                    message="Persisted review queues must be append-only open records",
                    context={"queue_id": str(queue.queue_id), "status": queue.status.value},
                )
            queues_by_id[queue.queue_id] = queue

        open_queue_by_target = {(queue.target_type, queue.target_id): queue for queue in normalized_queues}
        if len(open_queue_by_target) != len(normalized_queues):
            raise ConflictError(
                code="duplicate_open_review_target",
                message="Only one open review queue may exist for a target",
            )

        for decision in normalized_decisions:
            existing = decisions_by_id.get(decision.decision_id)
            if existing is not None and existing != decision:
                raise ConflictError(
                    code="duplicate_review_decision",
                    message="A different review decision already exists for the same decision id",
                    context={"decision_id": str(decision.decision_id)},
                )
            queue = queues_by_id.get(decision.review_queue_id)
            if queue is None:
                raise ConflictError(
                    code="review_decision_missing_queue",
                    message="Review decision references an unknown review queue",
                    context={"review_queue_id": str(decision.review_queue_id)},
                )
            if decision.target_type != queue.target_type or decision.target_id != queue.target_id:
                raise ConflictError(
                    code="review_decision_target_mismatch",
                    message="Review decision target must match the queue target",
                    context={"review_queue_id": str(decision.review_queue_id)},
                )
            existing_queue_decision = decision_by_queue.get(decision.review_queue_id)
            if existing_queue_decision is not None and existing_queue_decision != decision:
                raise ConflictError(
                    code="duplicate_review_queue_decision",
                    message="A queue cannot have multiple different decisions",
                    context={"review_queue_id": str(decision.review_queue_id)},
                )
            decisions_by_id[decision.decision_id] = decision
            decision_by_queue[decision.review_queue_id] = decision

        object.__setattr__(self, "queues", normalized_queues)
        object.__setattr__(self, "decisions", normalized_decisions)
        object.__setattr__(self, "_queues_by_id", queues_by_id)
        object.__setattr__(self, "_open_queue_by_target", {pair: queue for pair, queue in open_queue_by_target.items() if queue.queue_id not in decision_by_queue})
        object.__setattr__(self, "_decisions_by_id", decisions_by_id)
        object.__setattr__(self, "_decision_by_queue", decision_by_queue)

    @classmethod
    def empty(cls) -> "InMemoryReviewRepository":
        return cls((), ())

    def get_queue(self, queue_id: EntityId) -> ReviewQueueItem | None:
        return self._queues_by_id.get(queue_id)

    def get_open_queue(self, target_type: ReviewTargetType, target_id: EntityId) -> ReviewQueueItem | None:
        return self._open_queue_by_target.get((target_type, target_id))

    def list_queues(self) -> tuple[ReviewQueueItem, ...]:
        return self.queues

    def list_open_queues(self) -> tuple[ReviewQueueItem, ...]:
        return tuple(sorted(self._open_queue_by_target.values(), key=self._queue_sort_key))

    def get_decision(self, decision_id: EntityId) -> ReviewDecision | None:
        return self._decisions_by_id.get(decision_id)

    def get_queue_decision(self, queue_id: EntityId) -> ReviewDecision | None:
        return self._decision_by_queue.get(queue_id)

    def list_decisions(self) -> tuple[ReviewDecision, ...]:
        return self.decisions

    def append_queue(self, queue: ReviewQueueItem) -> "InMemoryReviewRepository":
        existing = self._queues_by_id.get(queue.queue_id)
        if existing is not None:
            if existing != queue:
                raise ConflictError(
                    code="duplicate_review_queue",
                    message="A different review queue item already exists for the same queue id",
                    context={"queue_id": str(queue.queue_id)},
                )
            return self
        if self.get_open_queue(queue.target_type, queue.target_id) is not None:
            raise ConflictError(
                code="duplicate_open_review_target",
                message="Only one open review queue may exist for a target",
                context={"target_type": queue.target_type.value, "target_id": str(queue.target_id)},
            )
        return InMemoryReviewRepository(self.queues + (queue,), self.decisions)

    def append_decision(self, decision: ReviewDecision) -> "InMemoryReviewRepository":
        existing = self._decisions_by_id.get(decision.decision_id)
        if existing is not None:
            if existing != decision:
                raise ConflictError(
                    code="duplicate_review_decision",
                    message="A different review decision already exists for the same decision id",
                    context={"decision_id": str(decision.decision_id)},
                )
            return self
        if self.get_queue_decision(decision.review_queue_id) is not None:
            raise ConflictError(
                code="duplicate_review_queue_decision",
                message="A review queue cannot be decided more than once",
                context={"review_queue_id": str(decision.review_queue_id)},
            )
        return InMemoryReviewRepository(self.queues, self.decisions + (decision,))

    @staticmethod
    def _queue_sort_key(queue: ReviewQueueItem) -> tuple[int, str, str, str]:
        return (-queue.priority, queue.created_at.isoformat(), str(queue.target_id), str(queue.queue_id))

    @staticmethod
    def _decision_sort_key(decision: ReviewDecision) -> tuple[str, str, str]:
        return (decision.decided_at.isoformat(), str(decision.review_queue_id), str(decision.decision_id))