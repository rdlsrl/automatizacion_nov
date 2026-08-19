"""Deterministic services for technical knowledge registration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace
from drilling_knowledge.technical_knowledge.domain import (
    DerivedVariableDefinition,
    EvidenceLevel,
    EvidenceStatus,
    MeasurementKind,
    RawSignal,
    RawSignalType,
    TechnicalEntityReference,
    TechnicalEntityType,
    TechnicalEvidence,
    TechnicalRelation,
    TechnicalRelationType,
    TechnicalSensor,
    TechnicalVariable,
    WorkingRange,
    WorkingRangeKind,
)
from drilling_knowledge.technical_knowledge.repositories.contracts import TechnicalKnowledgeRepository


@dataclass(slots=True)
class TechnicalKnowledgeService:
    repository: TechnicalKnowledgeRepository

    @classmethod
    def create(cls, repository: TechnicalKnowledgeRepository) -> "TechnicalKnowledgeService":
        return cls(repository=repository)

    def register_evidence(
        self,
        *,
        evidence_id: EntityId,
        evidence_level: EvidenceLevel,
        status: EvidenceStatus,
        source_document_id: EntityId | None,
        source_version_id: EntityId | None,
        fragment_id: EntityId | None,
        original_text: str,
        rationale: str,
        confidence: float,
        created_at: datetime,
    ) -> TechnicalEvidence:
        latest = self.repository.get_latest_evidence(evidence_id)
        if latest is not None:
            self._validate_evidence_revision(
                latest=latest,
                evidence_level=evidence_level,
                source_document_id=source_document_id,
                source_version_id=source_version_id,
                fragment_id=fragment_id,
            )
        revision = 1 if latest is None else latest.revision + 1
        evidence = TechnicalEvidence(
            evidence_id=evidence_id,
            evidence_level=evidence_level,
            status=status,
            source_document_id=source_document_id,
            source_version_id=source_version_id,
            fragment_id=fragment_id,
            original_text=original_text,
            rationale=rationale,
            confidence=confidence,
            created_at=created_at,
            revision=revision,
        )
        if latest is not None and self._same_evidence(latest, evidence):
            return latest
        self.repository = self.repository.append_evidence(evidence)
        return evidence

    def register_variable(
        self,
        *,
        variable_id: EntityId,
        canonical_name: str,
        family: str | None,
        physical_quantity: str | None,
        subsystem: str | None,
        process_context: str | None,
        criticality: str | None,
        measurement_kind: MeasurementKind,
        evidence_ids: tuple[EntityId, ...],
    ) -> TechnicalVariable:
        self._require_evidences(evidence_ids)
        latest = self.repository.get_latest_variable(variable_id)
        revision = 1 if latest is None else latest.revision + 1
        variable = TechnicalVariable(
            variable_id=variable_id,
            canonical_name=canonical_name,
            family=family,
            physical_quantity=physical_quantity,
            subsystem=subsystem,
            process_context=process_context,
            criticality=criticality,
            measurement_kind=measurement_kind,
            evidence_ids=evidence_ids,
            revision=revision,
        )
        if latest is not None and self._same_variable(latest, variable):
            return latest
        self.repository = self.repository.append_variable(variable)
        return variable

    def register_sensor(
        self,
        *,
        sensor_id: EntityId,
        sensor_type: str,
        measurement_principle: str | None,
        manufacturer: str | None,
        model: str | None,
        physical_location_typical: str | None,
        physical_location_specific: str | None,
        installation_context: str | None,
        accuracy: str | None,
        resolution: str | None,
        sampling_rate: str | None,
        operating_conditions: str | None,
        evidence_ids: tuple[EntityId, ...],
    ) -> TechnicalSensor:
        self._require_evidences(evidence_ids)
        latest = self.repository.get_latest_sensor(sensor_id)
        revision = 1 if latest is None else latest.revision + 1
        sensor = TechnicalSensor(
            sensor_id=sensor_id,
            sensor_type=sensor_type,
            measurement_principle=measurement_principle,
            manufacturer=manufacturer,
            model=model,
            physical_location_typical=physical_location_typical,
            physical_location_specific=physical_location_specific,
            installation_context=installation_context,
            accuracy=accuracy,
            resolution=resolution,
            sampling_rate=sampling_rate,
            operating_conditions=operating_conditions,
            evidence_ids=evidence_ids,
            revision=revision,
        )
        if latest is not None and self._same_sensor(latest, sensor):
            return latest
        self.repository = self.repository.append_sensor(sensor)
        return sensor

    def register_raw_signal(
        self,
        *,
        raw_signal_id: EntityId,
        raw_signal_type: RawSignalType,
        raw_min: float | None,
        raw_max: float | None,
        raw_unit: str | None,
        protocol: str | None,
        channel: str | None,
        scaling_formula: str | None,
        evidence_ids: tuple[EntityId, ...],
    ) -> RawSignal:
        self._require_evidences(evidence_ids)
        latest = self.repository.get_latest_raw_signal(raw_signal_id)
        revision = 1 if latest is None else latest.revision + 1
        raw_signal = RawSignal(
            raw_signal_id=raw_signal_id,
            raw_signal_type=raw_signal_type,
            raw_min=raw_min,
            raw_max=raw_max,
            raw_unit=raw_unit,
            protocol=protocol,
            channel=channel,
            scaling_formula=scaling_formula,
            evidence_ids=evidence_ids,
            revision=revision,
        )
        self._validate_raw_signal(raw_signal)
        if latest is not None and self._same_raw_signal(latest, raw_signal):
            return latest
        self.repository = self.repository.append_raw_signal(raw_signal)
        return raw_signal

    def register_working_range(
        self,
        *,
        variable_id: EntityId,
        range_kind: WorkingRangeKind,
        min_value: float | None,
        max_value: float | None,
        unit: str | None,
        status: EvidenceStatus,
        evidence_ids: tuple[EntityId, ...],
    ) -> WorkingRange:
        self._require_variable(variable_id)
        self._require_evidences(evidence_ids)
        latest = self.repository.get_latest_working_range(variable_id, range_kind)
        revision = 1 if latest is None else latest.revision + 1
        working_range = WorkingRange(
            range_id=EntityId.from_seed("technical_knowledge.range", f"{variable_id}:{range_kind.value}:{revision}:{min_value}:{max_value}:{unit}:{status.value}:{'|'.join(str(evidence_id) for evidence_id in evidence_ids)}"),
            variable_id=variable_id,
            range_kind=range_kind,
            min_value=min_value,
            max_value=max_value,
            unit=unit,
            status=status,
            evidence_ids=evidence_ids,
            revision=revision,
        )
        self._validate_working_range(working_range)
        if latest is not None and self._same_working_range(latest, working_range):
            return latest
        self.repository = self.repository.append_working_range(working_range)
        return working_range

    def register_derived_variable(
        self,
        *,
        variable_id: EntityId,
        derivation_type: str,
        source_variable_ids: tuple[EntityId, ...],
        formula_original: str | None,
        formula_normalized: str | None,
        constants: tuple[tuple[str, str], ...],
        input_units: tuple[tuple[str, str], ...],
        output_unit: str | None,
        calculation_conditions: str | None,
        null_handling: str | None,
        filtering_or_averaging: str | None,
        calculating_equipment_or_software: str | None,
        evidence_ids: tuple[EntityId, ...],
    ) -> DerivedVariableDefinition:
        variable = self._require_variable(variable_id)
        if variable.measurement_kind != MeasurementKind.DERIVED_VARIABLE:
            raise ValueError("Derived variable definition requires a variable with measurement_kind DERIVED_VARIABLE")
        self._require_evidences(evidence_ids)
        for source_variable_id in source_variable_ids:
            self._require_variable(source_variable_id)
        self._assert_variable_has_no_physical_sensor(variable_id)
        latest = self.repository.get_latest_derived_variable(variable_id)
        revision = 1 if latest is None else latest.revision + 1
        derived = DerivedVariableDefinition(
            variable_id=variable_id,
            derivation_type=derivation_type,
            source_variable_ids=source_variable_ids,
            formula_original=formula_original,
            formula_normalized=formula_normalized,
            constants=constants,
            input_units=input_units,
            output_unit=output_unit,
            calculation_conditions=calculation_conditions,
            null_handling=null_handling,
            filtering_or_averaging=filtering_or_averaging,
            calculating_equipment_or_software=calculating_equipment_or_software,
            evidence_ids=evidence_ids,
            revision=revision,
        )
        self._validate_derived_variable(derived)
        if latest is not None and self._same_derived_variable(latest, derived):
            return latest
        self.repository = self.repository.append_derived_variable(derived)
        return derived

    def register_relation(
        self,
        *,
        source: TechnicalEntityReference,
        target: TechnicalEntityReference,
        relation_type: TechnicalRelationType,
        evidence_ids: tuple[EntityId, ...],
        rationale: str,
        source_trace: ExtractionSourceTrace,
        created_by: str,
        created_at: datetime,
    ) -> TechnicalRelation:
        self._require_evidences(evidence_ids)
        self._validate_reference(source)
        self._validate_reference(target)
        self._validate_relation_shape(source, target, relation_type)
        self._assert_no_relation_contradiction(source, target, relation_type)
        latest = self.repository.get_latest_relation(source.entity_id, target.entity_id, relation_type)
        revision = 1 if latest is None else latest.revision + 1
        relation = TechnicalRelation(
            relation_id=EntityId.from_seed(
                "technical_knowledge.relation",
                f"{source.entity_id}:{target.entity_id}:{relation_type.value}:{revision}:{'|'.join(str(evidence_id) for evidence_id in evidence_ids)}:{rationale.strip()}:{created_by.strip()}:{created_at.isoformat()}:{self._source_trace_key(source_trace)}",
            ),
            source=source,
            target=target,
            relation_type=relation_type,
            evidence_ids=evidence_ids,
            rationale=rationale,
            source_trace=source_trace,
            created_by=created_by,
            created_at=created_at,
            revision=revision,
        )
        if latest is not None and self._same_relation(latest, relation):
            return latest
        self.repository = self.repository.append_relation(relation)
        return relation

    def list_all_relations(self) -> tuple[TechnicalRelation, ...]:
        return self.repository.list_all_relations()

    def list_variable_history(self, variable_id: EntityId) -> tuple[TechnicalVariable, ...]:
        return self.repository.list_variable_history(variable_id)

    def _require_evidences(self, evidence_ids: tuple[EntityId, ...]) -> None:
        if not evidence_ids:
            raise ValueError("Technical knowledge assertions require at least one evidence reference")
        for evidence_id in evidence_ids:
            if self.repository.get_latest_evidence(evidence_id) is None:
                raise ValueError(f"Technical evidence not found: {evidence_id}")

    def _require_variable(self, variable_id: EntityId) -> TechnicalVariable:
        variable = self.repository.get_latest_variable(variable_id)
        if variable is None:
            raise ValueError(f"Technical variable not found: {variable_id}")
        return variable

    def _assert_variable_has_no_physical_sensor(self, variable_id: EntityId) -> None:
        for relation in self.repository.list_all_relations():
            if relation.relation_type != TechnicalRelationType.VARIABLE_PRODUCED_BY_SENSOR:
                continue
            if relation.source.entity_id == variable_id:
                raise ValueError("Derived variables cannot be assigned to a physical sensor")

    def _validate_reference(self, reference: TechnicalEntityReference) -> None:
        if reference.entity_type == TechnicalEntityType.VARIABLE:
            self._require_variable(reference.entity_id)
        elif reference.entity_type == TechnicalEntityType.SENSOR and self.repository.get_latest_sensor(reference.entity_id) is None:
            raise ValueError(f"Technical sensor not found: {reference.entity_id}")
        elif reference.entity_type == TechnicalEntityType.RAW_SIGNAL and self.repository.get_latest_raw_signal(reference.entity_id) is None:
            raise ValueError(f"Raw signal not found: {reference.entity_id}")

    def _validate_relation_shape(
        self,
        source: TechnicalEntityReference,
        target: TechnicalEntityReference,
        relation_type: TechnicalRelationType,
    ) -> None:
        if source.entity_id == target.entity_id:
            raise ValueError("Self-referential technical relations are not allowed")
        expected = {
            TechnicalRelationType.VARIABLE_BELONGS_TO_FAMILY: (TechnicalEntityType.VARIABLE, TechnicalEntityType.FAMILY),
            TechnicalRelationType.VARIABLE_MEASURES_QUANTITY: (TechnicalEntityType.VARIABLE, TechnicalEntityType.PHYSICAL_QUANTITY),
            TechnicalRelationType.VARIABLE_PRODUCED_BY_SENSOR: (TechnicalEntityType.VARIABLE, TechnicalEntityType.SENSOR),
            TechnicalRelationType.VARIABLE_DERIVED_FROM: (TechnicalEntityType.VARIABLE, TechnicalEntityType.VARIABLE),
            TechnicalRelationType.SENSOR_INSTALLED_AT: (TechnicalEntityType.SENSOR, TechnicalEntityType.LOCATION),
            TechnicalRelationType.SENSOR_CONNECTED_TO_CHANNEL: (TechnicalEntityType.SENSOR, TechnicalEntityType.CHANNEL),
            TechnicalRelationType.CHANNEL_EXPOSED_AS_TAG: (TechnicalEntityType.CHANNEL, TechnicalEntityType.TAG),
            TechnicalRelationType.TAG_EXPORTED_AS_VARIABLE: (TechnicalEntityType.TAG, TechnicalEntityType.VARIABLE),
            TechnicalRelationType.VARIABLE_USES_UNIT: (TechnicalEntityType.VARIABLE, TechnicalEntityType.UNIT),
            TechnicalRelationType.EQUIPMENT_PART_OF_SUBSYSTEM: (TechnicalEntityType.EQUIPMENT, TechnicalEntityType.SUBSYSTEM),
            TechnicalRelationType.SENSOR_REDUNDANT_WITH: (TechnicalEntityType.SENSOR, TechnicalEntityType.SENSOR),
            TechnicalRelationType.SENSOR_BACKUP_FOR: (TechnicalEntityType.SENSOR, TechnicalEntityType.SENSOR),
        }[relation_type]
        if (source.entity_type, target.entity_type) != expected:
            raise ValueError(f"Invalid technical relation endpoints for {relation_type.value}")
        if relation_type == TechnicalRelationType.VARIABLE_PRODUCED_BY_SENSOR:
            variable = self._require_variable(source.entity_id)
            if variable.measurement_kind == MeasurementKind.DERIVED_VARIABLE:
                raise ValueError("Derived variables cannot be assigned to a physical sensor")
        if relation_type == TechnicalRelationType.VARIABLE_DERIVED_FROM:
            variable = self._require_variable(source.entity_id)
            if variable.measurement_kind != MeasurementKind.DERIVED_VARIABLE:
                raise ValueError("VARIABLE_DERIVED_FROM requires a derived variable as source")
            derived_definition = self.repository.get_latest_derived_variable(source.entity_id)
            if derived_definition is not None and target.entity_id not in derived_definition.source_variable_ids:
                raise ValueError("VARIABLE_DERIVED_FROM target must exist in the documented derived variable sources")
        if relation_type == TechnicalRelationType.CHANNEL_EXPOSED_AS_TAG:
            if not self._has_active_relation(target_entity_id=source.entity_id, relation_type=TechnicalRelationType.SENSOR_CONNECTED_TO_CHANNEL):
                raise ValueError("CHANNEL_EXPOSED_AS_TAG requires a documented SENSOR_CONNECTED_TO_CHANNEL relation")
        if relation_type == TechnicalRelationType.TAG_EXPORTED_AS_VARIABLE:
            if not self._has_active_relation(target_entity_id=source.entity_id, relation_type=TechnicalRelationType.CHANNEL_EXPOSED_AS_TAG):
                raise ValueError("TAG_EXPORTED_AS_VARIABLE requires a documented CHANNEL_EXPOSED_AS_TAG relation")

    def _assert_no_relation_contradiction(
        self,
        source: TechnicalEntityReference,
        target: TechnicalEntityReference,
        relation_type: TechnicalRelationType,
    ) -> None:
        if relation_type not in self._single_target_relation_types():
            return
        for relation in self.repository.list_all_relations():
            if relation.relation_type != relation_type:
                continue
            if relation.source.entity_id != source.entity_id:
                continue
            latest = self.repository.get_latest_relation(relation.source.entity_id, relation.target.entity_id, relation.relation_type)
            if latest is None or latest != relation:
                continue
            if relation.target.entity_id != target.entity_id:
                raise ValueError("Contradictory active technical relation detected")

    def _single_target_relation_types(self) -> set[TechnicalRelationType]:
        return {
            TechnicalRelationType.VARIABLE_BELONGS_TO_FAMILY,
            TechnicalRelationType.VARIABLE_MEASURES_QUANTITY,
            TechnicalRelationType.VARIABLE_PRODUCED_BY_SENSOR,
            TechnicalRelationType.SENSOR_CONNECTED_TO_CHANNEL,
            TechnicalRelationType.CHANNEL_EXPOSED_AS_TAG,
            TechnicalRelationType.TAG_EXPORTED_AS_VARIABLE,
            TechnicalRelationType.VARIABLE_USES_UNIT,
            TechnicalRelationType.EQUIPMENT_PART_OF_SUBSYSTEM,
        }

    def _same_variable(self, left: TechnicalVariable, right: TechnicalVariable) -> bool:
        return replace(left, revision=right.revision) == right

    def _same_evidence(self, left: TechnicalEvidence, right: TechnicalEvidence) -> bool:
        return replace(left, revision=right.revision) == right

    def _same_sensor(self, left: TechnicalSensor, right: TechnicalSensor) -> bool:
        return replace(left, revision=right.revision) == right

    def _same_raw_signal(self, left: RawSignal, right: RawSignal) -> bool:
        return replace(left, revision=right.revision) == right

    def _same_working_range(self, left: WorkingRange, right: WorkingRange) -> bool:
        return replace(left, range_id=right.range_id, revision=right.revision) == right

    def _same_derived_variable(self, left: DerivedVariableDefinition, right: DerivedVariableDefinition) -> bool:
        return replace(left, revision=right.revision) == right

    def _same_relation(self, left: TechnicalRelation, right: TechnicalRelation) -> bool:
        return replace(left, relation_id=right.relation_id, revision=right.revision) == right

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

    def _validate_evidence_revision(
        self,
        *,
        latest: TechnicalEvidence,
        evidence_level: EvidenceLevel,
        source_document_id: EntityId | None,
        source_version_id: EntityId | None,
        fragment_id: EntityId | None,
    ) -> None:
        if latest.evidence_level != evidence_level:
            raise ValueError("Evidence level cannot change across revisions for the same evidence_id")
        if (
            latest.source_document_id != source_document_id
            or latest.source_version_id != source_version_id
            or latest.fragment_id != fragment_id
        ):
            raise ValueError("Evidence provenance cannot change across revisions for the same evidence_id")

    def _validate_raw_signal(self, raw_signal: RawSignal) -> None:
        numeric_types = {
            RawSignalType.CURRENT,
            RawSignalType.VOLTAGE,
            RawSignalType.FREQUENCY,
            RawSignalType.PULSE,
        }
        non_numeric_types = {RawSignalType.DIGITAL, RawSignalType.PROTOCOL}
        has_partial_bounds = (raw_signal.raw_min is None) != (raw_signal.raw_max is None)
        if raw_signal.raw_signal_type in numeric_types and has_partial_bounds:
            raise ValueError("Numeric raw signals require both raw_min and raw_max when bounds are documented")
        if raw_signal.raw_signal_type in non_numeric_types:
            if raw_signal.raw_min is not None or raw_signal.raw_max is not None:
                raise ValueError("DIGITAL and PROTOCOL raw signals cannot declare numeric raw_min/raw_max bounds")
            if raw_signal.scaling_formula is not None:
                raise ValueError("DIGITAL and PROTOCOL raw signals cannot declare engineering scaling formulas")

    def _validate_working_range(self, working_range: WorkingRange) -> None:
        evidence_levels = self._evidence_levels(working_range.evidence_ids)
        if working_range.range_kind == WorkingRangeKind.OBSERVED_RANGE:
            if EvidenceLevel.OBSERVED_IN_LAS not in evidence_levels:
                raise ValueError("OBSERVED_RANGE requires at least one OBSERVED_IN_LAS evidence")
        elif EvidenceLevel.OBSERVED_IN_LAS in evidence_levels:
            raise ValueError("OBSERVED_IN_LAS evidence can only be used for OBSERVED_RANGE")

        if working_range.range_kind == WorkingRangeKind.ENGINEERING_RANGE:
            documented_unit = self._documented_variable_unit_label(working_range.variable_id)
            if documented_unit is not None and working_range.unit is not None and working_range.unit != documented_unit:
                raise ValueError("ENGINEERING_RANGE unit must match the documented engineering unit")

    def _validate_derived_variable(self, derived: DerivedVariableDefinition) -> None:
        if derived.formula_original is not None and derived.formula_normalized is not None:
            if self._normalize_formula(derived.formula_original) != derived.formula_normalized:
                raise ValueError("formula_original and formula_normalized must be consistent")
        documented_unit = self._documented_variable_unit_label(derived.variable_id)
        if documented_unit is not None and derived.output_unit is not None and derived.output_unit != documented_unit:
            raise ValueError("Derived variable output_unit must match the documented engineering unit")

    def _documented_variable_unit_label(self, variable_id: EntityId) -> str | None:
        for relation in self.repository.list_all_relations():
            if relation.relation_type != TechnicalRelationType.VARIABLE_USES_UNIT:
                continue
            if relation.source.entity_id != variable_id:
                continue
            latest = self.repository.get_latest_relation(relation.source.entity_id, relation.target.entity_id, relation.relation_type)
            if latest == relation:
                return relation.target.label
        return None

    def _evidence_levels(self, evidence_ids: tuple[EntityId, ...]) -> tuple[EvidenceLevel, ...]:
        return tuple(self.repository.get_latest_evidence(evidence_id).evidence_level for evidence_id in evidence_ids)

    def _normalize_formula(self, formula: str) -> str:
        return "".join(formula.split())

    def _has_active_relation(
        self,
        *,
        target_entity_id: EntityId,
        relation_type: TechnicalRelationType,
    ) -> bool:
        for relation in self.repository.list_all_relations():
            if relation.relation_type != relation_type:
                continue
            if relation.target.entity_id != target_entity_id:
                continue
            latest = self.repository.get_latest_relation(relation.source.entity_id, relation.target.entity_id, relation.relation_type)
            if latest == relation:
                return True
        return False
