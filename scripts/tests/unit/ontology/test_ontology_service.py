from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, SensorClass, SubsystemClass, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace
from drilling_knowledge.ontology import (
    InMemoryOntologyRelationRepository,
    OntologyRelationStatus,
    OntologyRelationType,
    OntologyService,
)


class OntologyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.service = OntologyService.create(InMemoryOntologyRelationRepository.empty(), self.catalog)
        self.trace = ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=10)
        self.created_at = datetime(2026, 1, 1, 12, 0, 0)

    def test_creates_each_supported_relation_type(self) -> None:
        relation_specs = (
            (OntologyRelationType.IS_A, self._id("variable"), self._id("quantity")),
            (OntologyRelationType.MEASURES, self._id("sensor"), self._id("quantity")),
            (OntologyRelationType.BELONGS_TO_SUBSYSTEM, self._id("variable"), self._id("subsystem")),
            (OntologyRelationType.PRODUCED_BY_SENSOR, self._id("variable"), self._id("sensor")),
            (OntologyRelationType.USES_UNIT, self._id("variable"), self._id("unit")),
            (OntologyRelationType.UNIT_COMPATIBLE_WITH_QUANTITY, self._id("unit"), self._id("quantity")),
            (OntologyRelationType.ALIAS_OF, self._id("variable"), self._id("quantity")),
            (OntologyRelationType.RELATED_TO, self._id("variable"), self._id("sensor")),
        )

        for relation_type, source_id, target_id in relation_specs:
            relation = self.service.register(
                source_concept_id=source_id,
                target_concept_id=target_id,
                relation_type=relation_type,
                status=OntologyRelationStatus.ACTIVE,
                evidence=f"evidence:{relation_type.value}",
                rationale=f"rationale:{relation_type.value}",
                source_trace=self.trace,
                created_by="qa.engineer",
                created_at=self.created_at,
            )
            self.assertEqual(relation.relation_type, relation_type)

    def test_duplicate_active_identical_relation_is_idempotent(self) -> None:
        first = self._register(OntologyRelationType.RELATED_TO, self._id("variable"), self._id("sensor"))
        second = self._register(OntologyRelationType.RELATED_TO, self._id("variable"), self._id("sensor"))

        self.assertIs(first, second)
        self.assertEqual(len(self.service.list_all()), 1)

    def test_relation_history_is_preserved(self) -> None:
        first = self._register(OntologyRelationType.RELATED_TO, self._id("variable"), self._id("sensor"))
        second = self._register(
            OntologyRelationType.RELATED_TO,
            self._id("variable"),
            self._id("sensor"),
            status=OntologyRelationStatus.INACTIVE,
            evidence="inactive-evidence",
            rationale="deprecated relation",
            created_at=datetime(2026, 1, 2, 12, 0, 0),
        )

        history = self.service.list_history(self._id("variable"), self._id("sensor"), OntologyRelationType.RELATED_TO)
        self.assertEqual(history, (first, second))

    def test_active_and_inactive_statuses_are_handled(self) -> None:
        self._register(OntologyRelationType.RELATED_TO, self._id("variable"), self._id("sensor"))
        self._register(
            OntologyRelationType.RELATED_TO,
            self._id("variable"),
            self._id("sensor"),
            status=OntologyRelationStatus.INACTIVE,
            evidence="inactive-evidence",
            rationale="deprecated relation",
            created_at=datetime(2026, 1, 2, 12, 0, 0),
        )

        self.assertEqual(len(self.service.list_by_status(OntologyRelationStatus.ACTIVE)), 1)
        self.assertEqual(len(self.service.list_by_status(OntologyRelationStatus.INACTIVE)), 1)
        self.assertIsNone(self.service.get_active(self._id("variable"), self._id("sensor"), OntologyRelationType.RELATED_TO))

    def test_contradictory_single_target_relations_are_rejected(self) -> None:
        self._register(OntologyRelationType.USES_UNIT, self._id("variable"), self._id("unit"))

        with self.assertRaises(ValueError):
            self._register(
                OntologyRelationType.USES_UNIT,
                self._id("variable"),
                self._id("unit_alt"),
                evidence="alt-unit",
                rationale="conflicting active unit",
            )

    def test_invalid_self_reference_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._register(OntologyRelationType.RELATED_TO, self._id("variable"), self._id("variable"))

    def test_empty_catalog_or_missing_references_are_rejected(self) -> None:
        empty_service = OntologyService.create(InMemoryOntologyRelationRepository.empty(), InMemoryCatalogRepository.empty())
        with self.assertRaises(ValueError):
            empty_service.register(
                source_concept_id=self._id("variable"),
                target_concept_id=self._id("sensor"),
                relation_type=OntologyRelationType.RELATED_TO,
                status=OntologyRelationStatus.ACTIVE,
                evidence="missing",
                rationale="missing",
                source_trace=self.trace,
                created_by="qa.engineer",
                created_at=self.created_at,
            )

        with self.assertRaises(ValueError):
            self._register(
                OntologyRelationType.RELATED_TO,
                self._id("variable"),
                EntityId.from_seed("ontology.test.missing", "missing"),
            )

    def test_repository_order_is_stable(self) -> None:
        self._register(OntologyRelationType.RELATED_TO, self._id("variable"), self._id("sensor"))
        self._register(
            OntologyRelationType.IS_A,
            self._id("variable"),
            self._id("quantity"),
            created_at=datetime(2026, 1, 2, 12, 0, 0),
        )

        ordered = self.service.list_all()
        self.assertEqual(ordered, tuple(sorted(ordered, key=lambda relation: (str(relation.source_concept_id), str(relation.target_concept_id), relation.relation_type.value, relation.revision, relation.created_at.isoformat(), str(relation.relation_id)))))

    def test_inputs_are_not_mutated(self) -> None:
        source_id = self._id("variable")
        target_id = self._id("sensor")
        trace = self.trace
        created_at = self.created_at

        self._register(OntologyRelationType.RELATED_TO, source_id, target_id)

        self.assertEqual(source_id, self._id("variable"))
        self.assertEqual(target_id, self._id("sensor"))
        self.assertEqual(trace, self.trace)
        self.assertEqual(created_at, self.created_at)

    def test_no_transitive_inference_is_applied(self) -> None:
        self._register(OntologyRelationType.IS_A, self._id("variable"), self._id("quantity"))
        self._register(
            OntologyRelationType.IS_A,
            self._id("quantity"),
            self._id("subsystem"),
            created_at=datetime(2026, 1, 2, 12, 0, 0),
        )

        self.assertIsNone(self.service.get_active(self._id("variable"), self._id("subsystem"), OntologyRelationType.IS_A))

    def _register(
        self,
        relation_type: OntologyRelationType,
        source_concept_id: EntityId,
        target_concept_id: EntityId,
        *,
        status: OntologyRelationStatus = OntologyRelationStatus.ACTIVE,
        evidence: str = "manual-review",
        rationale: str = "validated relation",
        created_at: datetime | None = None,
    ):
        return self.service.register(
            source_concept_id=source_concept_id,
            target_concept_id=target_concept_id,
            relation_type=relation_type,
            status=status,
            evidence=evidence,
            rationale=rationale,
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=created_at or self.created_at,
        )

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=self._id("unit"),
                        code=CatalogCode("psi"),
                        names=LocalizedName("PSI"),
                        description="Pressure unit.",
                        scope=scope,
                        symbol="psi",
                        dimension_code="pressure",
                    ),
                    EngineeringUnit(
                        entity_id=self._id("unit_alt"),
                        code=CatalogCode("kpa"),
                        names=LocalizedName("KPA"),
                        description="Pressure unit alt.",
                        scope=scope,
                        symbol="kpa",
                        dimension_code="pressure",
                    ),
                )
            ),
            quantities=InMemoryEntityRepository(
                (
                    PhysicalQuantity(
                        entity_id=self._id("quantity"),
                        code=CatalogCode("pressure"),
                        names=LocalizedName("Pressure"),
                        description="Pressure quantity.",
                        scope=scope,
                        quantity_family="hydraulic",
                        dimension_code="pressure",
                    ),
                )
            ),
            principles=InMemoryEntityRepository(()),
            quantity_unit_compatibilities=InMemoryEntityRepository(()),
            classifications=InMemoryEntityRepository(()),
            origins=InMemoryEntityRepository(()),
            publishers=InMemoryEntityRepository(()),
            systems=InMemoryEntityRepository(()),
            subsystems=InMemoryEntityRepository(
                (
                    SubsystemClass(
                        entity_id=self._id("subsystem"),
                        code=CatalogCode("mud_system"),
                        names=LocalizedName("Mud System"),
                        description="Mud subsystem.",
                        scope=scope,
                        system_code=CatalogCode("surface_system"),
                    ),
                )
            ),
            processes=InMemoryEntityRepository(()),
            operational_contexts=InMemoryEntityRepository(()),
            locations=InMemoryEntityRepository(()),
            sensors=InMemoryEntityRepository(
                (
                    SensorClass(
                        entity_id=self._id("sensor"),
                        code=CatalogCode("pressure_sensor"),
                        names=LocalizedName("Pressure Sensor"),
                        description="Pressure sensor.",
                        scope=scope,
                    ),
                )
            ),
            instruments=InMemoryEntityRepository(()),
            equipment=InMemoryEntityRepository(()),
            variables=InMemoryEntityRepository(
                (
                    Variable(
                        entity_id=self._id("variable"),
                        code=CatalogCode("hook_load"),
                        names=LocalizedName("Hook Load"),
                        description="Hook load variable.",
                        scope=scope,
                    ),
                )
            ),
        )

    def _id(self, seed: str) -> EntityId:
        return EntityId.from_seed("ontology.test", seed)