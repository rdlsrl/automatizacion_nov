"""Deterministic reasoning query planner with static retrieval recipes."""

from __future__ import annotations

from dataclasses import dataclass
import json

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.reasoning.domain import ReasoningQuestionType, ReasoningRequest
from drilling_knowledge.reasoning.queries.domain import (
    PlanningMetrics,
    QueryPlanStage,
    ReasoningExecutionPlan,
    ReasoningPlanStep,
)


@dataclass(frozen=True, slots=True)
class _StageBlueprint:
    stage: QueryPlanStage
    required_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    fact_predicates: tuple[str, ...] = ()


class ReasoningQueryPlanner:
    def __init__(self, recipes: dict[ReasoningQuestionType, tuple[_StageBlueprint, ...]]) -> None:
        self._recipes = {question_type: tuple(recipe) for question_type, recipe in recipes.items()}

    @classmethod
    def create(cls) -> "ReasoningQueryPlanner":
        return cls(_DEFAULT_RECIPES)

    def build_plan(self, request: ReasoningRequest) -> ReasoningExecutionPlan:
        if request is None:
            raise ValueError("ReasoningQueryPlanner.build_plan request cannot be null")
        if not isinstance(request, ReasoningRequest):
            raise ValueError("ReasoningQueryPlanner.build_plan request must be a ReasoningRequest")
        blueprints = self._recipes.get(request.question_type)
        if blueprints is None:
            raise ValueError("ReasoningQueryPlanner.build_plan does not support request.question_type")
        request_signature = json.dumps(request.as_serializable(), sort_keys=True, separators=(",", ":"))
        plan_id = EntityId.from_seed("reasoning.query.plan", request_signature)
        steps = []
        for sequence, blueprint in enumerate(blueprints, start=1):
            dependency_ids = () if sequence == 1 else (steps[-1].step_id,)
            step_signature = f"{request_signature}:{sequence}:{blueprint.stage.value}"
            steps.append(
                ReasoningPlanStep(
                    step_id=EntityId.from_seed("reasoning.query.plan.step", step_signature),
                    plan_id=plan_id,
                    question_type=request.question_type,
                    stage=blueprint.stage,
                    sequence=sequence,
                    required_inputs=blueprint.required_inputs,
                    expected_outputs=blueprint.expected_outputs,
                    depends_on_step_ids=dependency_ids,
                    fact_predicates=blueprint.fact_predicates,
                )
            )
        metrics = PlanningMetrics(
            total_steps=len(steps),
            retrieval_steps=len(steps),
            max_dependency_depth=max((step.sequence - 1 for step in steps), default=0),
            question_family=request.question_type,
        )
        return ReasoningExecutionPlan(
            plan_id=plan_id,
            request=request,
            steps=tuple(steps),
            planning_metrics=metrics,
        )


