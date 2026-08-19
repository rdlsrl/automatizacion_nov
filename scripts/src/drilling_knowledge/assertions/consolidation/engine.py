"""Deterministic, append-only fact consolidation from accepted assertions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from drilling_knowledge.assertions.consolidation.domain import (
    ConsolidatedFact,
    FactConsolidationMetrics,
    FactConsolidationRun,
    FactLifecycle,
    FactProvenance,
    FactSupport,
    FactSupportRole,
)
from drilling_knowledge.assertions.consolidation.repositories.contracts import FactConsolidationRunRepository
from drilling_knowledge.assertions.conflict_resolution.domain import ConflictDecisionType, ConflictResolutionRun, ConflictSetStatus
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionGenerationRun, AssertionStatus, EvidenceAssertion
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId


@dataclass(frozen=True, slots=True)
class _FactCandidate:
    assertion: EvidenceAssertion
    evidence_links: tuple[AssertionEvidenceLink, ...]
    claim_key: str
    scope: str
    group_scope: str
    value_key: str
    support_role: FactSupportRole


@dataclass(slots=True)
class FactConsolidator:
    rule_pack_version: str = "fact.consolidation.rules.v1"
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
    def create(cls, *, rule_pack_version: str = "fact.consolidation.rules.v1") -> "FactConsolidator":
        return cls(rule_pack_version=rule_pack_version)

    def consolidate(
        self,
        assertion_run: AssertionGenerationRun,
        conflict_run: ConflictResolutionRun,
        *,
        existing_facts: tuple[ConsolidatedFact, ...] = (),
        existing_support_links: tuple[FactSupport, ...] = (),
    ) -> FactConsolidationRun:
        self._validate_inputs(assertion_run, conflict_run, existing_facts, existing_support_links)
        links_by_assertion = self._links_by_assertion(assertion_run.evidence_links)
        split_assertion_ids = self._split_assertion_ids(conflict_run)
        candidates = self._accepted_candidates(assertion_run.assertions, links_by_assertion, split_assertion_ids)
        self._validate_no_open_conflicts(candidates, conflict_run)

        facts: list[ConsolidatedFact] = []
        supports: list[FactSupport] = []
        selected_assertions: list[EvidenceAssertion] = []
        selected_links: list[AssertionEvidenceLink] = []
        facts_created = 0
        facts_reused = 0
        superseded_facts = 0

        grouped: dict[tuple[str, str, str, str, str, str], list[_FactCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[self._family_key(candidate)].append(candidate)

        for family_key in sorted(grouped):
            grouped_candidates = tuple(sorted(grouped[family_key], key=self._candidate_sort_key))
            lineage_key = self._lineage_key(grouped_candidates[0])
            existing_lineage = tuple(sorted((fact for fact in existing_facts if self._fact_lineage_key(fact) == lineage_key), key=self._existing_fact_sort_key))
            active_revision = self._active_revision(existing_lineage)
            existing_supports_for_active = self._supports_for_fact(active_revision.fact_id, existing_support_links) if active_revision is not None else ()
            signature = self._candidate_signature(grouped_candidates)
            if active_revision is not None and signature == self._existing_signature(existing_supports_for_active):
                facts.extend(existing_lineage)
                lineage_supports = self._supports_for_facts(existing_lineage, existing_support_links)
                supports.extend(lineage_supports)
                selected_assertions.extend(support.source_assertion for support in lineage_supports)
                selected_links.extend(self._links_for_supports(lineage_supports, assertion_run.evidence_links, existing_support_links))
                facts_reused += 1
                continue

            version = 1 if active_revision is None else active_revision.version + 1
            lineage_supports = self._supports_for_facts(existing_lineage, existing_support_links)
            if active_revision is not None:
                superseded_facts += 1
                facts.append(self._supersede_fact(active_revision, assertion_run.finished_at))
            for historical_fact in existing_lineage:
                if active_revision is not None and historical_fact.fact_id == active_revision.fact_id:
                    continue
                facts.append(historical_fact)
            supports.extend(lineage_supports)
            selected_assertions.extend(support.source_assertion for support in lineage_supports)
            selected_links.extend(self._links_for_supports(lineage_supports, assertion_run.evidence_links, existing_support_links))
            fact = self._build_fact(
                grouped_candidates,
                version=version,
                created_at=assertion_run.finished_at,
                supersedes_fact_id=active_revision.fact_id if active_revision is not None else None,
            )
            fact_supports = tuple(self._build_support(fact.fact_id, candidate, assertion_run.finished_at) for candidate in grouped_candidates)
            fact = ConsolidatedFact(
                fact_id=fact.fact_id,
                claim_key=fact.claim_key,
                scope=fact.scope,
                lifecycle=fact.lifecycle,
                version=fact.version,
                active_revision=fact.active_revision,
                supersedes_fact_id=fact.supersedes_fact_id,
                created_at=fact.created_at,
                updated_at=fact.updated_at,
                value_key=fact.value_key,
                subject_table=fact.subject_table,
                subject_id=fact.subject_id,
                predicate_code=fact.predicate_code,
                object_table=fact.object_table,
                object_id=fact.object_id,
                literal_value=fact.literal_value,
                support_link_ids=tuple(sorted((support.fact_support_id for support in fact_supports), key=str)),
            )
            facts.append(fact)
            supports.extend(fact_supports)
            selected_assertions.extend(candidate.assertion for candidate in grouped_candidates)
            for candidate in grouped_candidates:
                selected_links.extend(candidate.evidence_links)
            facts_created += 1

        ordered_facts = tuple(sorted(facts, key=self._fact_sort_key))
        ordered_supports = tuple(sorted(supports, key=self._support_sort_key))
        ordered_assertions = tuple(sorted(self._unique_assertions(selected_assertions), key=self._assertion_sort_key))
        ordered_links = tuple(sorted(self._unique_links(selected_links), key=self._link_sort_key))
        metrics = FactConsolidationMetrics(
            candidate_assertions=len(candidates),
            split_contexts=len(conflict_run.contexts),
            facts_created=facts_created,
            facts_reused=facts_reused,
            supports_created=len(ordered_supports),
            superseded_facts=superseded_facts,
            skipped_assertions=len(assertion_run.assertions) - len(candidates),
        )
        run_seed = "|".join(
            [
                str(assertion_run.run_id),
                str(conflict_run.run_id),
                self.rule_pack_version,
                *(str(fact.fact_id) for fact in ordered_facts),
                *(str(support.fact_support_id) for support in ordered_supports),
            ]
        )
        return FactConsolidationRun(
            run_id=RunId.from_seed("semantic.fact_consolidation.run", run_seed),
            assertion_run_id=assertion_run.run_id,
            conflict_resolution_run_id=conflict_run.run_id,
            rule_pack_version=self.rule_pack_version,
            started_at=assertion_run.finished_at,
            finished_at=assertion_run.finished_at,
            assertions=ordered_assertions,
            evidence_links=ordered_links,
            facts=ordered_facts,
            support_links=ordered_supports,
            metrics=metrics,
            errors=(),
        )

    def consolidate_and_persist(
        self,
        assertion_run: AssertionGenerationRun,
        conflict_run: ConflictResolutionRun,
        repository: FactConsolidationRunRepository,
        *,
        existing_facts: tuple[ConsolidatedFact, ...] = (),
        existing_support_links: tuple[FactSupport, ...] = (),
    ) -> tuple[FactConsolidationRun, FactConsolidationRunRepository]:
        run = self.consolidate(
            assertion_run,
            conflict_run,
            existing_facts=existing_facts,
            existing_support_links=existing_support_links,
        )
        return run, repository.append_run(run)

    def _validate_inputs(
        self,
        assertion_run: AssertionGenerationRun,
        conflict_run: ConflictResolutionRun,
        existing_facts: tuple[ConsolidatedFact, ...],
        existing_support_links: tuple[FactSupport, ...],
    ) -> None:
        if conflict_run.assertion_run_id != assertion_run.run_id:
            raise ConflictError(
                code="fact_consolidation_run_mismatch",
                message="Conflict resolution run must belong to the same assertion generation run",
                context={"assertion_run_id": str(assertion_run.run_id), "conflict_run_assertion_run_id": str(conflict_run.assertion_run_id)},
            )
        lineage_versions: dict[str, set[int]] = defaultdict(set)
        for fact in existing_facts:
            lineage_key = self._fact_lineage_key(fact)
            if fact.version in lineage_versions[lineage_key]:
                raise ConflictError(
                    code="duplicate_fact_version",
                    message="Existing facts cannot reuse the same version within a lineage",
                    context={"claim_key": fact.claim_key, "scope": fact.scope, "version": str(fact.version)},
                )
            lineage_versions[lineage_key].add(fact.version)
        self._validate_active_revisions(existing_facts)
        support_fact_ids = {support.fact_id for support in existing_support_links}
        missing = support_fact_ids.difference({fact.fact_id for fact in existing_facts})
        if missing:
            raise ConflictError(
                code="support_missing_existing_fact",
                message="Existing support links must reference existing facts",
                context={"fact_ids": tuple(sorted(str(fact_id) for fact_id in missing))},
            )

    def _accepted_candidates(
        self,
        assertions: tuple[EvidenceAssertion, ...],
        links_by_assertion: dict[EntityId, tuple[AssertionEvidenceLink, ...]],
        split_assertion_ids: set[EntityId],
    ) -> tuple[_FactCandidate, ...]:
        candidates: list[_FactCandidate] = []
        for assertion in assertions:
            if assertion.status != AssertionStatus.ACCEPTED:
                continue
            links = links_by_assertion.get(assertion.assertion_id, ())
            if not links:
                raise ConflictError(
                    code="accepted_assertion_missing_links",
                    message="Accepted assertions must provide persisted evidence links for consolidation",
                    context={"assertion_id": str(assertion.assertion_id)},
                )
            candidates.append(
                _FactCandidate(
                    assertion=assertion,
                    evidence_links=links,
                    claim_key=self._claim_key(assertion),
                    scope=self._scope_key(assertion),
                    group_scope=self._group_scope_key(assertion),
                    value_key=self._value_key(assertion),
                    support_role=FactSupportRole.COEXISTENCE_CONTEXT if assertion.assertion_id in split_assertion_ids else FactSupportRole.ACCEPTED_ASSERTION,
                )
            )
        return tuple(sorted(candidates, key=self._candidate_sort_key))

    def _validate_no_open_conflicts(
        self,
        candidates: tuple[_FactCandidate, ...],
        conflict_run: ConflictResolutionRun,
    ) -> None:
        open_conflicts = {
            (conflict_set.claim_key, conflict_set.scope_key)
            for conflict_set in conflict_run.conflict_sets
            if conflict_set.status == ConflictSetStatus.OPEN
        }
        for candidate in candidates:
            if (candidate.claim_key, candidate.group_scope) in open_conflicts:
                raise ConflictError(
                    code="open_conflict_blocks_fact",
                    message="Facts cannot be created while an unresolved hard conflict exists in the same scope",
                    context={"claim_key": candidate.claim_key, "scope": candidate.group_scope, "assertion_id": str(candidate.assertion.assertion_id)},
                )

    def _build_fact(
        self,
        candidates: tuple[_FactCandidate, ...],
        *,
        version: int,
        created_at,
        supersedes_fact_id: EntityId | None,
    ) -> ConsolidatedFact:
        seed = self._candidate_signature(candidates)
        first = candidates[0]
        return ConsolidatedFact(
            fact_id=EntityId.from_seed("semantic.consolidated_fact", f"{self._lineage_key(first)}:v{version}:{seed}"),
            claim_key=first.claim_key,
            scope=first.scope,
            lifecycle=FactLifecycle.ACTIVE,
            version=version,
            active_revision=True,
            supersedes_fact_id=supersedes_fact_id,
            created_at=created_at,
            updated_at=created_at,
            value_key=first.value_key,
            subject_table=first.assertion.subject_table,
            subject_id=first.assertion.subject_id,
            predicate_code=first.assertion.predicate_code,
            object_table=first.assertion.object_table,
            object_id=first.assertion.object_id,
            literal_value=first.assertion.literal_value,
            support_link_ids=(EntityId.from_seed("semantic.fact_support", "placeholder"),),
        )

    def _supersede_fact(self, fact: ConsolidatedFact, updated_at) -> ConsolidatedFact:
        return ConsolidatedFact(
            fact_id=fact.fact_id,
            claim_key=fact.claim_key,
            scope=fact.scope,
            lifecycle=FactLifecycle.SUPERSEDED,
            version=fact.version,
            active_revision=False,
            supersedes_fact_id=fact.supersedes_fact_id,
            created_at=fact.created_at,
            updated_at=updated_at,
            value_key=fact.value_key,
            subject_table=fact.subject_table,
            subject_id=fact.subject_id,
            predicate_code=fact.predicate_code,
            object_table=fact.object_table,
            object_id=fact.object_id,
            literal_value=fact.literal_value,
            support_link_ids=fact.support_link_ids,
        )

    def _build_support(self, fact_id: EntityId, candidate: _FactCandidate, created_at) -> FactSupport:
        evidence_link_ids = tuple(sorted((link.link_id for link in candidate.evidence_links), key=str))
        support_ids = tuple(sorted((support.support_id for support in candidate.assertion.source_supports), key=str))
        provenance = tuple(
            sorted(
                {
                    FactProvenance(
                        document_id=link.document_id,
                        document_version_id=link.document_version_id,
                        fragment_id=link.fragment_id,
                    )
                    for link in candidate.evidence_links
                },
                key=lambda item: (str(item.document_id), str(item.document_version_id), str(item.fragment_id)),
            )
        )
        return FactSupport(
            fact_support_id=EntityId.from_seed(
                "semantic.fact_support",
                f"{fact_id}:{candidate.assertion.assertion_id}:{candidate.support_role.value}:{'|'.join(str(link_id) for link_id in evidence_link_ids)}",
            ),
            fact_id=fact_id,
            assertion_id=candidate.assertion.assertion_id,
            evidence_assertion_id=candidate.assertion.assertion_id,
            assertion_evidence_link_ids=evidence_link_ids,
            hypothesis_support_ids=support_ids,
            provenance=provenance,
            support_role=candidate.support_role,
            created_at=created_at,
            source_assertion=candidate.assertion,
        )

    def _split_assertion_ids(self, conflict_run: ConflictResolutionRun) -> set[EntityId]:
        assertion_ids: set[EntityId] = set()
        split_sets = {
            conflict_set.conflict_set_id
            for conflict_set in conflict_run.conflict_sets
            if conflict_set.decision_type == ConflictDecisionType.COEXISTENCE_SPLIT
        }
        for member in conflict_run.members:
            if member.conflict_set_id in split_sets and member.source_assertion.status == AssertionStatus.ACCEPTED:
                assertion_ids.add(member.assertion_id)
        return assertion_ids

    def _links_by_assertion(self, evidence_links: tuple[AssertionEvidenceLink, ...]) -> dict[EntityId, tuple[AssertionEvidenceLink, ...]]:
        grouped: dict[EntityId, list[AssertionEvidenceLink]] = defaultdict(list)
        for link in evidence_links:
            grouped[link.assertion_id].append(link)
        return {
            assertion_id: tuple(sorted(links, key=self._link_sort_key))
            for assertion_id, links in grouped.items()
        }

    def _supports_for_fact(self, fact_id: EntityId, supports: tuple[FactSupport, ...]) -> tuple[FactSupport, ...]:
        return tuple(sorted((support for support in supports if support.fact_id == fact_id), key=self._support_sort_key))

    def _supports_for_facts(
        self,
        facts: tuple[ConsolidatedFact, ...],
        supports: tuple[FactSupport, ...],
    ) -> tuple[FactSupport, ...]:
        fact_ids = {fact.fact_id for fact in facts}
        return tuple(sorted((support for support in supports if support.fact_id in fact_ids), key=self._support_sort_key))

    def _links_for_supports(
        self,
        supports: tuple[FactSupport, ...],
        assertion_links: tuple[AssertionEvidenceLink, ...],
        existing_support_links: tuple[FactSupport, ...],
    ) -> tuple[AssertionEvidenceLink, ...]:
        link_map = {link.link_id: link for link in assertion_links}
        existing_assertions = {support.source_assertion.assertion_id: support.source_assertion for support in existing_support_links}
        for support in supports:
            assertion = existing_assertions.get(support.assertion_id, support.source_assertion)
            for link in self._assertion_links_from_assertion(assertion):
                link_map.setdefault(link.link_id, link)
        selected: list[AssertionEvidenceLink] = []
        for support in supports:
            selected.extend(link_map[link_id] for link_id in support.assertion_evidence_link_ids)
        return tuple(sorted(self._unique_links(selected), key=self._link_sort_key))

    def _assertion_links_from_assertion(self, assertion: EvidenceAssertion) -> tuple[AssertionEvidenceLink, ...]:
        if assertion.source_hypothesis.source_entity_candidate is not None:
            mention = assertion.source_hypothesis.source_entity_candidate.source_mention
            document_id = mention.document_id
            document_version_id = mention.version_id
            fragment_id = mention.fragment_id
            original_text = mention.original_text
            normalized_text = mention.normalized_text
            source_trace = mention.source_trace
        else:
            observation = assertion.source_hypothesis.source_relation_candidate.source_observation
            document_id = observation.document_id
            document_version_id = observation.version_id
            fragment_id = observation.fragment_id
            original_text = observation.original_text
            normalized_text = observation.normalized_text
            source_trace = observation.source_trace
        return tuple(
            AssertionEvidenceLink(
                link_id=link_id,
                assertion_id=assertion.assertion_id,
                hypothesis_id=assertion.source_hypothesis_id,
                support_id=support.support_id,
                document_id=document_id,
                document_version_id=document_version_id,
                fragment_id=fragment_id,
                evidence_role=support.support_kind.value,
                weight=assertion.score if support.support_kind.value == "candidate" else None,
                source_trace=source_trace,
                original_text=original_text,
                normalized_text=normalized_text,
            )
            for link_id, support in zip(assertion.evidence_link_ids, assertion.source_supports, strict=True)
        )

    def _existing_signature(self, supports: tuple[FactSupport, ...]) -> str:
        return "|".join(
            f"{support.assertion_id}:{','.join(str(link_id) for link_id in support.assertion_evidence_link_ids)}"
            for support in sorted(supports, key=self._support_sort_key)
        )

    def _candidate_signature(self, candidates: tuple[_FactCandidate, ...]) -> str:
        return "|".join(
            f"{candidate.assertion.assertion_id}:{','.join(str(link.link_id) for link in candidate.evidence_links)}"
            for candidate in sorted(candidates, key=self._candidate_sort_key)
        )

    def _family_key(self, candidate: _FactCandidate) -> tuple[str, str, str, str, str, str]:
        return (
            candidate.claim_key,
            candidate.scope,
            candidate.value_key,
            candidate.assertion.subject_table,
            str(candidate.assertion.subject_id),
            candidate.assertion.predicate_code,
        )

    def _lineage_key(self, candidate: _FactCandidate) -> str:
        return f"{candidate.claim_key}:{candidate.scope}:{candidate.value_key}:{candidate.assertion.subject_table}:{candidate.assertion.subject_id}:{candidate.assertion.predicate_code}"

    def _fact_lineage_key(self, fact: ConsolidatedFact) -> str:
        return f"{fact.claim_key}:{fact.scope}:{fact.value_key}:{fact.subject_table}:{fact.subject_id}:{fact.predicate_code}"

    def _active_revision(self, facts: tuple[ConsolidatedFact, ...]) -> ConsolidatedFact | None:
        active = [fact for fact in facts if fact.active_revision]
        if not active:
            return None
        if len(active) > 1:
            raise ConflictError(
                code="multiple_active_fact_revisions",
                message="Fact consolidation requires at most one active revision per lineage",
                context={"fact_ids": tuple(sorted(str(fact.fact_id) for fact in active))},
            )
        return active[0]

    def _validate_active_revisions(self, existing_facts: tuple[ConsolidatedFact, ...]) -> None:
        lineages: dict[str, list[ConsolidatedFact]] = defaultdict(list)
        for fact in existing_facts:
            lineages[self._fact_lineage_key(fact)].append(fact)
        for facts in lineages.values():
            self._active_revision(tuple(facts))

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

    def _scope_key(self, assertion: EvidenceAssertion) -> str:
        document_id, version_id = self._scope_ids(assertion)
        return f"{document_id}:{version_id}"

    def _group_scope_key(self, assertion: EvidenceAssertion) -> str:
        document_id, _ = self._scope_ids(assertion)
        return str(document_id)

    def _value_key(self, assertion: EvidenceAssertion) -> str:
        if assertion.predicate_code == "explicit_scaling":
            attributes = dict(assertion.literal_value)
            engineering_value = attributes.get("engineering_value", "")
            engineering_unit = attributes.get("normalized_engineering_unit_code") or attributes.get("engineering_unit", "")
            return f"{engineering_value}:{engineering_unit}"
        if assertion.object_id is not None:
            return f"{assertion.object_table}:{assertion.object_id}"
        return "literal:" + "|".join(f"{key}={value}" for key, value in assertion.literal_value)

    def _scope_ids(self, assertion: EvidenceAssertion) -> tuple[EntityId, EntityId]:
        if assertion.source_hypothesis.source_entity_candidate is not None:
            mention = assertion.source_hypothesis.source_entity_candidate.source_mention
            return mention.document_id, mention.version_id
        observation = assertion.source_hypothesis.source_relation_candidate.source_observation
        return observation.document_id, observation.version_id

    def _unique_assertions(self, assertions: list[EvidenceAssertion]) -> tuple[EvidenceAssertion, ...]:
        unique: dict[EntityId, EvidenceAssertion] = {}
        for assertion in assertions:
            unique.setdefault(assertion.assertion_id, assertion)
        return tuple(unique.values())

    def _unique_links(self, links: list[AssertionEvidenceLink]) -> tuple[AssertionEvidenceLink, ...]:
        unique: dict[EntityId, AssertionEvidenceLink] = {}
        for link in links:
            unique.setdefault(link.link_id, link)
        return tuple(unique.values())

    def _assertion_sort_key(self, assertion: EvidenceAssertion) -> tuple[str, str]:
        return (assertion.predicate_code, str(assertion.assertion_id))

    def _candidate_sort_key(self, candidate: _FactCandidate) -> tuple[str, str, str, str]:
        return (candidate.claim_key, candidate.scope, candidate.value_key, str(candidate.assertion.assertion_id))

    def _fact_sort_key(self, fact: ConsolidatedFact) -> tuple[str, str, str, int, str]:
        return (fact.claim_key, fact.scope, fact.value_key, fact.version, str(fact.fact_id))

    def _existing_fact_sort_key(self, fact: ConsolidatedFact) -> tuple[int, str]:
        return (fact.version, str(fact.fact_id))

    def _support_sort_key(self, support: FactSupport) -> tuple[str, str, str]:
        return (str(support.fact_id), support.support_role.value, str(support.fact_support_id))

    def _link_sort_key(self, link: AssertionEvidenceLink) -> tuple[str, str]:
        return (str(link.assertion_id), str(link.link_id))