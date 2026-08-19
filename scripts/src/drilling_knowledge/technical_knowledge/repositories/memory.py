"""In-memory append-only repository for technical knowledge records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.technical_knowledge.domain import (
    DerivedVariableDefinition,
    RawSignal,
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
class InMemoryTechnicalKnowledgeRepository(TechnicalKnowledgeRepository):
    evidences: tuple[TechnicalEvidence, ...] | Iterable[TechnicalEvidence] = ()
    variables: tuple[TechnicalVariable, ...] | Iterable[TechnicalVariable] = ()
    sensors: tuple[TechnicalSensor, ...] | Iterable[TechnicalSensor] = ()
    raw_signals: tuple[RawSignal, ...] | Iterable[RawSignal] = ()
    working_ranges: tuple[WorkingRange, ...] | Iterable[WorkingRange] = ()
    derived_variables: tuple[DerivedVariableDefinition, ...] | Iterable[DerivedVariableDefinition] = ()
    relations: tuple[TechnicalRelation, ...] | Iterable[TechnicalRelation] = ()
    _evidence_history: dict[EntityId, tuple[TechnicalEvidence, ...]] = field(init=False, default_factory=dict)
    _variable_history: dict[EntityId, tuple[TechnicalVariable, ...]] = field(init=False, default_factory=dict)
    _sensor_history: dict[EntityId, tuple[TechnicalSensor, ...]] = field(init=False, default_factory=dict)
    _raw_signal_history: dict[EntityId, tuple[RawSignal, ...]] = field(init=False, default_factory=dict)
    _working_range_history: dict[tuple[EntityId, WorkingRangeKind], tuple[WorkingRange, ...]] = field(init=False, default_factory=dict)
    _derived_variable_history: dict[EntityId, tuple[DerivedVariableDefinition, ...]] = field(init=False, default_factory=dict)
    _relation_history: dict[tuple[EntityId, EntityId, TechnicalRelationType], tuple[TechnicalRelation, ...]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        evidences = tuple(sorted(tuple(self.evidences), key=lambda item: (str(item.evidence_id), item.revision, item.created_at.isoformat())))
        variables = tuple(sorted(tuple(self.variables), key=lambda item: (str(item.variable_id), item.revision, item.canonical_name.casefold())))
        sensors = tuple(sorted(tuple(self.sensors), key=lambda item: (str(item.sensor_id), item.revision, item.sensor_type.casefold())))
        raw_signals = tuple(sorted(tuple(self.raw_signals), key=lambda item: (str(item.raw_signal_id), item.revision, item.raw_signal_type.value)))
        working_ranges = tuple(sorted(tuple(self.working_ranges), key=lambda item: (str(item.variable_id), item.range_kind.value, item.revision)))
        derived_variables = tuple(sorted(tuple(self.derived_variables), key=lambda item: (str(item.variable_id), item.revision, item.derivation_type.casefold())))
        relations = tuple(sorted(tuple(self.relations), key=lambda item: (str(item.source.entity_id), str(item.target.entity_id), item.relation_type.value, item.revision, item.created_at.isoformat(), str(item.relation_id))))

        object.__setattr__(self, "evidences", evidences)
        object.__setattr__(self, "variables", variables)
        object.__setattr__(self, "sensors", sensors)
        object.__setattr__(self, "raw_signals", raw_signals)
        object.__setattr__(self, "working_ranges", working_ranges)
        object.__setattr__(self, "derived_variables", derived_variables)
        object.__setattr__(self, "relations", relations)
        object.__setattr__(self, "_evidence_history", self._build_history(evidences, lambda item: item.evidence_id, lambda item: item.revision, "evidence"))
        object.__setattr__(self, "_variable_history", self._build_history(variables, lambda item: item.variable_id, lambda item: item.revision, "variable"))
        object.__setattr__(self, "_sensor_history", self._build_history(sensors, lambda item: item.sensor_id, lambda item: item.revision, "sensor"))
        object.__setattr__(self, "_raw_signal_history", self._build_history(raw_signals, lambda item: item.raw_signal_id, lambda item: item.revision, "raw_signal"))
        object.__setattr__(self, "_working_range_history", self._build_history(working_ranges, lambda item: (item.variable_id, item.range_kind), lambda item: item.revision, "working_range"))
        object.__setattr__(self, "_derived_variable_history", self._build_history(derived_variables, lambda item: item.variable_id, lambda item: item.revision, "derived_variable"))
        object.__setattr__(self, "_relation_history", self._build_history(relations, lambda item: (item.source.entity_id, item.target.entity_id, item.relation_type), lambda item: item.revision, "relation"))

    @classmethod
    def empty(cls) -> "InMemoryTechnicalKnowledgeRepository":
        return cls()

    def get_latest_evidence(self, evidence_id: EntityId) -> TechnicalEvidence | None:
        history = self.list_evidence_history(evidence_id)
        return history[-1] if history else None

    def list_evidence_history(self, evidence_id: EntityId) -> tuple[TechnicalEvidence, ...]:
        return self._evidence_history.get(evidence_id, ())

    def list_all_evidences(self) -> tuple[TechnicalEvidence, ...]:
        return self.evidences

    def append_evidence(self, evidence: TechnicalEvidence) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences + (evidence,),
            variables=self.variables,
            sensors=self.sensors,
            raw_signals=self.raw_signals,
            working_ranges=self.working_ranges,
            derived_variables=self.derived_variables,
            relations=self.relations,
        )

    def get_latest_variable(self, variable_id: EntityId) -> TechnicalVariable | None:
        history = self.list_variable_history(variable_id)
        return history[-1] if history else None

    def list_variable_history(self, variable_id: EntityId) -> tuple[TechnicalVariable, ...]:
        return self._variable_history.get(variable_id, ())

    def list_all_variables(self) -> tuple[TechnicalVariable, ...]:
        return self.variables

    def append_variable(self, variable: TechnicalVariable) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences,
            variables=self.variables + (variable,),
            sensors=self.sensors,
            raw_signals=self.raw_signals,
            working_ranges=self.working_ranges,
            derived_variables=self.derived_variables,
            relations=self.relations,
        )

    def get_latest_sensor(self, sensor_id: EntityId) -> TechnicalSensor | None:
        history = self.list_sensor_history(sensor_id)
        return history[-1] if history else None

    def list_sensor_history(self, sensor_id: EntityId) -> tuple[TechnicalSensor, ...]:
        return self._sensor_history.get(sensor_id, ())

    def list_all_sensors(self) -> tuple[TechnicalSensor, ...]:
        return self.sensors

    def append_sensor(self, sensor: TechnicalSensor) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences,
            variables=self.variables,
            sensors=self.sensors + (sensor,),
            raw_signals=self.raw_signals,
            working_ranges=self.working_ranges,
            derived_variables=self.derived_variables,
            relations=self.relations,
        )

    def get_latest_raw_signal(self, raw_signal_id: EntityId) -> RawSignal | None:
        history = self.list_raw_signal_history(raw_signal_id)
        return history[-1] if history else None

    def list_raw_signal_history(self, raw_signal_id: EntityId) -> tuple[RawSignal, ...]:
        return self._raw_signal_history.get(raw_signal_id, ())

    def list_all_raw_signals(self) -> tuple[RawSignal, ...]:
        return self.raw_signals

    def append_raw_signal(self, raw_signal: RawSignal) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences,
            variables=self.variables,
            sensors=self.sensors,
            raw_signals=self.raw_signals + (raw_signal,),
            working_ranges=self.working_ranges,
            derived_variables=self.derived_variables,
            relations=self.relations,
        )

    def get_latest_working_range(self, variable_id: EntityId, range_kind: WorkingRangeKind) -> WorkingRange | None:
        history = self.list_working_range_history(variable_id, range_kind)
        return history[-1] if history else None

    def list_working_range_history(self, variable_id: EntityId, range_kind: WorkingRangeKind) -> tuple[WorkingRange, ...]:
        return self._working_range_history.get((variable_id, range_kind), ())

    def list_all_working_ranges(self) -> tuple[WorkingRange, ...]:
        return self.working_ranges

    def append_working_range(self, working_range: WorkingRange) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences,
            variables=self.variables,
            sensors=self.sensors,
            raw_signals=self.raw_signals,
            working_ranges=self.working_ranges + (working_range,),
            derived_variables=self.derived_variables,
            relations=self.relations,
        )

    def get_latest_derived_variable(self, variable_id: EntityId) -> DerivedVariableDefinition | None:
        history = self.list_derived_variable_history(variable_id)
        return history[-1] if history else None

    def list_derived_variable_history(self, variable_id: EntityId) -> tuple[DerivedVariableDefinition, ...]:
        return self._derived_variable_history.get(variable_id, ())

    def list_all_derived_variables(self) -> tuple[DerivedVariableDefinition, ...]:
        return self.derived_variables

    def append_derived_variable(self, derived_variable: DerivedVariableDefinition) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences,
            variables=self.variables,
            sensors=self.sensors,
            raw_signals=self.raw_signals,
            working_ranges=self.working_ranges,
            derived_variables=self.derived_variables + (derived_variable,),
            relations=self.relations,
        )

    def get_latest_relation(self, source_id: EntityId, target_id: EntityId, relation_type: TechnicalRelationType) -> TechnicalRelation | None:
        history = self.list_relation_history(source_id, target_id, relation_type)
        return history[-1] if history else None

    def list_relation_history(self, source_id: EntityId, target_id: EntityId, relation_type: TechnicalRelationType) -> tuple[TechnicalRelation, ...]:
        return self._relation_history.get((source_id, target_id, relation_type), ())

    def list_all_relations(self) -> tuple[TechnicalRelation, ...]:
        return self.relations

    def append_relation(self, relation: TechnicalRelation) -> "InMemoryTechnicalKnowledgeRepository":
        return InMemoryTechnicalKnowledgeRepository(
            evidences=self.evidences,
            variables=self.variables,
            sensors=self.sensors,
            raw_signals=self.raw_signals,
            working_ranges=self.working_ranges,
            derived_variables=self.derived_variables,
            relations=self.relations + (relation,),
        )

    def _build_history(self, items: tuple[object, ...], key_fn, revision_fn, label: str):
        history: dict[object, list[object]] = defaultdict(list)
        seen_identity: set[tuple[object, int]] = set()
        for item in items:
            key = key_fn(item)
            revision = revision_fn(item)
            identity = (key, revision)
            if identity in seen_identity:
                raise ValueError(f"Duplicate technical_knowledge {label} revision detected")
            seen_identity.add(identity)
            history[key].append(item)
        for key, revisions in history.items():
            actual = tuple(revision_fn(item) for item in revisions)
            expected = tuple(range(1, len(revisions) + 1))
            if actual != expected:
                raise ValueError(f"Technical knowledge {label} history must be contiguous for {key}: expected {expected}, got {actual}")
        return {key: tuple(values) for key, values in history.items()}
