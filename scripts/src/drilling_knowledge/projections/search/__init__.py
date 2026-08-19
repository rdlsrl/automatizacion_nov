"""Deterministic search projection service."""

from drilling_knowledge.projections.search.domain import EmbeddingRequest, EmbeddingResult, SearchDocument, SearchProjectionBatch, SearchProjectionMetrics
from drilling_knowledge.projections.search.opensearch import OpenSearchIndexAlias, OpenSearchIndexTemplate, OpenSearchTemplateBundle, OpenSearchTemplateBundleLoader
from drilling_knowledge.projections.search.repositories import InMemorySearchProjectionBatchRepository, InMemorySearchSynonymRepository, SearchProjectionBatchRepository, SQLiteSearchProjectionBatchRepository
from drilling_knowledge.projections.search.service import EmbeddingProvider, SearchProjector
from drilling_knowledge.projections.search.synonyms import SearchSynonymCatalog, SearchSynonymCatalogLoader, SearchSynonymEntry, SynonymStatus

__all__ = [
    "EmbeddingProvider",
    "EmbeddingRequest",
    "EmbeddingResult",
    "InMemorySearchProjectionBatchRepository",
    "InMemorySearchSynonymRepository",
    "OpenSearchIndexAlias",
    "OpenSearchIndexTemplate",
    "OpenSearchTemplateBundle",
    "OpenSearchTemplateBundleLoader",
    "SearchDocument",
    "SearchProjectionBatch",
    "SearchProjectionBatchRepository",
    "SQLiteSearchProjectionBatchRepository",
    "SearchProjectionMetrics",
    "SearchProjector",
    "SearchSynonymCatalog",
    "SearchSynonymCatalogLoader",
    "SearchSynonymEntry",
    "SynonymStatus",
]