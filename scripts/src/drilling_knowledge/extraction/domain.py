"""Deterministic document extraction domain for explicit technical mentions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId, RunId


class ExtractedEntityType(StrEnum):
    VARIABLE = "VARIABLE"
    MNEMONIC = "MNEMONIC"
    SENSOR = "SENSOR"
    INSTRUMENT = "INSTRUMENT"
    EQUIPMENT = "EQUIPMENT"
    SYSTEM = "SYSTEM"
    SUBSYSTEM = "SUBSYSTEM"
    PROCESS = "PROCESS"
    ORIGIN = "ORIGIN"
    PUBLISHER = "PUBLISHER"
    PHYSICAL_QUANTITY = "PHYSICAL_QUANTITY"
    ENGINEERING_UNIT = "ENGINEERING_UNIT"
    MANUFACTURER = "MANUFACTURER"
    MODEL = "MODEL"
    STANDARD = "STANDARD"
    ALIAS = "ALIAS"
    ABBREVIATION = "ABBREVIATION"
    TAG = "TAG"
    TAG_TOKEN = "TAG_TOKEN"
    DOCUMENT_REFERENCE = "DOCUMENT_REFERENCE"
    TABLE_REFERENCE = "TABLE_REFERENCE"
    FIGURE_REFERENCE = "FIGURE_REFERENCE"
    SECTION_REFERENCE = "SECTION_REFERENCE"
    NUMBER = "NUMBER"
    RANGE = "RANGE"
    RAW_SIGNAL = "RAW_SIGNAL"
    FORMULA = "FORMULA"
    IDENTIFIER = "IDENTIFIER"


class ExtractedObservationType(StrEnum):
    TEXTUAL_UNIT_ASSOCIATION = "TEXTUAL_UNIT_ASSOCIATION"
    EXPLICIT_SCALING = "EXPLICIT_SCALING"
    ORIGIN_PUBLISHER_ASSOCIATION = "ORIGIN_PUBLISHER_ASSOCIATION"
    MEASUREMENT_CHAIN_COMPATIBILITY = "MEASUREMENT_CHAIN_COMPATIBILITY"
    HAS_PROPERTY = "HAS_PROPERTY"
    MEASUREMENT_TYPE = "MEASUREMENT_TYPE"
    DERIVED_FROM = "DERIVED_FROM"
    HAS_RELATIONSHIP = "HAS_RELATIONSHIP"


class ExtractionRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExtractionSourceTrace:
    page_number: int | None = None
    section_id: EntityId | None = None
    table_id: EntityId | None = None
    figure_id: EntityId | None = None
    paragraph_ordinal: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass(frozen=True, slots=True)
class ContextWindow:
    before_text: str = ""
    match_text: str = ""
    after_text: str = ""


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    entity_id: EntityId
    entity_type: ExtractedEntityType
    original_text: str
    normalized_text: str
    document_position: str
    fragment_id: EntityId
    document_id: EntityId
    version_id: EntityId
    extraction_confidence: float
    extraction_rule: str
    source_trace: ExtractionSourceTrace
    context_window: ContextWindow

    def __post_init__(self) -> None:
        original_text = self.original_text.strip()
        normalized_text = self.normalized_text.strip()
        document_position = self.document_position.strip()
        extraction_rule = self.extraction_rule.strip()
        if not original_text:
            raise ValueError("ExtractedEntity.original_text cannot be empty")
        if not normalized_text:
            raise ValueError("ExtractedEntity.normalized_text cannot be empty")
        if not document_position:
            raise ValueError("ExtractedEntity.document_position cannot be empty")
        if not extraction_rule:
            raise ValueError("ExtractedEntity.extraction_rule cannot be empty")
        if self.extraction_confidence < 0 or self.extraction_confidence > 1:
            raise ValueError("ExtractedEntity.extraction_confidence must be between 0 and 1")
        object.__setattr__(self, "original_text", original_text)
        object.__setattr__(self, "normalized_text", normalized_text)
        object.__setattr__(self, "document_position", document_position)
        object.__setattr__(self, "extraction_rule", extraction_rule)


@dataclass(frozen=True, slots=True)
class ExtractedObservation:
    observation_id: EntityId
    observation_type: ExtractedObservationType
    original_text: str
    normalized_text: str
    document_position: str
    fragment_id: EntityId
    document_id: EntityId
    version_id: EntityId
    extraction_confidence: float
    extraction_rule: str
    source_trace: ExtractionSourceTrace
    context_window: ContextWindow
    source_entity_id: EntityId | None = None
    target_entity_id: EntityId | None = None
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        original_text = self.original_text.strip()
        normalized_text = self.normalized_text.strip()
        document_position = self.document_position.strip()
        extraction_rule = self.extraction_rule.strip()
        if not original_text:
            raise ValueError("ExtractedObservation.original_text cannot be empty")
        if not normalized_text:
            raise ValueError("ExtractedObservation.normalized_text cannot be empty")
        if not document_position:
            raise ValueError("ExtractedObservation.document_position cannot be empty")
        if not extraction_rule:
            raise ValueError("ExtractedObservation.extraction_rule cannot be empty")
        if self.extraction_confidence < 0 or self.extraction_confidence > 1:
            raise ValueError("ExtractedObservation.extraction_confidence must be between 0 and 1")
        object.__setattr__(self, "original_text", original_text)
        object.__setattr__(self, "normalized_text", normalized_text)
        object.__setattr__(self, "document_position", document_position)
        object.__setattr__(self, "extraction_rule", extraction_rule)


@dataclass(frozen=True, slots=True)
class ExtractionMetricRecord:
    entity_type: ExtractedEntityType
    document_id: EntityId
    version_id: EntityId
    extraction_rule: str
    count: int


@dataclass(frozen=True, slots=True)
class ExtractionMetrics:
    total_entities: int
    entity_counts_by_type: dict[str, int]
    entity_counts_by_rule: dict[str, int]
    document_counts: dict[str, int]
    records: tuple[ExtractionMetricRecord, ...]
    duration_ms: float
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractionRun:
    run_id: RunId
    document_id: EntityId
    version_id: EntityId
    started_at: datetime
    finished_at: datetime
    status: ExtractionRunStatus
    entities: tuple[ExtractedEntity, ...] = ()
    observations: tuple[ExtractedObservation, ...] = ()
    metrics: ExtractionMetrics = field(
        default_factory=lambda: ExtractionMetrics(
            total_entities=0,
            entity_counts_by_type={},
            entity_counts_by_rule={},
            document_counts={},
            records=(),
            duration_ms=0.0,
            errors=(),
        )
    )

    @classmethod
    def empty(cls, document_id: EntityId, version_id: EntityId) -> "ExtractionRun":
        now = datetime.now(UTC)
        return cls(
            run_id=RunId.new(),
            document_id=document_id,
            version_id=version_id,
            started_at=now,
            finished_at=now,
            status=ExtractionRunStatus.COMPLETED,
        )