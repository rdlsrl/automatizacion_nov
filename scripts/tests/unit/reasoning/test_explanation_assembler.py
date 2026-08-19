from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.reasoning import (
    ExplanationAssembler,
    QueryPlanStage,
    ReasoningAppliedRule,
    ReasoningQuestionType,
    ReasoningRejectedAlternative,
    ReasoningQueryPlanner,
    ReasoningRequest,
    StructuredAnswerStatement,
    UnresolvedGap,
)
from drilling_knowledge.common.ids import EntityId

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class ExplanationAssemblerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        self.assembler = ExplanationAssembler.create()
        self.planner = ReasoningQueryPlanner.create()
        accepted = self.helpers._assertion(
            "4 mA = 0 psi",
            version_seed="reasoning-assembler-v1",
            status=AssertionStatus.ACCEPTED,
        )
        assertion_run = self.helpers._assertion_run((accepted,), run_seed="reasoning-assembler")
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.fact = fact_run.facts[0]
        self.assertion = fact_run.assertions[0]
        self.fragments = tuple(fragment for fragment in fact_run.evidence_links if fragment.assertion_id == self.assertion.assertion_id)
        self.answer = StructuredAnswerStatement(
            statement_text="The pressure signal comes from the configured sensor chain.",
            answer_kind="justification",
            target_entity_id=self.fact.subject_id,
        )
        self.rule = ReasoningAppliedRule(
            rule_code="reasoning.chain_complete",
            rule_summary="The measurement chain is complete.",
            rule_priority=1,
        )
        self.alternative = ReasoningRejectedAlternative(
            alternative_id=EntityId.from_seed("reasoning.assembler.alternative", "secondary-sensor"),
            reason_code="rejected",
            detail="Secondary sensor lacks corroborating provenance.",
        )
        self.gap = UnresolvedGap(
            gap_code="missing_secondary_provenance",
            detail="Competing sensor provenance was not recovered.",
        )
        self.request = ReasoningRequest(
            target_entity_id=self.fact.subject_id,
            question_type=ReasoningQuestionType.PRODUCER_SOURCE_JUSTIFICATION,
            context_scope=self.fact.scope,
            requested_confidence_threshold=0.8,
        )
        self.plan = self.planner.build_plan(self.request)

    def test_valid_assembly_builds_traceable_response(self) -> None:
        response = self._assemble()

        self.assertEqual(response.answer_statement, self.answer)
        self.assertEqual(response.explanation.answer_statement, self.answer)
        self.assertEqual(response.supporting_facts, (self.fact,))
        self.assertEqual(response.supporting_assertions, (self.assertion,))
        self.assertEqual(response.supporting_fragments, self.fragments)

    def test_complete_evidence_preserves_provenance_and_plan_target(self) -> None:
        response = self._assemble()

        self.assertEqual(response.answer_statement.target_entity_id, self.plan.request.target_entity_id)
        self.assertEqual(
            {fragment.document_id for fragment in response.supporting_fragments},
            {fragment.document_id for fragment in self.fragments},
        )
        self.assertIn(QueryPlanStage.FETCH_PROVENANCE_FRAGMENTS, {step.stage for step in self.plan.steps})

    def test_incomplete_evidence_can_only_be_expressed_via_unresolved_gaps(self) -> None:
        response = self._assemble(unresolved_gaps=(self.gap,))

        self.assertEqual(response.unresolved_gaps, (self.gap,))
        self.assertEqual(response.explanation.unresolved_gaps, (self.gap,))

    def test_missing_fragments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._assemble(supporting_fragments=self.fragments[:1])

    def test_canonicalization_and_determinism_are_order_independent(self) -> None:
        response = self._assemble(
            supporting_fragments=tuple(reversed(self.fragments)),
            applied_rules=(
                ReasoningAppliedRule(
                    rule_code="reasoning.z_rule",
                    rule_summary="Lower priority rule.",
                    rule_priority=5,
                ),
                self.rule,
            ),
            unresolved_gaps=(
                UnresolvedGap(gap_code="z_gap", detail="Later gap."),
                self.gap,
            ),
        )
        equivalent = self._assemble(
            applied_rules=(
                self.rule,
                ReasoningAppliedRule(
                    rule_code="reasoning.z_rule",
                    rule_summary="Lower priority rule.",
                    rule_priority=5,
                ),
            ),
            unresolved_gaps=(self.gap, UnresolvedGap(gap_code="z_gap", detail="Later gap.")),
        )

        self.assertEqual(response, equivalent)
        self.assertEqual(response.as_serializable(), equivalent.as_serializable())

    def test_serialization_is_stable(self) -> None:
        response = self._assemble(unresolved_gaps=(self.gap,))

        self.assertEqual(
            json.dumps(response.as_serializable(), sort_keys=True),
            json.dumps(self._assemble(unresolved_gaps=(self.gap,)).as_serializable(), sort_keys=True),
        )

    def test_duplicate_rules_are_rejected(self) -> None:
        duplicate_rule = ReasoningAppliedRule(
            rule_code=self.rule.rule_code,
            rule_summary="Duplicate rule.",
            rule_priority=99,
        )

        with self.assertRaises(ValueError):
            self._assemble(applied_rules=(self.rule, duplicate_rule))

    def test_duplicate_rejected_alternatives_are_rejected(self) -> None:
        duplicate_alternative = ReasoningRejectedAlternative(
            alternative_id=self.alternative.alternative_id,
            reason_code="rejected",
            detail="Duplicate alternative.",
        )

        with self.assertRaises(ValueError):
            self._assemble(rejected_alternatives=(self.alternative, duplicate_alternative))

    def test_duplicate_unresolved_gaps_are_rejected(self) -> None:
        duplicate_gap = UnresolvedGap(gap_code=self.gap.gap_code, detail=self.gap.detail)

        with self.assertRaises(ValueError):
            self._assemble(unresolved_gaps=(self.gap, duplicate_gap))

    def test_invalid_references_are_rejected(self) -> None:
        orphan_fragment = replace(
            self.fragments[0],
            link_id=EntityId.from_seed("reasoning.assembler.fragment", "orphan"),
            assertion_id=EntityId.from_seed("reasoning.assembler.assertion", "missing"),
        )

        with self.assertRaises(ValueError):
            self._assemble(supporting_fragments=(orphan_fragment, *self.fragments[1:]))

    def test_inconsistent_provenance_is_rejected(self) -> None:
        inconsistent_fragment = replace(
            self.fragments[0],
            link_id=EntityId.from_seed("reasoning.assembler.fragment", "same-fragment-different-doc"),
            document_id=EntityId.from_seed("reasoning.assembler.doc", "other"),
        )
        duplicated_fragment_id = replace(inconsistent_fragment, fragment_id=self.fragments[0].fragment_id)

        with self.assertRaises(ValueError):
            self._assemble(supporting_fragments=(self.fragments[0], duplicated_fragment_id, *self.fragments[1:]))

    def test_inmutability_is_enforced(self) -> None:
        response = self._assemble()

        with self.assertRaises(FrozenInstanceError):
            response.confidence = 0.1

    def _assemble(
        self,
        *,
        supporting_fragments=None,
        applied_rules=None,
        rejected_alternatives=None,
        unresolved_gaps=None,
    ):
        return self.assembler.assemble(
            self.plan,
            answer_statement=self.answer,
            supporting_facts=(self.fact,),
            supporting_assertions=(self.assertion,),
            supporting_fragments=self.fragments if supporting_fragments is None else supporting_fragments,
            applied_rules=(self.rule,) if applied_rules is None else applied_rules,
            rejected_alternatives=(self.alternative,) if rejected_alternatives is None else rejected_alternatives,
            confidence=0.9,
            unresolved_gaps=() if unresolved_gaps is None else unresolved_gaps,
        )