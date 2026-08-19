from __future__ import annotations

from datetime import UTC, datetime
import unittest

from drilling_knowledge.catalog.domain import (
    CatalogCode,
    CatalogScope,
    EngineeringUnit,
    EquipmentClass,
    LocalizedName,
    PhysicalQuantity,
    QuantityUnitCompatibility,
    Variable,
    VariableAlias,
)
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import (
    ContextWindow,
    ExtractedEntity,
    ExtractedEntityType,
    ExtractedObservation,
    ExtractedObservationType,
    ExtractionMetrics,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionSourceTrace,
)
from drilling_knowledge.normalization import NormalizationCandidateStatus, NormalizationEngine, NormalizationMatchMethod
from drilling_knowledge.normalization.repositories import InMemoryNormalizationRunRepository


class NormalizationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = NormalizationEngine.create(self._catalog_repository())

    def test_resolves_exact_quantity_and_unit_mentions(self) -> None:
        mentions = (
            self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY, start_offset=0),
            self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=10),
        )

        run = self.engine.normalize(self._extraction_run(mentions, ()))

        by_mention = {candidate.candidate_mention_id: candidate for candidate in run.entity_candidates}
        self.assertEqual(by_mention[mentions[0].entity_id].status, NormalizationCandidateStatus.RESOLVED)
        self.assertEqual(by_mention[mentions[0].entity_id].canonical_text, "Pressure")
        self.assertEqual(by_mention[mentions[1].entity_id].status, NormalizationCandidateStatus.RESOLVED)
        self.assertEqual(by_mention[mentions[1].entity_id].match_method, NormalizationMatchMethod.EXACT_NAME)

    def test_ambiguous_equipment_matches_become_alternatives(self) -> None:
        mention = self._mention("Mud Pump", ExtractedEntityType.EQUIPMENT)

        run = self.engine.normalize(self._extraction_run((mention,), ()))

        candidates = [candidate for candidate in run.entity_candidates if candidate.candidate_mention_id == mention.entity_id]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.status == NormalizationCandidateStatus.ALTERNATIVE for candidate in candidates))

    def test_unmatched_tag_remains_proposed(self) -> None:
        mention = self._mention("Pileta_Gas_Oil_Q1", ExtractedEntityType.TAG)

        run = self.engine.normalize(self._extraction_run((mention,), ()))

        candidate = run.entity_candidates[0]
        self.assertEqual(candidate.status, NormalizationCandidateStatus.PROPOSED)
        self.assertTrue(candidate.is_new_concept_proposal)
        self.assertEqual(candidate.canonical_text, "Pileta_Gas_Oil_Q1")

    def test_mnemonic_matcher_generates_only_candidates(self) -> None:
        mention = self._mention("SPP", ExtractedEntityType.MNEMONIC)

        run = self.engine.normalize(self._extraction_run((mention,), ()))

        candidate = run.entity_candidates[0]
        self.assertEqual(candidate.match_method, NormalizationMatchMethod.MNEMONIC_ALIAS)
        self.assertEqual(candidate.status, NormalizationCandidateStatus.RESOLVED)
        self.assertEqual(candidate.source_mention, mention)

    def test_tag_pattern_matcher_generates_only_candidates(self) -> None:
        mention = self._mention("standpipe-pressure", ExtractedEntityType.TAG)

        run = self.engine.normalize(self._extraction_run((mention,), ()))

        candidate = run.entity_candidates[0]
        self.assertEqual(candidate.match_method, NormalizationMatchMethod.TAG_PATTERN)
        self.assertEqual(candidate.matched_table, "catalog.variable")
        self.assertEqual(candidate.status, NormalizationCandidateStatus.RESOLVED)

    def test_model_matcher_generates_only_candidates(self) -> None:
        mention = self._mention("Nova 8000", ExtractedEntityType.MODEL)

        run = self.engine.normalize(self._extraction_run((mention,), ()))

        candidate = run.entity_candidates[0]
        self.assertEqual(candidate.match_method, NormalizationMatchMethod.MODEL_SCOPE)
        self.assertEqual(candidate.matched_table, "catalog.equipment_class")
        self.assertEqual(candidate.status, NormalizationCandidateStatus.RESOLVED)

    def test_vendor_matcher_generates_only_candidates(self) -> None:
        mention = self._mention("Acme", ExtractedEntityType.MANUFACTURER)

        run = self.engine.normalize(self._extraction_run((mention,), ()))

        candidate = run.entity_candidates[0]
        self.assertEqual(candidate.match_method, NormalizationMatchMethod.VENDOR_SCOPE)
        self.assertEqual(candidate.matched_table, "catalog.equipment_class")
        self.assertEqual(candidate.status, NormalizationCandidateStatus.RESOLVED)

    def test_textual_unit_association_is_resolved_when_unit_is_compatible(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=0)
        unit = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._unit_association(variable, unit)

        run = self.engine.normalize(self._extraction_run((variable, unit), (observation,)))

        relation = run.relation_candidates[0]
        self.assertEqual(relation.status, NormalizationCandidateStatus.RESOLVED)
        self.assertEqual(relation.predicate_code, "textual_unit_association")
        self.assertEqual(relation.issues, ())

    def test_incompatible_unit_quantity_association_is_flagged(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=0)
        unit = self._mention("gpm", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._unit_association(variable, unit)

        run = self.engine.normalize(self._extraction_run((variable, unit), (observation,)))

        relation = run.relation_candidates[0]
        self.assertEqual(relation.status, NormalizationCandidateStatus.ALTERNATIVE)
        self.assertIn("incompatible_unit_quantity", relation.issues)

    def test_explicit_scaling_preserves_original_literals(self) -> None:
        observation = ExtractedObservation(
            observation_id=EntityId.from_seed("test.observation", "scaling"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text="1000 psi = 68.95 psi",
            normalized_text="1000 psi = 68.95 psi",
            document_position="fragment=scaling|page=1|section=section-1|paragraph=1|span=0:18",
            fragment_id=EntityId.from_seed("test.fragment", "scaling"),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="test.scaling",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=18),
            context_window=ContextWindow(match_text="1000 psi = 68.95 psi"),
            attributes=(
                ("raw_value", "1000"),
                ("raw_unit", "psi"),
                ("engineering_value", "68.95"),
                ("engineering_unit", "psi"),
            ),
        )

        run = self.engine.normalize(self._extraction_run((), (observation,)))

        relation = run.relation_candidates[0]
        self.assertEqual(relation.status, NormalizationCandidateStatus.RESOLVED)
        self.assertIn(("raw_unit", "psi"), relation.attributes)
        self.assertIn(("engineering_unit", "psi"), relation.attributes)

    def test_normalization_run_is_idempotent_for_same_input(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=0)
        unit = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=20)
        observation = self._unit_association(variable, unit)
        extraction_run = self._extraction_run((variable, unit), (observation,))

        first = self.engine.normalize(extraction_run)
        second = self.engine.normalize(extraction_run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(
            [(candidate.candidate_id, candidate.status) for candidate in first.entity_candidates],
            [(candidate.candidate_id, candidate.status) for candidate in second.entity_candidates],
        )
        self.assertEqual(
            [(candidate.candidate_id, candidate.status) for candidate in first.relation_candidates],
            [(candidate.candidate_id, candidate.status) for candidate in second.relation_candidates],
        )

    def test_in_memory_repository_persists_runs_end_to_end(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        run = self.engine.normalize(self._extraction_run((mention,), ()))
        repository = InMemoryNormalizationRunRepository().append_run(run)

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.list_runs(), (run,))

    def test_document_local_energistics_entities_and_relations_are_resolved(self) -> None:
        owner = self._mention("SurfaceEquipment", ExtractedEntityType.EQUIPMENT, extraction_rule="energistics.schema.class.v1")
        prop = self._mention("IdStandpipe", ExtractedEntityType.IDENTIFIER, start_offset=5, extraction_rule="energistics.schema.property.v1")
        obs = ExtractedObservation(
            observation_id=EntityId.from_seed("test.observation", "energistics-has-property"),
            observation_type=ExtractedObservationType.HAS_PROPERTY,
            original_text="SurfaceEquipment has property IdStandpipe",
            normalized_text="surfaceequipment has property idstandpipe",
            document_position="fragment=energistics|page=1|section=section-1|paragraph=1|span=0:40",
            fragment_id=EntityId.from_seed("test.fragment", "energistics"),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="energistics.schema.has_property.v1",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=40),
            context_window=ContextWindow(match_text="SurfaceEquipment has property IdStandpipe"),
            source_entity_id=owner.entity_id,
            target_entity_id=prop.entity_id,
            attributes=(("description", "Inner diameter of the standpipe."),),
        )

        run = self.engine.normalize(self._extraction_run((owner, prop), (obs,)))

        entity_candidates = {candidate.candidate_mention_id: candidate for candidate in run.entity_candidates}
        self.assertEqual(entity_candidates[owner.entity_id].status, NormalizationCandidateStatus.RESOLVED)
        self.assertEqual(entity_candidates[prop.entity_id].matched_table, "extract.document_local_entity")
        relation = run.relation_candidates[0]
        self.assertEqual(relation.status, NormalizationCandidateStatus.RESOLVED)
        self.assertEqual(relation.predicate_code, "has_property")

    def test_entity_candidate_preserves_full_evidence(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY, start_offset=4, end_offset=12)
        extraction_run = self._extraction_run((mention,), ())

        run = self.engine.normalize(extraction_run)

        candidate = run.entity_candidates[0]
        self.assertEqual(run.extraction_run_id, extraction_run.run_id)
        self.assertEqual(candidate.extraction_run_id, extraction_run.run_id)
        self.assertEqual(candidate.candidate_mention_id, mention.entity_id)
        self.assertEqual(candidate.mention_text, mention.original_text)
        self.assertEqual(candidate.source_mention.original_text, mention.original_text)
        self.assertEqual(candidate.source_mention.normalized_text, mention.normalized_text)
        self.assertEqual(candidate.source_mention.document_id, mention.document_id)
        self.assertEqual(candidate.source_mention.version_id, mention.version_id)
        self.assertEqual(candidate.source_mention.fragment_id, mention.fragment_id)
        self.assertEqual(candidate.source_mention.source_trace.start_offset, 4)
        self.assertEqual(candidate.source_mention.source_trace.end_offset, 12)

    def test_relation_candidate_preserves_full_evidence(self) -> None:
        variable = self._mention("Standpipe Pressure", ExtractedEntityType.VARIABLE, start_offset=2, end_offset=20)
        unit = self._mention("psi", ExtractedEntityType.ENGINEERING_UNIT, start_offset=22, end_offset=25)
        observation = self._unit_association(variable, unit)
        extraction_run = self._extraction_run((variable, unit), (observation,))

        run = self.engine.normalize(extraction_run)

        relation = run.relation_candidates[0]
        self.assertEqual(relation.extraction_run_id, extraction_run.run_id)
        self.assertEqual(relation.candidate_relation_id, observation.observation_id)
        self.assertEqual(relation.source_observation.original_text, observation.original_text)
        self.assertEqual(relation.source_observation.normalized_text, observation.normalized_text)
        self.assertEqual(relation.source_observation.document_id, observation.document_id)
        self.assertEqual(relation.source_observation.version_id, observation.version_id)
        self.assertEqual(relation.source_observation.fragment_id, observation.fragment_id)
        self.assertEqual(relation.source_observation.source_trace.start_offset, observation.source_trace.start_offset)
        self.assertEqual(relation.source_observation.source_trace.end_offset, observation.source_trace.end_offset)

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
                QuantityUnitCompatibility(
                    entity_id=EntityId.from_seed("test.compatibility", "flow_rate.gpm"),
                    code=CatalogCode("flow_rate.gpm"),
                    names=LocalizedName("flow rate to gpm"),
                    description="Allowed flow rate to gpm.",
                    scope=scope,
                    quantity_code=CatalogCode("flow_rate"),
                    unit_code=CatalogCode("gpm"),
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
                    entity_id=EntityId.from_seed("test.equipment", "mud_pump_a"),
                    code=CatalogCode("mud_pump_a"),
                    names=LocalizedName("Mud Pump"),
                    description="Mud pump A.",
                    scope=CatalogScope(model_family="nova 8000", vendor="acme"),
                ),
                EquipmentClass(
                    entity_id=EntityId.from_seed("test.equipment", "mud_pump_b"),
                    code=CatalogCode("mud_pump_b"),
                    names=LocalizedName("Mud Pump"),
                    description="Mud pump B.",
                    scope=CatalogScope(model_family="titan 9000", vendor="beta"),
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
            origins=empty,
            publishers=empty,
            systems=empty,
            subsystems=empty,
            processes=empty,
            operational_contexts=empty,
            locations=empty,
            sensors=empty,
            instruments=empty,
            equipment=equipment,
            variables=variables,
        )

    def _mention(
        self,
        text: str,
        entity_type: ExtractedEntityType,
        *,
        start_offset: int = 0,
        end_offset: int | None = None,
        extraction_rule: str = "test.rule",
    ) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("test.mention", f"{entity_type.value}:{text}:{start_offset}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=" ".join(text.split()).strip().lower(),
            document_position=f"fragment=fragment-1|page=1|section=section-1|paragraph=1|span={start_offset}:{end_offset or start_offset + len(text)}",
            fragment_id=EntityId.from_seed("test.fragment", "fragment-1"),
            document_id=EntityId.from_seed("test.document", "doc-1"),
            version_id=EntityId.from_seed("test.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule=extraction_rule,
            source_trace=ExtractionSourceTrace(
                page_number=1,
                paragraph_ordinal=1,
                start_offset=start_offset,
                end_offset=end_offset or start_offset + len(text),
            ),
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
            attributes=(
                ("subject_entity_id", str(subject.entity_id)),
                ("unit_entity_id", str(unit.entity_id)),
            ),
        )

    def _extraction_run(
        self,
        entities: tuple[ExtractedEntity, ...],
        observations: tuple[ExtractedObservation, ...],
    ) -> ExtractionRun:
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
            metrics=ExtractionMetrics(
                total_entities=len(entities),
                entity_counts_by_type={},
                entity_counts_by_rule={},
                document_counts={},
                records=(),
                duration_ms=0.0,
                errors=(),
            ),
        )