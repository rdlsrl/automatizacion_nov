"""Deterministic technical knowledge domain for industrial drilling variables and instrumentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class MeasurementKind(StrEnum):
    PRIMARY_MEASUREMENT = "PRIMARY_MEASUREMENT"
    DERIVED_VARIABLE = "DERIVED_VARIABLE"
    CONFIGURED_VALUE = "CONFIGURED_VALUE"
    DISCRETE_STATE = "DISCRETE_STATE"
    ACCUMULATOR = "ACCUMULATOR"
    UNKNOWN = "UNKNOWN"


class RawSignalType(StrEnum):
    CURRENT = "CURRENT"
    VOLTAGE = "VOLTAGE"
    FREQUENCY = "FREQUENCY"
    PULSE = "PULSE"
    DIGITAL = "DIGITAL"
    PROTOCOL = "PROTOCOL"
    UNKNOWN = "UNKNOWN"


class WorkingRangeKind(StrEnum):
    SENSOR_NOMINAL_RANGE = "SENSOR_NOMINAL_RANGE"
    CONFIGURED_RANGE = "CONFIGURED_RANGE"
    ENGINEERING_RANGE = "ENGINEERING_RANGE"
    EXPECTED_OPERATING_RANGE = "EXPECTED_OPERATING_RANGE"
    OBSERVED_RANGE = "OBSERVED_RANGE"


class EvidenceLevel(StrEnum):
    INDUSTRY_STANDARD = "INDUSTRY_STANDARD"
    MANUFACTURER_DOCUMENTED = "MANUFACTURER_DOCUMENTED"
    MODEL_DOCUMENTED = "MODEL_DOCUMENTED"
    INSTALLATION_DOCUMENTED = "INSTALLATION_DOCUMENTED"
    CUSTOMER_SUPPLIED = "CUSTOMER_SUPPLIED"
    OBSERVED_IN_LAS = "OBSERVED_IN_LAS"


class EvidenceStatus(StrEnum):
    DOCUMENTED = "DOCUMENTED"
    INFERRED_CANDIDATE = "INFERRED_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    REQUIRES_EQUIPMENT_MODEL = "REQUIRES_EQUIPMENT_MODEL"
    REQUIRES_CONFIGURATION = "REQUIRES_CONFIGURATION"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"


class TechnicalEntityType(StrEnum):
    VARIABLE = "VARIABLE"
    SENSOR = "SENSOR"
    RAW_SIGNAL = "RAW_SIGNAL"
    CHANNEL = "CHANNEL"
    TAG = "TAG"
    UNIT = "UNIT"
    FAMILY = "FAMILY"
    PHYSICAL_QUANTITY = "PHYSICAL_QUANTITY"
    SUBSYSTEM = "SUBSYSTEM"
    LOCATION = "LOCATION"
    EQUIPMENT = "EQUIPMENT"
    EXPORTED_VARIABLE = "EXPORTED_VARIABLE"


class TechnicalRelationType(StrEnum):
    VARIABLE_BELONGS_TO_FAMILY = "VARIABLE_BELONGS_TO_FAMILY"
    VARIABLE_MEASURES_QUANTITY = "VARIABLE_MEASURES_QUANTITY"
    VARIABLE_PRODUCED_BY_SENSOR = "VARIABLE_PRODUCED_BY_SENSOR"
    VARIABLE_DERIVED_FROM = "VARIABLE_DERIVED_FROM"
    SENSOR_INSTALLED_AT = "SENSOR_INSTALLED_AT"
    SENSOR_CONNECTED_TO_CHANNEL = "SENSOR_CONNECTED_TO_CHANNEL"
    CHANNEL_EXPOSED_AS_TAG = "CHANNEL_EXPOSED_AS_TAG"
    TAG_EXPORTED_AS_VARIABLE = "TAG_EXPORTED_AS_VARIABLE"
    VARIABLE_USES_UNIT = "VARIABLE_USES_UNIT"
    EQUIPMENT_PART_OF_SUBSYSTEM = "EQUIPMENT_PART_OF_SUBSYSTEM"
    SENSOR_REDUNDANT_WITH = "SENSOR_REDUNDANT_WITH"
    SENSOR_BACKUP_FOR = "SENSOR_BACKUP_FOR"


@dataclass(frozen=True, slots=True)
class TechnicalEntityReference:
    entity_id: EntityId
    entity_type: TechnicalEntityType
    label: str

    def __post_init__(self) -> None:
        label = self.label.strip()
        if not label:
            raise ValueError("TechnicalEntityReference.label cannot be empty")
        object.__setattr__(self, "label", label)


@dataclass(frozen=True, slots=True)
class TechnicalEvidence:
    evidence_id: EntityId
    evidence_level: EvidenceLevel
    status: EvidenceStatus
    source_document_id: EntityId | None
    source_version_id: EntityId | None
    fragment_id: EntityId | None
    original_text: str
    rationale: str
    confidence: float
    created_at: datetime
    revision: int

    def __post_init__(self) -> None:
        original_text = self.original_text.strip()
        rationale = self.rationale.strip()
        if not original_text:
            raise ValueError("TechnicalEvidence.original_text cannot be empty")
        if not rationale:
            raise ValueError("TechnicalEvidence.rationale cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("TechnicalEvidence.confidence must be between 0 and 1")
        if self.revision < 1:
            raise ValueError("TechnicalEvidence.revision must be >= 1")
        object.__setattr__(self, "original_text", original_text)
        object.__setattr__(self, "rationale", rationale)


@dataclass(frozen=True, slots=True)
class TechnicalVariable:
    variable_id: EntityId
    canonical_name: str
    family: str | None
    physical_quantity: str | None
    subsystem: str | None
    process_context: str | None
    criticality: str | None
    measurement_kind: MeasurementKind
    evidence_ids: tuple[EntityId, ...]
    revision: int

    def __post_init__(self) -> None:
        canonical_name = self.canonical_name.strip()
        if not canonical_name:
            raise ValueError("TechnicalVariable.canonical_name cannot be empty")
        if not self.evidence_ids:
            raise ValueError("TechnicalVariable.evidence_ids cannot be empty")
        if self.revision < 1:
            raise ValueError("TechnicalVariable.revision must be >= 1")
        object.__setattr__(self, "canonical_name", canonical_name)
        object.__setattr__(self, "family", self._clean_optional(self.family))
        object.__setattr__(self, "physical_quantity", self._clean_optional(self.physical_quantity))
        object.__setattr__(self, "subsystem", self._clean_optional(self.subsystem))
        object.__setattr__(self, "process_context", self._clean_optional(self.process_context))
        object.__setattr__(self, "criticality", self._clean_optional(self.criticality))

    def as_reference(self) -> TechnicalEntityReference:
        return TechnicalEntityReference(entity_id=self.variable_id, entity_type=TechnicalEntityType.VARIABLE, label=self.canonical_name)

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class TechnicalSensor:
    sensor_id: EntityId
    sensor_type: str
    measurement_principle: str | None
    manufacturer: str | None
    model: str | None
    physical_location_typical: str | None
    physical_location_specific: str | None
    installation_context: str | None
    accuracy: str | None
    resolution: str | None
    sampling_rate: str | None
    operating_conditions: str | None
    evidence_ids: tuple[EntityId, ...]
    revision: int

    def __post_init__(self) -> None:
        sensor_type = self.sensor_type.strip()
        if not sensor_type:
            raise ValueError("TechnicalSensor.sensor_type cannot be empty")
        if not self.evidence_ids:
            raise ValueError("TechnicalSensor.evidence_ids cannot be empty")
        if self.revision < 1:
            raise ValueError("TechnicalSensor.revision must be >= 1")
        object.__setattr__(self, "sensor_type", sensor_type)
        for field_name in (
            "measurement_principle",
            "manufacturer",
            "model",
            "physical_location_typical",
            "physical_location_specific",
            "installation_context",
            "accuracy",
            "resolution",
            "sampling_rate",
            "operating_conditions",
        ):
            object.__setattr__(self, field_name, self._clean_optional(getattr(self, field_name)))

    def as_reference(self) -> TechnicalEntityReference:
        return TechnicalEntityReference(entity_id=self.sensor_id, entity_type=TechnicalEntityType.SENSOR, label=self.sensor_type)

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class RawSignal:
    raw_signal_id: EntityId
    raw_signal_type: RawSignalType
    raw_min: float | None
    raw_max: float | None
    raw_unit: str | None
    protocol: str | None
    channel: str | None
    scaling_formula: str | None
    evidence_ids: tuple[EntityId, ...]
    revision: int

    def __post_init__(self) -> None:
        if self.evidence_ids == ():
            raise ValueError("RawSignal.evidence_ids cannot be empty")
        if self.raw_min is not None and self.raw_max is not None and self.raw_min > self.raw_max:
            raise ValueError("RawSignal.raw_min cannot be greater than raw_max")
        if self.revision < 1:
            raise ValueError("RawSignal.revision must be >= 1")
        for field_name in ("raw_unit", "protocol", "channel", "scaling_formula"):
            object.__setattr__(self, field_name, self._clean_optional(getattr(self, field_name)))

    def as_reference(self) -> TechnicalEntityReference:
        label = self.channel or self.raw_signal_type.value
        return TechnicalEntityReference(entity_id=self.raw_signal_id, entity_type=TechnicalEntityType.RAW_SIGNAL, label=label)

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class WorkingRange:
    range_id: EntityId
    variable_id: EntityId
    range_kind: WorkingRangeKind
    min_value: float | None
    max_value: float | None
    unit: str | None
    status: EvidenceStatus
    evidence_ids: tuple[EntityId, ...]
    revision: int

    def __post_init__(self) -> None:
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("WorkingRange.min_value cannot be greater than max_value")
        if not self.evidence_ids:
            raise ValueError("WorkingRange.evidence_ids cannot be empty")
        if self.revision < 1:
            raise ValueError("WorkingRange.revision must be >= 1")
        object.__setattr__(self, "unit", self._clean_optional(self.unit))

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class DerivedVariableDefinition:
    variable_id: EntityId
    derivation_type: str
    source_variable_ids: tuple[EntityId, ...]
    formula_original: str | None
    formula_normalized: str | None
    constants: tuple[tuple[str, str], ...]
    input_units: tuple[tuple[str, str], ...]
    output_unit: str | None
    calculation_conditions: str | None
    null_handling: str | None
    filtering_or_averaging: str | None
    calculating_equipment_or_software: str | None
    evidence_ids: tuple[EntityId, ...]
    revision: int

    def __post_init__(self) -> None:
        derivation_type = self.derivation_type.strip()
        if not derivation_type:
            raise ValueError("DerivedVariableDefinition.derivation_type cannot be empty")
        if not self.source_variable_ids:
            raise ValueError("DerivedVariableDefinition.source_variable_ids cannot be empty")
        if not self.evidence_ids:
            raise ValueError("DerivedVariableDefinition.evidence_ids cannot be empty")
        if self.revision < 1:
            raise ValueError("DerivedVariableDefinition.revision must be >= 1")
        object.__setattr__(self, "derivation_type", derivation_type)
        for field_name in (
            "formula_original",
            "formula_normalized",
            "output_unit",
            "calculation_conditions",
            "null_handling",
            "filtering_or_averaging",
            "calculating_equipment_or_software",
        ):
            object.__setattr__(self, field_name, self._clean_optional(getattr(self, field_name)))

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class TechnicalRelation:
    relation_id: EntityId
    source: TechnicalEntityReference
    target: TechnicalEntityReference
    relation_type: TechnicalRelationType
    evidence_ids: tuple[EntityId, ...]
    rationale: str
    source_trace: ExtractionSourceTrace
    created_by: str
    created_at: datetime
    revision: int

    def __post_init__(self) -> None:
        rationale = self.rationale.strip()
        created_by = self.created_by.strip()
        if not self.evidence_ids:
            raise ValueError("TechnicalRelation.evidence_ids cannot be empty")
        if not rationale:
            raise ValueError("TechnicalRelation.rationale cannot be empty")
        if not created_by:
            raise ValueError("TechnicalRelation.created_by cannot be empty")
        if self.revision < 1:
            raise ValueError("TechnicalRelation.revision must be >= 1")
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "created_by", created_by)
