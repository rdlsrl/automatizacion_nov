from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.reasoning import (
    PlanningMetrics,
    QueryPlanStage,
    ReasoningExecutionPlan,
    ReasoningPlanStep,
    ReasoningQueryPlanner,
    ReasoningQuestionType,
    ReasoningRequest,
)


class ReasoningQueryPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = ReasoningQueryPlanner.create()
        self.request = ReasoningRequest(
            target_entity_id=EntityId.from_seed("reasoning.planner.target", "pressure"),
            question_type=ReasoningQuestionType.PRODUCER_SOURCE_JUSTIFICATION,
            context_scope="well-a",
            requested_confidence_threshold=0.8,
        )

    def test_valid_planning_builds_deterministic_execution_plan(self) -> None:
        plan = self.planner.build_plan(self.request)

        self.assertEqual(plan.request, self.request)
        self.assertEqual(plan.planning_metrics.total_steps, 5)
        self.assertEqual(
            tuple(step.stage for step in plan.steps),
            (
                QueryPlanStage.RESOLVE_TARGET_ENTITY,
                QueryPlanStage.FETCH_ACTIVE_CONSOLIDATED_FACTS,
                QueryPlanStage.EXPAND_FACT_NEIGHBORHOOD,
                QueryPlanStage.FETCH_SUPPORTING_ASSERTIONS,
                QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS,
            ),
        )

    def test_request_invalid_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.planner.build_plan(None)

    def test_order_is_deterministic_for_same_request(self) -> None:
        first_plan = self.planner.build_plan(self.request)
        second_plan = self.planner.build_plan(self.request)

        self.assertEqual(first_plan, second_plan)
        self.assertEqual(first_plan.plan_id, second_plan.plan_id)

    def test_plan_equality_is_independent_of_input_step_order(self) -> None:
        plan = self.planner.build_plan(self.request)
        rebuilt = ReasoningExecutionPlan(
            plan_id=plan.plan_id,
            request=plan.request,
            steps=tuple(reversed(plan.steps)),
            planning_metrics=plan.planning_metrics,
        )

        self.assertEqual(rebuilt, plan)

    def test_serialization_is_stable(self) -> None:
        plan = self.planner.build_plan(self.request)

        self.assertEqual(plan.as_serializable(), plan.as_serializable())
        self.assertEqual(
            json.dumps(plan.as_serializable(), sort_keys=True),
            json.dumps(self.planner.build_plan(self.request).as_serializable(), sort_keys=True),
        )

    def test_duplicate_steps_are_rejected(self) -> None:
        plan = self.planner.build_plan(self.request)

        with self.assertRaises(ValueError):
            ReasoningExecutionPlan(
                plan_id=plan.plan_id,
                request=plan.request,
                steps=(plan.steps[0], plan.steps[0]),
                planning_metrics=replace(plan.planning_metrics, total_steps=2, retrieval_steps=2, max_dependency_depth=0),
            )

    def test_invalid_dependencies_are_rejected(self) -> None:
        plan = self.planner.build_plan(self.request)
        missing_dependency = EntityId.from_seed("reasoning.planner.step", "missing")
        invalid_step = replace(plan.steps[1], depends_on_step_ids=(missing_dependency,))
        invalid_metrics = PlanningMetrics(
            total_steps=len(plan.steps),
            retrieval_steps=len(plan.steps),
            max_dependency_depth=1,
            question_family=plan.request.question_type,
        )

        with self.assertRaises(ValueError):
            ReasoningExecutionPlan(
                plan_id=plan.plan_id,
                request=plan.request,
                steps=(plan.steps[0], invalid_step, *plan.steps[2:]),
                planning_metrics=invalid_metrics,
            )

    def test_empty_plan_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningExecutionPlan(
                plan_id=EntityId.from_seed("reasoning.planner.plan", "empty"),
                request=self.request,
                steps=(),
                planning_metrics=PlanningMetrics(
                    total_steps=1,
                    retrieval_steps=1,
                    max_dependency_depth=0,
                    question_family=self.request.question_type,
                ),
            )

    def test_idempotence_preserves_same_serialized_plan(self) -> None:
        first_plan = self.planner.build_plan(self.request)
        second_plan = self.planner.build_plan(replace(self.request, context_scope="  well-a  "))

        self.assertEqual(first_plan, second_plan)
        self.assertEqual(first_plan.as_serializable(), second_plan.as_serializable())

    def test_inmutability_is_enforced(self) -> None:
        plan = self.planner.build_plan(self.request)

        with self.assertRaises(FrozenInstanceError):
            plan.steps = ()

    def test_plan_rejects_request_incompatible_steps(self) -> None:
        plan = self.planner.build_plan(self.request)
        incompatible_step = replace(plan.steps[0], question_type=ReasoningQuestionType.CONFLICT_EXPLANATION)
        invalid_metrics = PlanningMetrics(
            total_steps=len(plan.steps),
            retrieval_steps=len(plan.steps),
            max_dependency_depth=4,
            question_family=plan.request.question_type,
        )

        with self.assertRaises(ValueError):
            ReasoningExecutionPlan(
                plan_id=plan.plan_id,
                request=plan.request,
                steps=(incompatible_step, *plan.steps[1:]),
                planning_metrics=invalid_metrics,
            )

    def test_conflict_question_uses_rejection_and_rule_log_stages(self) -> None:
        request = ReasoningRequest(
            target_entity_id=EntityId.from_seed("reasoning.planner.target", "conflict"),
            question_type=ReasoningQuestionType.CONFLICT_EXPLANATION,
        )
        plan = self.planner.build_plan(request)

        self.assertEqual(
            tuple(step.stage for step in plan.steps[-2:]),
            (
                QueryPlanStage.FETCH_REJECTED_ALTERNATIVES,
                QueryPlanStage.FETCH_RULE_LOG_REFERENCES,
            ),
        )