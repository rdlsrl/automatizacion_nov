from __future__ import annotations

import unittest

from drilling_knowledge.catalog.services.ontology_proposals import InMemoryOntologyProposalRunRepository, OntologyProposalGenerator
from drilling_knowledge.assertions.domain import AssertionStatus

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class OntologyProposalGeneratorEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        self.generator = OntologyProposalGenerator.create()

    def test_consolidated_facts_generate_persist_and_recover_same_proposal(self) -> None:
        assertions = (
            self.helpers._assertion("4 mA = 0 psi", version_seed="e2e-v1", status=AssertionStatus.ACCEPTED),
            self.helpers._assertion("4 mA = 0 psi", version_seed="e2e-v2", status=AssertionStatus.ACCEPTED),
        )
        assertion_run = self.helpers._assertion_run(assertions, run_seed="e2e-proposal")
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.helpers.consolidator.consolidate(assertion_run, conflict_run)

        run, repository = self.generator.generate_and_persist(fact_run, conflict_run, InMemoryOntologyProposalRunRepository())
        repeated, repository = self.generator.generate_and_persist(
            fact_run,
            conflict_run,
            repository,
            existing_proposals=run.proposals,
            existing_proposal_evidences=run.proposal_evidences,
        )

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.get_run(repeated.run_id), repeated)
        self.assertEqual(repeated.proposals, run.proposals)
        self.assertEqual(repeated.proposal_evidences, run.proposal_evidences)
