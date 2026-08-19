from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.review import (
    InMemoryReviewRepository,
    ReviewDecision,
    ReviewDecisionAction,
    ReviewPolicyCatalogLoader,
    ReviewQueueItem,
    ReviewQueueService,
    ReviewQueueStatus,
    ReviewTargetType,
)

from tests.unit.assertions.test_assertion_engine import EvidenceAssertionEngineTests


class ReviewRepositoryContractsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policies = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.created_at = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
        self.decided_at = datetime(2026, 2, 2, 12, 0, tzinfo=UTC)
        self.provenance = (("source", "contract-test"),)
        helpers = EvidenceAssertionEngineTests()
        helpers.setUp()
        built = helpers.engine.build(
            helpers._atomic_scaling_semantic_run(
                "formula: 4 mA = 0 psi",
                "4",
                "mA",
                "0",
                "psi",
                normalized_raw_unit_code="ma",
                normalized_engineering_unit_code="psi",
            )
        ).assertions[0]
        self.assertion = replace(built, status=AssertionStatus.CANDIDATE, review_state=AssertionReviewState.PENDING_HUMAN)

    def test_append_only_queue_and_decision_recover_stably(self) -> None:
        repository = InMemoryReviewRepository.empty()
        queue_service = ReviewQueueService.create(repository, self.policies)
        queue = queue_service.create_queue(
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=self.assertion.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        repository = queue_service.repository.append_decision(
            ReviewDecision(
                decision_id=EntityId.from_seed("review.contract.decision", "decision-1"),
                review_queue_id=queue.queue_id,
                target_type=ReviewTargetType.ASSERTION,
                target_id=self.assertion.assertion_id,
                action=ReviewDecisionAction.APPROVE,
                reason="approved after review",
                decided_by="qa.engineer",
                decided_at=self.decided_at,
                provenance=self.provenance,
                previous_state="candidate:pending_human",
                resulting_state="accepted:approved",
            )
        )

        self.assertEqual(repository.get_queue(queue.queue_id), queue)
        self.assertEqual(repository.list_open_queues(), ())
        self.assertEqual(len(repository.list_decisions()), 1)

    def test_conflicting_queue_id_is_rejected(self) -> None:
        queue = ReviewQueueItem(
            queue_id=EntityId.from_seed("review.contract.queue", "same"),
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=self.assertion.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            status=ReviewQueueStatus.OPEN,
            assigned_to=None,
            created_at=self.created_at,
            updated_at=self.created_at,
            created_by="qa.engineer",
            updated_by="qa.engineer",
            provenance=self.provenance,
            policy_version="review.seed.v1",
        )
        conflicting = replace(queue, review_reason="high_impact_conflict")

        with self.assertRaises(ConflictError):
            InMemoryReviewRepository((queue, conflicting), ())

    def test_only_one_open_queue_per_target_is_allowed(self) -> None:
        first = ReviewQueueItem(
            queue_id=EntityId.from_seed("review.contract.queue", "first"),
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=self.assertion.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            status=ReviewQueueStatus.OPEN,
            assigned_to=None,
            created_at=self.created_at,
            updated_at=self.created_at,
            created_by="qa.engineer",
            updated_by="qa.engineer",
            provenance=self.provenance,
            policy_version="review.seed.v1",
        )
        second = replace(first, queue_id=EntityId.from_seed("review.contract.queue", "second"))

        with self.assertRaises(ConflictError):
            InMemoryReviewRepository((first, second), ())

    def test_decision_must_reference_existing_queue(self) -> None:
        decision = ReviewDecision(
            decision_id=EntityId.from_seed("review.contract.decision", "missing-queue"),
            review_queue_id=EntityId.from_seed("review.contract.queue", "missing"),
            target_type=ReviewTargetType.ASSERTION,
            target_id=self.assertion.assertion_id,
            action=ReviewDecisionAction.APPROVE,
            reason="approved after review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
            previous_state="candidate:pending_human",
            resulting_state="accepted:approved",
        )

        with self.assertRaises(ConflictError):
            InMemoryReviewRepository((), (decision,))