from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.catalog import Variable
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.documents.domain import Document, DocumentFragment, DocumentMetadata, DocumentTrace
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult, InMemorySearchProjectionBatchRepository, SearchProjectionBatch, SearchProjector

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class SearchProjectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="search-projection-contract-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="search-projection-contract")
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
            entity_id=EntityId.from_seed("search.contract.document", "manual"),
            title="Pump Manual",
            metadata=DocumentMetadata(document_type="manual", source="vendor", language="en", published_at=date(2026, 1, 1)),
            logical_key="std.manual.pump-x",
        )
        self.fragment = DocumentFragment(
            entity_id=EntityId.from_seed("search.contract.fragment", "manual-fragment"),
            trace=DocumentTrace(
                document_id=self.document.entity_id,
                document_version_id=EntityId.from_seed("search.contract.document.version", "manual-v1"),
                page_number=1,
            ),
            fragment_type="paragraph",
            ordinal_in_parent=0,
            text_content="4 mA equals 0 psi.",
            normalized_text="4 ma equals 0 psi.",
            content_hash="fragment-hash",
        )
        self.projector = SearchProjector.create(_StubEmbeddingProvider())

    def test_public_contract_and_recovery(self) -> None:
        batch = self._batch()
        repository = InMemorySearchProjectionBatchRepository().append_batch(batch)

        self.assertEqual(repository.get_batch(batch.projection_batch_id), batch)
        self.assertEqual(repository.list_batches(), (batch,))

    def test_append_only_idempotence(self) -> None:
        batch = self._batch()
        repository = InMemorySearchProjectionBatchRepository().append_batch(batch)

        self.assertIs(repository.append_batch(batch), repository)

    def test_conflicting_batch_id_is_rejected(self) -> None:
        batch = self._batch()
        mutated_document = replace(batch.documents[0], fields=batch.documents[0].fields + (("extra_field", "changed"),))
        conflicting = replace(batch, documents=(mutated_document, *batch.documents[1:]))

        with self.assertRaises(ConflictError):
            InMemorySearchProjectionBatchRepository((batch, conflicting))

    def test_determinism_is_stable_for_recovery(self) -> None:
        batch = self._batch()
        recovered = InMemorySearchProjectionBatchRepository((batch,)).get_batch(batch.projection_batch_id)

        self.assertEqual(json.dumps(batch.as_serializable(), sort_keys=True), json.dumps(recovered.as_serializable(), sort_keys=True))

    def test_reversed_input_order_produces_same_persisted_batch(self) -> None:
        first = self._batch()
        second = self.projector.project(
            variables=(self.variable,),
            documents=(self.document,),
            fragments=(self.fragment,),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )

        self.assertEqual(first, second)

    def _batch(self):
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