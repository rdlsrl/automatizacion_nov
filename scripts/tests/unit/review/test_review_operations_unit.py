from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
import unittest

from drilling_knowledge.assertions.consolidation.domain import FactLifecycle
from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus
from drilling_knowledge.common.exceptions import ConflictError, NotFoundError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.review import (
    InMemoryReviewRepository,
    ReviewDecisionAction,
    ReviewDecisionApplier,
    ReviewPolicyCatalogLoader,
    ReviewQueueService,
    ReviewTargetType,
    SQLiteReviewRepository,
)

from tests.unit.assertions.test_assertion_engine import EvidenceAssertionEngineTests
from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests
from tests.unit.catalog.test_ontology_proposal_service import OntologyProposalGeneratorTests


class ReviewOperationsUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policies = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.repository = InMemoryReviewRepository.empty()
        self.queue_service = ReviewQueueService.create(self.repository, self.policies)
        self.applier = ReviewDecisionApplier.create(self.repository, self.policies)
        self.created_at = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
        self.decided_at = datetime(2026, 2, 2, 12, 0, tzinfo=UTC)
        self.provenance = (("source", "unit-test"), ("workflow_stage", "manual_review"))
        self.assertion_helpers = EvidenceAssertionEngineTests()
        self.assertion_helpers.setUp()
        self.fact_helpers = FactConsolidatorTests()
        self.fact_helpers.setUp()
        self.proposal_helpers = OntologyProposalGeneratorTests()
        self.proposal_helpers.setUp()

    def test_creates_review_queue_idempotently_for_same_input(self) -> None:
        assertion = self._pending_assertion()

        first = self.queue_service.create_queue(
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=assertion.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        self._sync_services()
        second = self.queue_service.create_queue(
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=assertion.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )

        self.assertEqual(first, second)
        self.assertEqual(len(self.queue_service.repository.list_queues()), 1)

    def test_approves_pending_assertion_and_records_traceable_decision(self) -> None:
        assertion = self._pending_assertion()
        queue = self._queue_for_assertion(assertion)

        result = self.applier.apply_assertion_decision(
            queue_id=queue.queue_id,
            assertion=assertion,
            action=ReviewDecisionAction.APPROVE,
            reason="approved after manual review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )
        self._sync_services()

        self.assertEqual(result.updated_assertion.status, AssertionStatus.ACCEPTED)
        self.assertEqual(result.updated_assertion.review_state, AssertionReviewState.APPROVED)
        self.assertEqual(result.decision.previous_state, "candidate:pending_human")
        self.assertEqual(result.decision.resulting_state, "accepted:approved")
        self.assertEqual(self.repository.list_open_queues(), ())

    def test_rejects_pending_assertion(self) -> None:
        assertion = self._pending_assertion()
        queue = self._queue_for_assertion(assertion)

        result = self.applier.apply_assertion_decision(
            queue_id=queue.queue_id,
            assertion=assertion,
            action=ReviewDecisionAction.REJECT,
            reason="rejected after manual review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )

        self.assertEqual(result.updated_assertion.status, AssertionStatus.REJECTED)
        self.assertEqual(result.updated_assertion.review_state, AssertionReviewState.REJECTED)

    def test_rejecting_fact_supersedes_active_revision(self) -> None:
        fact = self._active_fact()
        queue = self.queue_service.create_queue(
            queue_type="fact_manual_review",
            target_type=ReviewTargetType.FACT,
            target_id=fact.fact_id,
            reference_table="semantic.consolidated_fact",
            priority=95,
            review_reason="high_impact_conflict",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        self._sync_services()

        result = self.applier.apply_fact_decision(
            queue_id=queue.queue_id,
            fact=fact,
            action=ReviewDecisionAction.REJECT,
            reason="rejected after safety review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )

        self.assertEqual(result.updated_fact.lifecycle, FactLifecycle.SUPERSEDED)
        self.assertFalse(result.updated_fact.active_revision)
        self.assertEqual(result.decision.resulting_state, "superseded:historical")

    def test_approving_proposal_marks_it_approved(self) -> None:
        proposal = self._queued_proposal()
        queue = self.queue_service.create_queue(
            queue_type="proposal_manual_review",
            target_type=ReviewTargetType.PROPOSAL,
            target_id=proposal.proposal_id,
            reference_table="semantic.ontology_change_proposal",
            priority=80,
            review_reason="new_canonical_variable_concept",
            created_by="ontology.curator",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        self._sync_services()

        result = self.applier.apply_proposal_decision(
            queue_id=queue.queue_id,
            proposal=proposal,
            action=ReviewDecisionAction.APPROVE,
            reason="approved by ontology board",
            decided_by="ontology.curator",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )

        self.assertEqual(result.updated_proposal.proposal_status.value, "approved")

    def test_duplicate_decision_application_is_rejected(self) -> None:
        assertion = self._pending_assertion()
        queue = self._queue_for_assertion(assertion)
        self.applier.apply_assertion_decision(
            queue_id=queue.queue_id,
            assertion=assertion,
            action=ReviewDecisionAction.APPROVE,
            reason="approved after manual review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )
        self._sync_services()

        with self.assertRaises(ConflictError):
            self.applier.apply_assertion_decision(
                queue_id=queue.queue_id,
                assertion=assertion,
                action=ReviewDecisionAction.APPROVE,
                reason="approved after manual review",
                decided_by="qa.engineer",
                decided_at=self.decided_at,
                provenance=self.provenance,
            )

    def test_missing_target_queue_is_rejected(self) -> None:
        with self.assertRaises(NotFoundError):
            self.applier.apply_assertion_decision(
                queue_id=EntityId.from_seed("review.test.queue", "missing"),
                assertion=self._pending_assertion(),
                action=ReviewDecisionAction.APPROVE,
                reason="approved after manual review",
                decided_by="qa.engineer",
                decided_at=self.decided_at,
                provenance=self.provenance,
            )

    def test_sqlite_repository_preserves_idempotence_and_recovery(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = SQLiteReviewRepository.create(f"{temp_dir}/review.db")
            queue_service = ReviewQueueService.create(repository, self.policies)
            applier = ReviewDecisionApplier.create(repository, self.policies)
            assertion = self._pending_assertion()
            queue = queue_service.create_queue(
                queue_type="assertion_manual_review",
                target_type=ReviewTargetType.ASSERTION,
                target_id=assertion.assertion_id,
                reference_table="semantic.evidence_assertion",
                priority=90,
                review_reason="weak_evidence_only",
                created_by="qa.engineer",
                created_at=self.created_at,
                provenance=self.provenance,
            )
            result = applier.apply_assertion_decision(
                queue_id=queue.queue_id,
                assertion=assertion,
                action=ReviewDecisionAction.APPROVE,
                reason="approved after manual review",
                decided_by="qa.engineer",
                decided_at=self.decided_at,
                provenance=self.provenance,
            )

            reopened = SQLiteReviewRepository.create(f"{temp_dir}/review.db")
            self.assertEqual(reopened.get_queue(queue.queue_id), queue)
            self.assertEqual(reopened.get_decision(result.decision.decision_id), result.decision)
            self.assertEqual(reopened.list_open_queues(), ())

    def _sync_services(self) -> None:
        repository = self.queue_service.repository
        if self.applier.repository.list_decisions() or self.applier.repository.list_queues():
            repository = self.applier.repository
        self.repository = repository
        self.queue_service.repository = self.repository
        self.applier.repository = self.repository

    def _queue_for_assertion(self, assertion):
        queue = self.queue_service.create_queue(
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=assertion.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        self._sync_services()
        return queue

    def _pending_assertion(self):
        assertion = self.assertion_helpers.engine.build(
            self.assertion_helpers._atomic_scaling_semantic_run(
                "formula: 4 mA = 0 psi",
                "4",
                "mA",
                "0",
                "psi",
                normalized_raw_unit_code="ma",
                normalized_engineering_unit_code="psi",
            )
        ).assertions[0]
        return replace(assertion, status=AssertionStatus.CANDIDATE, review_state=AssertionReviewState.PENDING_HUMAN)

    def _active_fact(self):
        accepted = self.fact_helpers._assertion("4 mA = 0 psi", version_seed="review-fact", status=AssertionStatus.ACCEPTED)
        assertion_run = self.fact_helpers._assertion_run((accepted,), run_seed="review-fact")
        conflict_run = self.fact_helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.fact_helpers.consolidator.consolidate(assertion_run, conflict_run)
        return fact_run.facts[0]

    def _queued_proposal(self):
        conflict_run, fact_run = self.proposal_helpers._fact_pipeline(
            (
                self.fact_helpers._assertion("4 mA = 0 psi", version_seed="review-proposal-v1", status=AssertionStatus.ACCEPTED),
                self.fact_helpers._assertion("4 mA = 0 psi", version_seed="review-proposal-v2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed="review-proposal",
        )
        proposal_run = self.proposal_helpers.generator.generate(fact_run, conflict_run)
        return proposal_run.proposals[0]