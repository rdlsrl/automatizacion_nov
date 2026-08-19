"""In-memory catalog repositories for tests and bootstrap usage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar

from drilling_knowledge.catalog.domain import (
    CanonicalIdentity,
    EquipmentClass,
    EngineeringUnit,
    InstrumentClass,
    KnowledgeEntity,
    LocationClass,
    MeasurementPrinciple,
    OperationalContextClass,
    OriginClass,
    PhysicalQuantity,
    ProcessClass,
    PublisherClass,
    QuantityUnitCompatibility,
    SensorClass,
    SubsystemClass,
    SystemClass,
    Variable,
    VariableClassification,
)
from drilling_knowledge.catalog.domain.value_objects import CatalogCode
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository, EntityRepository
from drilling_knowledge.common.exceptions import DuplicateCanonicalCodeError

TEntity = TypeVar("TEntity", bound=KnowledgeEntity)


@dataclass(slots=True)
class InMemoryEntityRepository(EntityRepository[TEntity], Generic[TEntity]):
    entities: tuple[TEntity, ...] | Iterable[TEntity] | TEntity = ()
    _entities_by_identity: dict[CanonicalIdentity, TEntity] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.entities, KnowledgeEntity):
            source_entities = (self.entities,)
        else:
            source_entities = tuple(self.entities)
        normalized = tuple(sorted(source_entities, key=self._sort_key))
        identities: dict[CanonicalIdentity, TEntity] = {}
        for entity in normalized:
            identity = entity.canonical_identity
            if identity in identities:
                raise DuplicateCanonicalCodeError(
                    code="duplicate_canonical_code",
                    message="Duplicate canonical code detected for the same effective scope and version",
                    context={
                        "catalog_code": str(entity.code),
                        "scope": entity.scope.label(),
                        "semantic_version": entity.version.semantic_version,
                        "record_status": entity.version.status,
                    },
                )
            identities[identity] = entity
        object.__setattr__(self, "entities", normalized)
        object.__setattr__(self, "_entities_by_identity", identities)

    def get_by_identity(self, identity: CanonicalIdentity) -> TEntity | None:
        return self._entities_by_identity.get(identity)

    def get_by_code(self, code: CatalogCode) -> tuple[TEntity, ...]:
        return tuple(entity for entity in self.entities if entity.code == code)

    def list_all(self) -> tuple[TEntity, ...]:
        return self.entities

    def merge(self, new_entities: Iterable[TEntity]) -> "InMemoryEntityRepository[TEntity]":
        identity_map = {entity.canonical_identity: entity for entity in self.entities}
        merged_entities = list(self.entities)
        for entity in new_entities:
            existing = identity_map.get(entity.canonical_identity)
            if existing is None:
                merged_entities.append(entity)
                identity_map[entity.canonical_identity] = entity
                continue
            if existing != entity:
                raise DuplicateCanonicalCodeError(
                    code="duplicate_canonical_code",
                    message="Duplicate canonical code detected for the same effective scope and version",
                    context={
                        "catalog_code": str(entity.code),
                        "scope": entity.scope.label(),
                        "semantic_version": entity.version.semantic_version,
                        "record_status": entity.version.status,
                    },
                )
        return InMemoryEntityRepository(tuple(merged_entities))

    @staticmethod
    def _sort_key(entity: TEntity) -> tuple[str, str, int, str, datetime | None, datetime | None, str]:
        return (
            str(entity.code),
            entity.scope.label(),
            entity.version.semantic_version,
            entity.version.status,
            entity.version.valid_from,
            entity.version.valid_to,
            str(entity.entity_id),
        )


@dataclass(slots=True)
class InMemoryCatalogRepository(CatalogRepository):
    units: InMemoryEntityRepository[EngineeringUnit]
    quantities: InMemoryEntityRepository[PhysicalQuantity]
    principles: InMemoryEntityRepository[MeasurementPrinciple]
    quantity_unit_compatibilities: InMemoryEntityRepository[QuantityUnitCompatibility] = field(
        default_factory=lambda: InMemoryEntityRepository(())
    )
    classifications: InMemoryEntityRepository[VariableClassification]
    origins: InMemoryEntityRepository[OriginClass]
    publishers: InMemoryEntityRepository[PublisherClass] = field(default_factory=lambda: InMemoryEntityRepository(()))
    systems: InMemoryEntityRepository[SystemClass]
    subsystems: InMemoryEntityRepository[SubsystemClass]
    processes: InMemoryEntityRepository[ProcessClass] = field(default_factory=lambda: InMemoryEntityRepository(()))
    operational_contexts: InMemoryEntityRepository[OperationalContextClass] = field(
        default_factory=lambda: InMemoryEntityRepository(())
    )
    locations: InMemoryEntityRepository[LocationClass] = field(default_factory=lambda: InMemoryEntityRepository(()))
    sensors: InMemoryEntityRepository[SensorClass] = field(default_factory=lambda: InMemoryEntityRepository(()))
    instruments: InMemoryEntityRepository[InstrumentClass] = field(default_factory=lambda: InMemoryEntityRepository(()))
    equipment: InMemoryEntityRepository[EquipmentClass] = field(default_factory=lambda: InMemoryEntityRepository(()))
    variables: InMemoryEntityRepository[Variable]

    @classmethod
    def empty(cls) -> "InMemoryCatalogRepository":
        return cls(
            units=InMemoryEntityRepository(()),
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
            variables=InMemoryEntityRepository(()),
        )
