from __future__ import annotations

from datetime import UTC, datetime
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, Variable, VariableAlias
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationCandidateStatus, NormalizationEngine


class NormalizationEngineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        scope = CatalogScope()
        self.engine = NormalizationEngine.create(
            InMemoryCatalogRepository(
                units=InMemoryEntityRepository(
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
                ),
                quantities=InMemoryEntityRepository(
                    (
                        PhysicalQuantity(
                            entity_id=EntityId.from_seed("test.quantity", "pressure"),
                            code=CatalogCode("pressure"),
                            names=LocalizedName("Pressure"),
                            description="Pressure quantity.",
                            scope=scope,
                            quantity_family="hydraulic",
                            dimension_code="pressure",
                            canonical_unit_code=CatalogCode("psi"),
                        ),
                    )
                ),
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
                variables=InMemoryEntityRepository(
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
                ),
            )
        )

    def test_normalization_outputs_only_terminal_candidate_statuses(self) -> None:
        extraction_run = self._extraction_run(
            self._mention("Hookload", ExtractedEntityType.VARIABLE),
            self._mention("Unknown Tag", ExtractedEntityType.TAG, start_offset=10),
        )

        result = self.engine.normalize(extraction_run)

        self.assertTrue(result.entity_candidates)
        self.assertEqual(
            {candidate.status for candidate in result.entity_candidates},
            {NormalizationCandidateStatus.RESOLVED, NormalizationCandidateStatus.PROPOSED},
        )

    def test_normalization_is_idempotent_for_same_extraction_run(self) -> None:
        extraction_run = self._extraction_run(self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY))

        first = self.engine.normalize(extraction_run)
        second = self.engine.normalize(extraction_run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(
            tuple(candidate.candidate_id for candidate in first.entity_candidates),
            tuple(candidate.candidate_id for candidate in second.entity_candidates),
        )

    def test_normalization_output_order_is_stable(self) -> None:
        extraction_run = self._extraction_run(
            self._mention("Hookload", ExtractedEntityType.VARIABLE, start_offset=20),
            self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY, start_offset=0),
        )

        result = self.engine.normalize(extraction_run)

        self.assertEqual(
            [candidate.mention_text for candidate in result.entity_candidates],
            ["Pressure", "Hookload"],
        )

    def _mention(self, text: str, entity_type: ExtractedEntityType, *, start_offset: int = 0) -> ExtractedEntity:
        suffix = f"{entity_type.value}:{text}:{start_offset}"
        return ExtractedEntity(
            entity_id=EntityId.from_seed("test.mention", suffix),
            entity_type=entity_type,
            original_text=text,
            normalized_text=" ".join(text.split()).strip().lower(),
            document_position=f"fragment={suffix}|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("test.fragment", suffix),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="test.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _extraction_run(self, *mentions: ExtractedEntity) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("test.extraction_run", "contract-run"),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=tuple(mentions),
            observations=(),
            metrics=ExtractionMetrics(
                total_entities=len(mentions),
                entity_counts_by_type={},
                entity_counts_by_rule={},
                document_counts={},
                records=(),
                duration_ms=0.0,
                errors=(),
            ),
        )
