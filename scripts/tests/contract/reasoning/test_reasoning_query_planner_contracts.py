from __future__ import annotations

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


class ReasoningQueryPlannerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = ReasoningRequest(
            target_entity_id=EntityId.from_seed("reasoning.planner.contract.target", "lineage"),
            question_type=ReasoningQuestionType.LINEAGE_JUSTIFICATION,
            context_scope="well-b",
            requested_confidence_threshold=0.6,
        )

    def test_public_contract_exports_plan_and_planner(self) -> None:
        planner = ReasoningQueryPlanner.create()
        plan = planner.build_plan(self.request)

        self.assertIsInstance(plan, ReasoningExecutionPlan)
        self.assertIsInstance(plan.planning_metrics, PlanningMetrics)
        self.assertTrue(all(isinstance(step, ReasoningPlanStep) for step in plan.steps))

    def test_contract_plan_shape_is_stable(self) -> None:
        planner = ReasoningQueryPlanner.create()
        plan = planner.build_plan(self.request)

        self.assertEqual(plan.request.question_type, ReasoningQuestionType.LINEAGE_JUSTIFICATION)
        self.assertEqual(plan.steps[0].stage, QueryPlanStage.RESOLVE_TARGET_ENTITY)
        self.assertEqual(plan.steps[-1].stage, QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS)
        self.assertEqual(plan.planning_metrics.total_steps, len(plan.steps))

    def test_contract_serialization_is_deterministic(self) -> None:
        planner = ReasoningQueryPlanner.create()
        plan = planner.build_plan(self.request)
        equivalent = ReasoningExecutionPlan(
            plan_id=plan.plan_id,
            request=plan.request,
            steps=tuple(reversed(plan.steps)),
            planning_metrics=plan.planning_metrics,
        )

        self.assertEqual(
            json.dumps(plan.as_serializable(), sort_keys=True),
            json.dumps(equivalent.as_serializable(), sort_keys=True),
        )

    def test_contract_rejects_circular_dependency(self) -> None:
        planner = ReasoningQueryPlanner.create()
        plan = planner.build_plan(self.request)
        first_step = plan.steps[0]
        second_step = plan.steps[1]
        invalid_first = ReasoningPlanStep(
            step_id=first_step.step_id,
            plan_id=first_step.plan_id,
            question_type=first_step.question_type,
            stage=first_step.stage,
            sequence=first_step.sequence,
            required_inputs=first_step.required_inputs,
            expected_outputs=first_step.expected_outputs,
            depends_on_step_ids=(second_step.step_id,),
            fact_predicates=first_step.fact_predicates,
        )

        with self.assertRaises(ValueError):
            ReasoningExecutionPlan(
                plan_id=plan.plan_id,
                request=plan.request,
                steps=(invalid_first, *plan.steps[1:]),
                planning_metrics=PlanningMetrics(
                    total_steps=len(plan.steps),
                    retrieval_steps=len(plan.steps),
                    max_dependency_depth=4,
                    question_family=plan.request.question_type,
                ),
            )

    def test_contract_rejects_non_contiguous_order(self) -> None:
        planner = ReasoningQueryPlanner.create()
        plan = planner.build_plan(self.request)
        invalid_step = ReasoningPlanStep(
            step_id=plan.steps[-1].step_id,
            plan_id=plan.steps[-1].plan_id,
            question_type=plan.steps[-1].question_type,
            stage=plan.steps[-1].stage,
            sequence=99,
            required_inputs=plan.steps[-1].required_inputs,
            expected_outputs=plan.steps[-1].expected_outputs,
            depends_on_step_ids=plan.steps[-1].depends_on_step_ids,
            fact_predicates=plan.steps[-1].fact_predicates,
        )

        with self.assertRaises(ValueError):
            ReasoningExecutionPlan(
                plan_id=plan.plan_id,
                request=plan.request,
                steps=(*plan.steps[:-1], invalid_step),
                planning_metrics=PlanningMetrics(
                    total_steps=len(plan.steps),
                    retrieval_steps=len(plan.steps),
                    max_dependency_depth=4,
                    question_family=plan.request.question_type,
                ),
            )