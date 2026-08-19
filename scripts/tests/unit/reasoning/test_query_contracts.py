from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
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


class ReasoningQueryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        accepted = self.helpers._assertion("4 mA = 0 psi", version_seed="reasoning-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self.helpers._assertion_run((accepted,), run_seed="reasoning-contract")
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.fact = fact_run.facts[0]
        self.assertion = fact_run.assertions[0]
        self.fragment = fact_run.evidence_links[0]
        self.answer = StructuredAnswerStatement(
            statement_text="Standpipe pressure is justified by explicit scaling evidence.",
            answer_kind="justification",
            target_entity_id=self.fact.subject_id,
        )
        self.rule = ReasoningAppliedRule(rule_code="reasoning.explicit_scaling", rule_summary="Uses explicit scaling fact.", rule_priority=10)
        self.alt = ReasoningRejectedAlternative(
            alternative_id=EntityId.from_seed("reasoning.alternative", "other-sensor"),
            reason_code="lower_ranked",
            detail="Alternative sensor path ranked lower.",
        )
        self.gap = UnresolvedGap(gap_code="missing_context_scope", detail="No contextual scope was provided.")
        self.secondary_rule = ReasoningAppliedRule(
            rule_code="reasoning.secondary",
            rule_summary="Secondary rule.",
            rule_priority=20,
        )
        self.secondary_gap = UnresolvedGap(gap_code="pending_review", detail="Pending expert review.")

    def test_request_accepts_official_inputs(self) -> None:
        request = ReasoningRequest(
            target_entity_id=self.fact.subject_id,
            question_type=ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION,
            context_scope=self.fact.scope,
            requested_confidence_threshold=0.8,
        )

        self.assertEqual(request.target_entity_id, self.fact.subject_id)
        self.assertEqual(request.question_type, ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION)
        self.assertEqual(request.context_scope, self.fact.scope)
        self.assertEqual(request.requested_confidence_threshold, 0.8)

    def test_request_rejects_null_target_entity_id(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=None,
                question_type=ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION,
            )

    def test_request_rejects_empty_target_entity_id(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=EntityId(UUID(int=0)),
                question_type=ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION,
            )

    def test_request_rejects_invalid_question_type(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=self.fact.subject_id,
                question_type="classification_justification",
            )

    def test_request_rejects_blank_context_scope(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=self.fact.subject_id,
                question_type=ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION,
                context_scope="   ",
            )

    def test_request_rejects_invalid_threshold(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningRequest(
                target_entity_id=self.fact.subject_id,
                question_type=ReasoningQuestionType.LINEAGE_JUSTIFICATION,
                requested_confidence_threshold=1.2,
            )

    def test_explanation_preserves_required_outputs(self) -> None:
        explanation = self._explanation()

        self.assertEqual(explanation.answer_statement, self.answer)
        self.assertEqual(explanation.supporting_facts, (self.fact,))
        self.assertEqual(explanation.supporting_assertions, (self.assertion,))
        self.assertEqual(explanation.supporting_fragments, (self.fragment,))
        self.assertEqual(explanation.applied_rules, (self.rule,))
        self.assertEqual(explanation.rejected_alternatives, (self.alt,))
        self.assertEqual(explanation.unresolved_gaps, (self.gap,))

    def test_explanation_rejects_null_references(self) -> None:
        with self.assertRaises(ValueError):
            ExplanationObject(
                answer_statement=None,
                supporting_facts=(self.fact,),
                supporting_assertions=(self.assertion,),
                supporting_fragments=(self.fragment,),
                applied_rules=(self.rule,),
                rejected_alternatives=(self.alt,),
            )

    def test_explanation_requires_fact_assertion_fragment_alignment(self) -> None:
        with self.assertRaises(ValueError):
            ExplanationObject(
                answer_statement=self.answer,
                supporting_facts=(replace(self.fact, subject_id=EntityId.from_seed("reasoning.fact", "other-target")),),
                supporting_assertions=(self.assertion,),
                supporting_fragments=(self.fragment,),
                applied_rules=(self.rule,),
                rejected_alternatives=(self.alt,),
            )

    def test_response_requires_explanation_consistency(self) -> None:
        explanation = self._explanation()

        with self.assertRaises(ValueError):
            ReasoningResponse(
                answer_statement=self.answer,
                supporting_facts=(self.fact,),
                supporting_assertions=(self.assertion,),
                supporting_fragments=(self.fragment,),
                applied_rules=(self.rule,),
                rejected_alternatives=(self.alt,),
                confidence=0.9,
                unresolved_gaps=(self.gap,),
                explanation=replace(explanation, unresolved_gaps=()),
            )

    def test_response_rejects_invalid_confidence(self) -> None:
        explanation = self._explanation()

        with self.assertRaises(ValueError):
            ReasoningResponse(
                answer_statement=self.answer,
                supporting_facts=(self.fact,),
                supporting_assertions=(self.assertion,),
                supporting_fragments=(self.fragment,),
                applied_rules=(self.rule,),
                rejected_alternatives=(self.alt,),
                confidence=1.1,
                unresolved_gaps=(self.gap,),
                explanation=explanation,
            )

    def test_response_rejects_null_references(self) -> None:
        explanation = self._explanation()

        with self.assertRaises(ValueError):
            ReasoningResponse(
                answer_statement=None,
                supporting_facts=(self.fact,),
                supporting_assertions=(self.assertion,),
                supporting_fragments=(self.fragment,),
                applied_rules=(self.rule,),
                rejected_alternatives=(self.alt,),
                confidence=0.9,
                unresolved_gaps=(self.gap,),
                explanation=explanation,
            )

    def test_response_accepts_official_outputs(self) -> None:
        explanation = self._explanation()
        response = ReasoningResponse(
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(self.rule,),
            rejected_alternatives=(self.alt,),
            confidence=0.9,
            unresolved_gaps=(self.gap,),
            explanation=explanation,
        )

        self.assertEqual(response.explanation, explanation)
        self.assertEqual(response.confidence, 0.9)

    def test_inmutability_is_enforced(self) -> None:
        request = ReasoningRequest(
            target_entity_id=self.fact.subject_id,
            question_type=ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION,
        )

        with self.assertRaises(FrozenInstanceError):
            request.context_scope = self.fact.scope

    def test_explanation_canonicalizes_order_for_deterministic_equality(self) -> None:
        first_fact, second_fact, first_assertion, second_assertion, first_fragment, second_fragment = self._multiple_items_bundle(
            run_seed="reasoning-order",
            version_seed="reasoning-v2",
        )
        answer = StructuredAnswerStatement(
            statement_text="Pressure scaling remains deterministic.",
            answer_kind="justification",
            target_entity_id=first_fact.subject_id,
        )

        left = ExplanationObject(
            answer_statement=answer,
            supporting_facts=(second_fact, first_fact),
            supporting_assertions=(second_assertion, first_assertion),
            supporting_fragments=(second_fragment, first_fragment),
            applied_rules=(self.secondary_rule, self.rule),
            rejected_alternatives=(self.alt,),
            unresolved_gaps=(self.secondary_gap, self.gap),
        )
        right = ExplanationObject(
            answer_statement=answer,
            supporting_facts=(first_fact, second_fact),
            supporting_assertions=(first_assertion, second_assertion),
            supporting_fragments=(first_fragment, second_fragment),
            applied_rules=(self.rule, self.secondary_rule),
            rejected_alternatives=(self.alt,),
            unresolved_gaps=(self.gap, self.secondary_gap),
        )

        self.assertEqual(left, right)
        self.assertEqual(left.as_serializable(), right.as_serializable())

    def test_response_serialization_is_deterministic(self) -> None:
        explanation = self._explanation_with_multiple_items()
        response = ReasoningResponse(
            answer_statement=explanation.answer_statement,
            supporting_facts=tuple(reversed(explanation.supporting_facts)),
            supporting_assertions=tuple(reversed(explanation.supporting_assertions)),
            supporting_fragments=tuple(reversed(explanation.supporting_fragments)),
            applied_rules=tuple(reversed(explanation.applied_rules)),
            rejected_alternatives=explanation.rejected_alternatives,
            confidence=0.9,
            unresolved_gaps=tuple(reversed(explanation.unresolved_gaps)),
            explanation=explanation,
        )
        serializable = response.as_serializable()

        self.assertEqual(serializable, response.as_serializable())
        self.assertEqual(json.dumps(serializable, sort_keys=True), json.dumps(response.as_serializable(), sort_keys=True))
        self.assertEqual(serializable["unresolved_gaps"][0]["gap_code"], "missing_context_scope")

    def test_unresolved_gaps_are_canonicalized(self) -> None:
        explanation = self._explanation_with_multiple_items()

        self.assertEqual(
            explanation.unresolved_gaps,
            (
                self.gap,
                self.secondary_gap,
            ),
        )

    def _explanation(self) -> ExplanationObject:
        return ExplanationObject(
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=(self.fragment,),
            applied_rules=(self.rule,),
            rejected_alternatives=(self.alt,),
            unresolved_gaps=(self.gap,),
        )

    def _explanation_with_multiple_items(self) -> ExplanationObject:
        first_fact, second_fact, first_assertion, second_assertion, first_fragment, second_fragment = self._multiple_items_bundle(
            run_seed="reasoning-serialization",
            version_seed="reasoning-v3",
        )
        answer = StructuredAnswerStatement(
            statement_text="Pressure scaling remains deterministic.",
            answer_kind="justification",
            target_entity_id=first_fact.subject_id,
        )
        return ExplanationObject(
            answer_statement=answer,
            supporting_facts=(second_fact, first_fact),
            supporting_assertions=(second_assertion, first_assertion),
            supporting_fragments=(second_fragment, first_fragment),
            applied_rules=(self.secondary_rule, self.rule),
            rejected_alternatives=(self.alt,),
            unresolved_gaps=(self.secondary_gap, self.gap),
        )

    def _multiple_items_bundle(
        self,
        *,
        run_seed: str,
        version_seed: str,
    ) -> tuple[object, object, object, object, object, object]:
        second_assertion = self.helpers._assertion(
            "20 mA = 5000 psi",
            version_seed=version_seed,
            status=AssertionStatus.ACCEPTED,
        )
        assertion_run = self.helpers._assertion_run((self.assertion, second_assertion), run_seed=run_seed)
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.helpers.consolidator.consolidate(assertion_run, conflict_run)
        first_fact, second_fact = fact_run.facts
        first_assertion, second_assertion = fact_run.assertions
        fragments_by_assertion_id = {}
        for fragment in fact_run.evidence_links:
            fragments_by_assertion_id.setdefault(fragment.assertion_id, []).append(fragment)
        first_fragment = fragments_by_assertion_id[first_assertion.assertion_id][0]
        second_fragment = fragments_by_assertion_id[second_assertion.assertion_id][0]
        return first_fact, second_fact, first_assertion, second_assertion, first_fragment, second_fragment