from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus
from drilling_knowledge.catalog.services.ontology_proposals import OntologyProposalGenerator
from drilling_knowledge.review import (
    InMemoryReviewRepository,
    ReviewDecisionAction,
    ReviewDecisionApplier,
    ReviewPolicyCatalogLoader,
    ReviewQueueService,
    ReviewTargetType,
)

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class ReviewOperationsEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fact_helpers = FactConsolidatorTests()
        self.fact_helpers.setUp()
        self.policy_catalog = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.repository = InMemoryReviewRepository.empty()
        self.queue_service = ReviewQueueService.create(self.repository, self.policy_catalog)
        self.applier = ReviewDecisionApplier.create(self.repository, self.policy_catalog)
        self.created_at = datetime(2026, 2, 5, 12, 0, tzinfo=UTC)
        self.decided_at = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
        self.provenance = (("pipeline_run", "e2e-run"), ("audit_report", "review-complete"))

    def test_official_review_flow_preserves_decision_trace(self) -> None:
        first = replace(
            self.fact_helpers._assertion("4 mA = 0 psi", version_seed="e2e-a", status=AssertionStatus.ACCEPTED),
            review_state=AssertionReviewState.APPROVED,
        )
        second = replace(
            self.fact_helpers._assertion("4 mA = 0 psi", version_seed="e2e-b", status=AssertionStatus.ACCEPTED),
            review_state=AssertionReviewState.APPROVED,
        )
        assertion_run = self.fact_helpers._assertion_run((first, second), run_seed="e2e-run")
        conflict_run = self.fact_helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.fact_helpers.consolidator.consolidate(assertion_run, conflict_run)
        proposal_run = OntologyProposalGenerator.create().generate(fact_run, conflict_run)

        fact_queue = self.queue_service.create_queue(
            queue_type="fact_manual_review",
            target_type=ReviewTargetType.FACT,
            target_id=fact_run.facts[0].fact_id,
            reference_table="semantic.consolidated_fact",
            priority=95,
            review_reason="high_impact_conflict",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        proposal_queue = self.queue_service.create_queue(
            queue_type="proposal_manual_review",
            target_type=ReviewTargetType.PROPOSAL,
            target_id=proposal_run.proposals[0].proposal_id,
            reference_table="semantic.ontology_change_proposal",
            priority=85,
            review_reason="new_canonical_variable_concept",
            created_by="ontology.curator",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        self.repository = self.queue_service.repository
        self.queue_service.repository = self.repository
        self.applier.repository = self.repository

        fact_result = self.applier.apply_fact_decision(
            queue_id=fact_queue.queue_id,
            fact=fact_run.facts[0],
            action=ReviewDecisionAction.REJECT,
            reason="fact rejected after end-to-end review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )
        self.repository = self.applier.repository
        self.queue_service.repository = self.repository
        self.applier.repository = self.repository
        proposal_result = self.applier.apply_proposal_decision(
            queue_id=proposal_queue.queue_id,
            proposal=proposal_run.proposals[0],
            action=ReviewDecisionAction.APPROVE,
            reason="proposal approved after end-to-end review",
            decided_by="ontology.curator",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )

        self.assertEqual(fact_result.decision.previous_state, "active:active")
        self.assertEqual(fact_result.decision.resulting_state, "superseded:historical")
        self.assertEqual(proposal_result.decision.previous_state, "queued")
        self.assertEqual(proposal_result.decision.resulting_state, "approved")
        self.assertEqual(self.applier.repository.list_open_queues(), ())
        self.assertEqual(len(self.applier.repository.list_decisions()), 2)