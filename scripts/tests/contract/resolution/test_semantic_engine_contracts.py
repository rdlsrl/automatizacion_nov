from __future__ import annotations

from datetime import UTC, datetime
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, EquipmentClass, LocalizedName, OriginClass, PhysicalQuantity, PublisherClass, QuantityUnitCompatibility, SensorClass, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import InMemorySemanticResolutionRunRepository, SemanticHypothesisStatus, SemanticResolutionEngine


class SemanticResolutionEngineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.engine = SemanticResolutionEngine.create(self.catalog)

    def test_semantic_resolution_is_idempotent_for_same_normalization_run(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))

        first = self.engine.resolve(normalization_run)
        second = self.engine.resolve(normalization_run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(
            [(hypothesis.hypothesis_id, hypothesis.status, hypothesis.score) for hypothesis in first.hypotheses],
            [(hypothesis.hypothesis_id, hypothesis.status, hypothesis.score) for hypothesis in second.hypotheses],
        )

    def test_each_claimable_candidate_has_hypothesis_or_explicit_rejection(self) -> None:
        mention = self._mention("Unknown Tag", ExtractedEntityType.TAG)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((mention,), ()))

        result = self.engine.resolve(normalization_run)

        self.assertEqual(len(result.hypotheses), len(normalization_run.entity_candidates) + len(normalization_run.relation_candidates))
        self.assertEqual(result.hypotheses[0].status, SemanticHypothesisStatus.REJECTED)

    def test_impossible_hypotheses_keep_reason_codes(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE)
        unit = self._mention("gpm", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._unit_association(variable, unit)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((variable, unit), (observation,)))

        result = self.engine.resolve(normalization_run)

        rejected = next(hypothesis for hypothesis in result.hypotheses if hypothesis.status == SemanticHypothesisStatus.REJECTED and hypothesis.predicate_code == "textual_unit_association")
        self.assertIn("quantity_unit_incompatible", rejected.reason_codes)

    def test_semantic_repository_round_trips_runs_and_associated_records(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self.engine.resolve(self.normalization_engine.normalize(self._extraction_run((mention,), ())))
        repository = InMemorySemanticResolutionRunRepository().append_run(semantic_run)

        self.assertEqual(repository.get_run(semantic_run.run_id), semantic_run)
        self.assertEqual(repository.list_hypotheses(semantic_run.run_id), semantic_run.hypotheses)
        self.assertEqual(repository.list_supports(semantic_run.run_id), semantic_run.supports)
        self.assertEqual(repository.list_execution_logs(semantic_run.run_id), semantic_run.execution_logs)

    def test_semantic_repository_is_idempotent_for_same_run(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self.engine.resolve(self.normalization_engine.normalize(self._extraction_run((mention,), ())))
        repository = InMemorySemanticResolutionRunRepository().append_run(semantic_run)

        self.assertIs(repository.append_run(semantic_run), repository)

    def test_semantic_repository_rejects_invalid_collisions(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self.engine.resolve(self.normalization_engine.normalize(self._extraction_run((mention,), ())))
        conflicting_run = SemanticResolutionEngine.create(self.catalog, rule_pack_version="semantic.rules.v2").resolve(
            self.normalization_engine.normalize(self._extraction_run((mention,), ()))
        )
        conflicting_run = type(conflicting_run)(
            run_id=semantic_run.run_id,
            normalization_run_id=conflicting_run.normalization_run_id,
            rule_pack_version=conflicting_run.rule_pack_version,
            started_at=conflicting_run.started_at,
            finished_at=conflicting_run.finished_at,
            hypotheses=conflicting_run.hypotheses,
            supports=conflicting_run.supports,
            execution_logs=conflicting_run.execution_logs,
            errors=conflicting_run.errors,
        )

        with self.assertRaises(Exception):
            InMemorySemanticResolutionRunRepository((semantic_run, conflicting_run))

    def test_semantic_repository_enforces_referential_integrity(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self.engine.resolve(self.normalization_engine.normalize(self._extraction_run((mention,), ())))
        bad_support = type(semantic_run.supports[0])(
            support_id=semantic_run.supports[0].support_id,
            hypothesis_id=EntityId.from_seed("bad.hypothesis", "missing"),
            support_kind=semantic_run.supports[0].support_kind,
            source_candidate_id=semantic_run.supports[0].source_candidate_id,
            rule_code=semantic_run.supports[0].rule_code,
            reason_code=semantic_run.supports[0].reason_code,
            detail=semantic_run.supports[0].detail,
        )
        bad_run = type(semantic_run)(
            run_id=semantic_run.run_id,
            normalization_run_id=semantic_run.normalization_run_id,
            rule_pack_version=semantic_run.rule_pack_version,
            started_at=semantic_run.started_at,
            finished_at=semantic_run.finished_at,
            hypotheses=semantic_run.hypotheses,
            supports=(bad_support,),
            execution_logs=semantic_run.execution_logs,
            errors=semantic_run.errors,
        )

        with self.assertRaises(Exception):
            InMemorySemanticResolutionRunRepository((bad_run,))

    def test_origin_publisher_hard_filter_runs_end_to_end(self) -> None:
        origin = self._mention("Imported", ExtractedEntityType.ORIGIN)
        publisher = self._mention("EDR Publisher", ExtractedEntityType.PUBLISHER, start_offset=20)
        observation = self._explicit_relation(origin, publisher, ExtractedObservationType.ORIGIN_PUBLISHER_ASSOCIATION)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((origin, publisher), (observation,)))

        result = self.engine.resolve(normalization_run)

        hypothesis = next(h for h in result.hypotheses if h.predicate_code == "origin_publisher_association")
        self.assertEqual(hypothesis.status, SemanticHypothesisStatus.SUPPORTED)

    def test_chain_hard_filter_runs_end_to_end(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE)
        unit = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._explicit_relation(variable, unit, ExtractedObservationType.MEASUREMENT_CHAIN_COMPATIBILITY)
        normalization_run = self.normalization_engine.normalize(self._extraction_run((variable, unit), (observation,)))

        result = self.engine.resolve(normalization_run)

        hypothesis = next(h for h in result.hypotheses if h.predicate_code == "measurement_chain_compatibility")
        self.assertEqual(hypothesis.status, SemanticHypothesisStatus.REJECTED)
        self.assertIn("chain_compatibility_rejected", hypothesis.reason_codes)

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
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
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("contract.unit", "gpm"),
                        code=CatalogCode("gpm"),
                        names=LocalizedName("GPM"),
                        description="Flow unit.",
                        scope=scope,
                        symbol="gpm",
                        dimension_code="flow_rate",
                    ),
                )
            ),
            quantities=InMemoryEntityRepository(
                (
                    PhysicalQuantity(
                        entity_id=EntityId.from_seed("contract.quantity", "pressure"),
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
                        entity_id=EntityId.from_seed("contract.compatibility", "pressure.psi"),
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
            origins=InMemoryEntityRepository(
                (
                    OriginClass(
                        entity_id=EntityId.from_seed("contract.origin", "imported"),
                        code=CatalogCode("imported"),
                        names=LocalizedName("Imported"),
                        description="Imported source.",
                        scope=scope,
                        axis="source_kind",
                    ),
                )
            ),
            publishers=InMemoryEntityRepository(
                (
                    PublisherClass(
                        entity_id=EntityId.from_seed("contract.publisher", "edr_publisher"),
                        code=CatalogCode("edr_publisher"),
                        names=LocalizedName("EDR Publisher"),
                        description="EDR publisher class.",
                        scope=scope,
                    ),
                )
            ),
            systems=InMemoryEntityRepository(()),
            subsystems=InMemoryEntityRepository(()),
            processes=InMemoryEntityRepository(()),
            operational_contexts=InMemoryEntityRepository(()),
            locations=InMemoryEntityRepository(()),
            sensors=InMemoryEntityRepository(
                (
                    SensorClass(
                        entity_id=EntityId.from_seed("contract.sensor", "pressure_sensor"),
                        code=CatalogCode("pressure_sensor"),
                        names=LocalizedName("Pressure Sensor"),
                        description="Pressure sensor.",
                        scope=scope,
                    ),
                )
            ),
            instruments=InMemoryEntityRepository(()),
            equipment=InMemoryEntityRepository(
                (
                    EquipmentClass(
                        entity_id=EntityId.from_seed("contract.equipment", "edr_publisher_proxy"),
                        code=CatalogCode("edr_publisher_proxy"),
                        names=LocalizedName("EDR Publisher"),
                        description="Publisher proxy equipment.",
                        scope=scope,
                    ),
                )
            ),
            variables=InMemoryEntityRepository(
                (
                    Variable(
                        entity_id=EntityId.from_seed("contract.variable", "standpipe_pressure"),
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

    def _mention(self, text: str, entity_type: ExtractedEntityType, *, start_offset: int = 0) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("contract.mention", f"{entity_type.value}:{text}:{start_offset}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=" ".join(text.split()).strip().lower(),
            document_position=f"fragment=fragment-1|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("contract.fragment", "fragment-1"),
            document_id=EntityId.from_seed("contract.document", "doc-1"),
            version_id=EntityId.from_seed("contract.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="contract.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _unit_association(self, subject: ExtractedEntity, unit: ExtractedEntity) -> ExtractedObservation:
        return ExtractedObservation(
            observation_id=EntityId.from_seed("contract.observation", f"unit-association:{subject.entity_id}:{unit.entity_id}"),
            observation_type=ExtractedObservationType.TEXTUAL_UNIT_ASSOCIATION,
            original_text=f"{subject.original_text} ({unit.original_text})",
            normalized_text=f"{subject.normalized_text} ({unit.normalized_text})",
            document_position="fragment=fragment-1|page=1|section=section-1|paragraph=1|span=0:30",
            fragment_id=subject.fragment_id,
            document_id=subject.document_id,
            version_id=subject.version_id,
            extraction_confidence=1.0,
            extraction_rule="contract.unit_association",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=30),
            context_window=ContextWindow(match_text=f"{subject.original_text} ({unit.original_text})"),
            source_entity_id=subject.entity_id,
            target_entity_id=unit.entity_id,
            attributes=(("subject_entity_id", str(subject.entity_id)), ("unit_entity_id", str(unit.entity_id))),
        )

    def _explicit_relation(self, subject: ExtractedEntity, obj: ExtractedEntity, observation_type: ExtractedObservationType) -> ExtractedObservation:
        return ExtractedObservation(
            observation_id=EntityId.from_seed("contract.observation", f"{observation_type.value}:{subject.entity_id}:{obj.entity_id}"),
            observation_type=observation_type,
            original_text=f"{subject.original_text} -> {obj.original_text}",
            normalized_text=f"{subject.normalized_text} -> {obj.normalized_text}",
            document_position="fragment=fragment-1|page=1|section=section-1|paragraph=1|span=0:30",
            fragment_id=subject.fragment_id,
            document_id=subject.document_id,
            version_id=subject.version_id,
            extraction_confidence=1.0,
            extraction_rule="contract.explicit_relation",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=30),
            context_window=ContextWindow(match_text=f"{subject.original_text} -> {obj.original_text}"),
            source_entity_id=subject.entity_id,
            target_entity_id=obj.entity_id,
            attributes=(("subject_entity_id", str(subject.entity_id)), ("object_entity_id", str(obj.entity_id))),
        )

    def _extraction_run(self, entities: tuple[ExtractedEntity, ...], observations: tuple[ExtractedObservation, ...]) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("contract.extraction", "run-1"),
            document_id=EntityId.from_seed("contract.document", "doc-1"),
            version_id=EntityId.from_seed("contract.version", "ver-1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=entities,
            observations=observations,
            metrics=ExtractionMetrics(total_entities=len(entities), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )