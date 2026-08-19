from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import unittest

from drilling_knowledge.documents.domain import DocumentMetadata
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult
from drilling_knowledge.review import ReviewDecisionAction, ReviewPolicyCatalogLoader, ReviewTargetType
from drilling_knowledge.workflows import AcquisitionWorkflowOrchestrator, PipelineRunStatus, WorkflowHumanDecision

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class AcquisitionWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        self.catalog = helpers.catalog
        self.policies = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.fixture = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/tests/fixtures/extraction/explicit_extraction.md")
        self.metadata = DocumentMetadata(document_type="manual", source="explicit_extraction", language="en", authority_level="reference")
        self.orchestrator = AcquisitionWorkflowOrchestrator.create(
            catalog_repository=self.catalog,
            embedding_provider=_StubEmbeddingProvider(),
            review_policy_catalog=self.policies,
        )

    def test_golden_document_produces_review_tasks_without_decision(self) -> None:
        result = self.orchestrator.run(document_path=self.fixture, metadata=self.metadata, created_by="qa.engineer", require_manual_fact_review=True)

        self.assertEqual(result.pipeline_run.status, PipelineRunStatus.AWAITING_REVIEW)
        self.assertGreater(result.review_queue_count + result.conflict_review_task_count, 0)

    def test_golden_document_produces_expected_facts_with_manual_decision(self) -> None:
        first = self.orchestrator.run(document_path=self.fixture, metadata=self.metadata, created_by="qa.engineer", require_manual_fact_review=True)
        decisions = tuple(
            WorkflowHumanDecision(
                target_type=ReviewTargetType.FACT,
                target_id=fact.fact_id,
                action=ReviewDecisionAction.APPROVE,
                reason="approved after integration review",
                decided_by="qa.engineer",
                decided_at=datetime(2026, 2, 12, 12, 0, tzinfo=UTC),
                provenance=(("source", "integration-test"),),
            )
            for fact in first.facts
        )
        result = self.orchestrator.run(
            document_path=self.fixture,
            metadata=self.metadata,
            created_by="qa.engineer",
            human_decisions=decisions,
            require_manual_fact_review=True,
        )

        self.assertEqual(result.pipeline_run.status, PipelineRunStatus.COMPLETED)
        self.assertEqual(len(result.facts), len(first.facts))
        self.assertTrue(any(fact.claim_key == "explicit_scaling:4:mA:PSI" for fact in result.facts))
        self.assertIsNotNone(result.reasoning_response)


class _StubEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )