from __future__ import annotations

from datetime import UTC, datetime
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, EquipmentClass, LocalizedName, OriginClass, PhysicalQuantity, PublisherClass, QuantityUnitCompatibility, SensorClass, Variable, VariableAlias
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import HypothesisSupportKind, InMemorySemanticResolutionRunRepository, SemanticHypothesisStatus, SemanticResolutionEngine


class SemanticResolutionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.engine = SemanticResolutionEngine.create(self.catalog)

    def test_generates_supported_entity_hypothesis_from_normalized_candidate(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))

        result = self.engine.resolve(normalization_run)

        hypothesis = result.hypotheses[0]
        self.assertEqual(hypothesis.status, SemanticHypothesisStatus.SUPPORTED)
        self.assertEqual(hypothesis.predicate_code, "denotes_catalog_entity")
        self.assertEqual(hypothesis.source_entity_candidate, normalization_run.entity_candidates[0])

    def test_proposed_entity_candidate_becomes_explicit_rejection(self) -> None:
        mention = self._mention("Unknown Tag", ExtractedEntityType.TAG)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))

        result = self.engine.resolve(normalization_run)

        hypothesis = result.hypotheses[0]
        self.assertEqual(hypothesis.status, SemanticHypothesisStatus.REJECTED)
        self.assertIn("no_catalog_anchor", hypothesis.reason_codes)

    def test_incompatible_quantity_unit_relation_is_rejected_with_reason_code(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=0)
        unit = self._mention("gpm", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._unit_association(variable, unit)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((variable, unit), (observation,)))

        result = self.engine.resolve(normalization_run)

        relation_hypothesis = next(h for h in result.hypotheses if h.predicate_code == "textual_unit_association")
        self.assertEqual(relation_hypothesis.status, SemanticHypothesisStatus.REJECTED)
        self.assertIn("quantity_unit_incompatible", relation_hypothesis.reason_codes)

    def test_rule_execution_logs_are_ordered_and_auditable(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=0)
        unit = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._unit_association(variable, unit)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((variable, unit), (observation,)))

        result = self.engine.resolve(normalization_run)

        self.assertTrue(result.execution_logs)
        self.assertEqual([log.priority for log in result.execution_logs], sorted(log.priority for log in result.execution_logs))
        self.assertTrue(all(log.rule_code for log in result.execution_logs))

    def test_supports_preserve_traceability_to_normalized_candidates(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))

        result = self.engine.resolve(normalization_run)

        candidate_support = next(s for s in result.supports if s.support_kind == HypothesisSupportKind.CANDIDATE)
        self.assertEqual(candidate_support.source_candidate_id, normalization_run.entity_candidates[0].candidate_id)

    def test_origin_publisher_filter_accepts_explicit_relation_from_extraction_through_normalization(self) -> None:
        origin = self._mention("Imported", ExtractedEntityType.ORIGIN, start_offset=0)
        publisher = self._mention("EDR Publisher", ExtractedEntityType.PUBLISHER, start_offset=20)
        observation = self._explicit_relation(origin, publisher, ExtractedObservationType.ORIGIN_PUBLISHER_ASSOCIATION)

        normalization_run = self.normalization_engine.normalize(self._extraction_run((origin, publisher), (observation,)))
        result = self.engine.resolve(normalization_run)

        hypothesis = next(h for h in result.hypotheses if h.predicate_code == "origin_publisher_association")
        self.assertEqual(hypothesis.status, SemanticHypothesisStatus.SUPPORTED)
        self.assertIn("origin_publisher_compatible", {support.reason_code for support in result.supports if support.hypothesis_id == hypothesis.hypothesis_id})

    def test_chain_filter_rejects_explicit_relation_from_extraction_through_normalization(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=0)
        unit = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._explicit_relation(variable, unit, ExtractedObservationType.MEASUREMENT_CHAIN_COMPATIBILITY)

        normalization_run = self.normalization_engine.normalize(self._extraction_run((variable, unit), (observation,)))
        result = self.engine.resolve(normalization_run)

        hypothesis = next(h for h in result.hypotheses if h.predicate_code == "measurement_chain_compatibility")
        self.assertEqual(hypothesis.status, SemanticHypothesisStatus.REJECTED)
        self.assertIn("chain_compatibility_rejected", hypothesis.reason_codes)

    def test_semantic_run_can_be_persisted_end_to_end(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))
        semantic_run = self.engine.resolve(normalization_run)
        repository = InMemorySemanticResolutionRunRepository().append_run(semantic_run)

        self.assertEqual(repository.get_run(semantic_run.run_id), semantic_run)
        self.assertEqual(repository.list_hypotheses(semantic_run.run_id), semantic_run.hypotheses)
        self.assertEqual(repository.list_supports(semantic_run.run_id), semantic_run.supports)
        self.assertEqual(repository.list_execution_logs(semantic_run.run_id), semantic_run.execution_logs)

    def test_exception_creates_fallback_rejection_instead_of_dropping_candidate(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))

        class FailingSemanticResolutionEngine(SemanticResolutionEngine):
            def _resolve_entity_candidate(self, candidate, created_at):  # type: ignore[override]
                raise RuntimeError("controlled failure")

        result = FailingSemanticResolutionEngine.create(self.catalog).resolve(normalization_run)

        self.assertEqual(len(result.hypotheses), 1)
        self.assertEqual(result.hypotheses[0].status, SemanticHypothesisStatus.REJECTED)
        self.assertIn("semantic_resolution_error", result.hypotheses[0].reason_codes)
        self.assertTrue(any(log.outcome == "error_rejected" for log in result.execution_logs))

    def _catalog_repository(self) -> InMemoryCatalogRepository:
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
                    canonical_unit_code=CatalogCode("psi"),
                ),
                PhysicalQuantity(
                    entity_id=EntityId.from_seed("test.quantity", "flow_rate"),
                    code=CatalogCode("flow_rate"),
                    names=LocalizedName("Flow Rate"),
                    description="Flow rate quantity.",
                    scope=scope,
                    quantity_family="hydraulic",
                    dimension_code="flow_rate",
                    canonical_unit_code=CatalogCode("gpm"),
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
                EngineeringUnit(
                    entity_id=EntityId.from_seed("test.unit", "gpm"),
                    code=CatalogCode("gpm"),
                    names=LocalizedName("GPM"),
                    description="Flow rate unit.",
                    scope=scope,
                    symbol="gpm",
                    dimension_code="flow_rate",
                ),
            )
        )
        compatibilities = InMemoryEntityRepository(
            (
                QuantityUnitCompatibility(
                    entity_id=EntityId.from_seed("test.compatibility", "pressure.psi"),
                    code=CatalogCode("pressure.psi"),
                    names=LocalizedName("pressure to psi"),
                    description="Allowed pressure to psi.",
                    scope=scope,
                    quantity_code=CatalogCode("pressure"),
                    unit_code=CatalogCode("psi"),
                ),
            )
        )
        variables = InMemoryEntityRepository(
            (
                Variable(
                    entity_id=EntityId.from_seed("test.variable", "standpipe_pressure"),
                    code=CatalogCode("standpipe_pressure"),
                    names=LocalizedName("Standpipe Pressure"),
                    description="Standpipe pressure variable.",
                    scope=scope,
                    physical_quantity_code=CatalogCode("pressure"),
                    canonical_unit_code=CatalogCode("psi"),
                    aliases=(VariableAlias("SPP", alias_type="mnemonic"),),
                ),
            )
        )
        equipment = InMemoryEntityRepository(
            (
                EquipmentClass(
                    entity_id=EntityId.from_seed("test.equipment", "mud_pump"),
                    code=CatalogCode("mud_pump"),
                    names=LocalizedName("Mud Pump"),
                    description="Mud pump.",
                    scope=scope,
                ),
                EquipmentClass(
                    entity_id=EntityId.from_seed("test.equipment", "edr_publisher_proxy"),
                    code=CatalogCode("edr_publisher_proxy"),
                    names=LocalizedName("EDR Publisher"),
                    description="Publisher proxy equipment.",
                    scope=scope,
                ),
            )
        )
        sensors = InMemoryEntityRepository(
            (
                SensorClass(
                    entity_id=EntityId.from_seed("test.sensor", "pressure_sensor"),
                    code=CatalogCode("pressure_sensor"),
                    names=LocalizedName("Pressure Sensor"),
                    description="Pressure sensor.",
                    scope=scope,
                ),
            )
        )
        origins = InMemoryEntityRepository(
            (
                OriginClass(
                    entity_id=EntityId.from_seed("test.origin", "imported"),
                    code=CatalogCode("imported"),
                    names=LocalizedName("Imported"),
                    description="Imported source.",
                    scope=scope,
                    axis="source_kind",
                ),
            )
        )
        publishers = InMemoryEntityRepository(
            (
                PublisherClass(
                    entity_id=EntityId.from_seed("test.publisher", "edr_publisher"),
                    code=CatalogCode("edr_publisher"),
                    names=LocalizedName("EDR Publisher"),
                    description="EDR publisher class.",
                    scope=scope,
                ),
            )
        )
        empty = InMemoryEntityRepository(())
        return InMemoryCatalogRepository(
            units=units,
            quantities=quantities,
            principles=empty,
            quantity_unit_compatibilities=compatibilities,
            classifications=empty,
            origins=origins,
            publishers=publishers,
            systems=empty,
            subsystems=empty,
            processes=empty,
            operational_contexts=empty,
            locations=empty,
            sensors=sensors,
            instruments=empty,
            equipment=equipment,
            variables=variables,
        )

    def _mention(self, text: str, entity_type: ExtractedEntityType, *, start_offset: int = 0) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("test.mention", f"{entity_type.value}:{text}:{start_offset}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=" ".join(text.split()).strip().lower(),
            document_position=f"fragment=fragment-1|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("test.fragment", "fragment-1"),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="test.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _unit_association(self, subject: ExtractedEntity, unit: ExtractedEntity) -> ExtractedObservation:
        return ExtractedObservation(
            observation_id=EntityId.from_seed("test.observation", f"unit-association:{subject.entity_id}:{unit.entity_id}"),
            observation_type=ExtractedObservationType.TEXTUAL_UNIT_ASSOCIATION,
            original_text=f"{subject.original_text} ({unit.original_text})",
            normalized_text=f"{subject.normalized_text} ({unit.normalized_text})",
            document_position="fragment=fragment-1|page=1|section=section-1|paragraph=1|span=0:30",
            fragment_id=subject.fragment_id,
            document_id=subject.document_id,
            version_id=subject.version_id,
            extraction_confidence=1.0,
            extraction_rule="test.unit_association",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=30),
            context_window=ContextWindow(match_text=f"{subject.original_text} ({unit.original_text})"),
            source_entity_id=subject.entity_id,
            target_entity_id=unit.entity_id,
            attributes=(("subject_entity_id", str(subject.entity_id)), ("unit_entity_id", str(unit.entity_id))),
        )

    def _explicit_relation(self, subject: ExtractedEntity, obj: ExtractedEntity, observation_type: ExtractedObservationType) -> ExtractedObservation:
        return ExtractedObservation(
            observation_id=EntityId.from_seed("test.observation", f"{observation_type.value}:{subject.entity_id}:{obj.entity_id}"),
            observation_type=observation_type,
            original_text=f"{subject.original_text} -> {obj.original_text}",
            normalized_text=f"{subject.normalized_text} -> {obj.normalized_text}",
            document_position="fragment=fragment-1|page=1|section=section-1|paragraph=1|span=0:30",
            fragment_id=subject.fragment_id,
            document_id=subject.document_id,
            version_id=subject.version_id,
            extraction_confidence=1.0,
            extraction_rule="test.explicit_relation",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=30),
            context_window=ContextWindow(match_text=f"{subject.original_text} -> {obj.original_text}"),
            source_entity_id=subject.entity_id,
            target_entity_id=obj.entity_id,
            attributes=(("subject_entity_id", str(subject.entity_id)), ("object_entity_id", str(obj.entity_id))),
        )

    def _extraction_run(self, entities: tuple[ExtractedEntity, ...], observations: tuple[ExtractedObservation, ...]) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("test.extraction", "run-1"),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=entities,
            observations=observations,
            metrics=ExtractionMetrics(total_entities=len(entities), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )