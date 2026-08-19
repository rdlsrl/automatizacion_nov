from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence import EquivalenceDecision, EquivalenceDecisionStatus, InMemoryEquivalenceDecisionRepository
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class EquivalenceRepositoryContractTests(unittest.TestCase):
    def test_empty_repository_returns_no_active_decisions(self) -> None:
        repository = InMemoryEquivalenceDecisionRepository.empty()
        mention_id = EntityId.from_seed("equivalence.contract.mention", "mention-1")
        catalog_entity_id = EntityId.from_seed("equivalence.contract.catalog", "catalog-1")

        self.assertIsNone(repository.get_active(mention_id, catalog_entity_id))
        self.assertEqual(repository.list_history(mention_id, catalog_entity_id), ())
        self.assertEqual(repository.list_all(), ())

    def test_repository_preserves_stable_order(self) -> None:
        first = self._decision("mention-b", "catalog-b", revision=1)
        second = self._decision("mention-a", "catalog-a", revision=1)
        forward = InMemoryEquivalenceDecisionRepository((first, second))
        reverse = InMemoryEquivalenceDecisionRepository((second, first))

        self.assertEqual(forward.list_all(), reverse.list_all())

    def test_active_decision_is_latest_revision_in_history(self) -> None:
        first = self._decision("mention-a", "catalog-a", revision=1, status=EquivalenceDecisionStatus.PENDING)
        second = self._decision(
            "mention-a",
            "catalog-a",
            revision=2,
            status=EquivalenceDecisionStatus.APPROVED,
            evidence="manual-review-v2",
            rationale="confirmed after review",
            decided_at=datetime(2026, 1, 2, 12, 0, 0),
        )
        repository = InMemoryEquivalenceDecisionRepository((second, first))

        mention_id = first.mention_id
        catalog_entity_id = first.catalog_entity_id
        self.assertEqual(repository.list_history(mention_id, catalog_entity_id), (first, second))
        self.assertEqual(repository.get_active(mention_id, catalog_entity_id), second)

    def _decision(
        self,
        mention_seed: str,
        catalog_seed: str,
        *,
        revision: int,
        status: EquivalenceDecisionStatus = EquivalenceDecisionStatus.APPROVED,
        evidence: str = "manual-review",
        rationale: str = "validated by engineer",
        decided_at: datetime | None = None,
    ) -> EquivalenceDecision:
        mention_id = EntityId.from_seed("equivalence.contract.mention", mention_seed)
        catalog_entity_id = EntityId.from_seed("equivalence.contract.catalog", catalog_seed)
        decided_at = decided_at or datetime(2026, 1, 1, 12, 0, 0)
        source_trace = ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=2, end_offset=8)
        return EquivalenceDecision(
            decision_id=EntityId.from_seed(
                "equivalence.contract.decision",
                f"{mention_seed}:{catalog_seed}:{revision}:{status.value}:{evidence}:{rationale}:{decided_at.isoformat()}",
            ),
            mention_id=mention_id,
            catalog_entity_id=catalog_entity_id,
            status=status,
            evidence=evidence,
            rationale=rationale,
            decided_by="contract.tester",
            decided_at=decided_at,
            source_trace=source_trace,
            revision=revision,
        )