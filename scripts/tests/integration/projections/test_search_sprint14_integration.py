from __future__ import annotations

from datetime import date
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.catalog import Variable
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.documents.domain import Document, DocumentFragment, DocumentMetadata, DocumentTrace
from drilling_knowledge.projections.search import (
    EmbeddingRequest,
    EmbeddingResult,
    InMemorySearchProjectionBatchRepository,
    InMemorySearchSynonymRepository,
    OpenSearchTemplateBundleLoader,
    SearchProjector,
    SearchSynonymCatalogLoader,
)

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class SearchSprint14IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="search-integration-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="search-integration")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.assertion = fact_run.assertions[0]
        self.fact = fact_run.facts[0]
        self.variable = Variable(
            entity_id=self.fact.subject_id,
            code=CatalogCode("variable.pressure"),
            names=LocalizedName("Standpipe Pressure"),
            description="Pressure variable.",
            scope=CatalogScope(),
            physical_quantity_code=CatalogCode("quantity.pressure"),
            canonical_unit_code=CatalogCode("unit.psi"),
        )
        self.document = Document(
            entity_id=EntityId.from_seed("search.integration.document", "manual"),
            title="Pump Manual",
            metadata=DocumentMetadata(document_type="manual", source="vendor", language="en", published_at=date(2026, 1, 1)),
            logical_key="std.manual.pump-x",
        )
        self.fragment = DocumentFragment(
            entity_id=EntityId.from_seed("search.integration.fragment", "manual-fragment"),
            trace=DocumentTrace(
                document_id=self.document.entity_id,
                document_version_id=EntityId.from_seed("search.integration.document.version", "manual-v1"),
                page_number=1,
            ),
            fragment_type="paragraph",
            ordinal_in_parent=0,
            text_content="4 mA equals 0 psi.",
            normalized_text="4 ma equals 0 psi.",
            content_hash="fragment-hash",
        )
        self.projector = SearchProjector.create(_StubEmbeddingProvider())

    def test_templates_synonyms_projection_batch_and_recovery_align(self) -> None:
        bundle = OpenSearchTemplateBundleLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/opensearch")
        catalog = SearchSynonymCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/opensearch/synonyms")
        batch = self.projector.project(
            variables=(self.variable,),
            documents=(self.document,),
            fragments=(self.fragment,),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )

        synonym_repository = InMemorySearchSynonymRepository(tuple(catalog.entries))
        batch_repository = InMemorySearchProjectionBatchRepository().append_batch(batch)
        recovered = batch_repository.get_batch(batch.projection_batch_id)

        self.assertTrue(bundle.templates)
        self.assertTrue(synonym_repository.list_entries())
        self.assertEqual(recovered, batch)
        self.assertEqual(json.dumps(recovered.as_serializable(), sort_keys=True), json.dumps(batch.as_serializable(), sort_keys=True))


class _StubEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )