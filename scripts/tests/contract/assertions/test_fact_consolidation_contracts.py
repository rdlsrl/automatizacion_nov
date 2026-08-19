from __future__ import annotations

from dataclasses import replace
import unittest

from drilling_knowledge.assertions.consolidation import FactConsolidator, InMemoryFactConsolidationRunRepository
from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.common.exceptions import ConflictError

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class FactConsolidationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        self.consolidator = FactConsolidator.create()

    def test_save_get_and_recovery(self) -> None:
        run = self._consolidation_run()
        repository = InMemoryFactConsolidationRunRepository().append_run(run)

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.list_facts(run.run_id), run.facts)
        self.assertEqual(repository.list_support_links(run.run_id), run.support_links)
        self.assertEqual(repository.list_assertions(run.run_id), run.assertions)
        self.assertEqual(repository.list_evidence_links(run.run_id), run.evidence_links)

    def test_idempotent_append(self) -> None:
        run = self._consolidation_run()
        repository = InMemoryFactConsolidationRunRepository().append_run(run)

        self.assertIs(repository.append_run(run), repository)

    def test_invalid_collision_is_rejected(self) -> None:
        run = self._consolidation_run()
        conflicting = replace(run, assertion_run_id=run.assertion_run_id.__class__.from_seed("fact.consolidation.assertion_run", "other"))

        with self.assertRaises(ConflictError):
            InMemoryFactConsolidationRunRepository((run, conflicting))

    def test_referential_integrity_is_enforced(self) -> None:
        run = self._consolidation_run()
        bad_support = replace(run.support_links[0], fact_id=run.support_links[0].fact_id.__class__.from_seed("semantic.consolidated_fact", "missing"))
        bad_run = replace(run, support_links=(bad_support, *run.support_links[1:]))

        with self.assertRaises(ConflictError):
            InMemoryFactConsolidationRunRepository((bad_run,))

    def test_fact_without_support_is_rejected(self) -> None:
        run = self._consolidation_run()
        with self.assertRaises((ConflictError, ValueError)):
            bad_fact = replace(run.facts[0], support_link_ids=())
            bad_run = replace(run, facts=(bad_fact,), support_links=())
            InMemoryFactConsolidationRunRepository((bad_run,))

    def test_support_with_nonaccepted_assertion_is_rejected(self) -> None:
        run = self._consolidation_run()
        bad_support = replace(run.support_links[0], source_assertion=replace(run.support_links[0].source_assertion, status=run.support_links[0].source_assertion.status.REJECTED))
        bad_run = replace(run, support_links=(bad_support,))

        with self.assertRaises(ConflictError):
            InMemoryFactConsolidationRunRepository((bad_run,))

    def test_rejects_two_active_revisions_for_same_lineage(self) -> None:
        run = self._consolidation_run()
        duplicate = replace(
            run.facts[0],
            fact_id=run.facts[0].fact_id.__class__.from_seed("semantic.consolidated_fact", "other-active"),
            version=2,
            supersedes_fact_id=run.facts[0].fact_id,
        )
        duplicate_support = replace(
            run.support_links[0],
            fact_support_id=run.support_links[0].fact_support_id.__class__.from_seed("semantic.fact_support", "other-active"),
            fact_id=duplicate.fact_id,
        )

        with self.assertRaises(ConflictError):
            InMemoryFactConsolidationRunRepository((replace(run, facts=(run.facts[0], duplicate), support_links=(run.support_links[0], duplicate_support)),))

    def test_rejects_superseded_revision_marked_active(self) -> None:
        run = self._consolidation_run()
        with self.assertRaises((ConflictError, ValueError)):
            bad_fact = replace(run.facts[0], lifecycle=run.facts[0].lifecycle.SUPERSEDED, active_revision=True)
            InMemoryFactConsolidationRunRepository((replace(run, facts=(bad_fact,), support_links=run.support_links),))

    def test_preserves_full_history_across_persisted_runs(self) -> None:
        accepted = self.helpers._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        base_run = self.helpers._assertion_run((accepted,), run_seed="history-contract-base")
        first_conflict = self.helpers.conflict_resolver.resolve(base_run)
        first_run = self.consolidator.consolidate(base_run, first_conflict)
        repository = InMemoryFactConsolidationRunRepository().append_run(first_run)
        second_assertion_run, _ = self.helpers._revision_run(base_run, accepted, run_seed="history-contract-v2", revision_seed="persist-history-v2")
        second_conflict = self.helpers.conflict_resolver.resolve(second_assertion_run)
        second_run = self.consolidator.consolidate(
            second_assertion_run,
            second_conflict,
            existing_facts=repository.list_facts(first_run.run_id),
            existing_support_links=repository.list_support_links(first_run.run_id),
        )
        repository = repository.append_run(second_run)

        recovered_first = repository.list_facts(first_run.run_id)
        recovered_second = repository.list_facts(second_run.run_id)
        self.assertEqual(len(recovered_first), 1)
        self.assertEqual(len(recovered_second), 2)
        self.assertEqual(len(repository.list_support_links(first_run.run_id)), 1)
        self.assertEqual(len(repository.list_support_links(second_run.run_id)), 2)

    def _consolidation_run(self):
        accepted = self.helpers._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self.helpers._assertion_run((accepted,), run_seed="contract")
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        return self.consolidator.consolidate(assertion_run, conflict_run)