from __future__ import annotations

from dataclasses import replace
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.catalog.services.ontology_proposals import InMemoryOntologyProposalRunRepository, OntologyProposalGenerator
from drilling_knowledge.common.exceptions import ConflictError

from tests.unit.catalog.test_ontology_proposal_service import OntologyProposalGeneratorTests

OntologyProposalGeneratorTests.__test__ = False


class OntologyProposalRepositoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = OntologyProposalGeneratorTests()
        self.helpers.setUp()
        self.generator = OntologyProposalGenerator.create()

    def test_save_get_and_recovery(self) -> None:
        run = self._proposal_run()
        repository = InMemoryOntologyProposalRunRepository().append_run(run)

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.list_proposals(run.run_id), run.proposals)
        self.assertEqual(repository.list_proposal_evidences(run.run_id), run.proposal_evidences)

    def test_idempotent_append(self) -> None:
        run = self._proposal_run()
        repository = InMemoryOntologyProposalRunRepository().append_run(run)

        self.assertIs(repository.append_run(run), repository)

    def test_duplicate_proposal_is_rejected(self) -> None:
        run = self._proposal_run()
        duplicate = replace(run.proposals[0], rationale="different")
        bad_run = replace(run, proposals=(duplicate,), proposal_evidences=run.proposal_evidences)

        with self.assertRaises(ConflictError):
            InMemoryOntologyProposalRunRepository((run, bad_run))

    def test_proposal_without_evidence_is_rejected(self) -> None:
        run = self._proposal_run()
        bad_proposal = replace(run.proposals[0], evidence_ids=(run.proposal_evidences[0].proposal_evidence_id,))
        bad_run = replace(run, proposals=(bad_proposal,), proposal_evidences=())

        with self.assertRaises(ConflictError):
            InMemoryOntologyProposalRunRepository((bad_run,))

    def test_missing_fact_reference_is_rejected(self) -> None:
        run = self._proposal_run()
        bad_evidence = replace(
            run.proposal_evidences[0],
            consolidated_fact_ids=(run.proposal_evidences[0].consolidated_fact_ids[0].__class__.from_seed("ontology.proposal.fact", "missing"),),
        )
        bad_run = replace(run, proposal_evidences=(bad_evidence,))

        with self.assertRaises(ConflictError):
            InMemoryOntologyProposalRunRepository((bad_run,))

    def test_history_can_be_recovered_across_persisted_runs(self) -> None:
        conflict_run, fact_run = self._fact_pipeline(run_seed="history-v1")
        first = self.generator.generate(fact_run, conflict_run)
        repository = InMemoryOntologyProposalRunRepository().append_run(first)
        second = self.generator.generate(
            fact_run,
            self.helpers._recurring_conflict_run(fact_run, reason="history-conflict"),
            existing_proposals=first.proposals,
            existing_proposal_evidences=first.proposal_evidences,
        )
        repository = repository.append_run(second)

        self.assertEqual(repository.list_proposals(first.run_id), first.proposals)
        self.assertEqual(repository.list_proposals(second.run_id), second.proposals)

    def _proposal_run(self, *, run_seed: str = "repository-run"):
        conflict_run, fact_run = self._fact_pipeline(run_seed=run_seed)
        return self.generator.generate(fact_run, conflict_run)

    def _fact_pipeline(self, *, run_seed: str):
        return self.helpers._fact_pipeline(
            (
                self.helpers.helpers._assertion("4 mA = 0 psi", version_seed=f"{run_seed}-1", status=AssertionStatus.ACCEPTED),
                self.helpers.helpers._assertion("4 mA = 0 psi", version_seed=f"{run_seed}-2", status=AssertionStatus.ACCEPTED),
            ),
            run_seed=run_seed,
        )
