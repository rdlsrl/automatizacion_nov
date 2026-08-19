"""Deterministic evidence assertion builder and validator."""

from __future__ import annotations

from dataclasses import dataclass

from drilling_knowledge.assertions.domain import (
    AssertionEvidenceLink,
    AssertionGenerationRun,
    AssertionReviewState,
    AssertionStatus,
    AssertionValidationLog,
    EvidenceAssertion,
)
from drilling_knowledge.common.exceptions import ValidationError
from drilling_knowledge.assertions.repositories.contracts import AssertionGenerationRunRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.resolution.domain import HypothesisSupport, HypothesisSupportKind, SemanticHypothesis, SemanticHypothesisStatus, SemanticResolutionRun


@dataclass(frozen=True, slots=True)
class _ValidationDecision:
    status: AssertionStatus
    review_state: AssertionReviewState
    reason_code: str
    detail: str


@dataclass(slots=True)
class EvidenceAssertionEngine:
    threshold: float = 0.5
    rule_pack_version: str = "assertion.rules.v1"

    @classmethod
    def create(
        cls,
        *,
        threshold: float = 0.5,
        rule_pack_version: str = "assertion.rules.v1",
    ) -> "EvidenceAssertionEngine":
        return cls(threshold=threshold, rule_pack_version=rule_pack_version)

    def build(self, semantic_run: SemanticResolutionRun) -> AssertionGenerationRun:
        created_at = semantic_run.finished_at
        assertions: list[EvidenceAssertion] = []
        links: list[AssertionEvidenceLink] = []
        logs: list[AssertionValidationLog] = []
        errors: list[str] = []
        supports_by_hypothesis = self._supports_by_hypothesis(semantic_run)

        for hypothesis in semantic_run.hypotheses:
            if hypothesis.status != SemanticHypothesisStatus.SUPPORTED:
                continue
            if hypothesis.score < self.threshold:
                continue
            try:
                supports = supports_by_hypothesis.get(hypothesis.hypothesis_id, ())
                support_links = self._evidence_links(hypothesis, supports)
                assertion = self._proposed_assertion(hypothesis, created_at, supports, support_links)
                decision, validation_logs = self._validate_assertion(assertion, support_links)
                assertion = EvidenceAssertion(
                    assertion_id=assertion.assertion_id,
                    source_hypothesis_id=assertion.source_hypothesis_id,
                    source_candidate_id=assertion.source_candidate_id,
                    evidence_link_ids=assertion.evidence_link_ids,
                    subject_table=assertion.subject_table,
                    subject_id=assertion.subject_id,
                    predicate_code=assertion.predicate_code,
                    object_table=assertion.object_table,
                    object_id=assertion.object_id,
                    literal_value=assertion.literal_value,
                    status=decision.status,
                    review_state=decision.review_state,
                    score=assertion.score,
                    score_breakdown=assertion.score_breakdown,
                    reason_codes=(decision.reason_code,),
                    supersedes_id=None,
                    invalidates_id=None,
                    created_at=assertion.created_at,
                    source_hypothesis=assertion.source_hypothesis,
                    source_supports=assertion.source_supports,
                )
                assertions.append(assertion)
                links.extend(support_links)
                logs.extend(validation_logs)
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"hypothesis:{hypothesis.hypothesis_id}:{exc}")

        ordered_assertions = tuple(sorted(assertions, key=self._assertion_sort_key))
        ordered_links = tuple(sorted(links, key=self._link_sort_key))
        ordered_logs = tuple(sorted(logs, key=self._log_sort_key))
        run_seed = "|".join(
            [
                str(semantic_run.run_id),
                self.rule_pack_version,
                *(str(assertion.assertion_id) for assertion in ordered_assertions),
                *(str(link.link_id) for link in ordered_links),
                *(str(log.log_id) for log in ordered_logs),
            ]
        )
        return AssertionGenerationRun(
            run_id=RunId.from_seed("assertion.generation.run", run_seed),
            semantic_run_id=semantic_run.run_id,
            rule_pack_version=self.rule_pack_version,
            threshold=self.threshold,
            started_at=semantic_run.finished_at,
            finished_at=semantic_run.finished_at,
            assertions=ordered_assertions,
            evidence_links=ordered_links,
            validation_logs=ordered_logs,
            errors=tuple(errors),
        )

    def build_and_persist(
        self,
        semantic_run: SemanticResolutionRun,
        repository: AssertionGenerationRunRepository,
    ) -> tuple[AssertionGenerationRun, AssertionGenerationRunRepository]:
        run = self.build(semantic_run)
        return run, repository.append_run(run)

    def _proposed_assertion(
        self,
        hypothesis: SemanticHypothesis,
        created_at,
        supports: tuple[HypothesisSupport, ...],
        support_links: tuple[AssertionEvidenceLink, ...],
    ) -> EvidenceAssertion:
        literal_value = self._literal_value(hypothesis)
        return EvidenceAssertion(
            assertion_id=EntityId.from_seed(
                "semantic.evidence_assertion",
                f"{hypothesis.hypothesis_id}:{hypothesis.source_candidate_id}:{hypothesis.subject_table}:{hypothesis.subject_id}:{hypothesis.predicate_code}:{hypothesis.object_table}:{hypothesis.object_id}",
            ),
            source_hypothesis_id=hypothesis.hypothesis_id,
            source_candidate_id=hypothesis.source_candidate_id,
            evidence_link_ids=tuple(link.link_id for link in support_links),
            subject_table=hypothesis.subject_table,
            subject_id=hypothesis.subject_id,
            predicate_code=hypothesis.predicate_code,
            object_table=hypothesis.object_table,
            object_id=hypothesis.object_id,
            literal_value=literal_value,
            status=AssertionStatus.CANDIDATE,
            review_state=AssertionReviewState.AUTO,
            score=hypothesis.score,
            score_breakdown=hypothesis.score_breakdown,
            reason_codes=(),
            supersedes_id=None,
            invalidates_id=None,
            created_at=created_at,
            source_hypothesis=hypothesis,
            source_supports=supports,
        )

    def _evidence_links(
        self,
        hypothesis: SemanticHypothesis,
        supports: tuple[HypothesisSupport, ...],
    ) -> tuple[AssertionEvidenceLink, ...]:
        if not supports:
            raise ValidationError(
                code="missing_hypothesis_support",
                message="Assertion cannot be built without at least one semantic support",
                context={"hypothesis_id": str(hypothesis.hypothesis_id)},
            )
        assertion_id = self._assertion_id(hypothesis)
        original_text, normalized_text, document_id, document_version_id, fragment_id, source_trace = self._provenance(hypothesis)
        return tuple(
            AssertionEvidenceLink(
                link_id=EntityId.from_seed(
                    "semantic.assertion_evidence_link",
                    f"{assertion_id}:{hypothesis.hypothesis_id}:{support.support_id}:{document_id}:{document_version_id}:{fragment_id}:{support.support_kind.value}:{original_text}:{normalized_text}",
                ),
                assertion_id=assertion_id,
                hypothesis_id=hypothesis.hypothesis_id,
                support_id=support.support_id,
                document_id=document_id,
                document_version_id=document_version_id,
                fragment_id=fragment_id,
                evidence_role=support.support_kind.value,
                weight=self._support_weight(hypothesis, support),
                source_trace=source_trace,
                original_text=original_text,
                normalized_text=normalized_text,
            )
            for support in supports
        )

    def _validate_assertion(
        self,
        assertion: EvidenceAssertion,
        links: tuple[AssertionEvidenceLink, ...],
    ) -> tuple[_ValidationDecision, tuple[AssertionValidationLog, ...]]:
        decisions: list[_ValidationDecision] = []
        decisions.append(self._validate_provenance(assertion, links))
        decisions.append(self._validate_evidence_roles(assertion, links))
        decisions.append(self._validate_atomicity(assertion))
        decisions.append(self._validate_value_shape(assertion))

        final = AssertionStatus.SUPPORTED
        review_state = AssertionReviewState.AUTO
        final_reason = "validated"
        final_detail = "Assertion activated after deterministic validation"
        for decision in decisions:
            if decision.status == AssertionStatus.REJECTED:
                final = AssertionStatus.REJECTED
                review_state = decision.review_state
                final_reason = decision.reason_code
                final_detail = decision.detail
                break
            if decision.status == AssertionStatus.CANDIDATE and final != AssertionStatus.REJECTED:
                final = AssertionStatus.CANDIDATE
                review_state = decision.review_state
                final_reason = decision.reason_code
                final_detail = decision.detail

        logs = tuple(
            AssertionValidationLog(
                log_id=EntityId.from_seed(
                    "semantic.assertion_validation_log",
                    f"{assertion.assertion_id}:{index}:{decision.status.value}:{decision.reason_code}:{decision.detail}",
                ),
                assertion_id=assertion.assertion_id,
                rule_code=f"ASSERT-VAL-{index:03d}",
                outcome=decision.status.value,
                reason_code=decision.reason_code,
                detail=decision.detail,
            )
            for index, decision in enumerate(decisions, start=1)
        )
        return _ValidationDecision(final, review_state, final_reason, final_detail), logs

    def _validate_provenance(self, assertion: EvidenceAssertion, links: tuple[AssertionEvidenceLink, ...]) -> _ValidationDecision:
        if not links:
            return _ValidationDecision(
                AssertionStatus.REJECTED,
                AssertionReviewState.AUTO,
                "missing_assertion_evidence_link",
                "Assertion cannot be created without at least one evidence link",
            )
        original_text, normalized_text, document_id, document_version_id, fragment_id, source_trace = self._provenance(assertion.source_hypothesis)
        for link in links:
            if link.document_id is None:
                return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "missing_document_id", "Assertion cannot be created without document provenance")
            if link.document_version_id is None:
                return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "missing_document_version_id", "Assertion cannot be created without document version provenance")
            if link.fragment_id is None:
                return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "missing_support_fragment", "Assertion cannot be created without fragment provenance")
            if link.document_id != document_id or link.document_version_id != document_version_id or link.fragment_id != fragment_id:
                return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "provenance_mismatch", "Assertion evidence links must preserve exact source provenance")
            if link.original_text != original_text or link.normalized_text != normalized_text or link.source_trace != source_trace:
                return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "provenance_payload_mismatch", "Assertion evidence text and trace must match the source hypothesis")
        return _ValidationDecision(AssertionStatus.SUPPORTED, AssertionReviewState.AUTO, "provenance_valid", "Fragment provenance is present")

    def _validate_evidence_roles(self, assertion: EvidenceAssertion, links: tuple[AssertionEvidenceLink, ...]) -> _ValidationDecision:
        link_support_ids = {link.support_id for link in links}
        if len(link_support_ids) != len(links):
            return _ValidationDecision(
                AssertionStatus.REJECTED,
                AssertionReviewState.AUTO,
                "duplicate_support_link",
                "Each semantic support can be linked at most once per assertion",
            )
        negative_supports = tuple(
            support
            for support in assertion.source_supports
            if self._is_negative_support(support)
        )
        if negative_supports:
            return _ValidationDecision(
                AssertionStatus.CANDIDATE,
                AssertionReviewState.PENDING_HUMAN,
                "conflicting_evidence_roles",
                "Assertion includes negative or contradictory semantic evidence and requires review",
            )
        return _ValidationDecision(AssertionStatus.SUPPORTED, AssertionReviewState.AUTO, "evidence_roles_consistent", "Semantic evidence roles are consistent")

    def _validate_atomicity(self, assertion: EvidenceAssertion) -> _ValidationDecision:
        if assertion.predicate_code == "explicit_scaling" and self._is_composite_explicit_scaling(assertion):
            return _ValidationDecision(
                AssertionStatus.CANDIDATE,
                AssertionReviewState.PENDING_HUMAN,
                "composite_fact_requires_review",
                "Explicit scaling contains multiple endpoints or an equation that cannot be activated atomically",
            )
        return _ValidationDecision(AssertionStatus.SUPPORTED, AssertionReviewState.AUTO, "atomic_claim", "Assertion is atomic")

    def _validate_value_shape(self, assertion: EvidenceAssertion) -> _ValidationDecision:
        if assertion.subject_id == assertion.object_id and assertion.object_id is not None:
            return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "self_referential_assertion", "Self-referential assertions are invalid")
        if assertion.predicate_code == "denotes_catalog_entity" and assertion.object_id is None:
            return _ValidationDecision(AssertionStatus.REJECTED, AssertionReviewState.AUTO, "invalid_value_type", "Entity binding assertions require a catalog object")
        return _ValidationDecision(AssertionStatus.SUPPORTED, AssertionReviewState.AUTO, "value_shape_valid", "Assertion value shape is valid")

    def _provenance(self, hypothesis: SemanticHypothesis) -> tuple[str, str, EntityId, EntityId, EntityId, ExtractionSourceTrace]:
        if hypothesis.source_entity_candidate is not None:
            mention = hypothesis.source_entity_candidate.source_mention
            return (
                mention.original_text,
                mention.normalized_text,
                mention.document_id,
                mention.version_id,
                mention.fragment_id,
                mention.source_trace,
            )
        observation = hypothesis.source_relation_candidate.source_observation
        return (
            observation.original_text,
            observation.normalized_text,
            observation.document_id,
            observation.version_id,
            observation.fragment_id,
            observation.source_trace,
        )

    def _assertion_id(self, hypothesis: SemanticHypothesis) -> EntityId:
        return EntityId.from_seed(
            "semantic.evidence_assertion",
            f"{hypothesis.hypothesis_id}:{hypothesis.source_candidate_id}:{hypothesis.subject_table}:{hypothesis.subject_id}:{hypothesis.predicate_code}:{hypothesis.object_table}:{hypothesis.object_id}",
        )

    def _supports_by_hypothesis(self, semantic_run: SemanticResolutionRun) -> dict[EntityId, tuple[HypothesisSupport, ...]]:
        grouped: dict[EntityId, list[HypothesisSupport]] = {}
        for support in semantic_run.supports:
            grouped.setdefault(support.hypothesis_id, []).append(support)
        return {
            hypothesis_id: tuple(sorted(values, key=self._support_sort_key))
            for hypothesis_id, values in grouped.items()
        }

    def _literal_value(self, hypothesis: SemanticHypothesis) -> tuple[tuple[str, str], ...]:
        if hypothesis.source_relation_candidate is None:
            return ()
        if hypothesis.predicate_code != "explicit_scaling":
            return ()
        attribute_map = dict(hypothesis.source_relation_candidate.attributes)
        literal_pairs = []
        for key in ("raw_value", "raw_unit", "normalized_raw_unit_code", "engineering_value", "engineering_unit", "normalized_engineering_unit_code"):
            value = attribute_map.get(key)
            if value:
                literal_pairs.append((key, value))
        return tuple(literal_pairs)

    def _is_composite_explicit_scaling(self, assertion: EvidenceAssertion) -> bool:
        if assertion.predicate_code != "explicit_scaling":
            return False
        attribute_map = dict(assertion.literal_value)
        original_text = assertion.source_hypothesis.source_relation_candidate.source_observation.original_text if assertion.source_hypothesis.source_relation_candidate is not None else ""
        if not {"raw_value", "engineering_value", "raw_unit", "engineering_unit"}.issubset(attribute_map):
            return True
        normalized_raw_unit_code = attribute_map.get("normalized_raw_unit_code")
        normalized_engineering_unit_code = attribute_map.get("normalized_engineering_unit_code")
        if normalized_raw_unit_code and normalized_engineering_unit_code and normalized_raw_unit_code == normalized_engineering_unit_code:
            return True
        if original_text.count("=") != 1:
            return True
        lowered = original_text.casefold()
        return " and " in lowered or ";" in lowered or "," in lowered or "table" in lowered or "formula" in lowered

    def _support_weight(self, hypothesis: SemanticHypothesis, support: HypothesisSupport) -> float | None:
        if support.support_kind == HypothesisSupportKind.CANDIDATE:
            return hypothesis.score
        return None

    def _is_negative_support(self, support: HypothesisSupport) -> bool:
        negative_tokens = (
            "reject",
            "incompatible",
            "error",
            "invalid",
            "mismatch",
            "conflict",
        )
        reason = support.reason_code.casefold()
        detail = support.detail.casefold()
        return any(token in reason or token in detail for token in negative_tokens)

    def _support_sort_key(self, support: HypothesisSupport) -> tuple[str, str, str, str]:
        return (support.support_kind.value, support.rule_code, support.reason_code, str(support.support_id))

    def _assertion_sort_key(self, assertion: EvidenceAssertion) -> tuple[str, str, str]:
        return (assertion.predicate_code, assertion.status.value, str(assertion.assertion_id))

    def _link_sort_key(self, link: AssertionEvidenceLink) -> tuple[str, str]:
        return (str(link.assertion_id), str(link.link_id))

    def _log_sort_key(self, log: AssertionValidationLog) -> tuple[str, str, str]:
        return (str(log.assertion_id), log.rule_code, str(log.log_id))
