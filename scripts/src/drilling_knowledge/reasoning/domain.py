"""DTO contracts for reasoning requests, responses, and explanations."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum, StrEnum
import math

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, Identifier


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


def _canonical_tuple[T](field_name: str, values: tuple[T, ...], *, expected_type: type[T], sort_key: callable) -> tuple[T, ...]:
    if values is None:
        raise ValueError(f"{field_name} cannot be null")
    normalized_values = tuple(values)
    for value in normalized_values:
        if value is None:
            raise ValueError(f"{field_name} cannot contain null entries")
        if not isinstance(value, expected_type):
            raise ValueError(f"{field_name} must contain only {expected_type.__name__} values")
    return tuple(sorted(normalized_values, key=sort_key))


def _serialize_value(value: object) -> object:
    if isinstance(value, Identifier):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return value


class ReasoningQuestionType(StrEnum):
    CLASSIFICATION_JUSTIFICATION = "classification_justification"
    LINEAGE_JUSTIFICATION = "lineage_justification"
    PRODUCER_SOURCE_JUSTIFICATION = "producer_source_justification"
    DERIVATION_JUSTIFICATION = "derivation_justification"
    CONFLICT_EXPLANATION = "conflict_explanation"
    EVIDENCE_PROVENANCE_EXPLANATION = "evidence_provenance_explanation"


@dataclass(frozen=True, slots=True)
class StructuredAnswerStatement:
    statement_text: str
    answer_kind: str
    target_entity_id: EntityId

    def __post_init__(self) -> None:
        statement_text = self.statement_text.strip()
        answer_kind = self.answer_kind.strip().lower()
        target_entity_id = _require_entity_id("StructuredAnswerStatement.target_entity_id", self.target_entity_id)
        if not statement_text:
            raise ValueError("StructuredAnswerStatement.statement_text cannot be empty")
        if not answer_kind:
            raise ValueError("StructuredAnswerStatement.answer_kind cannot be empty")
        object.__setattr__(self, "statement_text", statement_text)
        object.__setattr__(self, "answer_kind", answer_kind)
        object.__setattr__(self, "target_entity_id", target_entity_id)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReasoningAppliedRule:
    rule_code: str
    rule_summary: str
    rule_priority: int

    def __post_init__(self) -> None:
        rule_code = self.rule_code.strip()
        rule_summary = self.rule_summary.strip()
        if not rule_code:
            raise ValueError("ReasoningAppliedRule.rule_code cannot be empty")
        if not rule_summary:
            raise ValueError("ReasoningAppliedRule.rule_summary cannot be empty")
        if self.rule_priority < 0:
            raise ValueError("ReasoningAppliedRule.rule_priority cannot be negative")
        object.__setattr__(self, "rule_code", rule_code)
        object.__setattr__(self, "rule_summary", rule_summary)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReasoningRejectedAlternative:
    alternative_id: EntityId
    reason_code: str
    detail: str

    def __post_init__(self) -> None:
        alternative_id = _require_entity_id("ReasoningRejectedAlternative.alternative_id", self.alternative_id)
        reason_code = self.reason_code.strip()
        detail = self.detail.strip()
        if not reason_code:
            raise ValueError("ReasoningRejectedAlternative.reason_code cannot be empty")
        if not detail:
            raise ValueError("ReasoningRejectedAlternative.detail cannot be empty")
        object.__setattr__(self, "alternative_id", alternative_id)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "detail", detail)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class UnresolvedGap:
    gap_code: str
    detail: str

    def __post_init__(self) -> None:
        gap_code = self.gap_code.strip()
        detail = self.detail.strip()
        if not gap_code:
            raise ValueError("UnresolvedGap.gap_code cannot be empty")
        if not detail:
            raise ValueError("UnresolvedGap.detail cannot be empty")
        object.__setattr__(self, "gap_code", gap_code)
        object.__setattr__(self, "detail", detail)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ExplanationObject:
    answer_statement: StructuredAnswerStatement
    supporting_facts: tuple[ConsolidatedFact, ...]
    supporting_assertions: tuple[EvidenceAssertion, ...]
    supporting_fragments: tuple[AssertionEvidenceLink, ...]
    applied_rules: tuple[ReasoningAppliedRule, ...]
    rejected_alternatives: tuple[ReasoningRejectedAlternative, ...]
    unresolved_gaps: tuple[UnresolvedGap, ...] = ()

    def __post_init__(self) -> None:
        answer_statement = _require_instance("ExplanationObject.answer_statement", self.answer_statement, StructuredAnswerStatement)
        supporting_facts = _canonical_tuple(
            "ExplanationObject.supporting_facts",
            self.supporting_facts,
            expected_type=ConsolidatedFact,
            sort_key=lambda fact: str(fact.fact_id),
        )
        supporting_assertions = _canonical_tuple(
            "ExplanationObject.supporting_assertions",
            self.supporting_assertions,
            expected_type=EvidenceAssertion,
            sort_key=lambda assertion: str(assertion.assertion_id),
        )
        supporting_fragments = _canonical_tuple(
            "ExplanationObject.supporting_fragments",
            self.supporting_fragments,
            expected_type=AssertionEvidenceLink,
            sort_key=lambda fragment: str(fragment.link_id),
        )
        applied_rules = _canonical_tuple(
            "ExplanationObject.applied_rules",
            self.applied_rules,
            expected_type=ReasoningAppliedRule,
            sort_key=lambda rule: (rule.rule_priority, rule.rule_code, rule.rule_summary),
        )
        rejected_alternatives = _canonical_tuple(
            "ExplanationObject.rejected_alternatives",
            self.rejected_alternatives,
            expected_type=ReasoningRejectedAlternative,
            sort_key=lambda alternative: str(alternative.alternative_id),
        )
        unresolved_gaps = _canonical_tuple(
            "ExplanationObject.unresolved_gaps",
            self.unresolved_gaps,
            expected_type=UnresolvedGap,
            sort_key=lambda gap: (gap.gap_code, gap.detail),
        )
        object.__setattr__(self, "answer_statement", answer_statement)
        object.__setattr__(self, "supporting_facts", supporting_facts)
        object.__setattr__(self, "supporting_assertions", supporting_assertions)
        object.__setattr__(self, "supporting_fragments", supporting_fragments)
        object.__setattr__(self, "applied_rules", applied_rules)
        object.__setattr__(self, "rejected_alternatives", rejected_alternatives)
        object.__setattr__(self, "unresolved_gaps", unresolved_gaps)
        if not supporting_facts:
            raise ValueError("ExplanationObject.supporting_facts cannot be empty")
        if not supporting_assertions:
            raise ValueError("ExplanationObject.supporting_assertions cannot be empty")
        if not supporting_fragments:
            raise ValueError("ExplanationObject.supporting_fragments cannot be empty")
        if not applied_rules:
            raise ValueError("ExplanationObject.applied_rules cannot be empty")
        if len({fact.fact_id for fact in supporting_facts}) != len(supporting_facts):
            raise ValueError("ExplanationObject.supporting_facts cannot contain duplicate fact ids")
        if len({assertion.assertion_id for assertion in supporting_assertions}) != len(supporting_assertions):
            raise ValueError("ExplanationObject.supporting_assertions cannot contain duplicate assertion ids")
        if len({fragment.link_id for fragment in supporting_fragments}) != len(supporting_fragments):
            raise ValueError("ExplanationObject.supporting_fragments cannot contain duplicate fragment ids")
        if len({rule.rule_code for rule in applied_rules}) != len(applied_rules):
            raise ValueError("ExplanationObject.applied_rules cannot contain duplicate rule codes")
        if len({alternative.alternative_id for alternative in rejected_alternatives}) != len(rejected_alternatives):
            raise ValueError("ExplanationObject.rejected_alternatives cannot contain duplicate alternative ids")
        assertion_ids = {assertion.assertion_id for assertion in supporting_assertions}
        if answer_statement.target_entity_id not in {
            fact.subject_id for fact in supporting_facts
        } | {
            fact.object_id for fact in supporting_facts if fact.object_id is not None
        }:
            raise ValueError("ExplanationObject.answer_statement.target_entity_id must be present in supporting facts")
        fragment_ids = {fragment.link_id for fragment in supporting_fragments}
        for assertion in supporting_assertions:
            if not assertion.evidence_link_ids:
                raise ValueError("ExplanationObject.supporting_assertions must preserve evidence links")
        for fragment in supporting_fragments:
            if fragment.assertion_id not in assertion_ids:
                raise ValueError("ExplanationObject.supporting_fragments must reference supporting assertions")
        linked_assertions = {
            assertion.assertion_id
            for assertion in supporting_assertions
            if set(assertion.evidence_link_ids) & fragment_ids
        }
        if linked_assertions != assertion_ids:
            raise ValueError("ExplanationObject.supporting_fragments must cover every supporting assertion")
        supporting_fact_assertion_ids = {
            support_id
            for fact in supporting_facts
            for support_id in fact.support_link_ids
        }
        if not supporting_fact_assertion_ids:
            raise ValueError("ExplanationObject.supporting_facts must preserve support links")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    target_entity_id: EntityId
    question_type: ReasoningQuestionType
    context_scope: str | None = None
    requested_confidence_threshold: float | None = None

    def __post_init__(self) -> None:
        target_entity_id = _require_entity_id("ReasoningRequest.target_entity_id", self.target_entity_id)
        question_type = self.question_type
        if question_type is None:
            raise ValueError("ReasoningRequest.question_type cannot be null")
        if not isinstance(question_type, ReasoningQuestionType):
            raise ValueError("ReasoningRequest.question_type must be a ReasoningQuestionType")
        context_scope = None if self.context_scope is None else self.context_scope.strip()
        if context_scope == "":
            raise ValueError("ReasoningRequest.context_scope cannot be blank")
        if self.requested_confidence_threshold is not None and (
            not math.isfinite(self.requested_confidence_threshold)
            or not 0.0 <= self.requested_confidence_threshold <= 1.0
        ):
            raise ValueError("ReasoningRequest.requested_confidence_threshold must be between 0 and 1 when present")
        object.__setattr__(self, "target_entity_id", target_entity_id)
        object.__setattr__(self, "question_type", question_type)
        object.__setattr__(self, "context_scope", context_scope)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class ReasoningResponse:
    answer_statement: StructuredAnswerStatement
    supporting_facts: tuple[ConsolidatedFact, ...]
    supporting_assertions: tuple[EvidenceAssertion, ...]
    supporting_fragments: tuple[AssertionEvidenceLink, ...]
    applied_rules: tuple[ReasoningAppliedRule, ...]
    rejected_alternatives: tuple[ReasoningRejectedAlternative, ...]
    confidence: float
    unresolved_gaps: tuple[UnresolvedGap, ...]
    explanation: ExplanationObject

    def __post_init__(self) -> None:
        answer_statement = _require_instance("ReasoningResponse.answer_statement", self.answer_statement, StructuredAnswerStatement)
        explanation = _require_instance("ReasoningResponse.explanation", self.explanation, ExplanationObject)
        supporting_facts = _canonical_tuple(
            "ReasoningResponse.supporting_facts",
            self.supporting_facts,
            expected_type=ConsolidatedFact,
            sort_key=lambda fact: str(fact.fact_id),
        )
        supporting_assertions = _canonical_tuple(
            "ReasoningResponse.supporting_assertions",
            self.supporting_assertions,
            expected_type=EvidenceAssertion,
            sort_key=lambda assertion: str(assertion.assertion_id),
        )
        supporting_fragments = _canonical_tuple(
            "ReasoningResponse.supporting_fragments",
            self.supporting_fragments,
            expected_type=AssertionEvidenceLink,
            sort_key=lambda fragment: str(fragment.link_id),
        )
        applied_rules = _canonical_tuple(
            "ReasoningResponse.applied_rules",
            self.applied_rules,
            expected_type=ReasoningAppliedRule,
            sort_key=lambda rule: (rule.rule_priority, rule.rule_code, rule.rule_summary),
        )
        rejected_alternatives = _canonical_tuple(
            "ReasoningResponse.rejected_alternatives",
            self.rejected_alternatives,
            expected_type=ReasoningRejectedAlternative,
            sort_key=lambda alternative: str(alternative.alternative_id),
        )
        unresolved_gaps = _canonical_tuple(
            "ReasoningResponse.unresolved_gaps",
            self.unresolved_gaps,
            expected_type=UnresolvedGap,
            sort_key=lambda gap: (gap.gap_code, gap.detail),
        )
        object.__setattr__(self, "answer_statement", answer_statement)
        object.__setattr__(self, "explanation", explanation)
        object.__setattr__(self, "supporting_facts", supporting_facts)
        object.__setattr__(self, "supporting_assertions", supporting_assertions)
        object.__setattr__(self, "supporting_fragments", supporting_fragments)
        object.__setattr__(self, "applied_rules", applied_rules)
        object.__setattr__(self, "rejected_alternatives", rejected_alternatives)
        object.__setattr__(self, "unresolved_gaps", unresolved_gaps)
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("ReasoningResponse.confidence must be between 0 and 1")
        if answer_statement != explanation.answer_statement:
            raise ValueError("ReasoningResponse.answer_statement must match explanation.answer_statement")
        if supporting_facts != explanation.supporting_facts:
            raise ValueError("ReasoningResponse.supporting_facts must match explanation.supporting_facts")
        if supporting_assertions != explanation.supporting_assertions:
            raise ValueError("ReasoningResponse.supporting_assertions must match explanation.supporting_assertions")
        if supporting_fragments != explanation.supporting_fragments:
            raise ValueError("ReasoningResponse.supporting_fragments must match explanation.supporting_fragments")
        if applied_rules != explanation.applied_rules:
            raise ValueError("ReasoningResponse.applied_rules must match explanation.applied_rules")
        if rejected_alternatives != explanation.rejected_alternatives:
            raise ValueError("ReasoningResponse.rejected_alternatives must match explanation.rejected_alternatives")
        if unresolved_gaps != explanation.unresolved_gaps:
            raise ValueError("ReasoningResponse.unresolved_gaps must match explanation.unresolved_gaps")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)