"""Structural document domain for acquisition without semantic interpretation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.common.validation import ValidationReport


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    author: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    version_label: str | None = None
    language: str = "und"
    published_at: date | None = None
    authority_level: str = "unclassified"
    document_type: str = "unknown"
    source: str = "unknown"
    license_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "language", self.language.strip().lower() or "und")
        object.__setattr__(self, "authority_level", self.authority_level.strip().lower() or "unclassified")
        object.__setattr__(self, "document_type", self.document_type.strip().lower() or "unknown")
        object.__setattr__(self, "source", self.source.strip().lower() or "unknown")
        if self.author is not None:
            object.__setattr__(self, "author", self.author.strip() or None)
        if self.manufacturer is not None:
            object.__setattr__(self, "manufacturer", self.manufacturer.strip() or None)
        if self.model is not None:
            object.__setattr__(self, "model", self.model.strip() or None)
        if self.version_label is not None:
            object.__setattr__(self, "version_label", self.version_label.strip() or None)
        if self.license_name is not None:
            object.__setattr__(self, "license_name", self.license_name.strip() or None)

    def stable_label(self) -> str:
        parts = [
            self.document_type,
            self.source,
            self.language,
            self.authority_level,
            self.manufacturer or "",
            self.model or "",
            self.version_label or "",
        ]
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class DocumentTrace:
    document_id: EntityId
    document_version_id: EntityId
    page_number: int | None = None
    section_id: EntityId | None = None
    table_id: EntityId | None = None
    figure_id: EntityId | None = None
    paragraph_ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class Document:
    entity_id: EntityId
    title: str
    metadata: DocumentMetadata
    logical_key: str
    external_reference: str | None = None

    def __post_init__(self) -> None:
        title = self.title.strip()
        logical_key = self.logical_key.strip()
        if not title:
            raise ValueError("Document.title cannot be empty")
        if not logical_key:
            raise ValueError("Document.logical_key cannot be empty")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "logical_key", logical_key)
        if self.external_reference is not None:
            object.__setattr__(self, "external_reference", self.external_reference.strip() or None)


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    entity_id: EntityId
    document_id: EntityId
    content_hash: str
    file_name: str
    mime_type: str
    page_count: int | None
    parser_name: str
    size_bytes: int
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.content_hash.strip():
            raise ValueError("DocumentVersion.content_hash cannot be empty")
        if not self.file_name.strip():
            raise ValueError("DocumentVersion.file_name cannot be empty")
        if not self.mime_type.strip():
            raise ValueError("DocumentVersion.mime_type cannot be empty")
        if not self.parser_name.strip():
            raise ValueError("DocumentVersion.parser_name cannot be empty")
        if self.size_bytes < 0:
            raise ValueError("DocumentVersion.size_bytes cannot be negative")
        if self.page_count is not None and self.page_count < 0:
            raise ValueError("DocumentVersion.page_count cannot be negative")


@dataclass(frozen=True, slots=True)
class DocumentSection:
    entity_id: EntityId
    document_version_id: EntityId
    title: str
    level: int
    ordinal: int
    path: str
    page_start: int | None = None
    page_end: int | None = None
    parent_section_id: EntityId | None = None

    def __post_init__(self) -> None:
        title = self.title.strip()
        path = self.path.strip()
        if not title:
            raise ValueError("DocumentSection.title cannot be empty")
        if self.level <= 0:
            raise ValueError("DocumentSection.level must be positive")
        if self.ordinal < 0:
            raise ValueError("DocumentSection.ordinal cannot be negative")
        if not path:
            raise ValueError("DocumentSection.path cannot be empty")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "path", path)


@dataclass(frozen=True, slots=True)
class DocumentFragment:
    entity_id: EntityId
    trace: DocumentTrace
    fragment_type: str
    ordinal_in_parent: int
    text_content: str
    normalized_text: str
    content_hash: str
    layout_metadata: dict[str, Any] = field(default_factory=dict)
    parent_fragment_id: EntityId | None = None

    def __post_init__(self) -> None:
        fragment_type = self.fragment_type.strip().lower()
        text_content = self.text_content.strip()
        normalized_text = self.normalized_text.strip()
        content_hash = self.content_hash.strip().lower()
        if not fragment_type:
            raise ValueError("DocumentFragment.fragment_type cannot be empty")
        if self.ordinal_in_parent < 0:
            raise ValueError("DocumentFragment.ordinal_in_parent cannot be negative")
        if not text_content:
            raise ValueError("DocumentFragment.text_content cannot be empty")
        if not normalized_text:
            raise ValueError("DocumentFragment.normalized_text cannot be empty")
        if not content_hash:
            raise ValueError("DocumentFragment.content_hash cannot be empty")
        object.__setattr__(self, "fragment_type", fragment_type)
        object.__setattr__(self, "text_content", text_content)
        object.__setattr__(self, "normalized_text", normalized_text)
        object.__setattr__(self, "content_hash", content_hash)


@dataclass(frozen=True, slots=True)
class Figure:
    entity_id: EntityId
    trace: DocumentTrace
    ordinal: int
    label: str
    caption: str | None = None

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("Figure.ordinal cannot be negative")
        label = self.label.strip()
        if not label:
            raise ValueError("Figure.label cannot be empty")
        object.__setattr__(self, "label", label)
        if self.caption is not None:
            object.__setattr__(self, "caption", self.caption.strip() or None)


@dataclass(frozen=True, slots=True)
class Table:
    entity_id: EntityId
    trace: DocumentTrace
    ordinal: int
    label: str
    rows: tuple[tuple[str, ...], ...]
    caption: str | None = None

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("Table.ordinal cannot be negative")
        label = self.label.strip()
        if not label:
            raise ValueError("Table.label cannot be empty")
        if not self.rows:
            raise ValueError("Table.rows cannot be empty")
        object.__setattr__(self, "label", label)
        if self.caption is not None:
            object.__setattr__(self, "caption", self.caption.strip() or None)


@dataclass(frozen=True, slots=True)
class Reference:
    entity_id: EntityId
    trace: DocumentTrace
    reference_text: str
    reference_type: str
    target_text: str | None = None
    resolved_section_id: EntityId | None = None
    resolved_table_id: EntityId | None = None
    resolved_figure_id: EntityId | None = None

    def __post_init__(self) -> None:
        reference_text = self.reference_text.strip()
        reference_type = self.reference_type.strip().lower()
        if not reference_text:
            raise ValueError("Reference.reference_text cannot be empty")
        if not reference_type:
            raise ValueError("Reference.reference_type cannot be empty")
        resolved_targets = [
            self.resolved_section_id,
            self.resolved_table_id,
            self.resolved_figure_id,
        ]
        if sum(target is not None for target in resolved_targets) > 1:
            raise ValueError("Reference can resolve to at most one structural target")
        object.__setattr__(self, "reference_text", reference_text)
        object.__setattr__(self, "reference_type", reference_type)
        if self.target_text is not None:
            object.__setattr__(self, "target_text", self.target_text.strip() or None)


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    entity_id: EntityId
    trace: DocumentTrace
    term: str
    definition: str

    def __post_init__(self) -> None:
        term = self.term.strip()
        definition = self.definition.strip()
        if not term:
            raise ValueError("GlossaryTerm.term cannot be empty")
        if not definition:
            raise ValueError("GlossaryTerm.definition cannot be empty")
        object.__setattr__(self, "term", term)
        object.__setattr__(self, "definition", definition)


@dataclass(frozen=True, slots=True)
class DocumentKnowledgeSnapshot:
    document: Document
    version: DocumentVersion
    sections: tuple[DocumentSection, ...] = ()
    fragments: tuple[DocumentFragment, ...] = ()
    figures: tuple[Figure, ...] = ()
    tables: tuple[Table, ...] = ()
    references: tuple[Reference, ...] = ()
    glossary_terms: tuple[GlossaryTerm, ...] = ()

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        section_ids = {section.entity_id for section in self.sections}
        table_ids = {table.entity_id for table in self.tables}
        figure_ids = {figure.entity_id for figure in self.figures}

        for section in self.sections:
            if section.document_version_id != self.version.entity_id:
                report.add_error("section_version_mismatch", "Section references a different document version")
            if section.parent_section_id and section.parent_section_id not in section_ids:
                report.add_error("unknown_parent_section", "Section references an unknown parent section")

        for fragment in self.fragments:
            if fragment.trace.document_id != self.document.entity_id:
                report.add_error("fragment_document_mismatch", "Fragment references a different document")
            if fragment.trace.document_version_id != self.version.entity_id:
                report.add_error("fragment_version_mismatch", "Fragment references a different document version")
            if fragment.trace.section_id and fragment.trace.section_id not in section_ids:
                report.add_error("unknown_fragment_section", "Fragment references an unknown section")
            if fragment.trace.table_id and fragment.trace.table_id not in table_ids:
                report.add_error("unknown_fragment_table", "Fragment references an unknown table")
            if fragment.trace.figure_id and fragment.trace.figure_id not in figure_ids:
                report.add_error("unknown_fragment_figure", "Fragment references an unknown figure")

        for table in self.tables:
            if table.trace.document_version_id != self.version.entity_id:
                report.add_error("table_version_mismatch", "Table references a different document version")

        for figure in self.figures:
            if figure.trace.document_version_id != self.version.entity_id:
                report.add_error("figure_version_mismatch", "Figure references a different document version")

        for reference in self.references:
            if reference.trace.document_version_id != self.version.entity_id:
                report.add_error("reference_version_mismatch", "Reference references a different document version")
            if reference.resolved_section_id and reference.resolved_section_id not in section_ids:
                report.add_error("unknown_reference_section", "Reference resolves to an unknown section")
            if reference.resolved_table_id and reference.resolved_table_id not in table_ids:
                report.add_error("unknown_reference_table", "Reference resolves to an unknown table")
            if reference.resolved_figure_id and reference.resolved_figure_id not in figure_ids:
                report.add_error("unknown_reference_figure", "Reference resolves to an unknown figure")

        for glossary_term in self.glossary_terms:
            if glossary_term.trace.document_version_id != self.version.entity_id:
                report.add_error("glossary_version_mismatch", "Glossary term references a different document version")
        return report