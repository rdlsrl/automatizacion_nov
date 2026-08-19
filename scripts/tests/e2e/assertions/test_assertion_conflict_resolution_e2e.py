from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions import AssertionConflictResolver, AssertionGenerationRun, AssertionReviewState, AssertionStatus, EvidenceAssertionEngine, InMemoryConflictResolutionRunRepository
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import SemanticResolutionEngine


class AssertionConflictResolutionEndToEndTests(unittest.TestCase):
    def test_valid_assertions_flow_through_conflict_detection_persistence_and_recovery(self) -> None:
        catalog = self._catalog_repository()
        normalization_engine = NormalizationEngine.create(catalog)
        semantic_engine = SemanticResolutionEngine.create(catalog)
        assertion_engine = EvidenceAssertionEngine.create()
        resolver = AssertionConflictResolver.create()

        first = self._supported_assertion(assertion_engine, semantic_engine, normalization_engine, "4 mA = 0 psi", "v1")
        second = self._supported_assertion(assertion_engine, semantic_engine, normalization_engine, "4 mA = 10 psi", "v2")
        assertion_run = AssertionGenerationRun(
            run_id=RunId.from_seed("assertions.e2e.run", "split"),
            semantic_run_id=RunId.from_seed("assertions.e2e.semantic", "split"),
            rule_pack_version="assertion.rules.v1",
            threshold=0.5,
            started_at=first.created_at,
            finished_at=first.created_at,
            assertions=(first, second),
            evidence_links=(),
            validation_logs=(),
            errors=(),
        )

        conflict_run, repository = resolver.resolve_and_persist(assertion_run, InMemoryConflictResolutionRunRepository())

        recovered = repository.get_run(conflict_run.run_id)
        self.assertEqual(recovered, conflict_run)
        self.assertEqual(len(repository.list_conflict_sets(conflict_run.run_id)), 1)
        self.assertEqual(len(repository.list_contexts(conflict_run.run_id)), 2)
        self.assertEqual(repository.list_review_queue_items(conflict_run.run_id), ())
        self.assertTrue(repository.list_evidence_links(conflict_run.run_id))

    def _supported_assertion(self, assertion_engine, semantic_engine, normalization_engine, text: str, version_seed: str):
        extraction_run = self._extraction_run(text, version_seed)
        normalization_run = normalization_engine.normalize(extraction_run)
        semantic_run = semantic_engine.resolve(normalization_run)
        built = next(item for item in assertion_engine.build(semantic_run).assertions if item.predicate_code == "explicit_scaling")
        return replace(built, status=AssertionStatus.SUPPORTED, review_state=AssertionReviewState.AUTO)

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.e2e.unit", "psi"),
                        code=CatalogCode("psi"),
                        names=LocalizedName("PSI"),
                        description="Pressure unit.",
                        scope=scope,
                        symbol="psi",
                        dimension_code="pressure",
                    ),
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.e2e.unit", "ma"),
                        code=CatalogCode("ma"),
                        names=LocalizedName("mA"),
                        description="Current unit.",
                        scope=scope,
                        symbol="mA",
                        dimension_code="current",
                    ),
                )
            ),
            quantities=InMemoryEntityRepository(
                (
                    PhysicalQuantity(
                        entity_id=EntityId.from_seed("assertions.e2e.quantity", "pressure"),
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
            quantity_unit_compatibilities=InMemoryEntityRepository(
                (
                    QuantityUnitCompatibility(
                        entity_id=EntityId.from_seed("assertions.e2e.compatibility", "pressure.psi"),
                        code=CatalogCode("pressure.psi"),
                        names=LocalizedName("pressure to psi"),
                        description="Allowed pressure to psi.",
                        scope=scope,
                        quantity_code=CatalogCode("pressure"),
                        unit_code=CatalogCode("psi"),
                    ),
                )
            ),
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
                        entity_id=EntityId.from_seed("assertions.e2e.variable", "standpipe_pressure"),
                        code=CatalogCode("standpipe_pressure"),
                        names=LocalizedName("Standpipe Pressure"),
                        description="Standpipe pressure variable.",
                        scope=scope,
                        physical_quantity_code=CatalogCode("pressure"),
                        canonical_unit_code=CatalogCode("psi"),
                    ),
                )
            ),
        )

    def _extraction_run(self, text: str, version_seed: str) -> ExtractionRun:
        left, right = [part.strip() for part in text.split("=")]
        raw_value, raw_unit = left.split()
        engineering_value, engineering_unit = right.split()
        observation = ExtractedObservation(
            observation_id=EntityId.from_seed("assertions.e2e.observation", f"{text}:{version_seed}"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text=text,
            normalized_text=text.lower(),
            document_position="fragment=e2e|page=1|section=section-1|paragraph=1|span=0:12",
            fragment_id=EntityId.from_seed("assertions.e2e.fragment", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("assertions.e2e.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.e2e.version", version_seed),
            extraction_confidence=1.0,
            extraction_rule="assertions.e2e.scaling",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=len(text)),
            context_window=ContextWindow(match_text=text),
            attributes=(("raw_value", raw_value), ("raw_unit", raw_unit), ("engineering_value", engineering_value), ("engineering_unit", engineering_unit)),
        )
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("assertions.e2e.extraction", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("assertions.e2e.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.e2e.version", version_seed),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=(),
            observations=(observation,),
            metrics=ExtractionMetrics(total_entities=0, entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )