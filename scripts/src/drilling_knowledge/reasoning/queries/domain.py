"""Immutable planning contracts for reasoning query planners."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum

from drilling_knowledge.common.ids import EntityId, Identifier
from drilling_knowledge.reasoning.domain import ReasoningQuestionType, ReasoningRequest


def _require_entity_id(field_name: str, value: object) -> EntityId:
    if value is None:
        raise ValueError(f"{field_name} cannot be null")
    if not isinstance(value, EntityId):
        raise ValueError(f"{field_name} must be an EntityId")
    if value.as_uuid().int == 0:
        raise ValueError(f"{field_name} cannot be empty")
    return value


def _require_instance[T](field_name: str, value: object, expected_type: type[T]) -> T:
    if value is None:
        raise ValueError(f"{field_name} cannot be null")
    if not isinstance(value, expected_type):
        raise ValueError(f"{field_name} must be a {expected_type.__name__}")
    return value


def _canonical_string_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if values is None:
        raise ValueError(f"{field_name} cannot be null")
    normalized_values = []
    for value in tuple(values):
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must contain only strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} cannot contain blank entries")
        normalized_values.append(normalized)
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return tuple(sorted(normalized_values))


def _canonical_entity_id_tuple(field_name: str, values: tuple[EntityId, ...]) -> tuple[EntityId, ...]:
    if values is None:
        raise ValueError(f"{field_name} cannot be null")
    normalized_values = tuple(_require_entity_id(field_name, value) for value in tuple(values))
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return tuple(sorted(normalized_values, key=str))


def _serialize_value(value: object) -> object:
    if isinstance(value, Identifier):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return value


class QueryPlanStage(StrEnum):
    RESOLVE_TARGET_ENTITY = "resolve_target_entity"
    FETCH_ACTIVE_CONSOLIDATED_FACTS = "fetch_active_consolidated_facts"
    EXPAND_FACT_NEIGHBORHOOD = "expand_fact_neighborhood"
    FETCH_SUPPORTING_ASSERTIONS = "fetch_supporting_assertions"
    FETCH_PROVENANCE_FRAGMENTS = "fetch_provenance_fragments"
    FETCH_REJECTED_ALTERNATIVES = "fetch_rejected_alternatives"
    FETCH_RULE_LOG_REFERENCES = "fetch_rule_log_references"


@dataclass(frozen=True, slots=True)
class ReasoningPlanStep:
    step_id: EntityId
    plan_id: EntityId
    question_type: ReasoningQuestionType
    stage: QueryPlanStage
    sequence: int
    required_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    depends_on_step_ids: tuple[EntityId, ...] = ()
    fact_predicates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        step_id = _require_entity_id("ReasoningPlanStep.step_id", self.step_id)
        plan_id = _require_entity_id("ReasoningPlanStep.plan_id", self.plan_id)
        question_type = self.question_type
        if question_type is None:
            raise ValueError("ReasoningPlanStep.question_type cannot be null")
        if not isinstance(question_type, ReasoningQuestionType):
            raise ValueError("ReasoningPlanStep.question_type must be a ReasoningQuestionType")
        stage = self.stage
        if stage is None:
            raise ValueError("ReasoningPlanStep.stage cannot be null")
        if not isinstance(stage, QueryPlanStage):
            raise ValueError("ReasoningPlanStep.stage must be a QueryPlanStage")
        if self.sequence < 1:
            raise ValueError("ReasoningPlanStep.sequence must be >= 1")
        required_inputs = _canonical_string_tuple("ReasoningPlanStep.required_inputs", self.required_inputs)
        expected_outputs = _canonical_string_tuple("ReasoningPlanStep.expected_outputs", self.expected_outputs)
        depends_on_step_ids = _canonical_entity_id_tuple("ReasoningPlanStep.depends_on_step_ids", self.depends_on_step_ids)
        fact_predicates = _canonical_string_tuple("ReasoningPlanStep.fact_predicates", self.fact_predicates)
        if not required_inputs:
            raise ValueError("ReasoningPlanStep.required_inputs cannot be empty")
        if not expected_outputs:
            raise ValueError("ReasoningPlanStep.expected_outputs cannot be empty")
        if step_id in depends_on_step_ids:
            raise ValueError("ReasoningPlanStep.depends_on_step_ids cannot reference step_id")
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "question_type", question_type)
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "required_inputs", required_inputs)
        object.__setattr__(self, "expected_outputs", expected_outputs)
        object.__setattr__(self, "depends_on_step_ids", depends_on_step_ids)
        object.__setattr__(self, "fact_predicates", fact_predicates)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class PlanningMetrics:
    total_steps: int
    retrieval_steps: int
    max_dependency_depth: int
    question_family: ReasoningQuestionType

    def __post_init__(self) -> None:
        question_family = self.question_family
        if question_family is None:
            raise ValueError("PlanningMetrics.question_family cannot be null")
        if not isinstance(question_family, ReasoningQuestionType):
            raise ValueError("PlanningMetrics.question_family must be a ReasoningQuestionType")
        if self.total_steps < 1:
            raise ValueError("PlanningMetrics.total_steps must be >= 1")
        if self.retrieval_steps < 1:
            raise ValueError("PlanningMetrics.retrieval_steps must be >= 1")
        if self.retrieval_steps > self.total_steps:
            raise ValueError("PlanningMetrics.retrieval_steps cannot exceed total_steps")
        if self.max_dependency_depth < 0:
            raise ValueError("PlanningMetrics.max_dependency_depth cannot be negative")
        object.__setattr__(self, "question_family", question_family)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReasoningExecutionPlan:
    plan_id: EntityId
    request: ReasoningRequest
    steps: tuple[ReasoningPlanStep, ...]
    planning_metrics: PlanningMetrics

    def __post_init__(self) -> None:
        plan_id = _require_entity_id("ReasoningExecutionPlan.plan_id", self.plan_id)
        request = _require_instance("ReasoningExecutionPlan.request", self.request, ReasoningRequest)
        planning_metrics = _require_instance("ReasoningExecutionPlan.planning_metrics", self.planning_metrics, PlanningMetrics)
        if planning_metrics.question_family != request.question_type:
            raise ValueError("ReasoningExecutionPlan.planning_metrics.question_family must match request.question_type")
        if self.steps is None:
            raise ValueError("ReasoningExecutionPlan.steps cannot be null")
        normalized_steps = tuple(sorted(tuple(self.steps), key=lambda step: (step.sequence, step.stage.value, str(step.step_id))))
        if not normalized_steps:
            raise ValueError("ReasoningExecutionPlan.steps cannot be empty")
        for step in normalized_steps:
            if not isinstance(step, ReasoningPlanStep):
                raise ValueError("ReasoningExecutionPlan.steps must contain only ReasoningPlanStep values")
        if len({step.step_id for step in normalized_steps}) != len(normalized_steps):
            raise ValueError("ReasoningExecutionPlan.steps cannot contain duplicate step ids")
        if len({step.sequence for step in normalized_steps}) != len(normalized_steps):
            raise ValueError("ReasoningExecutionPlan.steps cannot contain duplicate sequence values")
        if len({step.stage for step in normalized_steps}) != len(normalized_steps):
            raise ValueError("ReasoningExecutionPlan.steps cannot contain duplicate stages")
        expected_sequence = tuple(range(1, len(normalized_steps) + 1))
        actual_sequence = tuple(step.sequence for step in normalized_steps)
        if actual_sequence != expected_sequence:
            raise ValueError("ReasoningExecutionPlan.steps must define a contiguous sequence starting at 1")
        step_by_id = {step.step_id: step for step in normalized_steps}
        for step in normalized_steps:
            if step.plan_id != plan_id:
                raise ValueError("ReasoningExecutionPlan.steps must reference plan_id")
            if step.question_type != request.question_type:
                raise ValueError("ReasoningExecutionPlan.steps must match request.question_type")
            for dependency_id in step.depends_on_step_ids:
                dependency = step_by_id.get(dependency_id)
                if dependency is None:
                    raise ValueError("ReasoningExecutionPlan.depends_on_step_ids cannot reference missing steps")
                if dependency.sequence >= step.sequence:
                    raise ValueError("ReasoningExecutionPlan.depends_on_step_ids must reference earlier steps")
        if self._has_cycle(normalized_steps):
            raise ValueError("ReasoningExecutionPlan.steps cannot contain circular dependencies")
        max_dependency_depth = self._max_dependency_depth(normalized_steps)
        if planning_metrics.total_steps != len(normalized_steps):
            raise ValueError("ReasoningExecutionPlan.planning_metrics.total_steps must match steps")
        if planning_metrics.retrieval_steps != len(normalized_steps):
            raise ValueError("ReasoningExecutionPlan.planning_metrics.retrieval_steps must match steps")
        if planning_metrics.max_dependency_depth != max_dependency_depth:
            raise ValueError("ReasoningExecutionPlan.planning_metrics.max_dependency_depth must match steps")
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "steps", normalized_steps)
        object.__setattr__(self, "planning_metrics", planning_metrics)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)

    @staticmethod
    def _has_cycle(steps: tuple[ReasoningPlanStep, ...]) -> bool:
        graph = {step.step_id: step.depends_on_step_ids for step in steps}
        visiting: set[EntityId] = set()
        visited: set[EntityId] = set()

        def visit(step_id: EntityId) -> bool:
            if step_id in visited:
                return False
            if step_id in visiting:
                return True
            visiting.add(step_id)
            for dependency_id in graph[step_id]:
                if visit(dependency_id):
                    return True
            visiting.remove(step_id)
            visited.add(step_id)
            return False

        return any(visit(step.step_id) for step in steps)

    @staticmethod
    def _max_dependency_depth(steps: tuple[ReasoningPlanStep, ...]) -> int:
        graph = {step.step_id: step.depends_on_step_ids for step in steps}
        cache: dict[EntityId, int] = {}

        def depth(step_id: EntityId) -> int:
            if step_id in cache:
                return cache[step_id]
            dependencies = graph[step_id]
            if not dependencies:
                cache[step_id] = 0
                return 0
            cache[step_id] = 1 + max(depth(dependency_id) for dependency_id in dependencies)
            return cache[step_id]

        return max(depth(step.step_id) for step in steps)