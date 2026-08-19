from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from drilling_knowledge.assertions.consolidation.repositories.sqlite import SQLiteFactConsolidationRunRepository
from drilling_knowledge.assertions.repositories.sqlite import SQLiteAssertionGenerationRunRepository
from drilling_knowledge.documents.domain import DocumentMetadata
from drilling_knowledge.documents.sqlite import SQLiteDocumentRepository
from drilling_knowledge.loader.knowledge_query import SQLiteKnowledgeQueryService
from drilling_knowledge.projections.search.repositories.sqlite import SQLiteSearchProjectionBatchRepository
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult
from drilling_knowledge.review import ReviewPolicyCatalogLoader
from drilling_knowledge.workflows import AcquisitionWorkflowOrchestrator, InMemoryWorkflowRunRepository

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class PersistedKnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        self.catalog = helpers.catalog
        self.policies = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        self.fixture = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/tests/fixtures/extraction/explicit_extraction.md")
        self.metadata = DocumentMetadata(document_type="manual", source="explicit_extraction", language="en", authority_level="reference")

    def test_persisted_knowledge_survives_reopen_and_is_queryable_with_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "loader.sqlite"
            orchestrator = AcquisitionWorkflowOrchestrator.create(
                catalog_repository=self.catalog,
                embedding_provider=_StubEmbeddingProvider(),
                review_policy_catalog=self.policies,
                repository=InMemoryWorkflowRunRepository.empty(),
                document_repository=SQLiteDocumentRepository.create(database_path),
                assertion_repository=SQLiteAssertionGenerationRunRepository.create(database_path),
                fact_repository=SQLiteFactConsolidationRunRepository.create(database_path),
                search_repository=SQLiteSearchProjectionBatchRepository.create(database_path),
            )

            result = orchestrator.run(document_path=self.fixture, metadata=self.metadata, created_by="qa.engineer")

            reopened_query = SQLiteKnowledgeQueryService.create(database_path)
            hits = reopened_query.search("psi")
            search_documents = SQLiteSearchProjectionBatchRepository.create(database_path).search("psi", source_type="fact")

            self.assertTrue(result.facts)
            self.assertTrue(SQLiteAssertionGenerationRunRepository.create(database_path).list_runs())
            self.assertTrue(SQLiteFactConsolidationRunRepository.create(database_path).list_runs())
            self.assertTrue(search_documents)
            self.assertTrue(hits)
            self.assertEqual(hits[0].fact.fact_id, result.facts[0].fact_id)
            self.assertEqual(hits[0].document.entity_id, result.document.entity_id)
            self.assertEqual(hits[0].fragment.trace.document_id, result.document.entity_id)
            self.assertEqual(hits[0].evidence_link.fragment_id, hits[0].fragment.entity_id)


class _StubEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )