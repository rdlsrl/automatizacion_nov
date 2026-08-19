from __future__ import annotations

import json
import unittest
from uuid import UUID

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.reasoning import (
    ExplanationObject,
    ReasoningAppliedRule,
    ReasoningQuestionType,
    ReasoningRejectedAlternative,
    ReasoningRequest,
    ReasoningResponse,
    StructuredAnswerStatement,
    UnresolvedGap,
)
from drilling_knowledge.common.ids import EntityId

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class ReasoningQueryContractShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="reasoning-contract-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="reasoning-contract-shape")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.fact = fact_run.facts[0]
        self.assertion = fact_run.assertions[0]
        self.fragment = fact_run.evidence_links[0]

    def test_request_contract_rejects_invalid_public_values(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=EntityId(UUID(int=0)),
                question_type=ReasoningQuestionType.EVIDENCE_PROVENANCE_EXPLANATION,
            )

        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=self.fact.subject_id,
                question_type="invalid",
            )

    def test_contract_contains_facts_assertions_fragments_rules_and_rejected_alternatives(self) -> None:
        answer = StructuredAnswerStatement(
            statement_text="Reasoning answer",
            answer_kind="justification",
            target_entity_id=self.fact.subject_id,
        )
        rule = ReasoningAppliedRule(rule_code="reasoning.rule", rule_summary="Rule summary", rule_priority=1)
        alternative = ReasoningRejectedAlternative(
            alternative_id=EntityId.from_seed("reasoning.contract.alt", "1"),
            reason_code="discarded",
            detail="Discarded alternative.",
        )
        gap = UnresolvedGap(gap_code="gap", detail="Gap detail")
        explanation = ExplanationObject(
            answer_statement=answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(rule,),
            rejected_alternatives=(alternative,),
            unresolved_gaps=(gap,),
        )
        response = ReasoningResponse(
            answer_statement=answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(rule,),
            rejected_alternatives=(alternative,),
            confidence=0.75,
            unresolved_gaps=(gap,),
            explanation=explanation,
        )
        request = ReasoningRequest(
            target_entity_id=self.fact.subject_id,
            question_type=ReasoningQuestionType.EVIDENCE_PROVENANCE_EXPLANATION,
            context_scope=self.fact.scope,
            requested_confidence_threshold=0.5,
        )

        self.assertEqual(request.question_type, ReasoningQuestionType.EVIDENCE_PROVENANCE_EXPLANATION)
        self.assertEqual(response.supporting_facts, (self.fact,))
        self.assertEqual(response.supporting_assertions, (self.assertion,))
        self.assertEqual(response.supporting_fragments, (self.fragment,))
        self.assertEqual(response.applied_rules, (rule,))
        self.assertEqual(response.rejected_alternatives, (alternative,))

    def test_contract_serialization_is_stable_and_order_independent(self) -> None:
        answer = StructuredAnswerStatement(
            statement_text="Reasoning answer",
            answer_kind="justification",
            target_entity_id=self.fact.subject_id,
        )
        first_rule = ReasoningAppliedRule(rule_code="reasoning.rule.a", rule_summary="Rule A", rule_priority=5)
        second_rule = ReasoningAppliedRule(rule_code="reasoning.rule.b", rule_summary="Rule B", rule_priority=2)
        first_gap = UnresolvedGap(gap_code="a_gap", detail="Gap A")
        second_gap = UnresolvedGap(gap_code="b_gap", detail="Gap B")
        alternative = ReasoningRejectedAlternative(
            alternative_id=EntityId.from_seed("reasoning.contract.alt", "stable"),
            reason_code="discarded",
            detail="Discarded alternative.",
        )
        explanation = ExplanationObject(
            answer_statement=answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(first_rule, second_rule),
            rejected_alternatives=(alternative,),
            unresolved_gaps=(second_gap, first_gap),
        )
        response = ReasoningResponse(
            answer_statement=answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(second_rule, first_rule),
            rejected_alternatives=(alternative,),
            confidence=0.75,
            unresolved_gaps=(first_gap, second_gap),
            explanation=explanation,
        )
        equivalent_response = ReasoningResponse(
            answer_statement=answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(first_rule, second_rule),
            rejected_alternatives=(alternative,),
            confidence=0.75,
            unresolved_gaps=(second_gap, first_gap),
            explanation=explanation,
        )

        self.assertEqual(response.applied_rules, (second_rule, first_rule))
        self.assertEqual(explanation.unresolved_gaps, (first_gap, second_gap))
        self.assertEqual(response.as_serializable(), response.as_serializable())
        self.assertEqual(
            json.dumps(response.as_serializable(), sort_keys=True),
            json.dumps(equivalent_response.as_serializable(), sort_keys=True),
        )