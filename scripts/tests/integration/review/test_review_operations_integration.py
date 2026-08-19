from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus
from drilling_knowledge.review import (
    InMemoryReviewRepository,
    ReviewDecisionAction,
    ReviewDecisionApplier,
    ReviewPolicyCatalogLoader,
    ReviewQueueService,
    ReviewTargetType,
)

from tests.unit.assertions.test_assertion_engine import EvidenceAssertionEngineTests
from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests
from tests.unit.catalog.test_ontology_proposal_service import OntologyProposalGeneratorTests


class ReviewOperationsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policies = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.repository = InMemoryReviewRepository.empty()
        self.queue_service = ReviewQueueService.create(self.repository, self.policies)
        self.applier = ReviewDecisionApplier.create(self.repository, self.policies)
        self.helpers = EvidenceAssertionEngineTests()
        self.helpers.setUp()
        self.fact_helpers = FactConsolidatorTests()
        self.fact_helpers.setUp()
        self.proposal_helpers = OntologyProposalGeneratorTests()
        self.proposal_helpers.setUp()
        self.created_at = datetime(2026, 2, 3, 12, 0, tzinfo=UTC)
        self.decided_at = datetime(2026, 2, 4, 12, 0, tzinfo=UTC)
        self.provenance = (("pipeline_run", "integration-run"), ("step_name", "manual_review"))

    def test_review_queue_and_assertion_decision_flow_round_trips(self) -> None:
        assertion = self.helpers.engine.build(
            self.helpers._atomic_scaling_semantic_run(
                "formula: 4 mA = 0 psi",
                "4",
                "mA",
                "0",
                "psi",
                normalized_raw_unit_code="ma",
                normalized_engineering_unit_code="psi",
            )
        ).assertions[0]
        pending = replace(assertion, status=AssertionStatus.CANDIDATE, review_state=AssertionReviewState.PENDING_HUMAN)
        queue = self.queue_service.create_queue(
            queue_type="assertion_manual_review",
            target_type=ReviewTargetType.ASSERTION,
            target_id=pending.assertion_id,
            reference_table="semantic.evidence_assertion",
            priority=90,
            review_reason="weak_evidence_only",
            created_by="qa.engineer",
            created_at=self.created_at,
            provenance=self.provenance,
        )
        self.repository = self.queue_service.repository
        self.queue_service.repository = self.repository
        self.applier.repository = self.repository

        result = self.applier.apply_assertion_decision(
            queue_id=queue.queue_id,
            assertion=pending,
            action=ReviewDecisionAction.APPROVE,
            reason="approved after integration review",
            decided_by="qa.engineer",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )

        self.assertEqual(result.updated_assertion.status, AssertionStatus.ACCEPTED)
        self.assertEqual(self.applier.repository.list_open_queues(), ())
        self.assertEqual(self.applier.repository.get_queue_decision(queue.queue_id), result.decision)

    def test_fact_and_proposal_reviews_preserve_full_traceability(self) -> None:
        accepted_a = self.fact_helpers._assertion("4 mA = 0 psi", version_seed="trace-a", status=AssertionStatus.ACCEPTED)
        accepted_b = self.fact_helpers._assertion("4 mA = 0 psi", version_seed="trace-b", status=AssertionStatus.ACCEPTED)
        assertion_run = self.fact_helpers._assertion_run((accepted_a, accepted_b), run_seed="trace-run")
        conflict_run = self.fact_helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.fact_helpers.consolidator.consolidate(assertion_run, conflict_run)
        proposal_run = self.proposal_helpers.generator.generate(fact_run, conflict_run)

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
            reason="fact rejected after conflict review",
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
            reason="proposal approved after board review",
            decided_by="ontology.curator",
            decided_at=self.decided_at,
            provenance=self.provenance,
        )

        self.assertEqual(fact_result.decision.target_id, fact_run.facts[0].fact_id)
        self.assertEqual(proposal_result.decision.target_id, proposal_run.proposals[0].proposal_id)
        self.assertEqual(proposal_result.updated_proposal.evidence_ids, proposal_run.proposals[0].evidence_ids)