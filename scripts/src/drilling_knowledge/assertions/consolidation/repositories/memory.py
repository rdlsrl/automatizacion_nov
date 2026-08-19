"""In-memory repository for fact consolidation runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactConsolidationRun, FactLifecycle, FactSupport, FactSupportRole
from drilling_knowledge.assertions.consolidation.repositories.contracts import FactConsolidationRunRepository
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionStatus, EvidenceAssertion
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId


@dataclass(frozen=True, slots=True)
class InMemoryFactConsolidationRunRepository(FactConsolidationRunRepository):
    runs: tuple[FactConsolidationRun, ...] = ()
    _runs_by_id: dict[RunId, FactConsolidationRun] = field(init=False, default_factory=dict)
    _assertions_by_run: dict[RunId, tuple[EvidenceAssertion, ...]] = field(init=False, default_factory=dict)
    _links_by_run: dict[RunId, tuple[AssertionEvidenceLink, ...]] = field(init=False, default_factory=dict)
    _facts_by_run: dict[RunId, tuple[ConsolidatedFact, ...]] = field(init=False, default_factory=dict)
    _supports_by_run: dict[RunId, tuple[FactSupport, ...]] = field(init=False, default_factory=dict)
    _facts_by_id: dict[EntityId, ConsolidatedFact] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, FactConsolidationRun] = {}
        assertions_by_run: dict[RunId, tuple[EvidenceAssertion, ...]] = {}
        links_by_run: dict[RunId, tuple[AssertionEvidenceLink, ...]] = {}
        facts_by_run: dict[RunId, tuple[ConsolidatedFact, ...]] = {}
        supports_by_run: dict[RunId, tuple[FactSupport, ...]] = {}
        facts_by_id: dict[EntityId, ConsolidatedFact] = {}
        lineage_facts: dict[tuple[str, str, str, str, str, str], list[ConsolidatedFact]] = defaultdict(list)
        ordered = self.runs
        for run in ordered:
            existing = runs_by_id.get(run.run_id)
            if existing is not None and existing != run:
                raise ConflictError(
                    code="duplicate_fact_consolidation_run",
                    message="A different fact consolidation run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            self._validate_references(run)
            runs_by_id[run.run_id] = run
            assertions_by_run[run.run_id] = run.assertions
            links_by_run[run.run_id] = run.evidence_links
            facts_by_run[run.run_id] = run.facts
            supports_by_run[run.run_id] = run.support_links
            for fact in run.facts:
                existing_fact = facts_by_id.get(fact.fact_id)
                if existing_fact is not None:
                    self._validate_fact_transition(existing_fact, fact)
                facts_by_id[fact.fact_id] = fact
                lineage_facts[self._lineage_key(fact)].append(fact)
            self._validate_active_lineages(facts_by_id.values())
        object.__setattr__(self, "runs", ordered)
        object.__setattr__(self, "_runs_by_id", runs_by_id)
        object.__setattr__(self, "_assertions_by_run", assertions_by_run)
        object.__setattr__(self, "_links_by_run", links_by_run)
        object.__setattr__(self, "_facts_by_run", facts_by_run)
        object.__setattr__(self, "_supports_by_run", supports_by_run)
        object.__setattr__(self, "_facts_by_id", facts_by_id)

    def get_run(self, run_id: RunId) -> FactConsolidationRun | None:
        return self._runs_by_id.get(run_id)

    def list_runs(self) -> tuple[FactConsolidationRun, ...]:
        return self.runs

    def list_assertions(self, run_id: RunId) -> tuple[EvidenceAssertion, ...]:
        return self._assertions_by_run.get(run_id, ())

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        return self._links_by_run.get(run_id, ())

    def list_facts(self, run_id: RunId) -> tuple[ConsolidatedFact, ...]:
        return self._facts_by_run.get(run_id, ())

    def list_support_links(self, run_id: RunId) -> tuple[FactSupport, ...]:
        return self._supports_by_run.get(run_id, ())

    def get_fact(self, fact_id: EntityId) -> ConsolidatedFact | None:
        return self._facts_by_id.get(fact_id)

    def append_run(self, run: FactConsolidationRun) -> "InMemoryFactConsolidationRunRepository":
        existing = self._runs_by_id.get(run.run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_fact_consolidation_run",
                    message="A different fact consolidation run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            return self
        return InMemoryFactConsolidationRunRepository(self.runs + (run,))

    def _validate_references(self, run: FactConsolidationRun) -> None:
        assertion_ids = {assertion.assertion_id for assertion in run.assertions}
        links_by_id = {link.link_id: link for link in run.evidence_links}
        facts_by_id = {fact.fact_id: fact for fact in run.facts}
        support_ids: set[EntityId] = set()
        supports_by_fact: dict[EntityId, list[FactSupport]] = defaultdict(list)
        versions_by_lineage: dict[tuple[str, str, str, str, str, str], set[int]] = defaultdict(set)

        for fact in run.facts:
            lineage_key = (fact.claim_key, fact.scope, fact.value_key, fact.subject_table, str(fact.subject_id), fact.predicate_code)
            if fact.version in versions_by_lineage[lineage_key]:
                raise ConflictError(
                    code="duplicate_fact_lineage_version",
                    message="Consolidated facts cannot reuse the same version within one lineage",
                    context={"fact_id": str(fact.fact_id), "version": str(fact.version)},
                )
            versions_by_lineage[lineage_key].add(fact.version)

        for support in run.support_links:
            if support.fact_support_id in support_ids:
                raise ConflictError(
                    code="duplicate_fact_support",
                    message="Fact support links cannot reuse the same fact_support_id",
                    context={"fact_support_id": str(support.fact_support_id)},
                )
            support_ids.add(support.fact_support_id)
            if support.fact_id not in facts_by_id:
                raise ConflictError(
                    code="fact_support_missing_fact",
                    message="Fact support references an unknown fact id",
                    context={"fact_id": str(support.fact_id)},
                )
            if support.assertion_id not in assertion_ids:
                raise ConflictError(
                    code="fact_support_missing_assertion",
                    message="Fact support references an unknown assertion id",
                    context={"assertion_id": str(support.assertion_id)},
                )
            if support.source_assertion.status != AssertionStatus.ACCEPTED:
                raise ConflictError(
                    code="fact_support_requires_accepted_assertion",
                    message="Facts can only be created from accepted assertions",
                    context={"assertion_id": str(support.assertion_id), "status": support.source_assertion.status.value},
                )
            source_support_ids = {item.support_id for item in support.source_assertion.source_supports}
            if set(support.hypothesis_support_ids) != source_support_ids:
                raise ConflictError(
                    code="fact_support_hypothesis_support_mismatch",
                    message="Fact support must preserve all hypothesis supports of the source assertion",
                    context={"fact_support_id": str(support.fact_support_id)},
                )
            if not set(support.assertion_evidence_link_ids).issubset(links_by_id):
                raise ConflictError(
                    code="fact_support_missing_evidence_link",
                    message="Fact support references an unknown assertion evidence link id",
                    context={"fact_support_id": str(support.fact_support_id)},
                )
            expected_provenance = {
                (links_by_id[link_id].document_id, links_by_id[link_id].document_version_id, links_by_id[link_id].fragment_id)
                for link_id in support.assertion_evidence_link_ids
            }
            actual_provenance = {(item.document_id, item.document_version_id, item.fragment_id) for item in support.provenance}
            if actual_provenance != expected_provenance:
                raise ConflictError(
                    code="fact_support_provenance_mismatch",
                    message="Fact support provenance must match the linked assertion evidence provenance",
                    context={"fact_support_id": str(support.fact_support_id)},
                )
            supports_by_fact[support.fact_id].append(support)

        for fact in run.facts:
            supports = tuple(sorted(supports_by_fact.get(fact.fact_id, ()), key=self._support_sort_key))
            if not supports:
                raise ConflictError(
                    code="fact_missing_support",
                    message="Consolidated facts must reference at least one support link",
                    context={"fact_id": str(fact.fact_id)},
                )
            support_ids_for_fact = {support.fact_support_id for support in supports}
            if support_ids_for_fact != set(fact.support_link_ids):
                raise ConflictError(
                    code="fact_support_set_mismatch",
                    message="Consolidated facts must match the persisted support link collection",
                    context={"fact_id": str(fact.fact_id)},
                )
            if fact.active_revision and fact.lifecycle != FactLifecycle.ACTIVE:
                raise ConflictError(
                    code="fact_active_revision_invalid",
                    message="Active fact revisions must have active lifecycle",
                    context={"fact_id": str(fact.fact_id)},
                )
            if fact.lifecycle == FactLifecycle.SUPERSEDED and fact.active_revision:
                raise ConflictError(
                    code="superseded_fact_cannot_be_active",
                    message="Superseded fact revisions cannot remain active",
                    context={"fact_id": str(fact.fact_id)},
                )
            if fact.version > 1 and fact.supersedes_fact_id is None:
                raise ConflictError(
                    code="fact_missing_supersedes_link",
                    message="Versioned fact revisions after v1 must reference supersedes_fact_id",
                    context={"fact_id": str(fact.fact_id), "version": str(fact.version)},
                )

    @staticmethod
    def _validate_fact_transition(previous: ConsolidatedFact, current: ConsolidatedFact) -> None:
        if previous == current:
            return
        same_revision_identity = (
            previous.claim_key == current.claim_key
            and previous.scope == current.scope
            and previous.value_key == current.value_key
            and previous.subject_table == current.subject_table
            and previous.subject_id == current.subject_id
            and previous.predicate_code == current.predicate_code
            and previous.version == current.version
            and previous.supersedes_fact_id == current.supersedes_fact_id
            and previous.support_link_ids == current.support_link_ids
        )
        valid_supersession = (
            same_revision_identity
            and previous.lifecycle == FactLifecycle.ACTIVE
            and previous.active_revision
            and current.lifecycle == FactLifecycle.SUPERSEDED
            and not current.active_revision
            and current.created_at == previous.created_at
            and current.updated_at >= previous.updated_at
        )
        if not valid_supersession:
            raise ConflictError(
                code="duplicate_consolidated_fact",
                message="A different consolidated fact already exists for the same fact id",
                context={"fact_id": str(current.fact_id)},
            )

    @staticmethod
    def _validate_active_lineages(facts: object) -> None:
        lineages: dict[tuple[str, str, str, str, str, str], list[ConsolidatedFact]] = defaultdict(list)
        for fact in facts:
            lineages[InMemoryFactConsolidationRunRepository._lineage_key(fact)].append(fact)
        for lineage_key, lineage_facts in lineages.items():
            active = [fact for fact in lineage_facts if fact.active_revision]
            if len(active) > 1:
                raise ConflictError(
                    code="multiple_active_fact_revisions",
                    message="Only one active fact revision is allowed per lineage",
                    context={"lineage": lineage_key, "fact_ids": tuple(sorted(str(fact.fact_id) for fact in active))},
                )

    @staticmethod
    def _lineage_key(fact: ConsolidatedFact) -> tuple[str, str, str, str, str, str]:
        return (fact.claim_key, fact.scope, fact.value_key, fact.subject_table, str(fact.subject_id), fact.predicate_code)

    @staticmethod
    def _sort_key(run: FactConsolidationRun) -> tuple[str, str]:
        return (run.finished_at.isoformat(), str(run.run_id))

    @staticmethod
    def _support_sort_key(support: FactSupport) -> tuple[str, str]:
        return (str(support.fact_id), str(support.fact_support_id))