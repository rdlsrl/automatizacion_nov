from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, Variable, VariableAlias
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.resolution import CandidateResolutionEngine, ResolutionStatus


class CandidateResolutionEngineContractTests(unittest.TestCase):
    def test_resolution_output_order_is_stable(self) -> None:
        engine = CandidateResolutionEngine.create(self._catalog_repository())
        run = self._extraction_run(
            self._mention("Hookload", start_offset=12),
            self._mention("Hookload", start_offset=30, suffix="second"),
        )

        first = engine.resolve(run)
        second = engine.resolve(run)

        self.assertEqual(
            [(resolution.resolution_id, resolution.mention.source_trace.start_offset, resolution.status) for resolution in first.mention_resolutions],
            [(resolution.resolution_id, resolution.mention.source_trace.start_offset, resolution.status) for resolution in second.mention_resolutions],
        )

    def test_resolution_is_idempotent_for_same_extraction_run(self) -> None:
        engine = CandidateResolutionEngine.create(self._catalog_repository())
        run = self._extraction_run(self._mention("Hookload", start_offset=12))

        first = engine.resolve(run)
        second = engine.resolve(run)

        self.assertEqual(
            [(resolution.resolution_id, tuple(candidate.candidate_id for candidate in resolution.candidates)) for resolution in first.mention_resolutions],
            [(resolution.resolution_id, tuple(candidate.candidate_id for candidate in resolution.candidates)) for resolution in second.mention_resolutions],
        )
        self.assertEqual(first.errors, ())
        self.assertEqual(second.errors, ())

    def test_same_catalog_entity_collects_multiple_evidences(self) -> None:
        engine = CandidateResolutionEngine.create(self._catalog_repository())
        run = self._extraction_run(self._mention("psi", start_offset=12, entity_type=ExtractedEntityType.ENGINEERING_UNIT))

        result = engine.resolve(run)
        candidate = result.mention_resolutions[0].candidates[0]

        self.assertEqual(candidate.catalog_code, "psi")
        self.assertEqual(len(candidate.supporting_evidences), 3)

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        units = InMemoryEntityRepository(
            (
                EngineeringUnit(
                    entity_id=EntityId.from_seed("contract.unit", "psi"),
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
                    entity_id=EntityId.from_seed("contract.variable", "hook_load"),
                    code=CatalogCode("hook_load"),
                    names=LocalizedName("Hook Load"),
                    description="Hook load variable.",
                    scope=scope,
                    aliases=(VariableAlias("Hookload", alias_type="vendor_alias"),),
                ),
            )
        )
        return InMemoryCatalogRepository(
            units=units,
            quantities=InMemoryEntityRepository(()),
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
            equipment=InMemoryEntityRepository(()),
            variables=variables,
        )

    def _mention(
        self,
        text: str,
        *,
        start_offset: int,
        suffix: str = "first",
        entity_type: ExtractedEntityType = ExtractedEntityType.VARIABLE,
    ) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("contract.mention", f"{suffix}:{start_offset}:{text}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=text.lower(),
            document_position=f"fragment=fragment-{suffix}|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("contract.fragment", f"fragment:{suffix}"),
            document_id=EntityId.from_seed("contract.document", "doc-1"),
            version_id=EntityId.from_seed("contract.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="contract.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _extraction_run(self, *mentions: ExtractedEntity) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, 0, 0, 0)
        return ExtractionRun(
            run_id=EntityId.from_seed("contract.run", "run-1"),
            document_id=EntityId.from_seed("contract.document", "doc-1"),
            version_id=EntityId.from_seed("contract.version", "ver-1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=tuple(mentions),
            metrics=ExtractionMetrics(total_entities=len(mentions), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0),
        )