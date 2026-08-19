"""Document acquisition package."""

from drilling_knowledge.documents.domain import (
    Document,
    DocumentFragment,
    DocumentKnowledgeSnapshot,
    DocumentMetadata,
    DocumentSection,
    DocumentTrace,
    DocumentVersion,
    Figure,
    GlossaryTerm,
    Reference,
    Table,
)
from drilling_knowledge.documents.pipeline import AcquisitionResult, DocumentKnowledgeAcquisitionEngine
from drilling_knowledge.documents.repositories import InMemoryDocumentRepository

__all__ = [
    "AcquisitionResult",
    "Document",
    "DocumentFragment",
    "DocumentKnowledgeAcquisitionEngine",
    "DocumentKnowledgeSnapshot",
    "DocumentMetadata",
    "DocumentSection",
    "DocumentTrace",
    "DocumentVersion",
    "Figure",
    "GlossaryTerm",
    "InMemoryDocumentRepository",
    "Reference",
    "Table",
]