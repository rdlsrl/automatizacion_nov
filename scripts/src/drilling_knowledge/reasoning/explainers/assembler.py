"""Deterministic assembler for reasoning explanations and responses."""

from __future__ import annotations

from collections.abc import Iterable

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.reasoning.domain import (
    ExplanationObject,
    ReasoningAppliedRule,
    ReasoningRejectedAlternative,
    ReasoningResponse,
    StructuredAnswerStatement,
    UnresolvedGap,
)
from drilling_knowledge.reasoning.queries import ReasoningExecutionPlan


def _normalize_tuple[T](field_name: str, values: Iterable[T] | None, expected_type: type[T]) -> tuple[T, ...]:
    if values is None:
        raise ValueError(f"{field_name} cannot be null")
    normalized_values = tuple(values)
    for value in normalized_values:
        if value is None:
            raise ValueError(f"{field_name} cannot contain null entries")
        if not isinstance(value, expected_type):
            raise ValueError(f"{field_name} must contain only {expected_type.__name__} values")
    return normalized_values


class ExplanationAssembler:
    @classmethod
    def create(cls) -> "ExplanationAssembler":
        return cls()

    def assemble(
        self,
        plan: ReasoningExecutionPlan,
        *,
        answer_statement: StructuredAnswerStatement,
        supporting_facts: Iterable[ConsolidatedFact],
        supporting_assertions: Iterable[EvidenceAssertion],
        supporting_fragments: Iterable[AssertionEvidenceLink],
        applied_rules: Iterable[ReasoningAppliedRule],
        rejected_alternatives: Iterable[ReasoningRejectedAlternative] = (),
        confidence: float,
        unresolved_gaps: Iterable[UnresolvedGap] = (),
    ) -> ReasoningResponse:
        if plan is None:
            raise ValueError("ExplanationAssembler.assemble plan cannot be null")
        if not isinstance(plan, ReasoningExecutionPlan):
            raise ValueError("ExplanationAssembler.assemble plan must be a ReasoningExecutionPlan")
        if not isinstance(answer_statement, StructuredAnswerStatement):
            raise ValueError("ExplanationAssembler.assemble answer_statement must be a StructuredAnswerStatement")

        facts = _normalize_tuple("ExplanationAssembler.supporting_facts", supporting_facts, ConsolidatedFact)
        assertions = _normalize_tuple("ExplanationAssembler.supporting_assertions", supporting_assertions, EvidenceAssertion)
        fragments = _normalize_tuple("ExplanationAssembler.supporting_fragments", supporting_fragments, AssertionEvidenceLink)
        rules = _normalize_tuple("ExplanationAssembler.applied_rules", applied_rules, ReasoningAppliedRule)
        alternatives = _normalize_tuple(
            "ExplanationAssembler.rejected_alternatives",
            rejected_alternatives,
            ReasoningRejectedAlternative,
        )
        gaps = _normalize_tuple("ExplanationAssembler.unresolved_gaps", unresolved_gaps, UnresolvedGap)

        self._validate_answer_target(plan, answer_statement, facts)
        self._validate_supports(facts)
        self._validate_fragments(assertions, fragments)
        self._validate_duplicate_rule_codes(rules)
        self._validate_duplicate_alternatives(alternatives)
        self._validate_duplicate_gaps(gaps)
        self._validate_provenance(fragments)

        explanation = ExplanationObject(
            answer_statement=answer_statement,
            supporting_facts=facts,
            supporting_assertions=assertions,
            supporting_fragments=fragments,
            applied_rules=rules,
            rejected_alternatives=alternatives,
            unresolved_gaps=gaps,
        )
        return ReasoningResponse(
            answer_statement=answer_statement,
            supporting_facts=facts,
            supporting_assertions=assertions,
            supporting_fragments=fragments,
            applied_rules=rules,
            rejected_alternatives=alternatives,
            confidence=confidence,
            unresolved_gaps=gaps,
            explanation=explanation,
        )

    @staticmethod
    def _validate_answer_target(
        plan: ReasoningExecutionPlan,
        answer_statement: StructuredAnswerStatement,
        facts: tuple[ConsolidatedFact, ...],
    ) -> None:
        if answer_statement.target_entity_id != plan.request.target_entity_id:
            raise ValueError("ExplanationAssembler.answer_statement.target_entity_id must match plan.request.target_entity_id")
        fact_entity_ids = {fact.subject_id for fact in facts} | {fact.object_id for fact in facts if fact.object_id is not None}
        if answer_statement.target_entity_id not in fact_entity_ids:
            raise ValueError("ExplanationAssembler.answer_statement.target_entity_id must be present in supporting_facts")

    @staticmethod
    def _validate_supports(facts: tuple[ConsolidatedFact, ...]) -> None:
        for fact in facts:
            if not fact.support_link_ids:
                raise ValueError("ExplanationAssembler.supporting_facts cannot include facts without support_link_ids")

    @staticmethod
    def _validate_fragments(
        assertions: tuple[EvidenceAssertion, ...],
        fragments: tuple[AssertionEvidenceLink, ...],
    ) -> None:
        assertion_by_id = {assertion.assertion_id: assertion for assertion in assertions}
        fragment_ids = {fragment.link_id for fragment in fragments}
        for fragment in fragments:
            if fragment.assertion_id not in assertion_by_id:
                raise ValueError("ExplanationAssembler.supporting_fragments cannot contain orphan fragments")
        for assertion in assertions:
            missing_fragment_ids = set(assertion.evidence_link_ids) - fragment_ids
            if missing_fragment_ids:
                raise ValueError("ExplanationAssembler.supporting_assertions must preserve all evidence fragments")

    @staticmethod
    def _validate_duplicate_rule_codes(rules: tuple[ReasoningAppliedRule, ...]) -> None:
        rule_codes = [rule.rule_code for rule in rules]
        if len(set(rule_codes)) != len(rule_codes):
            raise ValueError("ExplanationAssembler.applied_rules cannot contain duplicate rule codes")

    @staticmethod
    def _validate_duplicate_alternatives(alternatives: tuple[ReasoningRejectedAlternative, ...]) -> None:
        alternative_ids = [alternative.alternative_id for alternative in alternatives]
        if len(set(alternative_ids)) != len(alternative_ids):
            raise ValueError("ExplanationAssembler.rejected_alternatives cannot contain duplicate alternative ids")

    @staticmethod
    def _validate_duplicate_gaps(gaps: tuple[UnresolvedGap, ...]) -> None:
        gap_keys = [(gap.gap_code, gap.detail) for gap in gaps]
        if len(set(gap_keys)) != len(gap_keys):
            raise ValueError("ExplanationAssembler.unresolved_gaps cannot contain duplicates")

    @staticmethod
    def _validate_provenance(fragments: tuple[AssertionEvidenceLink, ...]) -> None:
        provenance_by_fragment_id: dict[object, tuple[object, object]] = {}
        for fragment in fragments:
            provenance_key = (fragment.document_id, fragment.document_version_id)
            existing = provenance_by_fragment_id.get(fragment.fragment_id)
            if existing is not None and existing != provenance_key:
                raise ValueError(
                    "ExplanationAssembler.supporting_fragments cannot map one fragment_id to multiple document provenance pairs"
                )
            provenance_by_fragment_id[fragment.fragment_id] = provenance_key