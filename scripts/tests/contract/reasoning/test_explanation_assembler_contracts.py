from __future__ import annotations

import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.reasoning import (
    ExplanationAssembler,
    ReasoningAppliedRule,
    ReasoningExecutionPlan,
    ReasoningQueryPlanner,
    ReasoningQuestionType,
    ReasoningRequest,
    ReasoningResponse,
    StructuredAnswerStatement,
)
from drilling_knowledge.common.ids import EntityId

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class ExplanationAssemblerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion(
            "4 mA = 0 psi",
            version_seed="reasoning-assembler-contract-v1",
            status=AssertionStatus.ACCEPTED,
        )
        assertion_run = helpers._assertion_run((accepted,), run_seed="reasoning-assembler-contract")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.fact = fact_run.facts[0]
        self.assertion = fact_run.assertions[0]
        self.fragments = tuple(fragment for fragment in fact_run.evidence_links if fragment.assertion_id == self.assertion.assertion_id)
        self.request = ReasoningRequest(
            target_entity_id=self.fact.subject_id,
            question_type=ReasoningQuestionType.EVIDENCE_PROVENANCE_EXPLANATION,
            context_scope=self.fact.scope,
            requested_confidence_threshold=0.7,
        )
        self.plan = ReasoningQueryPlanner.create().build_plan(self.request)
        self.answer = StructuredAnswerStatement(
            statement_text="The evidence provenance remains traceable.",
            answer_kind="justification",
            target_entity_id=self.fact.subject_id,
        )
        self.rule = ReasoningAppliedRule(
            rule_code="reasoning.provenance_trace",
            rule_summary="Preserve provenance links.",
            rule_priority=1,
        )

    def test_public_contract_exports_explanation_assembler(self) -> None:
        assembler = ExplanationAssembler.create()
        response = assembler.assemble(
            self.plan,
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=self.fragments,
            applied_rules=(self.rule,),
            confidence=0.8,
        )

        self.assertIsInstance(self.plan, ReasoningExecutionPlan)
        self.assertIsInstance(response, ReasoningResponse)

    def test_contract_shape_is_stable(self) -> None:
        response = ExplanationAssembler.create().assemble(
            self.plan,
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=self.fragments,
            applied_rules=(self.rule,),
            confidence=0.8,
        )

        self.assertEqual(response.answer_statement.target_entity_id, self.request.target_entity_id)
        self.assertEqual(response.supporting_facts, (self.fact,))
        self.assertEqual(response.supporting_assertions, (self.assertion,))

    def test_contract_serialization_is_deterministic(self) -> None:
        assembler = ExplanationAssembler.create()
        first = assembler.assemble(
            self.plan,
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=tuple(reversed(self.fragments)),
            applied_rules=(self.rule,),
            confidence=0.8,
        )
        second = assembler.assemble(
            self.plan,
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=self.fragments,
            applied_rules=(self.rule,),
            confidence=0.8,
        )

        self.assertEqual(
            json.dumps(first.as_serializable(), sort_keys=True),
            json.dumps(second.as_serializable(), sort_keys=True),
        )

    def test_contract_rejects_plan_target_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            ExplanationAssembler.create().assemble(
                self.plan,
                answer_statement=StructuredAnswerStatement(
                    statement_text=self.answer.statement_text,
                    answer_kind=self.answer.answer_kind,
                    target_entity_id=EntityId.from_seed("reasoning.assembler.target", "other"),
                ),
                supporting_facts=(self.fact,),
                supporting_assertions=(self.assertion,),
                supporting_fragments=self.fragments,
                applied_rules=(self.rule,),
                confidence=0.8,
            )

    def test_contract_rejects_missing_fragment_coverage(self) -> None:
        with self.assertRaises(ValueError):
            ExplanationAssembler.create().assemble(
                self.plan,
                answer_statement=self.answer,
                supporting_facts=(self.fact,),
                supporting_assertions=(self.assertion,),
                supporting_fragments=self.fragments[:1],
                applied_rules=(self.rule,),
                confidence=0.8,
            )