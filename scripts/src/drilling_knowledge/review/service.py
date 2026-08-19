"""Review queue service and human decision applier."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Protocol

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact
from drilling_knowledge.assertions.domain import EvidenceAssertion
from drilling_knowledge.catalog.services.ontology_proposals.domain import OntologyChangeProposal
from drilling_knowledge.common.exceptions import ConflictError, NotFoundError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.review.domain import (
    ReviewApplicationResult,
    ReviewDecision,
    ReviewDecisionAction,
    ReviewPolicyCatalog,
    ReviewQueueItem,
    ReviewQueueStatus,
    ReviewTargetType,
    apply_assertion_decision,
    apply_fact_decision,
    apply_proposal_decision,
    assertion_state,
    fact_state,
    proposal_state,
)
from drilling_knowledge.review.repositories.contracts import ReviewRepository


class ReviewQueue(Protocol):
    def create_queue(
        self,
        *,
        queue_type: str,
        target_type: ReviewTargetType,
        target_id: EntityId,
        reference_table: str,
        priority: int,
        review_reason: str,
        created_by: str,
        created_at: datetime,
        provenance: tuple[tuple[str, str], ...],
        assigned_to: str | None = None,
    ) -> ReviewQueueItem:
        ...


class ReviewDecisionHandler(Protocol):
    def apply_assertion_decision(
        self,
        *,
        queue_id: EntityId,
        assertion: EvidenceAssertion,
        action: ReviewDecisionAction,
        reason: str,
        decided_by: str,
        decided_at: datetime,
        provenance: tuple[tuple[str, str], ...],
    ) -> ReviewApplicationResult:
        ...


@dataclass(slots=True)
class ReviewQueueService:
    repository: ReviewRepository
    policy_catalog: ReviewPolicyCatalog
    policy_version: str = "review.seed.v1"

    @classmethod
    def create(cls, repository: ReviewRepository, policy_catalog: ReviewPolicyCatalog, *, policy_version: str = "review.seed.v1") -> "ReviewQueueService":
        return cls(repository=repository, policy_catalog=policy_catalog, policy_version=policy_version)

    def create_queue(
        self,
        *,
        queue_type: str,
        target_type: ReviewTargetType,
        target_id: EntityId,
        reference_table: str,
        priority: int,
        review_reason: str,
        created_by: str,
        created_at: datetime,
        provenance: tuple[tuple[str, str], ...],
        assigned_to: str | None = None,
    ) -> ReviewQueueItem:
        policy = self.policy_catalog.policy_for(queue_type)
        if target_type not in policy.allowed_target_types:
            raise ValueError(f"Queue type {queue_type} does not support target type {target_type.value}")
        normalized_reason = review_reason.strip().lower()
        if normalized_reason not in policy.allowed_reasons:
            raise ValueError(f"Review reason {review_reason} is not allowed for queue type {queue_type}")
        active = self.repository.get_open_queue(target_type, target_id)
        candidate = ReviewQueueItem(
            queue_id=self._queue_id(queue_type, target_type, target_id, normalized_reason, priority, provenance),
            queue_type=queue_type,
            target_type=target_type,
            target_id=target_id,
            reference_table=reference_table,
            priority=priority,
            review_reason=normalized_reason,
            status=ReviewQueueStatus.OPEN,
            assigned_to=assigned_to,
            created_at=created_at,
            updated_at=created_at,
            created_by=created_by,
            updated_by=created_by,
            provenance=tuple(sorted(provenance)),
            policy_version=self.policy_version,
        )
        if active is not None:
            if active == candidate:
                return active
            raise ConflictError(
                code="duplicate_open_review_target",
                message="Only one open review queue may exist for a target",
                context={"target_type": target_type.value, "target_id": str(target_id)},
            )
        self.repository = self.repository.append_queue(candidate)
        return candidate

    def list_open_queues(self) -> tuple[ReviewQueueItem, ...]:
        return self.repository.list_open_queues()

    def _queue_id(
        self,
        queue_type: str,
        target_type: ReviewTargetType,
        target_id: EntityId,
        review_reason: str,
        priority: int,
        provenance: tuple[tuple[str, str], ...],
    ) -> EntityId:
        return EntityId.from_seed(
            "review.queue",
            "|".join(
                (
                    queue_type.strip().lower(),
                    target_type.value,
                    str(target_id),
                    review_reason,
                    str(priority),
                    json.dumps(list(sorted(provenance)), separators=(",", ":")),
                )
            ),
        )


@dataclass(slots=True)
class ReviewDecisionApplier:
    repository: ReviewRepository
    policy_catalog: ReviewPolicyCatalog

    @classmethod
    def create(cls, repository: ReviewRepository, policy_catalog: ReviewPolicyCatalog) -> "ReviewDecisionApplier":
        return cls(repository=repository, policy_catalog=policy_catalog)

    def apply_assertion_decision(
        self,
        *,
        queue_id: EntityId,
        assertion: EvidenceAssertion,
        action: ReviewDecisionAction,
        reason: str,
        decided_by: str,
        decided_at: datetime,
        provenance: tuple[tuple[str, str], ...],
    ) -> ReviewApplicationResult:
        queue = self._required_queue(queue_id, ReviewTargetType.ASSERTION, assertion.assertion_id, action)
        updated = apply_assertion_decision(assertion, action)
        decision = self._build_decision(queue, action, reason, decided_by, decided_at, provenance, assertion_state(assertion), assertion_state(updated))
        self.repository = self.repository.append_decision(decision)
        return ReviewApplicationResult(queue=queue, decision=decision, updated_assertion=updated)

    def apply_fact_decision(
        self,
        *,
        queue_id: EntityId,
        fact: ConsolidatedFact,
        action: ReviewDecisionAction,
        reason: str,
        decided_by: str,
        decided_at: datetime,
        provenance: tuple[tuple[str, str], ...],
    ) -> ReviewApplicationResult:
        queue = self._required_queue(queue_id, ReviewTargetType.FACT, fact.fact_id, action)
        updated = apply_fact_decision(fact, action, decided_at=decided_at)
        decision = self._build_decision(queue, action, reason, decided_by, decided_at, provenance, fact_state(fact), fact_state(updated))
        self.repository = self.repository.append_decision(decision)
        return ReviewApplicationResult(queue=queue, decision=decision, updated_fact=updated)

    def apply_proposal_decision(
        self,
        *,
        queue_id: EntityId,
        proposal: OntologyChangeProposal,
        action: ReviewDecisionAction,
        reason: str,
        decided_by: str,
        decided_at: datetime,
        provenance: tuple[tuple[str, str], ...],
    ) -> ReviewApplicationResult:
        queue = self._required_queue(queue_id, ReviewTargetType.PROPOSAL, proposal.proposal_id, action)
        updated = apply_proposal_decision(proposal, action)
        decision = self._build_decision(queue, action, reason, decided_by, decided_at, provenance, proposal_state(proposal), proposal_state(updated))
        self.repository = self.repository.append_decision(decision)
        return ReviewApplicationResult(queue=queue, decision=decision, updated_proposal=updated)

    def _required_queue(self, queue_id: EntityId, target_type: ReviewTargetType, target_id: EntityId, action: ReviewDecisionAction) -> ReviewQueueItem:
        queue = self.repository.get_queue(queue_id)
        if queue is None:
            raise NotFoundError(code="review_queue_not_found", message="Review queue does not exist", context={"queue_id": str(queue_id)})
        if queue.target_type != target_type or queue.target_id != target_id:
            raise ConflictError(
                code="review_queue_target_mismatch",
                message="Review queue target does not match the decision target",
                context={"queue_id": str(queue_id), "target_id": str(target_id)},
            )
        if self.repository.get_queue_decision(queue_id) is not None:
            raise ConflictError(
                code="review_queue_already_decided",
                message="Review queue has already been decided",
                context={"queue_id": str(queue_id)},
            )
        policy = self.policy_catalog.policy_for(queue.queue_type)
        if action not in policy.allowed_actions:
            raise ValueError(f"Action {action.value} is not allowed for queue type {queue.queue_type}")
        return queue

    def _build_decision(
        self,
        queue: ReviewQueueItem,
        action: ReviewDecisionAction,
        reason: str,
        decided_by: str,
        decided_at: datetime,
        provenance: tuple[tuple[str, str], ...],
        previous_state: str,
        resulting_state: str,
    ) -> ReviewDecision:
        return ReviewDecision(
            decision_id=EntityId.from_seed(
                "review.decision",
                "|".join(
                    (
                        str(queue.queue_id),
                        queue.target_type.value,
                        str(queue.target_id),
                        action.value,
                        reason.strip(),
                        decided_by.strip(),
                        decided_at.isoformat(),
                        previous_state,
                        resulting_state,
                        json.dumps(list(sorted(provenance)), separators=(",", ":")),
                    )
                ),
            ),
            review_queue_id=queue.queue_id,
            target_type=queue.target_type,
            target_id=queue.target_id,
            action=action,
            reason=reason,
            decided_by=decided_by,
            decided_at=decided_at,
            provenance=tuple(sorted(provenance)),
            previous_state=previous_state,
            resulting_state=resulting_state,
        )