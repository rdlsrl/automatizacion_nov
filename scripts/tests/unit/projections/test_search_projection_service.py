from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus
from drilling_knowledge.catalog import Variable
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.documents.domain import Document, DocumentFragment, DocumentMetadata, DocumentTrace
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult, SearchProjectionBatch, SearchProjector

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class SearchProjectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="search-projection-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="search-projection")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.assertion = fact_run.assertions[0]
        self.fact = fact_run.facts[0]
        self.variable = Variable(
            entity_id=self.fact.subject_id,
            code=CatalogCode("variable.pressure"),
            names=LocalizedName("Standpipe Pressure", "Presion Standpipe"),
            description="Pressure variable.",
            scope=CatalogScope(),
            physical_quantity_code=CatalogCode("quantity.pressure"),
            canonical_unit_code=CatalogCode("unit.psi"),
            classification_codes=(CatalogCode("classification.process"),),
            subsystem_codes=(),
        )
        self.document = Document(
            entity_id=EntityId.from_seed("search.document", "manual"),
            title="Pump Manual",
            metadata=DocumentMetadata(
                manufacturer="Acme",
                model="Pump-X",
                version_label="v1",
                language="en",
                published_at=date(2026, 1, 1),
                document_type="manual",
                source="vendor",
            ),
            logical_key="std.manual.pump-x",
            external_reference="rev-a",
        )
        self.fragment = DocumentFragment(
            entity_id=EntityId.from_seed("search.fragment", "manual-fragment"),
            trace=DocumentTrace(
                document_id=self.document.entity_id,
                document_version_id=EntityId.from_seed("search.document.version", "manual-v1"),
                page_number=3,
            ),
            fragment_type="paragraph",
            ordinal_in_parent=0,
            text_content="4 mA equals 0 psi.",
            normalized_text="4 ma equals 0 psi.",
            content_hash="fragment-hash",
        )
        self.embedding_provider = _StubEmbeddingProvider()
        self.projector = SearchProjector.create(self.embedding_provider)

    def test_valid_projection_builds_required_index_documents(self) -> None:
        batch = self._project()

        index_names = {document.index_name for document in batch.documents}
        self.assertEqual(
            index_names,
            {
                "ikc-variables-v1",
                "ikc-documents-v1",
                "ikc-fragments-v1",
                "ikc-assertions-v1",
                "ikc-facts-v1",
            },
        )
        source_types = {document.source_type for document in batch.documents}
        self.assertEqual(source_types, {"variable", "document", "fragment", "assertion", "fact"})

    def test_projection_is_deterministic(self) -> None:
        first = self._project()
        second = self._project()

        self.assertEqual(first, second)
        self.assertEqual(first.projection_batch_id, second.projection_batch_id)

    def test_reversed_input_order_produces_same_batch(self) -> None:
        first = self._project()
        second = self.projector.project(
            variables=(self.variable,),
            documents=(self.document,),
            fragments=(self.fragment,),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )

        self.assertEqual(first, second)

    def test_embedding_provider_must_preserve_request_order(self) -> None:
        projector = SearchProjector.create(_OutOfOrderEmbeddingProvider())

        with self.assertRaises(ValueError):
            projector.project(
                variables=(self.variable,),
                documents=(self.document,),
                fragments=(self.fragment,),
                assertions=(self.assertion,),
                facts=(self.fact,),
            )

    def test_duplicate_documents_are_rejected(self) -> None:
        batch = self._project()
        with self.assertRaises(ValueError):
            SearchProjectionBatch(
                projection_batch_id=batch.projection_batch_id,
                documents=(batch.documents[0], batch.documents[0]),
                metrics=replace(batch.metrics, projected_documents_total=2, projected_variables=2, projected_documents=0, projected_fragments=0, projected_assertions=0, projected_facts=0),
            )

    def test_serialization_is_stable(self) -> None:
        batch = self._project()

        self.assertEqual(
            json.dumps(batch.as_serializable(), sort_keys=True),
            json.dumps(self._project().as_serializable(), sort_keys=True),
        )

    def test_public_fields_cover_required_mapping_surface(self) -> None:
        batch = self._project()
        by_index = {document.index_name: dict(document.fields) for document in batch.documents}
        variable_document = next(document for document in batch.documents if document.index_name == "ikc-variables-v1")

        self.assertIn("canonical_name", by_index["ikc-variables-v1"])
        self.assertIn("title", by_index["ikc-documents-v1"])
        self.assertIn("text_content", by_index["ikc-fragments-v1"])
        self.assertIn("predicate_code", by_index["ikc-assertions-v1"])
        self.assertIn("fact_key", by_index["ikc-facts-v1"])
        self.assertIn("embedding", by_index["ikc-variables-v1"])
        self.assertEqual(variable_document.source_type, "variable")
        self.assertTrue(variable_document.index_text)
        self.assertTrue(variable_document.provenance)
        self.assertTrue(variable_document.state)

    def test_immutability_is_enforced(self) -> None:
        batch = self._project()

        with self.assertRaises(FrozenInstanceError):
            batch.documents = ()

    def _project(self):
        return self.projector.project(
            variables=(self.variable,),
            documents=(self.document,),
            fragments=(self.fragment,),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )


class _StubEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )


class _OutOfOrderEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        results = tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )
        return tuple(reversed(results))