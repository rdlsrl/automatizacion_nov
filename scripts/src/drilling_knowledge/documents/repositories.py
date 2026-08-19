"""In-memory repositories for structural document acquisition."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.documents.domain import (
    Document,
    DocumentFragment,
    DocumentKnowledgeSnapshot,
    DocumentSection,
    DocumentVersion,
    Figure,
    GlossaryTerm,
    Reference,
    Table,
)


@dataclass(slots=True)
class InMemoryDocumentRepository:
    documents: tuple[Document, ...] = ()
    versions: tuple[DocumentVersion, ...] = ()
    sections: tuple[DocumentSection, ...] = ()
    fragments: tuple[DocumentFragment, ...] = ()
    figures: tuple[Figure, ...] = ()
    tables: tuple[Table, ...] = ()
    references: tuple[Reference, ...] = ()
    glossary_terms: tuple[GlossaryTerm, ...] = ()
    _documents_by_logical_key: dict[str, Document] = field(init=False, default_factory=dict)
    _versions_by_hash: dict[str, DocumentVersion] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        logical_keys: dict[str, Document] = {}
        for document in self.documents:
            if document.logical_key in logical_keys and logical_keys[document.logical_key] != document:
                raise ConflictError(
                    code="duplicate_document_logical_key",
                    message="Duplicate document logical key detected",
                    context={"logical_key": document.logical_key},
                )
            logical_keys[document.logical_key] = document
        version_hashes: dict[str, DocumentVersion] = {}
        for version in self.versions:
            if version.content_hash in version_hashes and version_hashes[version.content_hash] != version:
                raise ConflictError(
                    code="duplicate_document_version_hash",
                    message="Duplicate document version content hash detected",
                    context={"content_hash": version.content_hash},
                )
            version_hashes[version.content_hash] = version
        object.__setattr__(self, "_documents_by_logical_key", logical_keys)
        object.__setattr__(self, "_versions_by_hash", version_hashes)

    @classmethod
    def empty(cls) -> "InMemoryDocumentRepository":
        return cls()

    def merge(self, snapshot: DocumentKnowledgeSnapshot) -> "InMemoryDocumentRepository":
        existing_document = self._documents_by_logical_key.get(snapshot.document.logical_key)
        if existing_document is None:
            documents = self.documents + (snapshot.document,)
        elif existing_document != snapshot.document:
            raise ConflictError(
                code="document_logical_key_conflict",
                message="Existing document logical key maps to different document content",
                context={"logical_key": snapshot.document.logical_key},
            )
        else:
            documents = self.documents

        existing_version = self._versions_by_hash.get(snapshot.version.content_hash)
        if existing_version is None:
            versions = self.versions + (snapshot.version,)
            sections = self.sections + snapshot.sections
            fragments = self.fragments + snapshot.fragments
            figures = self.figures + snapshot.figures
            tables = self.tables + snapshot.tables
            references = self.references + snapshot.references
            glossary_terms = self.glossary_terms + snapshot.glossary_terms
        elif existing_version != snapshot.version:
            raise ConflictError(
                code="document_version_hash_conflict",
                message="Existing content hash maps to different document version metadata",
                context={"content_hash": snapshot.version.content_hash},
            )
        else:
            versions = self.versions
            sections = self.sections
            fragments = self.fragments
            figures = self.figures
            tables = self.tables
            references = self.references
            glossary_terms = self.glossary_terms

        return InMemoryDocumentRepository(
            documents=documents,
            versions=versions,
            sections=sections,
            fragments=fragments,
            figures=figures,
            tables=tables,
            references=references,
            glossary_terms=glossary_terms,
        )