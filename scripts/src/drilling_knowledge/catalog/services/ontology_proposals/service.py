"""Deterministic ontology proposal generation over existing evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactConsolidationRun, FactSupport
from drilling_knowledge.assertions.conflict_resolution.domain import AssertionConflictSet, ConflictResolutionRun
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionReviewState, EvidenceAssertion
from drilling_knowledge.catalog.services.ontology_proposals.domain import (
    OntologyChangeProposal,
    OntologyProposalEvidence,
    OntologyProposalMetrics,
    OntologyProposalProvenance,
    OntologyProposalRun,
    OntologyProposalRunOutcome,
    OntologyProposalStatus,
)
from drilling_knowledge.catalog.services.ontology_proposals.repositories.contracts import OntologyProposalRunRepository
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.normalization.domain import NormalizationCandidateStatus, NormalizationRun, NormalizedEntityCandidate


@dataclass(frozen=True, slots=True)
class _ProposalEvidenceGroup:
    trigger: str
    group_key: str
    facts: tuple[ConsolidatedFact, ...]
    supports: tuple[FactSupport, ...]
    assertions: tuple[EvidenceAssertion, ...]
    conflict_sets: tuple[AssertionConflictSet, ...]
    evidence_links: tuple[AssertionEvidenceLink, ...]
    normalization_candidates: tuple[NormalizedEntityCandidate, ...] = ()


@dataclass(slots=True)
class OntologyProposalGenerator:
    pattern_threshold: int
    conflict_threshold: int
    manual_decision_threshold: int
    rule_pack_version: str = "ontology.proposal.rules.v1"

    @classmethod
    def create(
        cls,
        *,
        pattern_threshold: int = 2,
        conflict_threshold: int = 2,
        manual_decision_threshold: int = 2,
    ) -> "OntologyProposalGenerator":
        return cls(
            pattern_threshold=pattern_threshold,
            conflict_threshold=conflict_threshold,
            manual_decision_threshold=manual_decision_threshold,
        )

    def generate(
        self,
        fact_run: FactConsolidationRun,
        conflict_run: ConflictResolutionRun,
        *,
        normalization_run: NormalizationRun | None = None,
        existing_proposals: tuple[OntologyChangeProposal, ...] = (),
        existing_proposal_evidences: tuple[OntologyProposalEvidence, ...] = (),
    ) -> OntologyProposalRun:
        self._validate_inputs(fact_run, conflict_run, normalization_run, existing_proposals, existing_proposal_evidences)
        created_at = max(fact_run.finished_at, conflict_run.finished_at)
        assertions = tuple(sorted(fact_run.assertions, key=self._assertion_sort_key))
        evidence_links = tuple(sorted(fact_run.evidence_links, key=self._link_sort_key))
        facts = tuple(sorted(fact_run.facts, key=self._fact_sort_key))
        fact_supports = tuple(sorted(fact_run.support_links, key=self._support_sort_key))
        active_facts = tuple(fact for fact in facts if fact.active_revision)
        supports_by_fact = self._supports_by_fact(fact_supports)
        supports_by_assertion = self._supports_by_assertion(fact_supports)
        facts_by_assertion = self._facts_by_assertion(facts, fact_supports)
        links_by_assertion = self._links_by_assertion(evidence_links)

        proposal_groups = (
            self._pattern_groups(active_facts, supports_by_fact, links_by_assertion)
            + self._unresolved_pattern_groups(normalization_run)
            + self._conflict_groups(conflict_run, facts_by_assertion, supports_by_assertion, links_by_assertion)
            + self._manual_decision_groups(assertions, facts_by_assertion, supports_by_assertion, links_by_assertion)
        )
        grouped = tuple(sorted(proposal_groups, key=lambda item: (item.trigger, item.group_key)))

        proposals = list(existing_proposals)
        evidences = list(existing_proposal_evidences)
        existing_proposal_by_id = {proposal.proposal_id: proposal for proposal in existing_proposals}
        existing_evidence_by_id = {evidence.proposal_evidence_id: evidence for evidence in existing_proposal_evidences}
        for group in grouped:
            proposal, evidence = self._build_group_outputs(group, created_at)
            stored_evidence = existing_evidence_by_id.get(evidence.proposal_evidence_id, evidence)
            stored_proposal = existing_proposal_by_id.get(proposal.proposal_id, proposal)
            if stored_evidence.proposal_evidence_id not in {item.proposal_evidence_id for item in evidences}:
                evidences.append(stored_evidence)
            if stored_proposal.proposal_id not in {item.proposal_id for item in proposals}:
                proposals.append(stored_proposal)

        ordered_proposals = tuple(sorted(proposals, key=self._proposal_sort_key))
        ordered_evidences = tuple(sorted(evidences, key=self._proposal_evidence_sort_key))
        outcome = OntologyProposalRunOutcome.PROPOSAL_QUEUED if ordered_proposals else OntologyProposalRunOutcome.NO_OP
        generated_signatures = {
            (group.trigger, group.group_key)
            for group in grouped
        }
        metrics = OntologyProposalMetrics(
            proposed_normalization_candidates=self._proposed_candidate_count(normalization_run),
            recurring_pattern_groups=sum(1 for group in grouped if group.trigger == "recurring_pattern"),
            recurring_conflict_groups=sum(1 for group in grouped if group.trigger == "recurring_conflict"),
            repeated_manual_decision_groups=sum(1 for group in grouped if group.trigger == "repeated_manual_decision"),
            proposals_created=len(generated_signatures),
            proposals_reused=0,
            no_op_outputs=1 if outcome == OntologyProposalRunOutcome.NO_OP else 0,
        )
        return OntologyProposalRun(
            run_id=RunId.from_seed(
                "ontology.proposal.run",
                "|".join(
                    (
                        str(fact_run.run_id),
                        str(conflict_run.run_id),
                        str(normalization_run.run_id) if normalization_run is not None else "none",
                        outcome.value,
                        "|".join(str(proposal.proposal_id) for proposal in ordered_proposals),
                    )
                ),
            ),
            fact_consolidation_run_id=fact_run.run_id,
            conflict_resolution_run_id=conflict_run.run_id,
            normalization_run_id=normalization_run.run_id if normalization_run is not None else None,
            rule_pack_version=self.rule_pack_version,
            started_at=min(fact_run.started_at, conflict_run.started_at),
            finished_at=created_at,
            outcome=outcome,
            normalization_run=normalization_run,
            normalization_candidates=tuple(sorted(self._proposed_candidates(normalization_run), key=self._candidate_sort_key)),
            assertions=assertions,
            evidence_links=evidence_links,
            facts=facts,
            fact_supports=fact_supports,
            conflict_sets=tuple(sorted(conflict_run.conflict_sets, key=self._conflict_sort_key)),
            proposals=ordered_proposals,
            proposal_evidences=ordered_evidences,
            metrics=metrics,
        )

    def generate_and_persist(
        self,
        fact_run: FactConsolidationRun,
        conflict_run: ConflictResolutionRun,
        repository: OntologyProposalRunRepository,
        *,
        normalization_run: NormalizationRun | None = None,
        existing_proposals: tuple[OntologyChangeProposal, ...] | None = None,
        existing_proposal_evidences: tuple[OntologyProposalEvidence, ...] | None = None,
    ) -> tuple[OntologyProposalRun, OntologyProposalRunRepository]:
        latest = repository.list_runs()[-1] if repository.list_runs() else None
        run = self.generate(
            fact_run,
            conflict_run,
            normalization_run=normalization_run,
            existing_proposals=existing_proposals if existing_proposals is not None else (latest.proposals if latest is not None else ()),
            existing_proposal_evidences=(
                existing_proposal_evidences if existing_proposal_evidences is not None else (latest.proposal_evidences if latest is not None else ())
            ),
        )
        return run, repository.append_run(run)

    def _validate_inputs(
        self,
        fact_run: FactConsolidationRun,
        conflict_run: ConflictResolutionRun,
        normalization_run: NormalizationRun | None,
        existing_proposals: tuple[OntologyChangeProposal, ...],
        existing_proposal_evidences: tuple[OntologyProposalEvidence, ...],
    ) -> None:
        if self.pattern_threshold < 2:
            raise ValueError("OntologyProposalGenerator.pattern_threshold must be >= 2")
        if self.conflict_threshold < 2:
            raise ValueError("OntologyProposalGenerator.conflict_threshold must be >= 2")
        if self.manual_decision_threshold < 2:
            raise ValueError("OntologyProposalGenerator.manual_decision_threshold must be >= 2")
        if fact_run.assertion_run_id != conflict_run.assertion_run_id:
            raise ConflictError(
                code="ontology_proposal_input_mismatch",
                message="Fact consolidation and conflict resolution runs must originate from the same assertion run",
                context={"fact_run_id": str(fact_run.run_id), "conflict_run_id": str(conflict_run.run_id)},
            )
        proposal_ids = {proposal.proposal_id for proposal in existing_proposals}
        if len(proposal_ids) != len(existing_proposals):
            raise ConflictError(
                code="duplicate_existing_ontology_proposal",
                message="Existing ontology proposals cannot contain duplicate proposal ids",
                context={},
            )
        evidence_ids = {evidence.proposal_evidence_id for evidence in existing_proposal_evidences}
        if len(evidence_ids) != len(existing_proposal_evidences):
            raise ConflictError(
                code="duplicate_existing_ontology_proposal_evidence",
                message="Existing ontology proposal evidences cannot contain duplicate proposal_evidence_ids",
                context={},
            )
        evidence_proposal_ids = {evidence.proposal_id for evidence in existing_proposal_evidences}
        if not evidence_proposal_ids.issubset(proposal_ids):
            raise ConflictError(
                code="existing_proposal_evidence_missing_proposal",
                message="Existing ontology proposal evidences must resolve to existing proposals",
                context={},
            )
        if normalization_run is not None and normalization_run.finished_at < normalization_run.started_at:
            raise ValueError("NormalizationRun.finished_at cannot be before started_at")

    def _pattern_groups(
        self,
        facts: tuple[ConsolidatedFact, ...],
        supports_by_fact: dict[EntityId, tuple[FactSupport, ...]],
        links_by_assertion: dict[EntityId, tuple[AssertionEvidenceLink, ...]],
    ) -> tuple[_ProposalEvidenceGroup, ...]:
        grouped: dict[tuple[str, str, str, str], list[ConsolidatedFact]] = defaultdict(list)
        for fact in facts:
            grouped[(fact.claim_key, fact.predicate_code, fact.object_table or "", str(fact.object_id) if fact.object_id is not None else self._literal_key(fact.literal_value))].append(fact)
        groups: list[_ProposalEvidenceGroup] = []
        for key, pattern_facts in grouped.items():
            unique_subjects = {fact.subject_id for fact in pattern_facts}
            if len(unique_subjects) < self.pattern_threshold:
                continue
            supports = tuple(sorted({support for fact in pattern_facts for support in supports_by_fact.get(fact.fact_id, ())}, key=self._support_sort_key))
            assertions = tuple(sorted({support.source_assertion for support in supports}, key=self._assertion_sort_key))
            links = tuple(sorted({link for assertion in assertions for link in links_by_assertion.get(assertion.assertion_id, ())}, key=self._link_sort_key))
            groups.append(
                _ProposalEvidenceGroup(
                    trigger="recurring_pattern",
                    group_key="|".join(key),
                    facts=tuple(sorted(pattern_facts, key=self._fact_sort_key)),
                    supports=supports,
                    assertions=assertions,
                    conflict_sets=(),
                    evidence_links=links,
                )
            )
        return tuple(groups)

    def _conflict_groups(
        self,
        conflict_run: ConflictResolutionRun,
        facts_by_assertion: dict[EntityId, tuple[ConsolidatedFact, ...]],
        supports_by_assertion: dict[EntityId, tuple[FactSupport, ...]],
        links_by_assertion: dict[EntityId, tuple[AssertionEvidenceLink, ...]],
    ) -> tuple[_ProposalEvidenceGroup, ...]:
        grouped: dict[tuple[str, str], list[AssertionConflictSet]] = defaultdict(list)
        for conflict_set in conflict_run.conflict_sets:
            key = (conflict_set.claim_key, conflict_set.decision_reason or (conflict_set.decision_type.value if conflict_set.decision_type is not None else conflict_set.status.value))
            grouped[key].append(conflict_set)
        groups: list[_ProposalEvidenceGroup] = []
        for key, conflict_sets in grouped.items():
            if len(conflict_sets) < self.conflict_threshold:
                continue
            assertion_ids = {member.assertion_id for conflict_set in conflict_sets for member in conflict_set.members}
            supports = tuple(sorted({support for assertion_id in assertion_ids for support in supports_by_assertion.get(assertion_id, ())}, key=self._support_sort_key))
            facts = tuple(sorted({fact for assertion_id in assertion_ids for fact in facts_by_assertion.get(assertion_id, ()) if fact.active_revision}, key=self._fact_sort_key))
            if not facts or not supports:
                continue
            assertions = tuple(sorted({support.source_assertion for support in supports}, key=self._assertion_sort_key))
            links = tuple(sorted({link for assertion in assertions for link in links_by_assertion.get(assertion.assertion_id, ())}, key=self._link_sort_key))
            groups.append(
                _ProposalEvidenceGroup(
                    trigger="recurring_conflict",
                    group_key="|".join(key),
                    facts=facts,
                    supports=supports,
                    assertions=assertions,
                    conflict_sets=tuple(sorted(conflict_sets, key=self._conflict_sort_key)),
                    evidence_links=links,
                )
            )
        return tuple(groups)

    def _unresolved_pattern_groups(self, normalization_run: NormalizationRun | None) -> tuple[_ProposalEvidenceGroup, ...]:
        if normalization_run is None:
            return ()
        grouped: dict[tuple[str, str], list[NormalizedEntityCandidate]] = defaultdict(list)
        for candidate in self._proposed_candidates(normalization_run):
            grouped[(candidate.entity_type.value, candidate.canonical_text)].append(candidate)
        groups: list[_ProposalEvidenceGroup] = []
        for key, candidates in grouped.items():
            if len(candidates) < self.pattern_threshold:
                continue
            groups.append(
                _ProposalEvidenceGroup(
                    trigger="recurring_pattern",
                    group_key="unresolved|" + "|".join(key),
                    facts=(),
                    supports=(),
                    assertions=(),
                    conflict_sets=(),
                    evidence_links=(),
                    normalization_candidates=tuple(sorted(candidates, key=self._candidate_sort_key)),
                )
            )
        return tuple(groups)

    def _manual_decision_groups(
        self,
        assertions: tuple[EvidenceAssertion, ...],
        facts_by_assertion: dict[EntityId, tuple[ConsolidatedFact, ...]],
        supports_by_assertion: dict[EntityId, tuple[FactSupport, ...]],
        links_by_assertion: dict[EntityId, tuple[AssertionEvidenceLink, ...]],
    ) -> tuple[_ProposalEvidenceGroup, ...]:
        grouped: dict[tuple[str, str, str, str, str], list[EvidenceAssertion]] = defaultdict(list)
        for assertion in assertions:
            if assertion.review_state not in {AssertionReviewState.APPROVED, AssertionReviewState.REJECTED}:
                continue
            grouped[
                (
                    assertion.predicate_code,
                    assertion.object_table or "",
                    str(assertion.object_id) if assertion.object_id is not None else self._literal_key(assertion.literal_value),
                    assertion.review_state.value,
                    assertion.status.value,
                )
            ].append(assertion)
        groups: list[_ProposalEvidenceGroup] = []
        for key, manual_assertions in grouped.items():
            if len(manual_assertions) < self.manual_decision_threshold:
                continue
            supports = tuple(sorted({support for assertion in manual_assertions for support in supports_by_assertion.get(assertion.assertion_id, ())}, key=self._support_sort_key))
            facts = tuple(sorted({fact for assertion in manual_assertions for fact in facts_by_assertion.get(assertion.assertion_id, ()) if fact.active_revision}, key=self._fact_sort_key))
            if not facts or not supports:
                continue
            links = tuple(sorted({link for assertion in manual_assertions for link in links_by_assertion.get(assertion.assertion_id, ())}, key=self._link_sort_key))
            groups.append(
                _ProposalEvidenceGroup(
                    trigger="repeated_manual_decision",
                    group_key="|".join(key),
                    facts=facts,
                    supports=supports,
                    assertions=tuple(sorted(manual_assertions, key=self._assertion_sort_key)),
                    conflict_sets=(),
                    evidence_links=links,
                )
            )
        return tuple(groups)

    def _build_group_outputs(self, group: _ProposalEvidenceGroup, created_at: datetime) -> tuple[OntologyChangeProposal, OntologyProposalEvidence]:
        evidence_bundle = tuple(sorted(self._evidence_bundle_ids(group), key=str))
        fact_ids = tuple(sorted((fact.fact_id for fact in group.facts), key=str))
        support_ids = tuple(sorted((support.fact_support_id for support in group.supports), key=str))
        assertion_ids = tuple(sorted((assertion.assertion_id for assertion in group.assertions), key=str))
        conflict_ids = tuple(sorted((conflict_set.conflict_set_id for conflict_set in group.conflict_sets), key=str))
        evidence_id = EntityId.from_seed(
            "semantic.ontology_change_proposal.evidence",
            "|".join((group.trigger, group.group_key, "|".join(str(item) for item in fact_ids), "|".join(str(item) for item in conflict_ids), "|".join(str(item) for item in evidence_bundle))),
        )
        proposal_id = EntityId.from_seed(
            "semantic.ontology_change_proposal",
            "|".join((group.trigger, group.group_key, str(evidence_id))),
        )
        evidence = OntologyProposalEvidence(
            proposal_evidence_id=evidence_id,
            proposal_id=proposal_id,
            consolidated_fact_ids=fact_ids,
            fact_support_ids=support_ids,
            conflict_set_ids=conflict_ids,
            assertion_ids=assertion_ids,
            evidence_bundle=evidence_bundle,
            provenance=self._provenance(group),
        )
        proposal = OntologyChangeProposal(
            proposal_id=proposal_id,
            proposal_type=group.trigger,
            proposal_status=OntologyProposalStatus.QUEUED,
            target_entity=self._target_entity(group),
            proposed_change=(
                ("output", "ontology_change_proposal"),
                ("policy", "queued_only"),
                ("trigger", group.trigger),
            ),
            rationale=self._rationale(group),
            impact_summary=self._impact_summary(group),
            created_at=created_at,
            revision=1,
            evidence_ids=(evidence_id,),
        )
        return proposal, evidence

    def _target_entity(self, group: _ProposalEvidenceGroup) -> tuple[tuple[str, str], ...]:
        if group.normalization_candidates:
            first_candidate = group.normalization_candidates[0]
            return (
                ("candidate_entity_type", first_candidate.entity_type.value),
                ("canonical_text", first_candidate.canonical_text),
                ("trigger_group", group.group_key),
            )
        first_fact = group.facts[0]
        target = [
            ("claim_key", first_fact.claim_key),
            ("predicate_code", first_fact.predicate_code),
            ("subject_table", first_fact.subject_table),
            ("trigger_group", group.group_key),
        ]
        if first_fact.object_table is not None and first_fact.object_id is not None:
            target.append(("object_table", first_fact.object_table))
            target.append(("object_id", str(first_fact.object_id)))
        else:
            target.append(("literal_value", self._literal_key(first_fact.literal_value)))
        return tuple(target)

    def _rationale(self, group: _ProposalEvidenceGroup) -> str:
        return (
            f"trigger={group.trigger}; facts={len(group.facts)}; supports={len(group.supports)}; "
            f"assertions={len(group.assertions)}; conflicts={len(group.conflict_sets)}; links={len(group.evidence_links)}; "
            f"normalization_candidates={len(group.normalization_candidates)}"
        )

    def _impact_summary(self, group: _ProposalEvidenceGroup) -> tuple[tuple[str, str], ...]:
        return (
            ("fact_count", str(len(group.facts))),
            ("support_count", str(len(group.supports))),
            ("assertion_count", str(len(group.assertions))),
            ("conflict_count", str(len(group.conflict_sets))),
            ("evidence_link_count", str(len(group.evidence_links))),
            ("normalization_candidate_count", str(len(group.normalization_candidates))),
            ("document_count", str(len(self._document_ids(group)))),
        )

    def _evidence_bundle_ids(self, group: _ProposalEvidenceGroup) -> tuple[EntityId, ...]:
        if group.normalization_candidates:
            return tuple(candidate.candidate_id for candidate in group.normalization_candidates)
        return tuple(link.link_id for link in group.evidence_links)

    def _provenance(self, group: _ProposalEvidenceGroup) -> tuple[OntologyProposalProvenance, ...]:
        items = {
            OntologyProposalProvenance(
                document_id=link.document_id,
                document_version_id=link.document_version_id,
                fragment_id=link.fragment_id,
            )
            for link in group.evidence_links
        }
        items.update(
            OntologyProposalProvenance(
                document_id=candidate.source_mention.document_id,
                document_version_id=candidate.source_mention.version_id,
                fragment_id=candidate.source_mention.fragment_id,
            )
            for candidate in group.normalization_candidates
        )
        return tuple(sorted(items, key=lambda item: (str(item.document_id), str(item.document_version_id), str(item.fragment_id))))

    def _document_ids(self, group: _ProposalEvidenceGroup) -> set[EntityId]:
        document_ids = {link.document_id for link in group.evidence_links}
        document_ids.update(candidate.source_mention.document_id for candidate in group.normalization_candidates)
        return document_ids

    def _proposed_candidates(self, normalization_run: NormalizationRun | None):
        if normalization_run is None:
            return ()
        return tuple(candidate for candidate in normalization_run.entity_candidates if candidate.status == NormalizationCandidateStatus.PROPOSED)

    def _proposed_candidate_count(self, normalization_run: NormalizationRun | None) -> int:
        return len(self._proposed_candidates(normalization_run))

    def _supports_by_fact(self, supports: tuple[FactSupport, ...]) -> dict[EntityId, tuple[FactSupport, ...]]:
        grouped: dict[EntityId, list[FactSupport]] = defaultdict(list)
        for support in supports:
            grouped[support.fact_id].append(support)
        return {fact_id: tuple(sorted(items, key=self._support_sort_key)) for fact_id, items in grouped.items()}

    def _supports_by_assertion(self, supports: tuple[FactSupport, ...]) -> dict[EntityId, tuple[FactSupport, ...]]:
        grouped: dict[EntityId, list[FactSupport]] = defaultdict(list)
        for support in supports:
            grouped[support.assertion_id].append(support)
        return {assertion_id: tuple(sorted(items, key=self._support_sort_key)) for assertion_id, items in grouped.items()}

    def _facts_by_assertion(self, facts: tuple[ConsolidatedFact, ...], supports: tuple[FactSupport, ...]) -> dict[EntityId, tuple[ConsolidatedFact, ...]]:
        facts_by_id = {fact.fact_id: fact for fact in facts}
        grouped: dict[EntityId, list[ConsolidatedFact]] = defaultdict(list)
        for support in supports:
            grouped[support.assertion_id].append(facts_by_id[support.fact_id])
        return {assertion_id: tuple(sorted({*items}, key=self._fact_sort_key)) for assertion_id, items in grouped.items()}

    def _links_by_assertion(self, links: tuple[AssertionEvidenceLink, ...]) -> dict[EntityId, tuple[AssertionEvidenceLink, ...]]:
        grouped: dict[EntityId, list[AssertionEvidenceLink]] = defaultdict(list)
        for link in links:
            grouped[link.assertion_id].append(link)
        return {assertion_id: tuple(sorted(items, key=self._link_sort_key)) for assertion_id, items in grouped.items()}

    @staticmethod
    def _literal_key(literal_value: tuple[tuple[str, str], ...]) -> str:
        return "|".join(f"{key}={value}" for key, value in literal_value)

    @staticmethod
    def _fact_sort_key(fact: ConsolidatedFact) -> tuple[str, int, str]:
        return (fact.claim_key, fact.version, str(fact.fact_id))

    @staticmethod
    def _support_sort_key(support: FactSupport) -> tuple[str, str]:
        return (str(support.fact_id), str(support.fact_support_id))

    @staticmethod
    def _assertion_sort_key(assertion: EvidenceAssertion) -> tuple[str, str]:
        return (assertion.predicate_code, str(assertion.assertion_id))

    @staticmethod
    def _link_sort_key(link: AssertionEvidenceLink) -> tuple[str, str]:
        return (str(link.assertion_id), str(link.link_id))

    @staticmethod
    def _conflict_sort_key(conflict_set: AssertionConflictSet) -> tuple[str, str]:
        return (conflict_set.claim_key, str(conflict_set.conflict_set_id))

    @staticmethod
    def _proposal_sort_key(proposal: OntologyChangeProposal) -> tuple[str, str]:
        return (proposal.proposal_type, str(proposal.proposal_id))

    @staticmethod
    def _proposal_evidence_sort_key(evidence: OntologyProposalEvidence) -> tuple[str, str]:
        return (str(evidence.proposal_id), str(evidence.proposal_evidence_id))

    @staticmethod
    def _candidate_sort_key(candidate) -> tuple[str, str]:
        return (candidate.entity_type.value, str(candidate.candidate_id))