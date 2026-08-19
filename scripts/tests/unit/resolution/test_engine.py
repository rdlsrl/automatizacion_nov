from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.catalog.domain import (
    CatalogCode,
    CatalogScope,
    EngineeringUnit,
    LocalizedName,
    PhysicalQuantity,
    Variable,
    VariableAlias,
)
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractionRun, ExtractionSourceTrace
from drilling_knowledge.resolution import CandidateResolutionEngine, ResolutionEvidenceType, ResolutionRun, ResolutionStatus


class CandidateResolutionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CandidateResolutionEngine.create(self._catalog_repository())

    def test_resolves_exact_name_match(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        result = self.engine.resolve(self._extraction_run(mention))

        resolution = result.mention_resolutions[0]
        self.assertEqual(resolution.status, ResolutionStatus.RESOLVED_CANDIDATE)
        self.assertEqual(resolution.candidates[0].canonical_name, "Pressure")
        self.assertEqual(resolution.candidates[0].evidence.evidence_type, ResolutionEvidenceType.EXACT_NAME)

    def test_resolves_explicit_alias_match(self) -> None:
        mention = self._mention("Hookload", ExtractedEntityType.VARIABLE)
        result = self.engine.resolve(self._extraction_run(mention))

        resolution = result.mention_resolutions[0]
        self.assertEqual(resolution.status, ResolutionStatus.RESOLVED_CANDIDATE)
        self.assertEqual(resolution.candidates[0].canonical_name, "Hook Load")
        self.assertEqual(resolution.candidates[0].evidence.evidence_type, ResolutionEvidenceType.EXPLICIT_ALIAS)

    def test_marks_multiple_candidates_as_ambiguous(self) -> None:
        mention = self._mention("Mud Pump", ExtractedEntityType.EQUIPMENT)
        result = self.engine.resolve(self._extraction_run(mention))

        resolution = result.mention_resolutions[0]
        self.assertEqual(resolution.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual(len(resolution.candidates), 2)
        self.assertEqual([candidate.rank for candidate in resolution.candidates], [1, 2])

    def test_marks_missing_candidates_as_unresolved(self) -> None:
        mention = self._mention("Unknown Quantity", ExtractedEntityType.PHYSICAL_QUANTITY)
        result = self.engine.resolve(self._extraction_run(mention))

        resolution = result.mention_resolutions[0]
        self.assertEqual(resolution.status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(resolution.candidates, ())

    def test_candidate_order_is_stable(self) -> None:
        mention = self._mention("Mud Pump", ExtractedEntityType.EQUIPMENT)
        first = self.engine.resolve(self._extraction_run(mention))
        second = self.engine.resolve(self._extraction_run(mention))

        first_candidates = [(candidate.candidate_id, candidate.catalog_code, candidate.rank) for candidate in first.mention_resolutions[0].candidates]
        second_candidates = [(candidate.candidate_id, candidate.catalog_code, candidate.rank) for candidate in second.mention_resolutions[0].candidates]
        self.assertEqual(first_candidates, second_candidates)

    def test_resolution_is_idempotent_for_same_mentions(self) -> None:
        mentions = (
            self._mention("Hookload", ExtractedEntityType.VARIABLE, start_offset=0),
            self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=10),
        )
        first = self.engine.resolve(self._extraction_run(*mentions))
        second = self.engine.resolve(self._extraction_run(*mentions))

        first_resolutions = [
            (resolution.resolution_id, resolution.status, tuple(candidate.candidate_id for candidate in resolution.candidates))
            for resolution in first.mention_resolutions
        ]
        second_resolutions = [
            (resolution.resolution_id, resolution.status, tuple(candidate.candidate_id for candidate in resolution.candidates))
            for resolution in second.mention_resolutions
        ]
        self.assertEqual(first_resolutions, second_resolutions)

    def test_same_concept_found_by_multiple_rules_is_consolidated(self) -> None:
        mention = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT)
        result = self.engine.resolve(self._extraction_run(mention))

        resolution = result.mention_resolutions[0]
        self.assertEqual(resolution.status, ResolutionStatus.RESOLVED_CANDIDATE)
        self.assertEqual(len(resolution.candidates), 1)
        self.assertEqual(
            [evidence.evidence_type for evidence in resolution.candidates[0].supporting_evidences],
            [ResolutionEvidenceType.EXACT_NAME, ResolutionEvidenceType.EXACT_CODE, ResolutionEvidenceType.EXACT_SYMBOL],
        )

    def test_incompatible_concept_types_do_not_resolve(self) -> None:
        mention = self._mention("psi", ExtractedEntityType.VARIABLE)
        result = self.engine.resolve(self._extraction_run(mention))

        resolution = result.mention_resolutions[0]
        self.assertEqual(resolution.status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(resolution.candidates, ())

    def test_empty_catalog_returns_unresolved(self) -> None:
        engine = CandidateResolutionEngine.create(InMemoryCatalogRepository.empty())
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)

        result = engine.resolve(self._extraction_run(mention))
        self.assertEqual(result.mention_resolutions[0].status, ResolutionStatus.UNRESOLVED)

    def test_resolution_run_metadata_is_deterministic_for_same_input(self) -> None:
        mention = self._mention("Hookload", ExtractedEntityType.VARIABLE)
        extraction_run = self._extraction_run(mention)

        first = self.engine.resolve(extraction_run)
        second = self.engine.resolve(extraction_run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.started_at, second.started_at)
        self.assertEqual(first.finished_at, second.finished_at)

    def test_resolution_run_does_not_expose_nondeterministic_empty_factory(self) -> None:
        self.assertFalse(hasattr(ResolutionRun, "empty"))

    def test_candidate_ranking_is_independent_from_repository_iteration_order(self) -> None:
        mention = self._mention("Mud Pump", ExtractedEntityType.EQUIPMENT)
        forward = CandidateResolutionEngine.create(self._catalog_repository(reverse_equipment=False)).resolve(self._extraction_run(mention))
        reverse = CandidateResolutionEngine.create(self._catalog_repository(reverse_equipment=True)).resolve(self._extraction_run(mention))

        self.assertEqual(
            [(candidate.catalog_entity_id, candidate.rank) for candidate in forward.mention_resolutions[0].candidates],
            [(candidate.catalog_entity_id, candidate.rank) for candidate in reverse.mention_resolutions[0].candidates],
        )

    def test_duplicate_aliases_for_multiple_concepts_become_ambiguous(self) -> None:
        engine = CandidateResolutionEngine.create(self._catalog_repository(include_duplicate_alias=True))
        mention = self._mention("Hookload", ExtractedEntityType.VARIABLE)

        result = engine.resolve(self._extraction_run(mention))
        resolution = result.mention_resolutions[0]

        self.assertEqual(resolution.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual(len(resolution.candidates), 2)

    def _catalog_repository(
        self,
        *,
        reverse_equipment: bool = False,
        include_duplicate_alias: bool = False,
    ) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        quantities = InMemoryEntityRepository(
            (
                PhysicalQuantity(
                    entity_id=EntityId.from_seed("test.quantity", "pressure"),
                    code=CatalogCode("pressure"),
                    names=LocalizedName("Pressure"),
                    description="Pressure quantity.",
                    scope=scope,
                    quantity_family="hydraulic",
                    dimension_code="pressure",
                ),
            )
        )
        units = InMemoryEntityRepository(
            (
                EngineeringUnit(
                    entity_id=EntityId.from_seed("test.unit", "psi"),
                    code=CatalogCode("psi"),
                    names=LocalizedName("PSI"),
                    description="Pressure unit.",
                    scope=scope,
                    symbol="psi",
                    dimension_code="pressure",
                ),
            )
        )
        variables = InMemoryEntityRepository(
            (
                Variable(
                    entity_id=EntityId.from_seed("test.variable", "hook_load"),
                    code=CatalogCode("hook_load"),
                    names=LocalizedName("Hook Load"),
                    description="Hook load variable.",
                    scope=scope,
                    aliases=(VariableAlias("Hookload", alias_type="vendor_alias"),),
                ),
            )
        )
        if include_duplicate_alias:
            variables = variables.merge(
                (
                    Variable(
                        entity_id=EntityId.from_seed("test.variable", "hook_load_alt"),
                        code=CatalogCode("hook_load_alt"),
                        names=LocalizedName("Hook Load Alternate"),
                        description="Alternative hook load variable.",
                        scope=scope,
                        aliases=(VariableAlias("Hookload", alias_type="vendor_alias"),),
                    ),
                )
            )
        equipment_entities = [
            self._equipment("mud_pump_a", "Mud Pump"),
            self._equipment("mud_pump_b", "Mud Pump"),
        ]
        if reverse_equipment:
            equipment_entities = list(reversed(equipment_entities))
        equipment = InMemoryEntityRepository(tuple(equipment_entities))
        return InMemoryCatalogRepository(
            units=units,
            quantities=quantities,
            principles=InMemoryEntityRepository(()),
            quantity_unit_compatibilities=InMemoryEntityRepository(()),
            classifications=InMemoryEntityRepository(()),
            origins=InMemoryEntityRepository(()),
            publishers=InMemoryEntityRepository(()),
            systems=InMemoryEntityRepository(()),
            subsystems=InMemoryEntityRepository(()),
            processes=InMemoryEntityRepository(()),
            operational_contexts=InMemoryEntityRepository(()),
            locations=InMemoryEntityRepository(()),
            sensors=InMemoryEntityRepository(()),
            instruments=InMemoryEntityRepository(()),
            equipment=equipment,
            variables=variables,
        )

    def _equipment(self, code: str, canonical_name: str):
        from drilling_knowledge.catalog.domain import EquipmentClass

        return EquipmentClass(
            entity_id=EntityId.from_seed("test.equipment", code),
            code=CatalogCode(code),
            names=LocalizedName(canonical_name),
            description=f"{canonical_name} equipment.",
            scope=CatalogScope(),
        )

    def _mention(
        self,
        text: str,
        entity_type: ExtractedEntityType,
        *,
        start_offset: int = 0,
        fragment_suffix: str | None = None,
    ) -> ExtractedEntity:
        fragment_suffix = fragment_suffix or f"{entity_type.value}:{text}:{start_offset}"
        return ExtractedEntity(
            entity_id=EntityId.from_seed("test.mention", fragment_suffix),
            entity_type=entity_type,
            original_text=text,
            normalized_text=" ".join(text.split()).strip().lower(),
            document_position=f"fragment={fragment_suffix}|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("test.fragment", fragment_suffix),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="test.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _extraction_run(self, *mentions: ExtractedEntity) -> ExtractionRun:
        document_id = EntityId.from_seed("test.document", "doc-1")
        version_id = EntityId.from_seed("test.version", "ver-1")
        run_time = datetime(2026, 1, 1, 0, 0, 0)
        return ExtractionRun(
            run_id=EntityId.from_seed("test.run", "run-1"),
            document_id=document_id,
            version_id=version_id,
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRun.empty(document_id, version_id).status,
            entities=tuple(mentions),
            metrics=ExtractionRun.empty(document_id, version_id).metrics,
        )