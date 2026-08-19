"""Document knowledge acquisition pipeline for structural ingestion only."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from drilling_knowledge.common.ids import EntityId
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
from drilling_knowledge.documents.parsers import ParsedDocumentStructure, StructuralDocumentParser
from drilling_knowledge.documents.repositories import InMemoryDocumentRepository


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    snapshot: DocumentKnowledgeSnapshot
    repository: InMemoryDocumentRepository


@dataclass(slots=True)
class DocumentKnowledgeAcquisitionEngine:
    repository: InMemoryDocumentRepository
    parser: StructuralDocumentParser

    @classmethod
    def create(cls) -> "DocumentKnowledgeAcquisitionEngine":
        return cls(repository=InMemoryDocumentRepository.empty(), parser=StructuralDocumentParser())

    def ingest(self, path: str | Path, metadata: DocumentMetadata, *, external_reference: str | None = None) -> AcquisitionResult:
        file_path = Path(path)
        content_bytes = file_path.read_bytes()
        parsed = self.parser.parse(file_path, content_bytes)
        snapshot = self._build_snapshot(file_path, content_bytes, parsed, metadata, external_reference=external_reference)
        snapshot.validate().require_valid(code="document_snapshot_validation_failed")
        merged_repository = self.repository.merge(snapshot)
        self.repository = merged_repository
        return AcquisitionResult(snapshot=snapshot, repository=merged_repository)

    def _build_snapshot(
        self,
        file_path: Path,
        content_bytes: bytes,
        parsed: ParsedDocumentStructure,
        metadata: DocumentMetadata,
        *,
        external_reference: str | None,
    ) -> DocumentKnowledgeSnapshot:
        content_hash = sha256(content_bytes).hexdigest()
        logical_key = self._stable_key(parsed.title, metadata)
        document_id = EntityId.from_seed("documents.document", logical_key)
        version_id = EntityId.from_seed("documents.version", content_hash)
        document = Document(
            entity_id=document_id,
            title=parsed.title,
            metadata=metadata,
            logical_key=logical_key,
            external_reference=external_reference,
        )
        version = DocumentVersion(
            entity_id=version_id,
            document_id=document_id,
            content_hash=content_hash,
            file_name=file_path.name,
            mime_type=parsed.mime_type,
            page_count=parsed.page_count,
            parser_name=parsed.parser_name,
            size_bytes=len(content_bytes),
        )
        sections, section_keys = self._build_sections(parsed, version_id)
        tables = self._build_tables(parsed, document_id, version_id, sections)
        figures = self._build_figures(parsed, document_id, version_id, sections)
        fragments = self._build_fragments(parsed, document_id, version_id, sections, section_keys, tables, figures)
        references = self._build_references(parsed, document_id, version_id, sections, section_keys, tables, figures)
        glossary_terms = self._build_glossary_terms(parsed, document_id, version_id, sections)
        return DocumentKnowledgeSnapshot(
            document=document,
            version=version,
            sections=sections,
            fragments=fragments,
            figures=figures,
            tables=tables,
            references=references,
            glossary_terms=glossary_terms,
        )

    def _build_sections(self, parsed: ParsedDocumentStructure, version_id: EntityId) -> tuple[tuple[DocumentSection, ...], list[tuple[int, EntityId]]]:
        sections: list[DocumentSection] = []
        stack: list[tuple[int, DocumentSection]] = []
        section_keys: list[tuple[int, EntityId]] = []
        root = DocumentSection(
            entity_id=EntityId.from_seed("documents.section", f"{version_id}:root"),
            document_version_id=version_id,
            title=parsed.title,
            level=1,
            ordinal=0,
            path=parsed.title,
        )
        sections.append(root)
        stack.append((1, root))
        section_keys.append((0, root.entity_id))
        heading_index = 1
        for paragraph_index, paragraph in enumerate(parsed.paragraphs, start=1):
            if paragraph.heading_level is None:
                continue
            while stack and stack[-1][0] >= paragraph.heading_level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            section = DocumentSection(
                entity_id=EntityId.from_seed("documents.section", f"{version_id}:{paragraph.heading_level}:{paragraph_index}:{paragraph.text}"),
                document_version_id=version_id,
                title=paragraph.text,
                level=paragraph.heading_level,
                ordinal=heading_index,
                path=f"{parent.path}/{paragraph.text}",
                parent_section_id=parent.entity_id,
                page_start=paragraph.page_number,
                page_end=paragraph.page_number,
            )
            sections.append(section)
            stack.append((paragraph.heading_level, section))
            section_keys.append((paragraph_index, section.entity_id))
            heading_index += 1
        return tuple(sections), section_keys

    def _section_for_paragraph(self, paragraph_index: int, section_keys: list[tuple[int, EntityId]]) -> EntityId:
        matching = [section_id for index, section_id in section_keys if index <= paragraph_index]
        return matching[-1]

    def _build_tables(
        self,
        parsed: ParsedDocumentStructure,
        document_id: EntityId,
        version_id: EntityId,
        sections: tuple[DocumentSection, ...],
    ) -> tuple[Table, ...]:
        root_section_id = sections[0].entity_id
        tables: list[Table] = []
        for ordinal, raw_table in enumerate(parsed.tables, start=1):
            table_id = EntityId.from_seed("documents.table", f"{version_id}:{ordinal}:{raw_table.label}")
            trace = DocumentTrace(document_id=document_id, document_version_id=version_id, page_number=raw_table.page_number, section_id=root_section_id, table_id=table_id)
            tables.append(Table(entity_id=table_id, trace=trace, ordinal=ordinal, label=raw_table.label, rows=raw_table.rows, caption=raw_table.caption))
        return tuple(tables)

    def _build_figures(
        self,
        parsed: ParsedDocumentStructure,
        document_id: EntityId,
        version_id: EntityId,
        sections: tuple[DocumentSection, ...],
    ) -> tuple[Figure, ...]:
        root_section_id = sections[0].entity_id
        figures: list[Figure] = []
        for ordinal, raw_figure in enumerate(parsed.figures, start=1):
            figure_id = EntityId.from_seed("documents.figure", f"{version_id}:{ordinal}:{raw_figure.label}")
            trace = DocumentTrace(document_id=document_id, document_version_id=version_id, page_number=raw_figure.page_number, section_id=root_section_id, figure_id=figure_id)
            figures.append(Figure(entity_id=figure_id, trace=trace, ordinal=ordinal, label=raw_figure.label, caption=raw_figure.caption))
        return tuple(figures)

    def _build_fragments(
        self,
        parsed: ParsedDocumentStructure,
        document_id: EntityId,
        version_id: EntityId,
        sections: tuple[DocumentSection, ...],
        section_keys: list[tuple[int, EntityId]],
        tables: tuple[Table, ...],
        figures: tuple[Figure, ...],
    ) -> tuple[DocumentFragment, ...]:
        table_cycle = list(tables)
        figure_cycle = list(figures)
        fragments: list[DocumentFragment] = []
        for ordinal, paragraph in enumerate(parsed.paragraphs, start=1):
            section_id = self._section_for_paragraph(ordinal, section_keys)
            normalized_text = self._normalize_text(paragraph.text)
            trace = DocumentTrace(
                document_id=document_id,
                document_version_id=version_id,
                page_number=paragraph.page_number,
                section_id=section_id,
                paragraph_ordinal=ordinal,
            )
            if paragraph.source_kind == "table_caption" and table_cycle:
                trace = DocumentTrace(
                    document_id=document_id,
                    document_version_id=version_id,
                    page_number=paragraph.page_number,
                    section_id=section_id,
                    paragraph_ordinal=ordinal,
                    table_id=table_cycle[0].entity_id,
                )
            if paragraph.source_kind == "figure_caption" and figure_cycle:
                trace = DocumentTrace(
                    document_id=document_id,
                    document_version_id=version_id,
                    page_number=paragraph.page_number,
                    section_id=section_id,
                    paragraph_ordinal=ordinal,
                    figure_id=figure_cycle[0].entity_id,
                )
            fragment = DocumentFragment(
                entity_id=EntityId.from_seed("documents.fragment", f"{version_id}:{ordinal}:{normalized_text}"),
                trace=trace,
                fragment_type="heading" if paragraph.heading_level is not None else "paragraph",
                ordinal_in_parent=ordinal,
                text_content=paragraph.text,
                normalized_text=normalized_text,
                content_hash=self._fragment_hash(version_id, "paragraph", ordinal, normalized_text, trace),
                layout_metadata={"source_kind": paragraph.source_kind, "heading_level": paragraph.heading_level},
            )
            fragments.append(fragment)
        for ordinal, table in enumerate(tables, start=1):
            trace = DocumentTrace(
                document_id=document_id,
                document_version_id=version_id,
                page_number=table.trace.page_number,
                section_id=table.trace.section_id,
                table_id=table.entity_id,
            )
            fragments.append(
                DocumentFragment(
                    entity_id=EntityId.from_seed("documents.fragment", f"{version_id}:table:{ordinal}:{table.label}"),
                    trace=trace,
                    fragment_type="table",
                    ordinal_in_parent=ordinal,
                    text_content="\n".join(" | ".join(row) for row in table.rows),
                    normalized_text=self._normalize_text(" ".join(" ".join(row) for row in table.rows)),
                    content_hash=self._fragment_hash(
                        version_id,
                        "table",
                        ordinal,
                        self._normalize_text(" ".join(" ".join(row) for row in table.rows)),
                        trace,
                    ),
                    layout_metadata={"row_count": len(table.rows), "column_count": len(table.rows[0]) if table.rows else 0},
                )
            )
        for ordinal, figure in enumerate(figures, start=1):
            trace = DocumentTrace(
                document_id=document_id,
                document_version_id=version_id,
                page_number=figure.trace.page_number,
                section_id=figure.trace.section_id,
                figure_id=figure.entity_id,
            )
            fragments.append(
                DocumentFragment(
                    entity_id=EntityId.from_seed("documents.fragment", f"{version_id}:figure:{ordinal}:{figure.label}"),
                    trace=trace,
                    fragment_type="figure",
                    ordinal_in_parent=ordinal,
                    text_content=figure.caption or figure.label,
                    normalized_text=self._normalize_text(figure.caption or figure.label),
                    content_hash=self._fragment_hash(
                        version_id,
                        "figure",
                        ordinal,
                        self._normalize_text(figure.caption or figure.label),
                        trace,
                    ),
                    layout_metadata={"label": figure.label},
                )
            )
        return tuple(fragments)

    def _build_references(
        self,
        parsed: ParsedDocumentStructure,
        document_id: EntityId,
        version_id: EntityId,
        sections: tuple[DocumentSection, ...],
        section_keys: list[tuple[int, EntityId]],
        tables: tuple[Table, ...],
        figures: tuple[Figure, ...],
    ) -> tuple[Reference, ...]:
        root_section_id = sections[0].entity_id
        section_number_map = self._section_number_map(sections)
        table_number_map = self._numbered_entity_map(tables)
        figure_number_map = self._numbered_entity_map(figures)
        references: list[Reference] = []
        for ordinal, raw_reference in enumerate(parsed.references, start=1):
            trace = DocumentTrace(document_id=document_id, document_version_id=version_id, page_number=raw_reference.page_number, section_id=root_section_id)
            resolved_section_id, resolved_table_id, resolved_figure_id = self._resolve_reference_targets(
                raw_reference.text,
                section_number_map,
                table_number_map,
                figure_number_map,
            )
            references.append(
                Reference(
                    entity_id=EntityId.from_seed("documents.reference", f"{version_id}:{ordinal}:{raw_reference.text}:{raw_reference.target or ''}"),
                    trace=trace,
                    reference_text=raw_reference.text,
                    reference_type=raw_reference.reference_type,
                    target_text=raw_reference.target,
                    resolved_section_id=resolved_section_id,
                    resolved_table_id=resolved_table_id,
                    resolved_figure_id=resolved_figure_id,
                )
            )
        structural_reference_index = len(references)
        for paragraph_ordinal, paragraph in enumerate(parsed.paragraphs, start=1):
            section_id = self._section_for_paragraph(paragraph_ordinal, section_keys)
            for match in self._extract_structural_references(paragraph.text):
                structural_reference_index += 1
                resolved_section_id, resolved_table_id, resolved_figure_id = self._resolve_reference_targets(
                    match.group(0),
                    section_number_map,
                    table_number_map,
                    figure_number_map,
                )
                references.append(
                    Reference(
                        entity_id=EntityId.from_seed(
                            "documents.reference",
                            f"{version_id}:structural:{structural_reference_index}:{paragraph_ordinal}:{match.group(0)}",
                        ),
                        trace=DocumentTrace(
                            document_id=document_id,
                            document_version_id=version_id,
                            page_number=paragraph.page_number,
                            section_id=section_id,
                            paragraph_ordinal=paragraph_ordinal,
                        ),
                        reference_text=match.group(0),
                        reference_type="structural_reference",
                        target_text=match.group("target_number"),
                        resolved_section_id=resolved_section_id,
                        resolved_table_id=resolved_table_id,
                        resolved_figure_id=resolved_figure_id,
                    )
                )
        return tuple(references)

    def _build_glossary_terms(
        self,
        parsed: ParsedDocumentStructure,
        document_id: EntityId,
        version_id: EntityId,
        sections: tuple[DocumentSection, ...],
    ) -> tuple[GlossaryTerm, ...]:
        root_section_id = sections[0].entity_id
        glossary_terms: list[GlossaryTerm] = []
        for ordinal, raw_term in enumerate(parsed.glossary_terms, start=1):
            trace = DocumentTrace(document_id=document_id, document_version_id=version_id, page_number=raw_term.page_number, section_id=root_section_id)
            glossary_terms.append(
                GlossaryTerm(
                    entity_id=EntityId.from_seed("documents.glossary", f"{version_id}:{ordinal}:{raw_term.term}"),
                    trace=trace,
                    term=raw_term.term,
                    definition=raw_term.definition,
                )
            )
        return tuple(glossary_terms)

    def _stable_key(self, title: str, metadata: DocumentMetadata) -> str:
        return self._normalize_text(f"{title}|{metadata.stable_label()}")

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _fragment_hash(
        self,
        version_id: EntityId,
        fragment_type: str,
        ordinal: int,
        normalized_text: str,
        trace: DocumentTrace,
    ) -> str:
        seed = "|".join(
            [
                str(version_id),
                fragment_type,
                str(ordinal),
                normalized_text,
                str(trace.page_number or ""),
                str(trace.section_id or ""),
                str(trace.table_id or ""),
                str(trace.figure_id or ""),
                str(trace.paragraph_ordinal or ""),
            ]
        )
        return sha256(seed.encode("utf-8")).hexdigest()

    def _extract_structural_references(self, text: str) -> list[re.Match[str]]:
        return list(
            re.finditer(
                r"\b(?P<target_type>figure|fig\.?|table|section)\s+(?P<target_number>\d+(?:\.\d+)*)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    def _resolve_reference_targets(
        self,
        reference_text: str,
        section_number_map: dict[str, EntityId],
        table_number_map: dict[str, EntityId],
        figure_number_map: dict[str, EntityId],
    ) -> tuple[EntityId | None, EntityId | None, EntityId | None]:
        match = re.search(
            r"\b(?P<target_type>figure|fig\.?|table|section)\s+(?P<target_number>\d+(?:\.\d+)*)\b",
            reference_text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None, None, None
        target_type = match.group("target_type").lower().rstrip(".")
        target_number = match.group("target_number")
        if target_type in {"figure", "fig"}:
            return None, None, figure_number_map.get(target_number)
        if target_type == "table":
            return None, table_number_map.get(target_number), None
        if target_type == "section":
            return section_number_map.get(target_number), None, None
        return None, None, None

    def _section_number_map(self, sections: tuple[DocumentSection, ...]) -> dict[str, EntityId]:
        mapping: dict[str, EntityId] = {}
        for section in sections:
            match = re.match(r"(?P<number>\d+(?:\.\d+)*)\b", section.title)
            if match is not None:
                mapping[match.group("number")] = section.entity_id
        return mapping

    def _numbered_entity_map(self, entities: tuple[Table, ...] | tuple[Figure, ...]) -> dict[str, EntityId]:
        mapping: dict[str, EntityId] = {}
        for entity in entities:
            mapping[str(entity.ordinal)] = entity.entity_id
            match = re.search(r"\b(\d+(?:\.\d+)*)\b", entity.label)
            if match is not None:
                mapping[match.group(1)] = entity.entity_id
        return mapping