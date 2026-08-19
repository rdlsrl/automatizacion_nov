"""Core catalog entities for the IKC domain layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.catalog.domain.value_objects import (
    CanonicalIdentity,
    CatalogCode,
    CatalogScope,
    LocalizedName,
    VersionInfo,
)
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.common.validation import ValidationReport


@dataclass(frozen=True, slots=True)
class KnowledgeEntity:
    """Base entity shared by all catalog master records."""

    entity_id: EntityId
    code: CatalogCode
    names: LocalizedName
    description: str
    scope: CatalogScope = field(default_factory=CatalogScope)
    version: VersionInfo = field(default_factory=VersionInfo)

    def __post_init__(self) -> None:
        description = self.description.strip()
        if not description:
            raise ValueError("KnowledgeEntity.description cannot be empty")
        object.__setattr__(self, "description", description)

    @property
    def canonical_name(self) -> str:
        return self.names.canonical

    @property
    def canonical_identity(self) -> CanonicalIdentity:
        return CanonicalIdentity(
            code=self.code,
            scope_label=self.scope.label(),
            semantic_version=self.version.semantic_version,
            record_status=self.version.status,
        )

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        if not self.description:
            report.add_error("empty_description", "Entity description cannot be empty")
        version_report = self.version.validate()
        report.issues.extend(version_report.issues)
        return report


@dataclass(frozen=True, slots=True)
class EngineeringUnit(KnowledgeEntity):
    symbol: str = ""
    dimension_code: str = ""

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        symbol = self.symbol.strip()
        dimension = self.dimension_code.strip().lower()
        if not symbol:
            raise ValueError("EngineeringUnit.symbol cannot be empty")
        if not dimension:
            raise ValueError("EngineeringUnit.dimension_code cannot be empty")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "dimension_code", dimension)


@dataclass(frozen=True, slots=True)
class PhysicalQuantity(KnowledgeEntity):
    quantity_family: str = ""
    dimension_code: str = ""
    canonical_unit_code: CatalogCode | None = None

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        family = self.quantity_family.strip().lower()
        dimension = self.dimension_code.strip().lower()
        if not family:
            raise ValueError("PhysicalQuantity.quantity_family cannot be empty")
        if not dimension:
            raise ValueError("PhysicalQuantity.dimension_code cannot be empty")
        object.__setattr__(self, "quantity_family", family)
        object.__setattr__(self, "dimension_code", dimension)


@dataclass(frozen=True, slots=True)
class MeasurementPrinciple(KnowledgeEntity):
    principle_family: str = ""
    directness_class: str = "direct"

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        family = self.principle_family.strip().lower()
        directness = self.directness_class.strip().lower()
        if not family:
            raise ValueError("MeasurementPrinciple.principle_family cannot be empty")
        if directness not in {"direct", "indirect", "computational"}:
            raise ValueError("MeasurementPrinciple.directness_class is invalid")
        object.__setattr__(self, "principle_family", family)
        object.__setattr__(self, "directness_class", directness)


@dataclass(frozen=True, slots=True)
class VariableClassification(KnowledgeEntity):
    axis: str = ""
    parent_code: CatalogCode | None = None
    is_mutually_exclusive: bool = False

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        axis = self.axis.strip().lower()
        if not axis:
            raise ValueError("VariableClassification.axis cannot be empty")
        object.__setattr__(self, "axis", axis)


@dataclass(frozen=True, slots=True)
class OriginClass(KnowledgeEntity):
    axis: str = ""
    parent_code: CatalogCode | None = None

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        axis = self.axis.strip().lower()
        if not axis:
            raise ValueError("OriginClass.axis cannot be empty")
        object.__setattr__(self, "axis", axis)


@dataclass(frozen=True, slots=True)
class PublisherClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class SystemClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class SubsystemClass(KnowledgeEntity):
    system_code: CatalogCode = field(default_factory=lambda: CatalogCode("undefined.system"))
    parent_subsystem_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class ProcessClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class OperationalContextClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class LocationClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class SensorClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class InstrumentClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class EquipmentClass(KnowledgeEntity):
    parent_code: CatalogCode | None = None


@dataclass(frozen=True, slots=True)
class QuantityUnitCompatibility(KnowledgeEntity):
    quantity_code: CatalogCode = field(default_factory=lambda: CatalogCode("undefined.quantity"))
    unit_code: CatalogCode = field(default_factory=lambda: CatalogCode("undefined.unit"))
    compatibility_kind: str = "allowed"

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        compatibility_kind = self.compatibility_kind.strip().lower()
        if compatibility_kind not in {"allowed"}:
            raise ValueError("QuantityUnitCompatibility.compatibility_kind is invalid")
        object.__setattr__(self, "compatibility_kind", compatibility_kind)


@dataclass(frozen=True, slots=True)
class VariableAlias:
    alias: str
    alias_type: str = "alias"
    scope: CatalogScope = field(default_factory=CatalogScope)

    def __post_init__(self) -> None:
        alias = self.alias.strip()
        alias_type = self.alias_type.strip().lower()
        if not alias:
            raise ValueError("VariableAlias.alias cannot be empty")
        if not alias_type:
            raise ValueError("VariableAlias.alias_type cannot be empty")
        object.__setattr__(self, "alias", alias)
        object.__setattr__(self, "alias_type", alias_type)

    @property
    def normalized_alias(self) -> str:
        return self.alias.lower()


@dataclass(frozen=True, slots=True)
class Variable(KnowledgeEntity):
    physical_quantity_code: CatalogCode | None = None
    canonical_unit_code: CatalogCode | None = None
    classification_codes: tuple[CatalogCode, ...] = ()
    origin_codes: tuple[CatalogCode, ...] = ()
    subsystem_codes: tuple[CatalogCode, ...] = ()
    aliases: tuple[VariableAlias, ...] = ()
    evidence_requirement_level: str = "standard"
    ambiguity_level: str = "medium"

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        evidence = self.evidence_requirement_level.strip().lower()
        ambiguity = self.ambiguity_level.strip().lower()
        if evidence not in {"strict", "standard", "relaxed"}:
            raise ValueError("Variable.evidence_requirement_level is invalid")
        if ambiguity not in {"low", "medium", "high"}:
            raise ValueError("Variable.ambiguity_level is invalid")
        object.__setattr__(self, "evidence_requirement_level", evidence)
        object.__setattr__(self, "ambiguity_level", ambiguity)
