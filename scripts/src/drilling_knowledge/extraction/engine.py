"""Deterministic extraction engine over structural document fragments."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from time import perf_counter
from uuid import UUID

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.documents.domain import DocumentFragment, DocumentKnowledgeSnapshot, Reference, Table
from drilling_knowledge.extraction.domain import (
    ContextWindow,
    ExtractedEntity,
    ExtractedEntityType,
    ExtractedObservation,
    ExtractedObservationType,
    ExtractionMetricRecord,
    ExtractionMetrics,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionSourceTrace,
)
from drilling_knowledge.extraction.rules import RuleMatch, apply_lexicon_rules, apply_regex_rules


@dataclass(slots=True)
class KnowledgeExtractionEngine:
    context_radius: int = 40
    scaling_pattern = __import__("re").compile(
        r"(?P<raw_value>\d+(?:\.\d+)?)\s*(?P<raw_unit>mA|V|counts?|pulses?)\s*=\s*(?P<engineering_value>\d+(?:\.\d+)?)\s*(?P<engineering_unit>klbf|psi|rpm|gpm|ft|in|m|degC|degF|%)",
        __import__("re").IGNORECASE,
    )
    energistics_topic_pattern = re.compile(r"\b(WITSML|RESQML|PRODML)\b", re.IGNORECASE)
    energistics_identifier_pattern = re.compile(r"^[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)*$")

    @classmethod
    def create(cls) -> "KnowledgeExtractionEngine":
        return cls()

    def extract(self, snapshot: DocumentKnowledgeSnapshot) -> ExtractionRun:
        started_clock = perf_counter()
        errors: list[str] = []
        entities: list[ExtractedEntity] = []
        observations: list[ExtractedObservation] = []

        fragment_by_identity = {fragment.entity_id: fragment for fragment in snapshot.fragments}
        paragraph_fragments = [fragment for fragment in snapshot.fragments if fragment.fragment_type in {"paragraph", "heading"}]
        fragment_by_paragraph = {
            fragment.trace.paragraph_ordinal: fragment
            for fragment in paragraph_fragments
            if fragment.trace.paragraph_ordinal is not None
        }
        reference_occurrences: dict[tuple[EntityId, str], int] = {}

        for fragment in snapshot.fragments:
            try:
                fragment_entities, fragment_observations = self._extract_from_fragment(snapshot, fragment)
                entities.extend(fragment_entities)
                observations.extend(fragment_observations)
            except Exception as exc:  # pragma: no cover - defensive guard for metrics
                errors.append(f"fragment:{fragment.entity_id}:{exc}")
        for glossary_term in snapshot.glossary_terms:
            try:
                glossary_entities, glossary_observations = self._extract_from_glossary_term(snapshot, glossary_term)
                entities.extend(glossary_entities)
                observations.extend(glossary_observations)
            except Exception as exc:  # pragma: no cover - defensive guard for metrics
                errors.append(f"glossary:{glossary_term.entity_id}:{exc}")
        for reference in snapshot.references:
            try:
                resolved_fragment = self._fragment_for_reference(reference, fragment_by_paragraph, fragment_by_identity)
                if resolved_fragment is None:
                    continue
                occurrence_key = (resolved_fragment.entity_id, reference.reference_text.casefold())
                occurrence_index = reference_occurrences.get(occurrence_key, 0)
                reference_occurrences[occurrence_key] = occurrence_index + 1
                entity = self._entity_from_reference(snapshot, reference, resolved_fragment, occurrence_index)
                if entity is not None:
                    entities.append(entity)
            except Exception as exc:  # pragma: no cover - defensive guard for metrics
                errors.append(f"reference:{reference.entity_id}:{exc}")
        if self._is_energistics_snapshot(snapshot):
            try:
                schema_entities, schema_observations = self._extract_energistics_schema(snapshot)
                entities.extend(schema_entities)
                observations.extend(schema_observations)
            except Exception as exc:  # pragma: no cover - defensive guard for metrics
                errors.append(f"energistics:{snapshot.version.entity_id}:{exc}")

        entities = self._finalize_entities(entities)
        observations = self._finalize_observations(observations)
        run_id = RunId.from_seed(
            "extraction.run",
            "|".join(
                (
                    str(snapshot.document.entity_id),
                    str(snapshot.version.entity_id),
                    *(str(entity.entity_id) for entity in entities),
                    *(str(observation.observation_id) for observation in observations),
                    *errors,
                )
            ),
        )
        started_at = self._base_timestamp_for(str(run_id))
        finished_at = started_at
        duration_ms = round((perf_counter() - started_clock) * 1000, 3)
        metrics = self._build_metrics(snapshot, entities, duration_ms, tuple(errors))
        status = ExtractionRunStatus.FAILED if errors else ExtractionRunStatus.COMPLETED
        return ExtractionRun(
            run_id=run_id,
            document_id=snapshot.document.entity_id,
            version_id=snapshot.version.entity_id,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            entities=tuple(entities),
            observations=tuple(observations),
            metrics=metrics,
        )

    def _base_timestamp_for(self, base_seed: str) -> datetime:
        seed_uuid = UUID(str(RunId.from_seed("extraction.timestamp", base_seed)))
        offset_seconds = seed_uuid.int % (365 * 24 * 60 * 60)
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset_seconds)

    def _extract_from_fragment(self, snapshot: DocumentKnowledgeSnapshot, fragment: DocumentFragment) -> tuple[list[ExtractedEntity], list[ExtractedObservation]]:
        matches = self._finalize_matches(apply_lexicon_rules(fragment.text_content) + apply_regex_rules(fragment.text_content))
        entities: list[ExtractedEntity] = []
        for ordinal, match in enumerate(matches, start=1):
            entities.append(self._entity_from_match(snapshot, fragment, match, ordinal))
        entities.extend(self._tag_token_entities(snapshot, fragment, entities))
        return entities, self._observations_from_text(snapshot, fragment.entity_id, fragment.text_content, fragment.trace, entities)

    def _extract_from_glossary_term(self, snapshot: DocumentKnowledgeSnapshot, glossary_term) -> tuple[list[ExtractedEntity], list[ExtractedObservation]]:
        glossary_text = f"{glossary_term.term}: {glossary_term.definition}"
        matches = self._finalize_matches(apply_lexicon_rules(glossary_text) + apply_regex_rules(glossary_text))
        entities: list[ExtractedEntity] = []
        for ordinal, match in enumerate(matches, start=1):
            entities.append(self._entity_from_glossary_match(snapshot, glossary_term, glossary_text, match, ordinal))
        entities.extend(self._tag_token_entities(snapshot, glossary_term, entities, glossary_text=glossary_text))
        return entities, self._observations_from_text(snapshot, glossary_term.entity_id, glossary_text, glossary_term.trace, entities)

    def _entity_from_match(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        fragment: DocumentFragment,
        match: RuleMatch,
        ordinal: int,
    ) -> ExtractedEntity:
        original_text = match.text.strip()
        normalized_text = self._normalize_text(original_text)
        source_trace = ExtractionSourceTrace(
            page_number=fragment.trace.page_number,
            section_id=fragment.trace.section_id,
            table_id=fragment.trace.table_id,
            figure_id=fragment.trace.figure_id,
            paragraph_ordinal=fragment.trace.paragraph_ordinal,
            start_offset=match.start_offset,
            end_offset=match.end_offset,
        )
        context_window = self._context_window(fragment.text_content, match.start_offset, match.end_offset)
        position = self._document_position(fragment, source_trace)
        entity_id = EntityId.from_seed(
            "extraction.entity",
            f"{snapshot.version.entity_id}:{fragment.entity_id}:{match.entity_type}:{match.extraction_rule}:{ordinal}:{match.start_offset}:{match.end_offset}:{normalized_text}",
        )
        return ExtractedEntity(
            entity_id=entity_id,
            entity_type=match.entity_type,
            original_text=original_text,
            normalized_text=normalized_text,
            document_position=position,
            fragment_id=fragment.entity_id,
            document_id=snapshot.document.entity_id,
            version_id=snapshot.version.entity_id,
            extraction_confidence=match.extraction_confidence,
            extraction_rule=match.extraction_rule,
            source_trace=source_trace,
            context_window=context_window,
        )

    def _entity_from_glossary_match(self, snapshot, glossary_term, glossary_text: str, match: RuleMatch, ordinal: int) -> ExtractedEntity:
        original_text = match.text.strip()
        normalized_text = self._normalize_text(original_text)
        source_trace = ExtractionSourceTrace(
            page_number=glossary_term.trace.page_number,
            section_id=glossary_term.trace.section_id,
            paragraph_ordinal=glossary_term.trace.paragraph_ordinal,
            start_offset=match.start_offset,
            end_offset=match.end_offset,
        )
        context_window = self._context_window(glossary_text, match.start_offset, match.end_offset)
        position = self._document_position_from_trace(glossary_term.entity_id, source_trace)
        entity_id = EntityId.from_seed(
            "extraction.entity",
            f"{snapshot.version.entity_id}:{glossary_term.entity_id}:{match.entity_type}:{match.extraction_rule}:{ordinal}:{match.start_offset}:{match.end_offset}:{normalized_text}",
        )
        return ExtractedEntity(
            entity_id=entity_id,
            entity_type=match.entity_type,
            original_text=original_text,
            normalized_text=normalized_text,
            document_position=position,
            fragment_id=glossary_term.entity_id,
            document_id=snapshot.document.entity_id,
            version_id=snapshot.version.entity_id,
            extraction_confidence=match.extraction_confidence,
            extraction_rule=match.extraction_rule,
            source_trace=source_trace,
            context_window=context_window,
        )

    def _entity_from_reference(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        reference: Reference,
        fragment: DocumentFragment,
        occurrence_index: int,
    ) -> ExtractedEntity | None:
        entity_type = self._reference_entity_type(reference)
        if entity_type is None:
            return None
        start_offset, end_offset = self._find_span(fragment.text_content, reference.reference_text, occurrence_index)
        source_trace = ExtractionSourceTrace(
            page_number=reference.trace.page_number,
            section_id=reference.trace.section_id,
            table_id=reference.resolved_table_id,
            figure_id=reference.resolved_figure_id,
            paragraph_ordinal=reference.trace.paragraph_ordinal,
            start_offset=start_offset,
            end_offset=end_offset,
        )
        context_window = self._context_window(fragment.text_content, start_offset, end_offset)
        position = self._document_position(fragment, source_trace)
        normalized_text = self._normalize_text(reference.reference_text)
        entity_id = EntityId.from_seed(
            "extraction.entity",
            f"{snapshot.version.entity_id}:{fragment.entity_id}:{entity_type}:{reference.reference_type}:{occurrence_index}:{reference.reference_text}:{reference.target_text or ''}",
        )
        return ExtractedEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            original_text=reference.reference_text,
            normalized_text=normalized_text,
            document_position=position,
            fragment_id=fragment.entity_id,
            document_id=snapshot.document.entity_id,
            version_id=snapshot.version.entity_id,
            extraction_confidence=1.0,
            extraction_rule=f"reference.snapshot.{reference.reference_type}",
            source_trace=source_trace,
            context_window=context_window,
        )

    def _fragment_for_reference(
        self,
        reference: Reference,
        fragment_by_paragraph: dict[int, DocumentFragment],
        fragment_by_identity: dict[EntityId, DocumentFragment],
    ) -> DocumentFragment | None:
        if reference.trace.paragraph_ordinal is not None:
            fragment = fragment_by_paragraph.get(reference.trace.paragraph_ordinal)
            if fragment is not None:
                return fragment
        for fragment in fragment_by_identity.values():
            if fragment.trace.section_id == reference.trace.section_id and reference.reference_text.lower() in fragment.text_content.lower():
                return fragment
        return None

    def _reference_entity_type(self, reference: Reference) -> ExtractedEntityType:
        if reference.resolved_figure_id is not None:
            return ExtractedEntityType.FIGURE_REFERENCE
        if reference.resolved_table_id is not None:
            return ExtractedEntityType.TABLE_REFERENCE
        if reference.resolved_section_id is not None:
            return ExtractedEntityType.SECTION_REFERENCE
        lowered = reference.reference_text.strip().lower()
        if lowered.startswith(("figure ", "fig. ", "fig ")):
            return ExtractedEntityType.FIGURE_REFERENCE
        if lowered.startswith("table "):
            return ExtractedEntityType.TABLE_REFERENCE
        if lowered.startswith("section "):
            return ExtractedEntityType.SECTION_REFERENCE
        return ExtractedEntityType.DOCUMENT_REFERENCE

    def _context_window(self, text: str, start_offset: int | None, end_offset: int | None) -> ContextWindow:
        if start_offset is None or end_offset is None or start_offset < 0 or end_offset < 0:
            return ContextWindow(match_text=text)
        before_start = max(0, start_offset - self.context_radius)
        after_end = min(len(text), end_offset + self.context_radius)
        return ContextWindow(
            before_text=text[before_start:start_offset],
            match_text=text[start_offset:end_offset],
            after_text=text[end_offset:after_end],
        )

    def _document_position(self, fragment: DocumentFragment, trace: ExtractionSourceTrace) -> str:
        return self._document_position_from_trace(fragment.entity_id, trace)

    def _document_position_from_trace(self, carrier_id: EntityId, trace: ExtractionSourceTrace) -> str:
        parts = [
            f"fragment={carrier_id}",
            f"page={trace.page_number if trace.page_number is not None else 'na'}",
            f"section={trace.section_id if trace.section_id is not None else 'na'}",
            f"paragraph={trace.paragraph_ordinal if trace.paragraph_ordinal is not None else 'na'}",
            f"span={trace.start_offset if trace.start_offset is not None else 'na'}:{trace.end_offset if trace.end_offset is not None else 'na'}",
        ]
        return "|".join(parts)

    def _tag_token_entities(self, snapshot, carrier, entities: list[ExtractedEntity], *, glossary_text: str | None = None) -> list[ExtractedEntity]:
        source_text = glossary_text
        if source_text is None:
            source_text = carrier.text_content
        token_entities: list[ExtractedEntity] = []
        for entity in entities:
            if entity.entity_type != ExtractedEntityType.TAG:
                continue
            if entity.source_trace.start_offset is None or entity.source_trace.end_offset is None:
                continue
            for token_ordinal, token_match in enumerate(__import__("re").finditer(r"[A-Za-z0-9]+", entity.original_text), start=1):
                start_offset = entity.source_trace.start_offset + token_match.start()
                end_offset = entity.source_trace.start_offset + token_match.end()
                token_text = token_match.group(0)
                source_trace = ExtractionSourceTrace(
                    page_number=entity.source_trace.page_number,
                    section_id=entity.source_trace.section_id,
                    table_id=entity.source_trace.table_id,
                    figure_id=entity.source_trace.figure_id,
                    paragraph_ordinal=entity.source_trace.paragraph_ordinal,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                token_entities.append(
                    ExtractedEntity(
                        entity_id=EntityId.from_seed(
                            "extraction.entity",
                            f"{snapshot.version.entity_id}:{entity.fragment_id}:{ExtractedEntityType.TAG_TOKEN.value}:{entity.entity_id}:{token_ordinal}:{token_text}:{start_offset}:{end_offset}",
                        ),
                        entity_type=ExtractedEntityType.TAG_TOKEN,
                        original_text=token_text,
                        normalized_text=self._normalize_text(token_text),
                        document_position=self._document_position_from_trace(entity.fragment_id, source_trace),
                        fragment_id=entity.fragment_id,
                        document_id=entity.document_id,
                        version_id=entity.version_id,
                        extraction_confidence=entity.extraction_confidence,
                        extraction_rule="tag.tokenization.v1",
                        source_trace=source_trace,
                        context_window=self._context_window(source_text, start_offset, end_offset),
                    )
                )
        return token_entities

    def _observations_from_text(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        fragment_id: EntityId,
        text: str,
        trace,
        entities: list[ExtractedEntity],
    ) -> list[ExtractedObservation]:
        observations: list[ExtractedObservation] = []
        observations.extend(self._unit_association_observations(snapshot, fragment_id, text, trace, entities))
        observations.extend(self._explicit_scaling_observations(snapshot, fragment_id, text, trace))
        return observations

    def _unit_association_observations(self, snapshot, fragment_id: EntityId, text: str, trace, entities: list[ExtractedEntity]) -> list[ExtractedObservation]:
        unit_types = {ExtractedEntityType.ENGINEERING_UNIT}
        variable_like_types = {ExtractedEntityType.VARIABLE, ExtractedEntityType.MNEMONIC}
        observations: list[ExtractedObservation] = []
        line_start = 0
        for line in text.splitlines() or [text]:
            line_end = line_start + len(line)
            line_entities = [
                entity for entity in entities
                if entity.source_trace.start_offset is not None
                and entity.source_trace.end_offset is not None
                and entity.source_trace.start_offset >= line_start
                and entity.source_trace.end_offset <= line_end
            ]
            variables = [entity for entity in line_entities if entity.entity_type in variable_like_types]
            units = [entity for entity in line_entities if entity.entity_type in unit_types]
            for variable in variables:
                for unit in units:
                    start_offset = min(variable.source_trace.start_offset, unit.source_trace.start_offset)
                    end_offset = max(variable.source_trace.end_offset, unit.source_trace.end_offset)
                    original_text = text[start_offset:end_offset]
                    source_trace = ExtractionSourceTrace(
                        page_number=trace.page_number,
                        section_id=trace.section_id,
                        table_id=trace.table_id,
                        figure_id=trace.figure_id,
                        paragraph_ordinal=trace.paragraph_ordinal,
                        start_offset=start_offset,
                        end_offset=end_offset,
                    )
                    observations.append(
                        ExtractedObservation(
                            observation_id=EntityId.from_seed(
                                "extraction.observation",
                                f"{snapshot.version.entity_id}:{fragment_id}:{ExtractedObservationType.TEXTUAL_UNIT_ASSOCIATION.value}:{variable.entity_id}:{unit.entity_id}:{start_offset}:{end_offset}",
                            ),
                            observation_type=ExtractedObservationType.TEXTUAL_UNIT_ASSOCIATION,
                            original_text=original_text,
                            normalized_text=self._normalize_text(original_text),
                            document_position=self._document_position_from_trace(fragment_id, source_trace),
                            fragment_id=fragment_id,
                            document_id=snapshot.document.entity_id,
                            version_id=snapshot.version.entity_id,
                            extraction_confidence=1.0,
                            extraction_rule="observation.unit_association.line.v1",
                            source_trace=source_trace,
                            context_window=self._context_window(text, start_offset, end_offset),
                            source_entity_id=variable.entity_id,
                            target_entity_id=unit.entity_id,
                            attributes=(("source_type", variable.entity_type.value), ("target_type", unit.entity_type.value)),
                        )
                    )
            line_start = line_end + 1
        return observations

    def _explicit_scaling_observations(self, snapshot, fragment_id: EntityId, text: str, trace) -> list[ExtractedObservation]:
        observations: list[ExtractedObservation] = []
        for ordinal, match in enumerate(self.scaling_pattern.finditer(text), start=1):
            source_trace = ExtractionSourceTrace(
                page_number=trace.page_number,
                section_id=trace.section_id,
                table_id=trace.table_id,
                figure_id=trace.figure_id,
                paragraph_ordinal=trace.paragraph_ordinal,
                start_offset=match.start(),
                end_offset=match.end(),
            )
            original_text = match.group(0)
            observations.append(
                ExtractedObservation(
                    observation_id=EntityId.from_seed(
                        "extraction.observation",
                        f"{snapshot.version.entity_id}:{fragment_id}:{ExtractedObservationType.EXPLICIT_SCALING.value}:{ordinal}:{match.start()}:{match.end()}:{original_text}",
                    ),
                    observation_type=ExtractedObservationType.EXPLICIT_SCALING,
                    original_text=original_text,
                    normalized_text=self._normalize_text(original_text),
                    document_position=self._document_position_from_trace(fragment_id, source_trace),
                    fragment_id=fragment_id,
                    document_id=snapshot.document.entity_id,
                    version_id=snapshot.version.entity_id,
                    extraction_confidence=1.0,
                    extraction_rule="observation.explicit_scaling.regex.v1",
                    source_trace=source_trace,
                    context_window=self._context_window(text, match.start(), match.end()),
                    attributes=(
                        ("raw_value", match.group("raw_value")),
                        ("raw_unit", match.group("raw_unit")),
                        ("engineering_value", match.group("engineering_value")),
                        ("engineering_unit", match.group("engineering_unit")),
                    ),
                )
            )
        return observations

    def _find_span(self, text: str, target: str, occurrence_index: int = 0) -> tuple[int | None, int | None]:
        lowered_text = text.lower()
        lowered_target = target.lower()
        search_from = 0
        found_count = 0
        while True:
            index = lowered_text.find(lowered_target, search_from)
            if index < 0:
                return None, None
            if found_count == occurrence_index:
                return index, index + len(target)
            found_count += 1
            search_from = index + len(target)

    def _is_energistics_snapshot(self, snapshot: DocumentKnowledgeSnapshot) -> bool:
        return bool(
            self.energistics_topic_pattern.search(snapshot.version.file_name)
            or self.energistics_topic_pattern.search(snapshot.document.title)
        )

    def _extract_energistics_schema(self, snapshot: DocumentKnowledgeSnapshot) -> tuple[list[ExtractedEntity], list[ExtractedObservation]]:
        entities: list[ExtractedEntity] = []
        observations: list[ExtractedObservation] = []
        table_fragments = {fragment.trace.table_id: fragment for fragment in snapshot.fragments if fragment.fragment_type == "table" and fragment.trace.table_id is not None}
        owner_text = snapshot.document.title.strip()
        for table in snapshot.tables:
            category = self._energistics_table_category(table)
            if category is None:
                continue
            fragment = table_fragments.get(table.entity_id)
            if fragment is None:
                continue
            owner_entity = self._energistics_schema_entity(snapshot, fragment, owner_text, owner_text, "class", 0)
            entities.append(owner_entity)
            if category == "attributes":
                attribute_entities, attribute_observations = self._extract_energistics_attribute_rows(snapshot, table, fragment, owner_entity)
                entities.extend(attribute_entities)
                observations.extend(attribute_observations)
                continue
            relationship_entities, relationship_observations = self._extract_energistics_relationship_rows(snapshot, table, fragment, owner_entity)
            entities.extend(relationship_entities)
            observations.extend(relationship_observations)
        return entities, observations

    def _energistics_table_category(self, table: Table) -> str | None:
        label = f"{table.label} {table.caption or ''}".strip().casefold()
        if "attributes" in label:
            return "attributes"
        if "relationships" in label:
            return "relationships"
        if not table.rows:
            return None
        header = [cell.strip().casefold() for cell in table.rows[0]]
        if {"name", "type", "notes"}.issubset(set(header)) or {"name", "data type", "notes"}.issubset(set(header)):
            return "attributes"
        if {"role", "class", "cardinality"}.issubset(set(header)):
            return "relationships"
        return None

    def _extract_energistics_attribute_rows(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        table: Table,
        fragment: DocumentFragment,
        owner_entity: ExtractedEntity,
    ) -> tuple[list[ExtractedEntity], list[ExtractedObservation]]:
        entities: list[ExtractedEntity] = []
        observations: list[ExtractedObservation] = []
        for ordinal, row in enumerate(table.rows[1:], start=1):
            name = self._cell(row, 0)
            measure_type = self._cell(row, 1)
            notes = self._cell(row, 2)
            if not name:
                continue
            property_entity = self._energistics_schema_entity(snapshot, fragment, name, owner_entity.original_text, "property", ordinal)
            entities.append(property_entity)
            observations.append(
                self._energistics_relation_observation(
                    snapshot,
                    fragment,
                    owner_entity,
                    property_entity,
                    ExtractedObservationType.HAS_PROPERTY,
                    f"{owner_entity.original_text} has property {name}",
                    ordinal,
                    attributes=(
                        ("table_label", table.label),
                        ("property_name", name),
                        ("description", notes),
                    ),
                )
            )
            if measure_type:
                type_entity = self._energistics_schema_entity(snapshot, fragment, measure_type, owner_entity.original_text, "measure_type", ordinal)
                entities.append(type_entity)
                observations.append(
                    self._energistics_relation_observation(
                        snapshot,
                        fragment,
                        property_entity,
                        type_entity,
                        ExtractedObservationType.MEASUREMENT_TYPE,
                        f"{name} measurement type {measure_type}",
                        ordinal,
                        attributes=(
                            ("table_label", table.label),
                            ("property_name", name),
                            ("description", notes),
                            ("measure_type", measure_type),
                        ),
                    )
                )
        return entities, observations

    def _extract_energistics_relationship_rows(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        table: Table,
        fragment: DocumentFragment,
        owner_entity: ExtractedEntity,
    ) -> tuple[list[ExtractedEntity], list[ExtractedObservation]]:
        entities: list[ExtractedEntity] = []
        observations: list[ExtractedObservation] = []
        for ordinal, row in enumerate(table.rows[1:], start=1):
            role = self._cell(row, 0)
            target_class = self._strip_reference_markup(self._cell(row, 1))
            cardinality = self._cell(row, 2)
            if not role or not target_class:
                continue
            role_entity = self._energistics_schema_entity(snapshot, fragment, role, owner_entity.original_text, "relationship_role", ordinal)
            target_entity = self._energistics_schema_entity(snapshot, fragment, target_class, owner_entity.original_text, "relationship_target", ordinal)
            entities.extend((role_entity, target_entity))
            observations.append(
                self._energistics_relation_observation(
                    snapshot,
                    fragment,
                    owner_entity,
                    target_entity,
                    ExtractedObservationType.HAS_RELATIONSHIP,
                    f"{owner_entity.original_text} has relationship {role} to {target_class}",
                    ordinal,
                    attributes=(
                        ("table_label", table.label),
                        ("role", role),
                        ("target_class", target_class),
                        ("cardinality", cardinality),
                    ),
                )
            )
        derived_from = self._extract_derived_from(snapshot, fragment, owner_entity)
        if derived_from is not None:
            entities.append(derived_from[0])
            observations.append(derived_from[1])
        return entities, observations

    def _extract_derived_from(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        fragment: DocumentFragment,
        owner_entity: ExtractedEntity,
    ) -> tuple[ExtractedEntity, ExtractedObservation] | None:
        pattern = re.compile(r"Derived From:\s+([A-Za-z][A-Za-z0-9]+)", re.IGNORECASE)
        match = pattern.search(fragment.text_content)
        if match is None:
            return None
        target_text = match.group(1).strip()
        target_entity = self._energistics_schema_entity(snapshot, fragment, target_text, owner_entity.original_text, "derived_from", 0)
        observation = self._energistics_relation_observation(
            snapshot,
            fragment,
            owner_entity,
            target_entity,
            ExtractedObservationType.DERIVED_FROM,
            f"{owner_entity.original_text} derived from {target_text}",
            0,
            attributes=(("relation_type", "derived_from"),),
        )
        return target_entity, observation

    def _energistics_schema_entity(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        fragment: DocumentFragment,
        text: str,
        owner_text: str,
        role: str,
        ordinal: int,
    ) -> ExtractedEntity:
        normalized_text = self._normalize_text(text)
        entity_type = ExtractedEntityType.EQUIPMENT if role == "class" else ExtractedEntityType.IDENTIFIER
        start_offset, end_offset = self._find_span(fragment.text_content, text)
        source_trace = ExtractionSourceTrace(
            page_number=fragment.trace.page_number,
            section_id=fragment.trace.section_id,
            table_id=fragment.trace.table_id,
            figure_id=fragment.trace.figure_id,
            paragraph_ordinal=fragment.trace.paragraph_ordinal,
            start_offset=start_offset,
            end_offset=end_offset,
        )
        return ExtractedEntity(
            entity_id=EntityId.from_seed(
                "extraction.entity",
                f"{snapshot.version.entity_id}:{fragment.entity_id}:energistics:{role}:{owner_text}:{ordinal}:{normalized_text}",
            ),
            entity_type=entity_type,
            original_text=text,
            normalized_text=normalized_text,
            document_position=self._document_position(fragment, source_trace),
            fragment_id=fragment.entity_id,
            document_id=snapshot.document.entity_id,
            version_id=snapshot.version.entity_id,
            extraction_confidence=1.0,
            extraction_rule=f"energistics.schema.{role}.v1",
            source_trace=source_trace,
            context_window=self._context_window(fragment.text_content, start_offset, end_offset),
        )

    def _energistics_relation_observation(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        fragment: DocumentFragment,
        source_entity: ExtractedEntity,
        target_entity: ExtractedEntity,
        observation_type: ExtractedObservationType,
        original_text: str,
        ordinal: int,
        *,
        attributes: tuple[tuple[str, str], ...],
    ) -> ExtractedObservation:
        start_offset = source_entity.source_trace.start_offset
        end_offset = target_entity.source_trace.end_offset
        source_trace = ExtractionSourceTrace(
            page_number=fragment.trace.page_number,
            section_id=fragment.trace.section_id,
            table_id=fragment.trace.table_id,
            figure_id=fragment.trace.figure_id,
            paragraph_ordinal=fragment.trace.paragraph_ordinal,
            start_offset=start_offset,
            end_offset=end_offset,
        )
        return ExtractedObservation(
            observation_id=EntityId.from_seed(
                "extraction.observation",
                f"{snapshot.version.entity_id}:{fragment.entity_id}:{observation_type.value}:{source_entity.entity_id}:{target_entity.entity_id}:{ordinal}",
            ),
            observation_type=observation_type,
            original_text=original_text,
            normalized_text=self._normalize_text(original_text),
            document_position=self._document_position(fragment, source_trace),
            fragment_id=fragment.entity_id,
            document_id=snapshot.document.entity_id,
            version_id=snapshot.version.entity_id,
            extraction_confidence=1.0,
            extraction_rule=f"energistics.schema.{observation_type.value.lower()}.v1",
            source_trace=source_trace,
            context_window=self._context_window(fragment.text_content, start_offset, end_offset),
            source_entity_id=source_entity.entity_id,
            target_entity_id=target_entity.entity_id,
            attributes=attributes,
        )

    def _cell(self, row: tuple[str, ...], index: int) -> str:
        if index >= len(row):
            return ""
        return " ".join(row[index].split()).strip()

    def _strip_reference_markup(self, text: str) -> str:
        return " ".join(text.replace("\n", " ").split()).strip()

    def _build_metrics(
        self,
        snapshot: DocumentKnowledgeSnapshot,
        entities: list[ExtractedEntity],
        duration_ms: float,
        errors: tuple[str, ...],
    ) -> ExtractionMetrics:
        type_counts = Counter(entity.entity_type.value for entity in entities)
        rule_counts = Counter(entity.extraction_rule for entity in entities)
        document_counts = Counter(str(entity.document_id) for entity in entities)
        record_counts = Counter((entity.entity_type, entity.document_id, entity.version_id, entity.extraction_rule) for entity in entities)
        records = tuple(
            ExtractionMetricRecord(
                entity_type=key[0],
                document_id=key[1],
                version_id=key[2],
                extraction_rule=key[3],
                count=count,
            )
            for key, count in sorted(record_counts.items(), key=lambda item: (item[0][0].value, str(item[0][1]), item[0][3]))
        )
        if not document_counts:
            document_counts[str(snapshot.document.entity_id)] = 0
        return ExtractionMetrics(
            total_entities=len(entities),
            entity_counts_by_type=dict(sorted(type_counts.items())),
            entity_counts_by_rule=dict(sorted(rule_counts.items())),
            document_counts=dict(sorted(document_counts.items())),
            records=records,
            duration_ms=duration_ms,
            errors=errors,
        )

    def _finalize_entities(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        unique: dict[tuple[str, str, str, int | None, int | None], ExtractedEntity] = {}
        for entity in sorted(entities, key=self._entity_sort_key):
            key = (
                str(entity.fragment_id),
                entity.entity_type.value,
                entity.original_text,
                entity.source_trace.start_offset,
                entity.source_trace.end_offset,
            )
            unique.setdefault(key, entity)
        filtered: list[ExtractedEntity] = []
        for entity in unique.values():
            if self._should_skip_overlapping_entity(entity, filtered):
                continue
            filtered.append(entity)
        return filtered

    def _finalize_observations(self, observations: list[ExtractedObservation]) -> list[ExtractedObservation]:
        unique: dict[tuple[str, str, str, int | None, int | None], ExtractedObservation] = {}
        for observation in sorted(observations, key=self._observation_sort_key):
            key = (
                str(observation.fragment_id),
                observation.observation_type.value,
                observation.original_text,
                observation.source_trace.start_offset,
                observation.source_trace.end_offset,
            )
            unique.setdefault(key, observation)
        return list(unique.values())

    def _finalize_matches(self, matches: list[RuleMatch]) -> list[RuleMatch]:
        ordered = sorted(
            matches,
            key=lambda match: (
                match.start_offset,
                -(match.end_offset - match.start_offset),
                -match.extraction_confidence,
                match.entity_type.value,
                match.extraction_rule,
            ),
        )
        filtered: list[RuleMatch] = []
        for match in ordered:
            if self._should_skip_overlapping_match(match, filtered):
                continue
            filtered.append(match)
        return filtered

    def _should_skip_overlapping_match(self, candidate: RuleMatch, accepted: list[RuleMatch]) -> bool:
        generic_types = {ExtractedEntityType.NUMBER, ExtractedEntityType.RANGE}
        stronger_types = {
            ExtractedEntityType.TAG,
            ExtractedEntityType.IDENTIFIER,
            ExtractedEntityType.MODEL,
            ExtractedEntityType.DOCUMENT_REFERENCE,
        }
        for existing in accepted:
            overlaps = candidate.start_offset < existing.end_offset and candidate.end_offset > existing.start_offset
            contained = candidate.start_offset >= existing.start_offset and candidate.end_offset <= existing.end_offset
            if candidate.entity_type == ExtractedEntityType.NUMBER and contained and existing.entity_type != ExtractedEntityType.NUMBER:
                return True
            if candidate.entity_type == ExtractedEntityType.RANGE and overlaps and existing.entity_type in stronger_types:
                return True
            if candidate.entity_type == existing.entity_type and candidate.start_offset == existing.start_offset and candidate.end_offset == existing.end_offset:
                return True
            if candidate.entity_type in generic_types and contained and existing.entity_type in stronger_types:
                return True
        return False

    def _should_skip_overlapping_entity(self, candidate: ExtractedEntity, accepted: list[ExtractedEntity]) -> bool:
        candidate_start = candidate.source_trace.start_offset
        candidate_end = candidate.source_trace.end_offset
        if candidate_start is None or candidate_end is None:
            return False
        for existing in accepted:
            if existing.fragment_id != candidate.fragment_id:
                continue
            existing_start = existing.source_trace.start_offset
            existing_end = existing.source_trace.end_offset
            if existing_start is None or existing_end is None:
                continue
            contained = candidate_start >= existing_start and candidate_end <= existing_end
            if candidate.entity_type == ExtractedEntityType.NUMBER and contained and existing.entity_type != ExtractedEntityType.NUMBER:
                return True
        return False

    def _entity_sort_key(self, entity: ExtractedEntity) -> tuple[str, int, int, str, str]:
        start_offset = entity.source_trace.start_offset if entity.source_trace.start_offset is not None else -1
        end_offset = entity.source_trace.end_offset if entity.source_trace.end_offset is not None else -1
        return (
            str(entity.fragment_id),
            start_offset,
            end_offset,
            entity.entity_type.value,
            entity.extraction_rule,
        )

    def _observation_sort_key(self, observation: ExtractedObservation) -> tuple[str, int, int, str, str]:
        start_offset = observation.source_trace.start_offset if observation.source_trace.start_offset is not None else -1
        end_offset = observation.source_trace.end_offset if observation.source_trace.end_offset is not None else -1
        return (
            str(observation.fragment_id),
            start_offset,
            end_offset,
            observation.observation_type.value,
            observation.extraction_rule,
        )

    def _normalize_text(self, text: str) -> str:
        return " ".join(text.split()).strip().lower()