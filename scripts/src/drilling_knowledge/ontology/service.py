"""Deterministic services for explicit ontology relations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from drilling_knowledge.catalog.domain import KnowledgeEntity
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository, EntityRepository
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace
from drilling_knowledge.ontology.domain import (
    OntologyConceptReference,
    OntologyRelation,
    OntologyRelationStatus,
    OntologyRelationType,
)
from drilling_knowledge.ontology.repositories.contracts import OntologyRelationRepository


@dataclass(slots=True)
class OntologyService:
    repository: OntologyRelationRepository
    catalog_repository: CatalogRepository
    _catalog_index: dict[EntityId, OntologyConceptReference] = field(init=False, default_factory=dict)

    @classmethod
    def create(cls, repository: OntologyRelationRepository, catalog_repository: CatalogRepository) -> "OntologyService":
        service = cls(repository=repository, catalog_repository=catalog_repository)
        service._catalog_index = service._build_catalog_index()
        return service

    def register(
        self,
        *,
        source_concept_id: EntityId,
        target_concept_id: EntityId,
        relation_type: OntologyRelationType,
        status: OntologyRelationStatus,
        evidence: str,
        rationale: str,
        source_trace: ExtractionSourceTrace,
        created_by: str,
        created_at: datetime,
    ) -> OntologyRelation:
        if source_concept_id == target_concept_id and not self._self_reference_allowed(relation_type):
            raise ValueError("Self-referential ontology relations are not allowed for this relation type")

        source_reference = self._require_concept(source_concept_id)
        target_reference = self._require_concept(target_concept_id)
        self._assert_no_conflicting_active_relation(source_concept_id, target_concept_id, relation_type, status)

        latest = self.repository.get_latest(source_concept_id, target_concept_id, relation_type)
        if latest is not None and self._matches(latest, status, evidence, rationale, source_trace, created_by, created_at):
            return latest

        revision = 1 if latest is None else latest.revision + 1
        relation = OntologyRelation(
            relation_id=self._relation_id(
                source_concept_id,
                target_concept_id,
                relation_type,
                status,
                revision,
                evidence,
                rationale,
                source_trace,
                created_by,
                created_at,
            ),
            source_concept=source_reference,
            target_concept=target_reference,
            relation_type=relation_type,
            status=status,
            evidence=evidence,
            rationale=rationale,
            source_trace=source_trace,
            created_by=created_by,
            created_at=created_at,
            revision=revision,
        )
        self.repository = self.repository.append(relation)
        return relation

    def get_active(
        self,
        source_concept_id: EntityId,
        target_concept_id: EntityId,
        relation_type: OntologyRelationType,
    ) -> OntologyRelation | None:
        return self.repository.get_active(source_concept_id, target_concept_id, relation_type)

    def list_history(
        self,
        source_concept_id: EntityId,
        target_concept_id: EntityId,
        relation_type: OntologyRelationType,
    ) -> tuple[OntologyRelation, ...]:
        return self.repository.list_history(source_concept_id, target_concept_id, relation_type)

    def list_all(self) -> tuple[OntologyRelation, ...]:
        return self.repository.list_all()

    def list_by_status(self, status: OntologyRelationStatus) -> tuple[OntologyRelation, ...]:
        return self.repository.list_by_status(status)

    def _assert_no_conflicting_active_relation(
        self,
        source_concept_id: EntityId,
        target_concept_id: EntityId,
        relation_type: OntologyRelationType,
        status: OntologyRelationStatus,
    ) -> None:
        if status != OntologyRelationStatus.ACTIVE:
            return
        if relation_type not in self._single_target_relation_types():
            return
        for relation in self.repository.list_by_status(OntologyRelationStatus.ACTIVE):
            if relation.relation_type != relation_type:
                continue
            if relation.source_concept_id != source_concept_id:
                continue
            if relation.target_concept_id != target_concept_id:
                raise ValueError("Contradictory active ontology relation detected for a single-target relation type")

    def _build_catalog_index(self) -> dict[EntityId, OntologyConceptReference]:
        index: dict[EntityId, OntologyConceptReference] = {}
        repositories: tuple[tuple[EntityRepository[KnowledgeEntity], str], ...] = (
            (self.catalog_repository.units, "EngineeringUnit"),
            (self.catalog_repository.quantities, "PhysicalQuantity"),
            (self.catalog_repository.principles, "MeasurementPrinciple"),
            (self.catalog_repository.classifications, "VariableClassification"),
            (self.catalog_repository.origins, "OriginClass"),
            (self.catalog_repository.publishers, "PublisherClass"),
            (self.catalog_repository.systems, "SystemClass"),
            (self.catalog_repository.subsystems, "SubsystemClass"),
            (self.catalog_repository.processes, "ProcessClass"),
            (self.catalog_repository.operational_contexts, "OperationalContextClass"),
            (self.catalog_repository.locations, "LocationClass"),
            (self.catalog_repository.sensors, "SensorClass"),
            (self.catalog_repository.instruments, "InstrumentClass"),
            (self.catalog_repository.equipment, "EquipmentClass"),
            (self.catalog_repository.variables, "Variable"),
            (self.catalog_repository.quantity_unit_compatibilities, "QuantityUnitCompatibility"),
        )
        for repository, entity_type in repositories:
            for entity in repository.list_all():
                existing = index.get(entity.entity_id)
                reference = OntologyConceptReference(
                    concept_id=entity.entity_id,
                    catalog_code=str(entity.code),
                    catalog_entity_type=entity_type,
                    canonical_name=entity.canonical_name,
                )
                if existing is None:
                    index[entity.entity_id] = reference
                elif existing != reference:
                    raise ValueError("Conflicting catalog concept metadata detected while building ontology index")
        return index

    def _require_concept(self, concept_id: EntityId) -> OntologyConceptReference:
        reference = self._catalog_index.get(concept_id)
        if reference is None:
            raise ValueError(f"Ontology concept does not exist in catalog: {concept_id}")
        return reference

    def _relation_id(
        self,
        source_concept_id: EntityId,
        target_concept_id: EntityId,
        relation_type: OntologyRelationType,
        status: OntologyRelationStatus,
        revision: int,
        evidence: str,
        rationale: str,
        source_trace: ExtractionSourceTrace,
        created_by: str,
        created_at: datetime,
    ) -> EntityId:
        return EntityId.from_seed(
            "ontology.relation",
            "|".join(
                (
                    str(source_concept_id),
                    str(target_concept_id),
                    relation_type.value,
                    status.value,
                    str(revision),
                    evidence.strip(),
                    rationale.strip(),
                    created_by.strip(),
                    created_at.isoformat(),
                    self._source_trace_key(source_trace),
                )
            ),
        )

    def _matches(
        self,
        relation: OntologyRelation,
        status: OntologyRelationStatus,
        evidence: str,
        rationale: str,
        source_trace: ExtractionSourceTrace,
        created_by: str,
        created_at: datetime,
    ) -> bool:
        return (
            relation.status == status
            and relation.evidence == evidence.strip()
            and relation.rationale == rationale.strip()
            and relation.source_trace == source_trace
            and relation.created_by == created_by.strip()
            and relation.created_at == created_at
        )

    def _self_reference_allowed(self, relation_type: OntologyRelationType) -> bool:
        return False

    def _single_target_relation_types(self) -> set[OntologyRelationType]:
        return {
            OntologyRelationType.BELONGS_TO_SUBSYSTEM,
            OntologyRelationType.PRODUCED_BY_SENSOR,
            OntologyRelationType.USES_UNIT,
            OntologyRelationType.ALIAS_OF,
        }

    def _source_trace_key(self, source_trace: ExtractionSourceTrace) -> str:
        return "|".join(
            (
                str(source_trace.page_number),
                str(source_trace.section_id),
                str(source_trace.table_id),
                str(source_trace.figure_id),
                str(source_trace.paragraph_ordinal),
                str(source_trace.start_offset),
                str(source_trace.end_offset),
            )
        )
