"""Deterministic search projection contracts for OpenSearch documents."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum

from drilling_knowledge.common.ids import EntityId, Identifier


_OFFICIAL_INDEX_NAMES = frozenset(
    {
        "ikc-variables-v1",
        "ikc-assets-v1",
        "ikc-processes-v1",
        "ikc-documents-v1",
        "ikc-fragments-v1",
        "ikc-assertions-v1",
        "ikc-facts-v1",
        "ikc-aliases-v1",
        "ikc-search-suggestions-v1",
    }
)

_OFFICIAL_SOURCE_TYPES = frozenset(
    {
        "variable",
        "document",
        "fragment",
        "assertion",
        "fact",
    }
)


def _require_entity_id(field_name: str, value: object) -> EntityId:
    if value is None:
        raise ValueError(f"{field_name} cannot be null")
    if not isinstance(value, EntityId):
        raise ValueError(f"{field_name} must be an EntityId")
    if value.as_uuid().int == 0:
        raise ValueError(f"{field_name} cannot be empty")
    return value


def _normalize_fields(field_name: str, values: tuple[tuple[str, object], ...]) -> tuple[tuple[str, object], ...]:
    if values is None:
        raise ValueError(f"{field_name} cannot be null")
    normalized: list[tuple[str, object]] = []
    seen_keys: set[str] = set()
    for key, value in tuple(values):
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError(f"{field_name} cannot contain blank field keys")
        if normalized_key in seen_keys:
            raise ValueError(f"{field_name} cannot contain duplicate field keys")
        seen_keys.add(normalized_key)
        normalized.append((normalized_key, value))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _serialize_value(value: object) -> object:
    if isinstance(value, Identifier):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return value


@dataclass(frozen=True, slots=True)
class SearchDocument:
    search_document_id: EntityId
    source_type: str
    source_entity_id: EntityId
    canonical_id: str
    index_text: str
    metadata: tuple[tuple[str, object], ...]
    provenance: tuple[tuple[str, str], ...]
    state: tuple[tuple[str, object], ...]
    index_name: str
    fields: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        search_document_id = _require_entity_id("SearchDocument.search_document_id", self.search_document_id)
        source_entity_id = _require_entity_id("SearchDocument.source_entity_id", self.source_entity_id)
        source_type = self.source_type.strip().lower()
        canonical_id = self.canonical_id.strip()
        index_text = self.index_text.strip()
        index_name = self.index_name.strip()
        if source_type not in _OFFICIAL_SOURCE_TYPES:
            raise ValueError("SearchDocument.source_type must be one of the official search projection source types")
        if not canonical_id:
            raise ValueError("SearchDocument.canonical_id cannot be empty")
        if not index_text:
            raise ValueError("SearchDocument.index_text cannot be empty")
        if index_name not in _OFFICIAL_INDEX_NAMES:
            raise ValueError("SearchDocument.index_name must be one of the official OpenSearch indices implemented by B050")
        metadata = _normalize_fields("SearchDocument.metadata", self.metadata)
        provenance = tuple(sorted(tuple(self.provenance), key=lambda item: item[0]))
        if not provenance:
            raise ValueError("SearchDocument.provenance cannot be empty")
        for key, value in provenance:
            if not key.strip() or not value.strip():
                raise ValueError("SearchDocument.provenance cannot contain blank keys or values")
        state = _normalize_fields("SearchDocument.state", self.state)
        fields = _normalize_fields("SearchDocument.fields", self.fields)
        object.__setattr__(self, "search_document_id", search_document_id)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "source_entity_id", source_entity_id)
        object.__setattr__(self, "canonical_id", canonical_id)
        object.__setattr__(self, "index_text", index_text)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "index_name", index_name)
        object.__setattr__(self, "fields", fields)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class SearchProjectionMetrics:
    projected_variables: int
    projected_documents: int
    projected_fragments: int
    projected_assertions: int
    projected_facts: int
    projected_documents_total: int

    def __post_init__(self) -> None:
        for field_name in (
            "projected_variables",
            "projected_documents",
            "projected_fragments",
            "projected_assertions",
            "projected_facts",
            "projected_documents_total",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"SearchProjectionMetrics.{field_name} cannot be negative")
        expected_total = (
            self.projected_variables
            + self.projected_documents
            + self.projected_fragments
            + self.projected_assertions
            + self.projected_facts
        )
        if self.projected_documents_total != expected_total:
            raise ValueError("SearchProjectionMetrics.projected_documents_total must match projected document counts")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class SearchProjectionBatch:
    projection_batch_id: EntityId
    documents: tuple[SearchDocument, ...]
    metrics: SearchProjectionMetrics

    def __post_init__(self) -> None:
        projection_batch_id = _require_entity_id("SearchProjectionBatch.projection_batch_id", self.projection_batch_id)
        normalized_documents = tuple(
            sorted(
                tuple(self.documents),
                key=lambda document: (document.index_name, str(document.source_entity_id), str(document.search_document_id)),
            )
        )
        if not normalized_documents:
            raise ValueError("SearchProjectionBatch.documents cannot be empty")
        for document in normalized_documents:
            if not isinstance(document, SearchDocument):
                raise ValueError("SearchProjectionBatch.documents must contain only SearchDocument values")
        if len({document.search_document_id for document in normalized_documents}) != len(normalized_documents):
            raise ValueError("SearchProjectionBatch.documents cannot contain duplicate search document ids")
        if len({(document.index_name, document.source_entity_id) for document in normalized_documents}) != len(normalized_documents):
            raise ValueError("SearchProjectionBatch.documents cannot contain duplicate index/source pairs")
        if self.metrics.projected_documents_total != len(normalized_documents):
            raise ValueError("SearchProjectionBatch.metrics.projected_documents_total must match documents")
        object.__setattr__(self, "projection_batch_id", projection_batch_id)
        object.__setattr__(self, "documents", normalized_documents)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    source_type: str
    source_entity_id: EntityId
    index_name: str
    text: str

    def __post_init__(self) -> None:
        source_type = self.source_type.strip().lower()
        source_entity_id = _require_entity_id("EmbeddingRequest.source_entity_id", self.source_entity_id)
        index_name = self.index_name.strip()
        text = self.text.strip()
        if source_type not in _OFFICIAL_SOURCE_TYPES:
            raise ValueError("EmbeddingRequest.source_type must be one of the official search projection source types")
        if index_name not in _OFFICIAL_INDEX_NAMES:
            raise ValueError("EmbeddingRequest.index_name must be one of the official OpenSearch indices implemented by B050")
        if not text:
            raise ValueError("EmbeddingRequest.text cannot be empty")
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "source_entity_id", source_entity_id)
        object.__setattr__(self, "index_name", index_name)
        object.__setattr__(self, "text", text)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    source_type: str
    source_entity_id: EntityId
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        source_type = self.source_type.strip().lower()
        source_entity_id = _require_entity_id("EmbeddingResult.source_entity_id", self.source_entity_id)
        if source_type not in _OFFICIAL_SOURCE_TYPES:
            raise ValueError("EmbeddingResult.source_type must be one of the official search projection source types")
        if not self.vector:
            raise ValueError("EmbeddingResult.vector cannot be empty")
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "source_entity_id", source_entity_id)
        object.__setattr__(self, "vector", tuple(float(value) for value in self.vector))

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)