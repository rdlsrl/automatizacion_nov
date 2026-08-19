"""Deterministic search projector over variables, documents, fragments, assertions, and facts."""

from __future__ import annotations

from collections.abc import Iterable
import json
from typing import Protocol

from drilling_knowledge.assertions.consolidation import ConsolidatedFact
from drilling_knowledge.assertions.domain import EvidenceAssertion
from drilling_knowledge.catalog import Variable
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.documents.domain import Document, DocumentFragment
from drilling_knowledge.projections.search.domain import EmbeddingRequest, EmbeddingResult, SearchDocument, SearchProjectionBatch, SearchProjectionMetrics


class EmbeddingProvider(Protocol):
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        ...


class SearchProjector:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._embedding_provider = embedding_provider

    @classmethod
    def create(cls, embedding_provider: EmbeddingProvider) -> "SearchProjector":
        return cls(embedding_provider)

    def project(
        self,
        *,
        variables: Iterable[Variable],
        documents: Iterable[Document],
        fragments: Iterable[DocumentFragment],
        assertions: Iterable[EvidenceAssertion],
        facts: Iterable[ConsolidatedFact],
    ) -> SearchProjectionBatch:
        variables = tuple(sorted(tuple(variables), key=lambda item: str(item.entity_id)))
        documents = tuple(sorted(tuple(documents), key=lambda item: str(item.entity_id)))
        fragments = tuple(sorted(tuple(fragments), key=lambda item: str(item.entity_id)))
        assertions = tuple(sorted(tuple(assertions), key=lambda item: str(item.assertion_id)))
        facts = tuple(sorted(tuple(facts), key=lambda item: str(item.fact_id)))

        requests = self._embedding_requests(variables, documents, fragments, assertions, facts)
        embedding_results = self._embedding_provider.project_batch(requests)
        embeddings_by_source = self._embedding_map(requests, embedding_results)

        projected_documents = [
            *(self._variable_document(variable, embeddings_by_source) for variable in variables),
            *(self._document_record(document, embeddings_by_source) for document in documents),
            *(self._fragment_document(fragment, embeddings_by_source) for fragment in fragments),
            *(self._assertion_document(assertion, embeddings_by_source) for assertion in assertions),
            *(self._fact_document(fact, embeddings_by_source) for fact in facts),
        ]

        batch_signature = json.dumps(
            [document.as_serializable() for document in projected_documents],
            sort_keys=True,
            separators=(",", ":"),
        )
        metrics = SearchProjectionMetrics(
            projected_variables=len(variables),
            projected_documents=len(documents),
            projected_fragments=len(fragments),
            projected_assertions=len(assertions),
            projected_facts=len(facts),
            projected_documents_total=len(projected_documents),
        )
        return SearchProjectionBatch(
            projection_batch_id=EntityId.from_seed("search.projection.batch", batch_signature),
            documents=tuple(projected_documents),
            metrics=metrics,
        )

    def _embedding_requests(
        self,
        variables: tuple[Variable, ...],
        documents: tuple[Document, ...],
        fragments: tuple[DocumentFragment, ...],
        assertions: tuple[EvidenceAssertion, ...],
        facts: tuple[ConsolidatedFact, ...],
    ) -> tuple[EmbeddingRequest, ...]:
        requests = [
            *(EmbeddingRequest(source_type="variable", source_entity_id=variable.entity_id, index_name="ikc-variables-v1", text=variable.canonical_name) for variable in variables),
            *(EmbeddingRequest(source_type="document", source_entity_id=document.entity_id, index_name="ikc-documents-v1", text=document.title) for document in documents),
            *(EmbeddingRequest(source_type="fragment", source_entity_id=fragment.entity_id, index_name="ikc-fragments-v1", text=fragment.text_content) for fragment in fragments),
            *(EmbeddingRequest(source_type="assertion", source_entity_id=assertion.assertion_id, index_name="ikc-assertions-v1", text=self._predicate_summary(assertion.subject_table, assertion.predicate_code, assertion.object_table, assertion.literal_value)) for assertion in assertions),
            *(EmbeddingRequest(source_type="fact", source_entity_id=fact.fact_id, index_name="ikc-facts-v1", text=self._predicate_summary(fact.subject_table, fact.predicate_code, fact.object_table, fact.literal_value)) for fact in facts),
        ]
        return tuple(sorted(requests, key=lambda item: (item.index_name, str(item.source_entity_id))))

    @staticmethod
    def _embedding_map(
        requests: tuple[EmbeddingRequest, ...],
        results: tuple[EmbeddingResult, ...],
    ) -> dict[EntityId, tuple[float, ...]]:
        if len(requests) != len(results):
            raise ValueError("EmbeddingProvider.project_batch must return one result per request")
        expected_keys = [(request.source_type, request.source_entity_id) for request in requests]
        result_keys = [(result.source_type, result.source_entity_id) for result in results]
        if expected_keys != result_keys:
            raise ValueError("EmbeddingProvider.project_batch must preserve request order and source ids")
        return {result.source_entity_id: result.vector for result in results}

    @staticmethod
    def _variable_document(variable: Variable, embeddings_by_source: dict[EntityId, tuple[float, ...]]) -> SearchDocument:
        return SearchDocument(
            search_document_id=EntityId.from_seed("search.document", f"ikc-variables-v1:{variable.entity_id}"),
            source_type="variable",
            source_entity_id=variable.entity_id,
            canonical_id=str(variable.entity_id),
            index_text=variable.canonical_name,
            metadata=(
                ("code", str(variable.code)),
                ("canonical_name_es", variable.names.spanish or ""),
                ("classification_codes", [str(code) for code in variable.classification_codes]),
                ("origin_codes", [str(code) for code in variable.origin_codes]),
                ("subsystem_codes", [str(code) for code in variable.subsystem_codes]),
            ),
            provenance=(("source", "catalog.variable"), ("scope", variable.scope.label())),
            state=(("record_status", variable.version.status), ("semantic_version", variable.version.semantic_version)),
            index_name="ikc-variables-v1",
            fields=(
                ("id", str(variable.entity_id)),
                ("code", str(variable.code)),
                ("canonical_name", variable.canonical_name),
                ("canonical_name_es", variable.names.spanish or ""),
                ("aliases", [alias.alias for alias in variable.aliases]),
                ("classification_codes", [str(code) for code in variable.classification_codes]),
                ("origin_codes", [str(code) for code in variable.origin_codes]),
                ("subsystem_codes", [str(code) for code in variable.subsystem_codes]),
                ("physical_quantity_code", "" if variable.physical_quantity_code is None else str(variable.physical_quantity_code)),
                ("canonical_unit_code", "" if variable.canonical_unit_code is None else str(variable.canonical_unit_code)),
                ("record_status", variable.version.status),
                ("semantic_version", variable.version.semantic_version),
                ("evidence_requirement_level", variable.evidence_requirement_level),
                ("ambiguity_level", variable.ambiguity_level),
                ("embedding", list(embeddings_by_source[variable.entity_id])),
            ),
        )

    @staticmethod
    def _document_record(document: Document, embeddings_by_source: dict[EntityId, tuple[float, ...]]) -> SearchDocument:
        return SearchDocument(
            search_document_id=EntityId.from_seed("search.document", f"ikc-documents-v1:{document.entity_id}"),
            source_type="document",
            source_entity_id=document.entity_id,
            canonical_id=str(document.entity_id),
            index_text=document.title,
            metadata=(("document_type_code", document.metadata.document_type), ("language_code", document.metadata.language), ("source_name", document.metadata.source)),
            provenance=(("source", "document.document"), ("logical_key", document.logical_key)),
            state=(("record_status", "active"), ("semantic_version", 1)),
            index_name="ikc-documents-v1",
            fields=(
                ("id", str(document.entity_id)),
                ("document_type_code", document.metadata.document_type),
                ("title", document.title),
                ("vendor_code", document.metadata.manufacturer or ""),
                ("model_code", document.metadata.model or ""),
                ("standard_code", document.logical_key),
                ("language_code", document.metadata.language),
                ("version_label", document.metadata.version_label or ""),
                ("revision_label", document.external_reference or ""),
                ("published_at", None if document.metadata.published_at is None else document.metadata.published_at.isoformat()),
                ("source_name", document.metadata.source),
                ("record_status", "active"),
                ("embedding", list(embeddings_by_source[document.entity_id])),
            ),
        )

    @staticmethod
    def _fragment_document(fragment: DocumentFragment, embeddings_by_source: dict[EntityId, tuple[float, ...]]) -> SearchDocument:
        return SearchDocument(
            search_document_id=EntityId.from_seed("search.document", f"ikc-fragments-v1:{fragment.entity_id}"),
            source_type="fragment",
            source_entity_id=fragment.entity_id,
            canonical_id=str(fragment.entity_id),
            index_text=fragment.text_content,
            metadata=(("fragment_type", fragment.fragment_type), ("document_version_id", str(fragment.trace.document_version_id))),
            provenance=(("source", "document.fragment"), ("document_id", str(fragment.trace.document_id))),
            state=(("record_status", "active"), ("semantic_version", 1)),
            index_name="ikc-fragments-v1",
            fields=(
                ("id", str(fragment.entity_id)),
                ("document_version_id", str(fragment.trace.document_version_id)),
                ("fragment_type", fragment.fragment_type),
                ("page_number", fragment.trace.page_number),
                ("section_path", "" if fragment.trace.section_id is None else str(fragment.trace.section_id)),
                ("text_content", fragment.text_content),
                ("normalized_text", fragment.normalized_text),
                ("quality_score", 1.0),
                ("entity_hints", []),
                ("embedding", list(embeddings_by_source[fragment.entity_id])),
            ),
        )

    @staticmethod
    def _assertion_document(assertion: EvidenceAssertion, embeddings_by_source: dict[EntityId, tuple[float, ...]]) -> SearchDocument:
        return SearchDocument(
            search_document_id=EntityId.from_seed("search.document", f"ikc-assertions-v1:{assertion.assertion_id}"),
            source_type="assertion",
            source_entity_id=assertion.assertion_id,
            canonical_id=str(assertion.assertion_id),
            index_text=SearchProjector._predicate_summary(assertion.subject_table, assertion.predicate_code, assertion.object_table, assertion.literal_value),
            metadata=(("predicate_code", assertion.predicate_code), ("subject_type", assertion.subject_table), ("object_type", assertion.object_table or "")),
            provenance=(("source", "semantic.evidence_assertion"), ("fragment_id", str(assertion.evidence_link_ids[0]))),
            state=(("lifecycle_status", assertion.status.value), ("review_state", assertion.review_state.value), ("semantic_version", 1)),
            index_name="ikc-assertions-v1",
            fields=(
                ("id", str(assertion.assertion_id)),
                ("assertion_key", f"{assertion.subject_table}:{assertion.subject_id}:{assertion.predicate_code}"),
                ("subject_type", assertion.subject_table),
                ("subject_id", str(assertion.subject_id)),
                ("predicate_code", assertion.predicate_code),
                ("object_type", assertion.object_table or ""),
                ("object_id", "" if assertion.object_id is None else str(assertion.object_id)),
                ("literal_value", {key: value for key, value in assertion.literal_value}),
                ("qualifiers", {}),
                ("document_version_id", ""),
                ("fragment_id", str(assertion.evidence_link_ids[0])),
                ("assertion_score", assertion.score),
                ("lifecycle_status", assertion.status.value),
                ("review_state", assertion.review_state.value),
                ("semantic_version", 1),
                ("valid_from", assertion.created_at.isoformat()),
                ("valid_to", None),
                ("embedding", list(embeddings_by_source[assertion.assertion_id])),
            ),
        )

    @staticmethod
    def _fact_document(fact: ConsolidatedFact, embeddings_by_source: dict[EntityId, tuple[float, ...]]) -> SearchDocument:
        return SearchDocument(
            search_document_id=EntityId.from_seed("search.document", f"ikc-facts-v1:{fact.fact_id}"),
            source_type="fact",
            source_entity_id=fact.fact_id,
            canonical_id=str(fact.fact_id),
            index_text=SearchProjector._predicate_summary(fact.subject_table, fact.predicate_code, fact.object_table, fact.literal_value),
            metadata=(("predicate_code", fact.predicate_code), ("subject_type", fact.subject_table), ("object_type", fact.object_table or "")),
            provenance=(("source", "semantic.consolidated_fact"), ("claim_key", fact.claim_key)),
            state=(("fact_status", fact.lifecycle.value), ("semantic_version", fact.version)),
            index_name="ikc-facts-v1",
            fields=(
                ("id", str(fact.fact_id)),
                ("fact_key", fact.claim_key),
                ("subject_type", fact.subject_table),
                ("subject_id", str(fact.subject_id)),
                ("predicate_code", fact.predicate_code),
                ("object_type", fact.object_table or ""),
                ("object_id", "" if fact.object_id is None else str(fact.object_id)),
                ("literal_value", {key: value for key, value in fact.literal_value}),
                ("qualifiers", {"scope": fact.scope, "value_key": fact.value_key}),
                ("confidence_score", 1.0),
                ("fact_status", fact.lifecycle.value),
                ("evidence_level", len(fact.support_link_ids)),
                ("semantic_version", fact.version),
                ("valid_from", fact.created_at.isoformat()),
                ("valid_to", None),
                ("explanation_summary", fact.claim_key),
                ("embedding", list(embeddings_by_source[fact.fact_id])),
            ),
        )

    @staticmethod
    def _predicate_summary(subject_table: str, predicate_code: str, object_table: str | None, literal_value: tuple[tuple[str, str], ...]) -> str:
        literal = " ".join(f"{key}={value}" for key, value in literal_value)
        return " ".join(part for part in (subject_table, predicate_code, object_table or "", literal) if part)