from __future__ import annotations

import unittest

from drilling_knowledge.assertions.consolidation import FactConsolidator, InMemoryFactConsolidationRunRepository
from drilling_knowledge.assertions.domain import AssertionStatus

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class FactConsolidationEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        self.consolidator = FactConsolidator.create()

    def test_accepted_assertions_consolidate_persist_recover_with_traceability(self) -> None:
        accepted = self.helpers._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self.helpers._assertion_run((accepted,), run_seed="e2e")
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)

        run, repository = self.consolidator.consolidate_and_persist(assertion_run, conflict_run, InMemoryFactConsolidationRunRepository())

        second_assertion_run, _ = self.helpers._revision_run(assertion_run, accepted, run_seed="e2e-v2", revision_seed="e2e-v2")
        second_conflict = self.helpers.conflict_resolver.resolve(second_assertion_run)
        second_run, repository = self.consolidator.consolidate_and_persist(
            second_assertion_run,
            second_conflict,
            repository,
            existing_facts=repository.list_facts(run.run_id),
            existing_support_links=repository.list_support_links(run.run_id),
        )

        recovered = repository.get_run(run.run_id)
        self.assertEqual(recovered, run)
        self.assertEqual(repository.list_facts(run.run_id), run.facts)
        self.assertEqual(repository.list_support_links(run.run_id), run.support_links)
        self.assertEqual(repository.list_evidence_links(run.run_id), run.evidence_links)
        recovered_second = repository.get_run(second_run.run_id)
        self.assertEqual(recovered_second, second_run)
        self.assertEqual(len(repository.list_facts(second_run.run_id)), 2)
        self.assertEqual(len(repository.list_support_links(second_run.run_id)), 2)