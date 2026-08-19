from __future__ import annotations

from dataclasses import replace
import unittest

from drilling_knowledge.assertions.conflict_resolution.domain import AssertionConflictMember, AssertionConflictSet, ConflictMemberRole, ConflictSetStatus, ConflictType
from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus
from drilling_knowledge.catalog.services.ontology_proposals import OntologyProposalGenerator, OntologyProposalRunOutcome
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractedEntityType
from drilling_knowledge.normalization import NormalizationCandidateStatus
from drilling_knowledge.normalization.domain import NormalizationRunStatus

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests
from tests.unit.normalization.test_normalization_engine import NormalizationEngineTests


class OntologyProposalGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        self.generator = OntologyProposalGenerator.create()
        self.normalization_helpers = NormalizationEngineTests()
        self.normalization_helpers.setUp()

    def test_recurring_patterns_create_queued_proposal(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (
                self.helpers._assertion("4 mA = 0 psi", version_seed="pattern-v1", status=AssertionStatus.ACCEPTED),
                self.helpers._assertion("4 mA = 0 psi", version_seed="pattern-v2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed="pattern-run",
        )

        result = self.generator.generate(fact_run, conflict_run)

        self.assertEqual(result.outcome, OntologyProposalRunOutcome.PROPOSAL_QUEUED)
        self.assertEqual(len(result.proposals), 1)
        self.assertEqual(result.proposals[0].proposal_type, "recurring_pattern")
        self.assertEqual(result.metrics.recurring_pattern_groups, 1)

    def test_recurring_conflicts_create_queued_proposal(self) -> None:
        assertions = (
            self.helpers._assertion("4 mA = 0 psi", version_seed="conflict-v1", status=AssertionStatus.ACCEPTED),
            self.helpers._assertion("4 mA = 0 psi", version_seed="conflict-v2", status=AssertionStatus.ACCEPTED),
        )
        _, fact_run = self._fact_pipeline(assertions, run_seed="conflict-run")
        conflict_run = self._recurring_conflict_run(fact_run, reason="repeated_conflict")

        result = self.generator.generate(fact_run, conflict_run)

        self.assertIn("recurring_conflict", {proposal.proposal_type for proposal in result.proposals})
        self.assertEqual(result.metrics.recurring_conflict_groups, 1)
        conflict_proposal = next(proposal for proposal in result.proposals if proposal.proposal_type == "recurring_conflict")
        conflict_evidence = next(evidence for evidence in result.proposal_evidences if evidence.proposal_id == conflict_proposal.proposal_id)
        self.assertEqual(len(conflict_evidence.conflict_set_ids), 2)

    def test_repeated_manual_decisions_create_queued_proposal(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (
                replace(
                    self.helpers._assertion("4 mA = 0 psi", version_seed="manual-v1", status=AssertionStatus.ACCEPTED),
                    review_state=AssertionReviewState.APPROVED,
                ),
                replace(
                    self.helpers._assertion("4 mA = 0 psi", version_seed="manual-v2", status=AssertionStatus.ACCEPTED),
                    review_state=AssertionReviewState.APPROVED,
                ),
            ),
            run_seed="manual-run",
        )

        result = self.generator.generate(fact_run, conflict_run)

        self.assertIn("repeated_manual_decision", {proposal.proposal_type for proposal in result.proposals})
        self.assertEqual(result.metrics.repeated_manual_decision_groups, 1)

    def test_threshold_not_reached_returns_no_op(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (self.helpers._assertion("4 mA = 0 psi", version_seed="noop-v1", status=AssertionStatus.ACCEPTED),),
            run_seed="noop-run",
        )

        result = self.generator.generate(fact_run, conflict_run)

        self.assertEqual(result.outcome, OntologyProposalRunOutcome.NO_OP)
        self.assertEqual(result.proposals, ())
        self.assertEqual(result.metrics.no_op_outputs, 1)

    def test_evidence_bundle_and_impact_summary_are_preserved(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (
                self.helpers._assertion("4 mA = 0 psi", version_seed="bundle-v1", status=AssertionStatus.ACCEPTED),
                self.helpers._assertion("4 mA = 0 psi", version_seed="bundle-v2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed="bundle-run",
        )

        result = self.generator.generate(fact_run, conflict_run)
        evidence = result.proposal_evidences[0]

        self.assertEqual(set(evidence.evidence_bundle), {link.link_id for link in fact_run.evidence_links})
        impact = dict(result.proposals[0].impact_summary)
        self.assertEqual(impact["fact_count"], "2")
        self.assertEqual(impact["support_count"], "2")

    def test_generation_is_idempotent_against_persisted_state(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (
                self.helpers._assertion("4 mA = 0 psi", version_seed="idempotent-v1", status=AssertionStatus.ACCEPTED),
                self.helpers._assertion("4 mA = 0 psi", version_seed="idempotent-v2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed="idempotent-run",
        )
        first = self.generator.generate(fact_run, conflict_run)

        second = self.generator.generate(
            fact_run,
            conflict_run,
            existing_proposals=first.proposals,
            existing_proposal_evidences=first.proposal_evidences,
        )

        self.assertEqual(second.proposals, first.proposals)
        self.assertEqual(second.proposal_evidences, first.proposal_evidences)
        self.assertEqual(second.metrics, first.metrics)

    def test_reversed_input_order_is_stable(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (
                self.helpers._assertion("4 mA = 0 psi", version_seed="stable-v1", status=AssertionStatus.ACCEPTED),
                self.helpers._assertion("4 mA = 0 psi", version_seed="stable-v2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed="stable-run",
        )
        reversed_run = replace(
            fact_run,
            assertions=tuple(reversed(fact_run.assertions)),
            evidence_links=tuple(reversed(fact_run.evidence_links)),
            facts=tuple(reversed(fact_run.facts)),
            support_links=tuple(reversed(fact_run.support_links)),
        )

        first = self.generator.generate(fact_run, conflict_run)
        second = self.generator.generate(reversed_run, conflict_run)

        self.assertEqual(first.proposals, second.proposals)
        self.assertEqual(first.proposal_evidences, second.proposal_evidences)

    def test_full_traceability_chain_is_preserved(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (
                self.helpers._assertion("4 mA = 0 psi", version_seed="trace-v1", status=AssertionStatus.ACCEPTED),
                self.helpers._assertion("4 mA = 0 psi", version_seed="trace-v2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed="trace-run",
        )

        result = self.generator.generate(fact_run, conflict_run)
        evidence = result.proposal_evidences[0]
        supports = {support.fact_support_id: support for support in fact_run.support_links}
        assertions = {assertion.assertion_id: assertion for assertion in fact_run.assertions}
        links = {link.link_id: link for link in fact_run.evidence_links}

        for support_id in evidence.fact_support_ids:
            support = supports[support_id]
            assertion = assertions[support.assertion_id]
            self.assertTrue(assertion.source_supports)
            for link_id in support.assertion_evidence_link_ids:
                self.assertIn(link_id, links)

    def test_counts_proposed_normalization_candidates_without_emitting_name_only_proposal(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (self.helpers._assertion("4 mA = 0 psi", version_seed="norm-v1", status=AssertionStatus.ACCEPTED),),
            run_seed="norm-run",
        )
        normalization_run = self._proposed_normalization_run("Pileta_Gas_Oil_Q1")

        result = self.generator.generate(fact_run, conflict_run, normalization_run=normalization_run)

        self.assertEqual(result.metrics.proposed_normalization_candidates, 1)
        self.assertEqual(result.outcome, OntologyProposalRunOutcome.NO_OP)

    def test_repeated_unresolved_patterns_create_queued_proposal(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (self.helpers._assertion("4 mA = 0 psi", version_seed="norm-repeat-v1", status=AssertionStatus.ACCEPTED),),
            run_seed="norm-repeat-run",
        )
        normalization_run = self._repeated_proposed_normalization_run("Pileta_Gas_Oil_Q1")

        result = self.generator.generate(fact_run, conflict_run, normalization_run=normalization_run)

        self.assertEqual(result.outcome, OntologyProposalRunOutcome.PROPOSAL_QUEUED)
        self.assertIn("recurring_pattern", {proposal.proposal_type for proposal in result.proposals})
        unresolved_proposal = next(
            proposal
            for proposal in result.proposals
            if dict(proposal.target_entity).get("canonical_text") == "Pileta_Gas_Oil_Q1"
        )
        unresolved_evidence = next(evidence for evidence in result.proposal_evidences if evidence.proposal_id == unresolved_proposal.proposal_id)
        self.assertEqual(unresolved_evidence.consolidated_fact_ids, ())
        self.assertEqual(len(unresolved_evidence.evidence_bundle), 2)

    def test_mismatched_fact_and_conflict_runs_are_rejected(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(
            (self.helpers._assertion("4 mA = 0 psi", version_seed="mismatch-v1", status=AssertionStatus.ACCEPTED),),
            run_seed="mismatch-run",
        )
        mismatched = replace(conflict_run, assertion_run_id=RunId.from_seed("ontology.proposal.assertion_run", "mismatch"))

        with self.assertRaises(ConflictError):
            self.generator.generate(fact_run, mismatched)

    def _fact_pipeline(self, assertions, *, run_seed: str):
        assertion_run = self.helpers._assertion_run(assertions, run_seed=run_seed)
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.helpers.consolidator.consolidate(assertion_run, conflict_run)
        return conflict_run, fact_run

    def _recurring_conflict_run(self, fact_run, *, reason: str):
        created_at = fact_run.finished_at
        conflict_sets = []
        members = []
        for index, assertion in enumerate(fact_run.assertions[:2], start=1):
            conflict_set_id = EntityId.from_seed("semantic.assertion_conflict_set", f"{reason}:{index}")
            member = AssertionConflictMember(
                member_id=EntityId.from_seed("semantic.assertion_conflict_member", f"{reason}:member:{index}"),
                conflict_set_id=conflict_set_id,
                assertion_id=assertion.assertion_id,
                member_role=ConflictMemberRole.REVIEW_CANDIDATE,
                member_score=assertion.score,
                scope_key=fact_run.facts[index - 1].scope,
                value_key=fact_run.facts[index - 1].value_key,
                created_at=created_at,
                source_assertion=assertion,
            )
            conflict_sets.append(
                AssertionConflictSet(
                    conflict_set_id=conflict_set_id,
                    claim_key=fact_run.facts[index - 1].claim_key,
                    scope_key=fact_run.facts[index - 1].scope,
                    conflict_type=ConflictType.INCOMPATIBLE_ASSERTION,
                    status=ConflictSetStatus.OPEN,
                    decision_type=None,
                    decision_reason=reason,
                    requires_human_review=False,
                    opened_at=created_at,
                    closed_at=None,
                    members=(member,),
                )
            )
            members.append(member)
        return replace(
            self.helpers.conflict_resolver.resolve(self.helpers._assertion_run(fact_run.assertions, run_seed="recurring-conflicts")),
            run_id=RunId.from_seed("semantic.conflict_resolution_run", reason),
            assertion_run_id=fact_run.assertion_run_id,
            started_at=created_at,
            finished_at=created_at,
            conflict_sets=tuple(conflict_sets),
            members=tuple(members),
            contexts=(),
            review_queue_items=(),
            evidence_links=fact_run.evidence_links,
            errors=(),
        )

    def _proposed_normalization_run(self, mention_text: str):
        mention = self.normalization_helpers._mention(mention_text, ExtractedEntityType.TAG, start_offset=0)
        extraction_run = self.normalization_helpers._extraction_run((mention,), ())
        run = self.normalization_helpers.engine.normalize(extraction_run)
        self.assertEqual(run.status, NormalizationRunStatus.COMPLETED)
        self.assertEqual(run.entity_candidates[0].status, NormalizationCandidateStatus.PROPOSED)
        return run

    def _repeated_proposed_normalization_run(self, mention_text: str):
        mentions = (
            self.normalization_helpers._mention(mention_text, ExtractedEntityType.TAG, start_offset=0),
            self.normalization_helpers._mention(mention_text, ExtractedEntityType.TAG, start_offset=20),
        )
        extraction_run = self.normalization_helpers._extraction_run(mentions, ())
        run = self.normalization_helpers.engine.normalize(extraction_run)
        self.assertEqual(run.status, NormalizationRunStatus.COMPLETED)
        self.assertTrue(all(candidate.status == NormalizationCandidateStatus.PROPOSED for candidate in run.entity_candidates))
        return run
