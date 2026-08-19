from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import time
import unittest

from drilling_knowledge.documents.domain import DocumentMetadata
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult
from drilling_knowledge.review import ReviewDecisionAction, ReviewPolicyCatalogLoader, ReviewTargetType
from drilling_knowledge.workflows import AcquisitionWorkflowOrchestrator, WorkflowHumanDecision

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class WorkflowValidationHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        self.catalog = helpers.catalog
        self.policies = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.fixture = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/tests/fixtures/extraction/explicit_extraction.md")
        self.metadata = DocumentMetadata(document_type="manual", source="explicit_extraction", language="en", authority_level="reference")

    def test_baseline_workflow_metrics_are_reproducible(self) -> None:
        orchestrator = AcquisitionWorkflowOrchestrator.create(
            catalog_repository=self.catalog,
            embedding_provider=_StubEmbeddingProvider(),
            review_policy_catalog=self.policies,
        )
        initial = orchestrator.run(document_path=self.fixture, metadata=self.metadata, created_by="qa.engineer", require_manual_fact_review=True)
        decisions = tuple(
            WorkflowHumanDecision(
                target_type=ReviewTargetType.FACT,
                target_id=fact.fact_id,
                action=ReviewDecisionAction.APPROVE,
                reason="approved after performance review",
                decided_by="qa.engineer",
                decided_at=datetime(2026, 2, 14, 12, 0, tzinfo=UTC),
                provenance=(("source", "performance"),),
            )
            for fact in initial.facts
        )

        start = time.perf_counter()
        first = orchestrator.run(document_path=self.fixture, metadata=self.metadata, created_by="qa.engineer", human_decisions=decisions, require_manual_fact_review=True)
        first_duration = time.perf_counter() - start
        start = time.perf_counter()
        second = AcquisitionWorkflowOrchestrator.create(
            catalog_repository=self.catalog,
            embedding_provider=_StubEmbeddingProvider(),
            review_policy_catalog=self.policies,
        ).run(document_path=self.fixture, metadata=self.metadata, created_by="qa.engineer", human_decisions=decisions, require_manual_fact_review=True)
        second_duration = time.perf_counter() - start

        self.assertEqual(_workflow_signature(first), _workflow_signature(second))
        self.assertGreaterEqual(first_duration, 0.0)
        self.assertGreaterEqual(second_duration, 0.0)
        self.assertEqual(len(first.pipeline_run.step_runs), len(second.pipeline_run.step_runs))


def _workflow_signature(result) -> dict[str, object]:
    return {
        "pipeline_run_id": str(result.pipeline_run.pipeline_run_id),
        "status": result.pipeline_run.status.value,
        "step_names": tuple(step.step_name for step in result.pipeline_run.step_runs),
        "review_queue_count": result.review_queue_count,
        "conflict_review_task_count": result.conflict_review_task_count,
        "assertion_ids": tuple(str(assertion.assertion_id) for assertion in result.assertions),
        "fact_ids": tuple(str(fact.fact_id) for fact in result.facts),
        "audit": result.audit_report.as_serializable(),
        "graph_metrics": None if result.graph_projection is None else result.graph_projection.metrics.as_serializable(),
        "search_metrics": None if result.search_projection is None else result.search_projection.metrics.as_serializable(),
        "reasoning_target_id": None if result.reasoning_response is None else str(result.reasoning_response.answer_statement.target_entity_id),
    }


class _StubEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )