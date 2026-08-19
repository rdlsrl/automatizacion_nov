"""Repository contracts for technical knowledge records."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.technical_knowledge.domain import (
    DerivedVariableDefinition,
    RawSignal,
    TechnicalEvidence,
    TechnicalRelation,
    TechnicalRelationType,
    TechnicalVariable,
    TechnicalSensor,
    WorkingRange,
    WorkingRangeKind,
)


class TechnicalKnowledgeRepository(Protocol):
    def get_latest_evidence(self, evidence_id: EntityId) -> TechnicalEvidence | None:
        ...

    def list_evidence_history(self, evidence_id: EntityId) -> tuple[TechnicalEvidence, ...]:
        ...

    def list_all_evidences(self) -> tuple[TechnicalEvidence, ...]:
        ...

    def append_evidence(self, evidence: TechnicalEvidence) -> "TechnicalKnowledgeRepository":
        ...

    def get_latest_variable(self, variable_id: EntityId) -> TechnicalVariable | None:
        ...

    def list_variable_history(self, variable_id: EntityId) -> tuple[TechnicalVariable, ...]:
        ...

    def list_all_variables(self) -> tuple[TechnicalVariable, ...]:
        ...

    def append_variable(self, variable: TechnicalVariable) -> "TechnicalKnowledgeRepository":
        ...

    def get_latest_sensor(self, sensor_id: EntityId) -> TechnicalSensor | None:
        ...

    def list_sensor_history(self, sensor_id: EntityId) -> tuple[TechnicalSensor, ...]:
        ...

    def list_all_sensors(self) -> tuple[TechnicalSensor, ...]:
        ...

    def append_sensor(self, sensor: TechnicalSensor) -> "TechnicalKnowledgeRepository":
        ...

    def get_latest_raw_signal(self, raw_signal_id: EntityId) -> RawSignal | None:
        ...

    def list_raw_signal_history(self, raw_signal_id: EntityId) -> tuple[RawSignal, ...]:
        ...

    def list_all_raw_signals(self) -> tuple[RawSignal, ...]:
        ...

    def append_raw_signal(self, raw_signal: RawSignal) -> "TechnicalKnowledgeRepository":
        ...

    def get_latest_working_range(self, variable_id: EntityId, range_kind: WorkingRangeKind) -> WorkingRange | None:
        ...

    def list_working_range_history(self, variable_id: EntityId, range_kind: WorkingRangeKind) -> tuple[WorkingRange, ...]:
        ...

    def list_all_working_ranges(self) -> tuple[WorkingRange, ...]:
        ...

    def append_working_range(self, working_range: WorkingRange) -> "TechnicalKnowledgeRepository":
        ...

    def get_latest_derived_variable(self, variable_id: EntityId) -> DerivedVariableDefinition | None:
        ...

    def list_derived_variable_history(self, variable_id: EntityId) -> tuple[DerivedVariableDefinition, ...]:
        ...

    def list_all_derived_variables(self) -> tuple[DerivedVariableDefinition, ...]:
        ...

    def append_derived_variable(self, derived_variable: DerivedVariableDefinition) -> "TechnicalKnowledgeRepository":
        ...

    def get_latest_relation(self, source_id: EntityId, target_id: EntityId, relation_type: TechnicalRelationType) -> TechnicalRelation | None:
        ...

    def list_relation_history(self, source_id: EntityId, target_id: EntityId, relation_type: TechnicalRelationType) -> tuple[TechnicalRelation, ...]:
        ...

    def list_all_relations(self) -> tuple[TechnicalRelation, ...]:
        ...

    def append_relation(self, relation: TechnicalRelation) -> "TechnicalKnowledgeRepository":
        ...