_DEFAULT_RECIPES: dict[ReasoningQuestionType, tuple[_StageBlueprint, ...]] = {
    ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION: (
        _StageBlueprint(
            stage=QueryPlanStage.RESOLVE_TARGET_ENTITY,
            required_inputs=("target_entity_id", "question_type"),
            expected_outputs=("resolved_target_entity",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
            required_inputs=("context_scope", "resolved_target_entity"),
            expected_outputs=("classification_fact_refs",),
            fact_predicates=("BELONGS_TO_SUBSYSTEM", "GENERATED_BY", "LOCATED_AT", "PUBLISHED_BY", "REPRESENTS_PROCESS"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.EXPAND_FACT_NEIGHBORHOOD,
            required_inputs=("classification_fact_refs", "requested_confidence_threshold"),
            expected_outputs=("classification_fact_neighborhood",),
            fact_predicates=("BELONGS_TO_SUBSYSTEM", "GENERATED_BY", "LOCATED_AT", "PUBLISHED_BY", "REPRESENTS_PROCESS"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_SUPPORTING_ASSERTIONS,
            required_inputs=("classification_fact_neighborhood",),
            expected_outputs=("supporting_assertion_refs",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS,
            required_inputs=("supporting_assertion_refs",),
            expected_outputs=("provenance_fragment_refs",),
        ),
    ),
    ReasoningQuestionType.LINEAGE_JUSTIFICATION: (
        _StageBlueprint(
            stage=QueryPlanStage.RESOLVE_TARGET_ENTITY,
            required_inputs=("target_entity_id", "question_type"),
            expected_outputs=("resolved_target_entity",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
            required_inputs=("context_scope", "resolved_target_entity"),
            expected_outputs=("lineage_fact_refs",),
            fact_predicates=("DEPENDS_ON", "DERIVES_FROM", "GENERATED_BY", "HAS_MEASUREMENT_CHAIN", "MEASURED_BY"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.EXPAND_FACT_NEIGHBORHOOD,
            required_inputs=("lineage_fact_refs", "requested_confidence_threshold"),
            expected_outputs=("lineage_fact_neighborhood",),
            fact_predicates=("DEPENDS_ON", "DERIVES_FROM", "GENERATED_BY", "HAS_MEASUREMENT_CHAIN", "MEASURED_BY"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_SUPPORTING_ASSERTIONS,
            required_inputs=("lineage_fact_neighborhood",),
            expected_outputs=("supporting_assertion_refs",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS,
            required_inputs=("supporting_assertion_refs",),
            expected_outputs=("provenance_fragment_refs",),
        ),
    ),
    ReasoningQuestionType.PRODUCER_SOURCE_JUSTIFICATION: (
        _StageBlueprint(
            stage=QueryPlanStage.RESOLVE_TARGET_ENTITY,
            required_inputs=("target_entity_id", "question_type"),
            expected_outputs=("resolved_target_entity",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
            required_inputs=("context_scope", "resolved_target_entity"),
            expected_outputs=("producer_source_fact_refs",),
            fact_predicates=("HAS_MEASUREMENT_CHAIN", "INSTALLED_ON", "LOCATED_AT", "MEASURED_BY", "USES_SENSOR"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.EXPAND_FACT_NEIGHBORHOOD,
            required_inputs=("producer_source_fact_refs", "requested_confidence_threshold"),
            expected_outputs=("producer_source_fact_neighborhood",),
            fact_predicates=("HAS_MEASUREMENT_CHAIN", "INSTALLED_ON", "LOCATED_AT", "MEASURED_BY", "USES_SENSOR"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_SUPPORTING_ASSERTIONS,
            required_inputs=("producer_source_fact_neighborhood",),
            expected_outputs=("supporting_assertion_refs",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS,
            required_inputs=("supporting_assertion_refs",),
            expected_outputs=("provenance_fragment_refs",),
        ),
    ),
    ReasoningQuestionType.DERIVATION_JUSTIFICATION: (
        _StageBlueprint(
            stage=QueryPlanStage.RESOLVE_TARGET_ENTITY,
            required_inputs=("target_entity_id", "question_type"),
            expected_outputs=("resolved_target_entity",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
            required_inputs=("context_scope", "resolved_target_entity"),
            expected_outputs=("derivation_fact_refs",),
            fact_predicates=("DEPENDS_ON", "DERIVES_FROM", "HAS_CLASSIFICATION", "HAS_MEASUREMENT_CHAIN", "HAS_ORIGIN_CLASS"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.EXPAND_FACT_NEIGHBORHOOD,
            required_inputs=("derivation_fact_refs", "requested_confidence_threshold"),
            expected_outputs=("derivation_fact_neighborhood",),
            fact_predicates=("DEPENDS_ON", "DERIVES_FROM", "HAS_CLASSIFICATION", "HAS_MEASUREMENT_CHAIN", "HAS_ORIGIN_CLASS"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_SUPPORTING_ASSERTIONS,
            required_inputs=("derivation_fact_neighborhood",),
            expected_outputs=("supporting_assertion_refs",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS,
            required_inputs=("supporting_assertion_refs",),
            expected_outputs=("provenance_fragment_refs",),
        ),
    ),
    ReasoningQuestionType.CONFLICT_EXPLANATION: (
        _StageBlueprint(
            stage=QueryPlanStage.RESOLVE_TARGET_ENTITY,
            required_inputs=("target_entity_id", "question_type"),
            expected_outputs=("resolved_target_entity",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
            required_inputs=("context_scope", "resolved_target_entity"),
            expected_outputs=("conflict_fact_refs",),
            fact_predicates=("HAS_MEASUREMENT_CHAIN", "MEASURED_BY", "USES_SENSOR"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.EXPAND_FACT_NEIGHBORHOOD,
            required_inputs=("conflict_fact_refs", "requested_confidence_threshold"),
            expected_outputs=("conflict_fact_neighborhood",),
            fact_predicates=("HAS_MEASUREMENT_CHAIN", "MEASURED_BY", "USES_SENSOR"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_REJECTED_ALTERNATIVES,
            required_inputs=("conflict_fact_neighborhood",),
            expected_outputs=("rejected_alternative_refs",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_RULE_LOG_REFERENCES,
            required_inputs=("rejected_alternative_refs",),
            expected_outputs=("rule_log_refs",),
        ),
    ),
    ReasoningQuestionType.EVIDENCE_PROVENANCE_EXPLANATION: (
        _StageBlueprint(
            stage=QueryPlanStage.RESOLVE_TARGET_ENTITY,
            required_inputs=("target_entity_id", "question_type"),
            expected_outputs=("resolved_target_entity",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
            required_inputs=("context_scope", "resolved_target_entity"),
            expected_outputs=("provenance_fact_refs",),
            fact_predicates=("BELONGS_TO_SUBSYSTEM", "DEPENDS_ON", "DERIVES_FROM", "MEASURED_BY", "USES_SENSOR"),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_SUPPORTING_ASSERTIONS,
            required_inputs=("provenance_fact_refs",),
            expected_outputs=("supporting_assertion_refs",),
        ),
        _StageBlueprint(
            stage=QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS,
            required_inputs=("supporting_assertion_refs",),
            expected_outputs=("provenance_fragment_refs",),
        ),
    ),
}