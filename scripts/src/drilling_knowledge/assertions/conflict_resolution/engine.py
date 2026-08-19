"""Deterministic conflict detection and conservative resolution for assertions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from drilling_knowledge.assertions.conflict_resolution.domain import (
    AssertionConflictContext,
    AssertionConflictMember,
    AssertionConflictSet,
    ConflictDecisionType,
    ConflictMemberRole,
    ConflictResolutionRun,
    ConflictReviewQueueItem,
    ConflictSetStatus,
    ConflictType,
)
from drilling_knowledge.assertions.conflict_resolution.repositories.contracts import ConflictResolutionRunRepository
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionGenerationRun, AssertionStatus, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace
from drilling_knowledge.resolution.domain import HypothesisSupportKind


@dataclass(frozen=True, slots=True)
class _ConflictCandidate:
    assertion: EvidenceAssertion
    origin: str
    claim_key: str
    scope_key: str
    group_scope_key: str
    value_key: str


@dataclass(slots=True)
class AssertionConflictResolver:
    rule_pack_version: str = "conflict.rules.v1"
    _explicit_relation_predicates = frozenset({
        "has_property",
        "measurement_type",
        "has_relationship",
        "derived_from",
        "has_unit",
        "quantity_class",
        "parent_object",
        "belongs_to",
    })

    @classmethod
    def create(cls, *, rule_pack_version: str = "conflict.rules.v1") -> "AssertionConflictResolver":
        return cls(rule_pack_version=rule_pack_version)

    def resolve(
        self,
        assertion_run: AssertionGenerationRun,
        *,
        existing_assertions: tuple[EvidenceAssertion, ...] = (),
    ) -> ConflictResolutionRun:
        candidates = self._active_assertions(assertion_run.assertions, existing_assertions)
        groups = self._group_conflicts(candidates)
        conflict_sets: list[AssertionConflictSet] = []
        members: list[AssertionConflictMember] = []
        contexts: list[AssertionConflictContext] = []
        review_items: list[ConflictReviewQueueItem] = []
        evidence_links: list[AssertionEvidenceLink] = []

        for candidates_in_group in groups:
            conflict_set, conflict_members, conflict_contexts, review_item = self._resolve_group(candidates_in_group, assertion_run.finished_at)
            if conflict_set is None:
                continue
            conflict_sets.append(conflict_set)
            members.extend(conflict_members)
            contexts.extend(conflict_contexts)
            if review_item is not None:
                review_items.append(review_item)
            evidence_links.extend(self._group_evidence_links(candidates_in_group))

        ordered_sets = tuple(sorted(conflict_sets, key=self._conflict_set_sort_key))
        ordered_members = tuple(sorted(members, key=self._member_sort_key))
        ordered_contexts = tuple(sorted(contexts, key=self._context_sort_key))
        ordered_review_items = tuple(sorted(review_items, key=self._review_item_sort_key))
        ordered_evidence_links = tuple(sorted(self._unique_links(evidence_links), key=self._link_sort_key))
        run_seed = "|".join(
            [
                str(assertion_run.run_id),
                self.rule_pack_version,
                *(str(conflict_set.conflict_set_id) for conflict_set in ordered_sets),
                *(str(member.member_id) for member in ordered_members),
                *(str(context.context_id) for context in ordered_contexts),
                *(str(item.review_item_id) for item in ordered_review_items),
                *(str(link.link_id) for link in ordered_evidence_links),
            ]
        )
        return ConflictResolutionRun(
            run_id=RunId.from_seed("assertion.conflict_resolution.run", run_seed),
            assertion_run_id=assertion_run.run_id,
            rule_pack_version=self.rule_pack_version,
            started_at=assertion_run.finished_at,
            finished_at=assertion_run.finished_at,
            conflict_sets=ordered_sets,
            members=ordered_members,
            contexts=ordered_contexts,
            review_queue_items=ordered_review_items,
            evidence_links=ordered_evidence_links,
            errors=(),
        )

    def resolve_and_persist(
        self,
        assertion_run: AssertionGenerationRun,
        repository: ConflictResolutionRunRepository,
        *,
        existing_assertions: tuple[EvidenceAssertion, ...] = (),
    ) -> tuple[ConflictResolutionRun, ConflictResolutionRunRepository]:
        run = self.resolve(assertion_run, existing_assertions=existing_assertions)
        return run, repository.append_run(run)

    def _active_assertions(
        self,
        current_assertions: tuple[EvidenceAssertion, ...],
        existing_assertions: tuple[EvidenceAssertion, ...],
    ) -> tuple[_ConflictCandidate, ...]:
        allowed = {AssertionStatus.SUPPORTED, AssertionStatus.ACCEPTED}
        unique: dict[EntityId, _ConflictCandidate] = {}
        for origin, assertions in (("current", current_assertions), ("existing", existing_assertions)):
            for assertion in assertions:
                if assertion.status not in allowed:
                    continue
                unique.setdefault(
                    assertion.assertion_id,
                    _ConflictCandidate(
                        assertion=assertion,
                        origin=origin,
                        claim_key=self._claim_key(assertion),
                        scope_key=self._scope_key(assertion),
                        group_scope_key=self._group_scope_key(assertion),
                        value_key=self._value_key(assertion),
                    ),
                )
        return tuple(sorted(unique.values(), key=self._candidate_sort_key))

    def _group_conflicts(self, candidates: tuple[_ConflictCandidate, ...]) -> tuple[tuple[_ConflictCandidate, ...], ...]:
        grouped: dict[tuple[str, str], list[_ConflictCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.claim_key, candidate.group_scope_key)].append(candidate)

        result: list[tuple[_ConflictCandidate, ...]] = []
        for values in grouped.values():
            ordered = tuple(sorted(values, key=self._candidate_sort_key))
            if len(ordered) < 2:
                continue
            if len({candidate.value_key for candidate in ordered}) < 2:
                continue
            result.append(ordered)
        return tuple(sorted(result, key=lambda cluster: (cluster[0].claim_key, cluster[0].group_scope_key)))

    def _resolve_group(
        self,
        candidates: tuple[_ConflictCandidate, ...],
        created_at,
    ) -> tuple[AssertionConflictSet | None, tuple[AssertionConflictMember, ...], tuple[AssertionConflictContext, ...], ConflictReviewQueueItem | None]:
        if len(candidates) < 2:
            return None, (), (), None

        claim_key = candidates[0].claim_key
        scope_key = candidates[0].group_scope_key
        conflict_set_id = EntityId.from_seed(
            "semantic.assertion_conflict_set",
            f"{claim_key}:{scope_key}:{'|'.join(str(candidate.assertion.assertion_id) for candidate in candidates)}",
        )
        scopes = self._scope_groups(candidates)
        contexts = self._build_contexts(conflict_set_id, scopes, created_at)

        if len(contexts) >= 2 and self._split_is_deterministic(scopes):
            members = tuple(
                self._member(conflict_set_id, candidate, ConflictMemberRole.SPLIT_CONTEXT, created_at)
                for candidate in candidates
            )
            conflict_set = AssertionConflictSet(
                conflict_set_id=conflict_set_id,
                claim_key=claim_key,
                scope_key=scope_key,
                conflict_type=ConflictType.INCOMPATIBLE_ASSERTION,
                status=ConflictSetStatus.CLOSED,
                decision_type=ConflictDecisionType.COEXISTENCE_SPLIT,
                decision_reason="distinct_scope_contexts",
                requires_human_review=False,
                opened_at=created_at,
                closed_at=created_at,
                members=members,
                contexts=contexts,
            )
            return conflict_set, members, contexts, None

        accepted_current = [candidate for candidate in candidates if candidate.origin == "current" and candidate.assertion.status == AssertionStatus.ACCEPTED]
        accepted_existing = [candidate for candidate in candidates if candidate.origin == "existing" and candidate.assertion.status == AssertionStatus.ACCEPTED]
        accepted_all = accepted_current + accepted_existing

        if len(accepted_current) == 1 and len(accepted_all) == 1:
            members = tuple(
                self._member(
                    conflict_set_id,
                    candidate,
                    ConflictMemberRole.ACCEPTED_MEMBER if candidate.assertion.assertion_id == accepted_current[0].assertion.assertion_id else ConflictMemberRole.REJECTED_MEMBER,
                    created_at,
                )
                for candidate in candidates
            )
            conflict_set = AssertionConflictSet(
                conflict_set_id=conflict_set_id,
                claim_key=claim_key,
                scope_key=scope_key,
                conflict_type=ConflictType.INCOMPATIBLE_ASSERTION,
                status=ConflictSetStatus.CLOSED,
                decision_type=ConflictDecisionType.ACCEPTED_MEMBER,
                decision_reason="accepted_assertion_precedence",
                requires_human_review=False,
                opened_at=created_at,
                closed_at=created_at,
                members=members,
                contexts=(),
            )
            return conflict_set, members, (), None

        if len(accepted_existing) == 1 and len(accepted_all) == 1:
            members = tuple(
                self._member(
                    conflict_set_id,
                    candidate,
                    ConflictMemberRole.ACCEPTED_MEMBER if candidate.assertion.assertion_id == accepted_existing[0].assertion.assertion_id else ConflictMemberRole.REJECTED_MEMBER,
                    created_at,
                )
                for candidate in candidates
            )
            conflict_set = AssertionConflictSet(
                conflict_set_id=conflict_set_id,
                claim_key=claim_key,
                scope_key=scope_key,
                conflict_type=ConflictType.INCOMPATIBLE_ASSERTION,
                status=ConflictSetStatus.CLOSED,
                decision_type=ConflictDecisionType.REJECTED_MEMBER,
                decision_reason="existing_accepted_assertion_precedence",
                requires_human_review=False,
                opened_at=created_at,
                closed_at=created_at,
                members=members,
                contexts=(),
            )
            return conflict_set, members, (), None

        members = tuple(
            self._member(conflict_set_id, candidate, ConflictMemberRole.REVIEW_CANDIDATE, created_at)
            for candidate in candidates
        )
        review_item = ConflictReviewQueueItem(
            review_item_id=EntityId.from_seed(
                "semantic.assertion_conflict_review_item",
                f"{conflict_set_id}:{claim_key}:{scope_key}:contradictory_active_assertions",
            ),
            conflict_set_id=conflict_set_id,
            queue_type="assertion_conflict",
            review_reason="contradictory_active_assertions",
            created_at=created_at,
        )
        conflict_set = AssertionConflictSet(
            conflict_set_id=conflict_set_id,
            claim_key=claim_key,
            scope_key=scope_key,
            conflict_type=ConflictType.INCOMPATIBLE_ASSERTION,
            status=ConflictSetStatus.OPEN,
            decision_type=ConflictDecisionType.REVIEW_REQUIRED,
            decision_reason="contradictory_active_assertions",
            requires_human_review=True,
            opened_at=created_at,
            closed_at=None,
            members=members,
            contexts=(),
            review_item=review_item,
        )
        return conflict_set, members, (), review_item

    def _member(
        self,
        conflict_set_id: EntityId,
        candidate: _ConflictCandidate,
        member_role: ConflictMemberRole,
        created_at,
    ) -> AssertionConflictMember:
        return AssertionConflictMember(
            member_id=EntityId.from_seed(
                "semantic.assertion_conflict_member",
                f"{conflict_set_id}:{candidate.assertion.assertion_id}:{member_role.value}:{candidate.scope_key}:{candidate.value_key}",
            ),
            conflict_set_id=conflict_set_id,
            assertion_id=candidate.assertion.assertion_id,
            member_role=member_role,
            member_score=candidate.assertion.score,
            scope_key=candidate.scope_key,
            value_key=candidate.value_key,
            created_at=created_at,
            source_assertion=candidate.assertion,
        )

    def _scope_groups(self, candidates: tuple[_ConflictCandidate, ...]) -> dict[str, tuple[_ConflictCandidate, ...]]:
        grouped: dict[str, list[_ConflictCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.scope_key].append(candidate)
        return {
            scope_key: tuple(sorted(values, key=self._candidate_sort_key))
            for scope_key, values in grouped.items()
        }

    def _build_contexts(
        self,
        conflict_set_id: EntityId,
        scopes: dict[str, tuple[_ConflictCandidate, ...]],
        created_at,
    ) -> tuple[AssertionConflictContext, ...]:
        contexts: list[AssertionConflictContext] = []
        for scope_key, candidates in scopes.items():
            document_id, version_id = self._split_scope_key(scope_key)
            member_ids = tuple(
                EntityId.from_seed(
                    "semantic.assertion_conflict_member",
                    f"{conflict_set_id}:{candidate.assertion.assertion_id}:{ConflictMemberRole.SPLIT_CONTEXT.value}:{candidate.scope_key}:{candidate.value_key}",
                )
                for candidate in candidates
            )
            contexts.append(
                AssertionConflictContext(
                    context_id=EntityId.from_seed(
                        "semantic.assertion_conflict_context",
                        f"{conflict_set_id}:{scope_key}:{'|'.join(str(member_id) for member_id in member_ids)}",
                    ),
                    conflict_set_id=conflict_set_id,
                    scope_key=scope_key,
                    document_id=EntityId.from_string(document_id),
                    document_version_id=EntityId.from_string(version_id),
                    member_ids=member_ids,
                    created_at=created_at,
                )
            )
        return tuple(sorted(contexts, key=self._context_sort_key))

    def _split_is_deterministic(self, scopes: dict[str, tuple[_ConflictCandidate, ...]]) -> bool:
        if len(scopes) < 2:
            return False
        return all(len({candidate.value_key for candidate in candidates}) == 1 for candidates in scopes.values())

    # claim_key: semantic identity of what is being claimed, excluding the contradictory value.
    def _claim_key(self, assertion: EvidenceAssertion) -> str:
        if assertion.predicate_code == "explicit_scaling":
            attributes = dict(assertion.literal_value)
            raw_value = attributes.get("raw_value", "")
            raw_unit = attributes.get("normalized_raw_unit_code") or attributes.get("raw_unit", "")
            engineering_anchor = attributes.get("normalized_engineering_unit_code") or attributes.get("engineering_unit", "")
            return f"explicit_scaling:{raw_value}:{raw_unit}:{engineering_anchor}"
        if assertion.predicate_code in self._explicit_relation_predicates:
            return f"{assertion.subject_table}:{assertion.subject_id}:{assertion.predicate_code}:{self._value_key(assertion)}"
        return f"{assertion.subject_table}:{assertion.subject_id}:{assertion.predicate_code}"

    # scope: exact provenance scope for a conflict candidate.
    def _scope_key(self, assertion: EvidenceAssertion) -> str:
        document_id, version_id = self._scope_ids(assertion)
        return f"{document_id}:{version_id}"

    # group_scope_key: document lineage scope used during grouping before resolution.
    def _group_scope_key(self, assertion: EvidenceAssertion) -> str:
        document_id, _ = self._scope_ids(assertion)
        return str(document_id)

    # value_key: the incompatible value within the same claim and scope.
    def _value_key(self, assertion: EvidenceAssertion) -> str:
        if assertion.predicate_code == "explicit_scaling":
            attributes = dict(assertion.literal_value)
            engineering_value = attributes.get("engineering_value", "")
            engineering_unit = attributes.get("normalized_engineering_unit_code") or attributes.get("engineering_unit", "")
            return f"{engineering_value}:{engineering_unit}"
        if assertion.object_id is not None:
            return f"{assertion.object_table}:{assertion.object_id}"
        literal_value = "|".join(f"{key}={value}" for key, value in assertion.literal_value)
        return f"literal:{literal_value}"

    def _scope_ids(self, assertion: EvidenceAssertion) -> tuple[EntityId, EntityId]:
        if assertion.source_hypothesis.source_entity_candidate is not None:
            mention = assertion.source_hypothesis.source_entity_candidate.source_mention
            return mention.document_id, mention.version_id
        observation = assertion.source_hypothesis.source_relation_candidate.source_observation
        return observation.document_id, observation.version_id

    def _split_scope_key(self, scope_key: str) -> tuple[str, str]:
        document_id, version_id = scope_key.split(":", maxsplit=1)
        return document_id, version_id

    def _group_evidence_links(self, candidates: tuple[_ConflictCandidate, ...]) -> tuple[AssertionEvidenceLink, ...]:
        collected: list[AssertionEvidenceLink] = []
        for candidate in candidates:
            collected.extend(self._assertion_evidence_links(candidate.assertion))
        return tuple(sorted(self._unique_links(collected), key=self._link_sort_key))

    def _assertion_evidence_links(self, assertion: EvidenceAssertion) -> tuple[AssertionEvidenceLink, ...]:
        original_text, normalized_text, document_id, document_version_id, fragment_id, source_trace = self._provenance(assertion)
        supports = tuple(sorted(assertion.source_supports, key=self._support_sort_key))
        return tuple(
            AssertionEvidenceLink(
                link_id=EntityId.from_seed(
                    "semantic.assertion_evidence_link",
                    f"{assertion.assertion_id}:{assertion.source_hypothesis_id}:{support.support_id}:{document_id}:{document_version_id}:{fragment_id}:{support.support_kind.value}:{original_text}:{normalized_text}",
                ),
                assertion_id=assertion.assertion_id,
                hypothesis_id=assertion.source_hypothesis_id,
                support_id=support.support_id,
                document_id=document_id,
                document_version_id=document_version_id,
                fragment_id=fragment_id,
                evidence_role=support.support_kind.value,
                weight=self._support_weight(assertion, support.support_kind),
                source_trace=source_trace,
                original_text=original_text,
                normalized_text=normalized_text,
            )
            for support in supports
        )

    def _provenance(self, assertion: EvidenceAssertion) -> tuple[str, str, EntityId, EntityId, EntityId, ExtractionSourceTrace]:
        if assertion.source_hypothesis.source_entity_candidate is not None:
            mention = assertion.source_hypothesis.source_entity_candidate.source_mention
            return (
                mention.original_text,
                mention.normalized_text,
                mention.document_id,
                mention.version_id,
                mention.fragment_id,
                mention.source_trace,
            )
        observation = assertion.source_hypothesis.source_relation_candidate.source_observation
        return (
            observation.original_text,
            observation.normalized_text,
            observation.document_id,
            observation.version_id,
            observation.fragment_id,
            observation.source_trace,
        )

    def _support_weight(self, assertion: EvidenceAssertion, support_kind: HypothesisSupportKind) -> float | None:
        if support_kind == HypothesisSupportKind.CANDIDATE:
            return assertion.score
        return None

    def _unique_links(self, links: list[AssertionEvidenceLink]) -> tuple[AssertionEvidenceLink, ...]:
        unique: dict[EntityId, AssertionEvidenceLink] = {}
        for link in links:
            unique.setdefault(link.link_id, link)
        return tuple(unique.values())

    def _support_sort_key(self, support) -> tuple[str, str, str, str]:
        return (support.support_kind.value, support.rule_code, support.reason_code, str(support.support_id))

    def _candidate_sort_key(self, candidate: _ConflictCandidate) -> tuple[str, str, str, float, str]:
        return (candidate.claim_key, candidate.group_scope_key, candidate.scope_key, -candidate.assertion.score, str(candidate.assertion.assertion_id))

    def _conflict_set_sort_key(self, conflict_set: AssertionConflictSet) -> tuple[str, str, str]:
        return (conflict_set.claim_key, conflict_set.scope_key, str(conflict_set.conflict_set_id))

    def _member_sort_key(self, member: AssertionConflictMember) -> tuple[str, str, str, str]:
        return (str(member.conflict_set_id), member.scope_key, member.member_role.value, str(member.member_id))

    def _context_sort_key(self, context: AssertionConflictContext) -> tuple[str, str, str]:
        return (str(context.conflict_set_id), context.scope_key, str(context.context_id))

    def _review_item_sort_key(self, review_item: ConflictReviewQueueItem) -> tuple[str, str]:
        return (str(review_item.conflict_set_id), str(review_item.review_item_id))

    def _link_sort_key(self, link: AssertionEvidenceLink) -> tuple[str, str]:
        return (str(link.assertion_id), str(link.link_id))