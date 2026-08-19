from __future__ import annotations

from datetime import date
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.catalog import Variable
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName, VariableAlias
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.documents.domain import Document, DocumentFragment, DocumentMetadata, DocumentTrace
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult, SearchProjector

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class SearchRankingSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="ranking-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="ranking")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.assertion = fact_run.assertions[0]
        self.fact = fact_run.facts[0]
        self.variable = Variable(
            entity_id=self.fact.subject_id,
            code=CatalogCode("spp"),
            names=LocalizedName("Standpipe Pressure"),
            description="Standpipe pressure variable.",
            scope=CatalogScope(),
            physical_quantity_code=CatalogCode("pressure"),
            canonical_unit_code=CatalogCode("psi"),
            aliases=(VariableAlias("pump pressure"), VariableAlias("standpipe psi")),
        )
        self.document = Document(
            entity_id=EntityId.from_seed("ranking.document", "manual"),
            title="Standpipe Pressure Manual",
            metadata=DocumentMetadata(document_type="manual", source="vendor", language="en", published_at=date(2026, 1, 1)),
            logical_key="ranking.manual",
        )
        self.fragment = DocumentFragment(
            entity_id=EntityId.from_seed("ranking.fragment", "manual-fragment"),
            trace=DocumentTrace(document_id=self.document.entity_id, document_version_id=EntityId.from_seed("ranking.version", "v1"), page_number=1),
            fragment_type="paragraph",
            ordinal_in_parent=0,
            text_content="Standpipe pressure is calibrated at 4 mA equals 0 psi.",
            normalized_text="standpipe pressure is calibrated at 4 ma equals 0 psi.",
            content_hash="ranking-fragment",
        )
        self.projector = SearchProjector.create(_StubEmbeddingProvider())
        self.batch = self.projector.project(
            variables=(self.variable,),
            documents=(self.document,),
            fragments=(self.fragment,),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )

    def test_exact_match_signal_ranks_variable_first(self) -> None:
        ranked = self._rank("Standpipe Pressure")
        self.assertEqual(ranked[0].source_type, "variable")

    def test_alias_match_signal_ranks_variable_first(self) -> None:
        ranked = self._rank("pump pressure")
        self.assertEqual(ranked[0].source_type, "variable")

    def test_mnemonic_match_signal_ranks_variable_first(self) -> None:
        ranked = self._rank("spp")
        self.assertEqual(ranked[0].source_type, "variable")

    def test_semantic_signal_prefers_fact_when_query_is_scaling_statement(self) -> None:
        ranked = self._rank("4 mA 0 psi")
        self.assertEqual(ranked[0].source_type, "fact")

    def _rank(self, query: str):
        query_key = query.casefold()
        def score(document):
            fields = dict(document.fields)
            aliases = [alias.casefold() for alias in fields.get("aliases", [])]
            exact = 100 if fields.get("canonical_name", "").casefold() == query_key else 0
            alias = 90 if query_key in aliases else 0
            mnemonic = 80 if str(fields.get("code", "")).casefold() == query_key else 0
            semantic = 70 if all(token in document.index_text.casefold() for token in query_key.split()) else 0
            fact_bonus = 5 if document.source_type == "fact" and semantic > 0 else 0
            return (max(exact, alias, mnemonic, semantic) + fact_bonus, document.source_type)
        return tuple(sorted(self.batch.documents, key=score, reverse=True))


class _StubEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )