"""Read-only repository contracts for the catalog core."""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

from drilling_knowledge.catalog.domain import (
    CanonicalIdentity,
    EquipmentClass,
    EngineeringUnit,
    InstrumentClass,
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

TEntity = TypeVar("TEntity")


class EntityRepository(Protocol, Generic[TEntity]):
    """Generic read-only repository for master catalog entities.

    Canonical uniqueness applies only to the effective identity formed by
    `CatalogCode + scope + semantic_version + record_status`.
    Repeated names, mnemonics, aliases, or source-specific realizations must be preserved.
    """

    def get_by_identity(self, identity: CanonicalIdentity) -> TEntity | None:
        ...

    def get_by_code(self, code: CatalogCode) -> tuple[TEntity, ...]:
        ...

    def list_all(self) -> tuple[TEntity, ...]:
        ...


class CatalogRepository(Protocol):
    """Aggregate read contract consumed by catalog services and validators."""

    @property
    def units(self) -> EntityRepository[EngineeringUnit]:
        ...

    @property
    def quantities(self) -> EntityRepository[PhysicalQuantity]:
        ...

    @property
    def principles(self) -> EntityRepository[MeasurementPrinciple]:
        ...

    @property
    def quantity_unit_compatibilities(self) -> EntityRepository[QuantityUnitCompatibility]:
        ...

    @property
    def classifications(self) -> EntityRepository[VariableClassification]:
        ...

    @property
    def origins(self) -> EntityRepository[OriginClass]:
        ...

    @property
    def publishers(self) -> EntityRepository[PublisherClass]:
        ...

    @property
    def systems(self) -> EntityRepository[SystemClass]:
        ...

    @property
    def subsystems(self) -> EntityRepository[SubsystemClass]:
        ...

    @property
    def processes(self) -> EntityRepository[ProcessClass]:
        ...

    @property
    def operational_contexts(self) -> EntityRepository[OperationalContextClass]:
        ...

    @property
    def locations(self) -> EntityRepository[LocationClass]:
        ...

    @property
    def sensors(self) -> EntityRepository[SensorClass]:
        ...

    @property
    def instruments(self) -> EntityRepository[InstrumentClass]:
        ...

    @property
    def equipment(self) -> EntityRepository[EquipmentClass]:
        ...

    @property
    def variables(self) -> EntityRepository[Variable]:
        ...
