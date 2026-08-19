from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence import (
    EquivalenceDecision,
    EquivalenceDecisionService,
    EquivalenceDecisionStatus,
    InMemoryEquivalenceDecisionRepository,
)
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class EquivalenceDecisionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = EquivalenceDecisionService.create(InMemoryEquivalenceDecisionRepository.empty())
        self.mention_id = EntityId.from_seed("equivalence.test.mention", "mention-1")
        self.catalog_entity_id = EntityId.from_seed("equivalence.test.catalog", "catalog-1")
        self.source_trace = ExtractionSourceTrace(page_number=1, paragraph_ordinal=2, start_offset=10, end_offset=18)
        self.decided_at = datetime(2026, 1, 1, 12, 0, 0)

    def test_records_approved_decision(self) -> None:
        decision = self._record(EquivalenceDecisionStatus.APPROVED)

        self.assertEqual(decision.status, EquivalenceDecisionStatus.APPROVED)
        self.assertEqual(decision.revision, 1)
        self.assertEqual(self.service.get_active(self.mention_id, self.catalog_entity_id), decision)

    def test_records_rejected_decision(self) -> None:
        decision = self._record(EquivalenceDecisionStatus.REJECTED)

        self.assertEqual(decision.status, EquivalenceDecisionStatus.REJECTED)
        self.assertEqual(decision.revision, 1)

    def test_records_pending_decision(self) -> None:
        decision = self._record(EquivalenceDecisionStatus.PENDING)

        self.assertEqual(decision.status, EquivalenceDecisionStatus.PENDING)
        self.assertEqual(decision.revision, 1)

    def test_preserves_history_without_overwriting_previous_records(self) -> None:
        first = self._record(EquivalenceDecisionStatus.PENDING)
        second = self._record(
            EquivalenceDecisionStatus.APPROVED,
            evidence="manual-review-v2",
            rationale="confirmed after catalog review",
            decided_at=datetime(2026, 1, 2, 12, 0, 0),
        )

        history = self.service.list_history(self.mention_id, self.catalog_entity_id)
        self.assertEqual(history, (first, second))
        self.assertEqual(self.service.get_active(self.mention_id, self.catalog_entity_id), second)

    def test_record_is_idempotent_for_identical_active_input(self) -> None:
        first = self._record(EquivalenceDecisionStatus.APPROVED)
        second = self._record(EquivalenceDecisionStatus.APPROVED)

        self.assertIs(first, second)
        self.assertEqual(len(self.service.list_history(self.mention_id, self.catalog_entity_id)), 1)

    def test_duplicate_decision_records_are_rejected_by_repository_validation(self) -> None:
        decision = self._record(EquivalenceDecisionStatus.APPROVED)

        with self.assertRaises(ValueError):
            InMemoryEquivalenceDecisionRepository((decision, decision))

    def test_contradictory_active_decisions_are_rejected(self) -> None:
        approved = self._build_decision(EquivalenceDecisionStatus.APPROVED, revision=1)
        rejected = self._build_decision(
            EquivalenceDecisionStatus.REJECTED,
            revision=1,
            evidence="conflict",
            rationale="same revision conflict",
        )

        with self.assertRaises(ValueError):
            InMemoryEquivalenceDecisionRepository((approved, rejected))

    def _record(
        self,
        status: EquivalenceDecisionStatus,
        *,
        evidence: str = "manual-review",
        rationale: str = "validated by engineer",
        decided_at: datetime | None = None,
    ) -> EquivalenceDecision:
        return self.service.record(
            mention_id=self.mention_id,
            catalog_entity_id=self.catalog_entity_id,
            status=status,
            evidence=evidence,
            rationale=rationale,
            decided_by="qa.engineer",
            decided_at=decided_at or self.decided_at,
            source_trace=self.source_trace,
        )

    def _build_decision(
        self,
        status: EquivalenceDecisionStatus,
        *,
        revision: int,
        evidence: str = "manual-review",
        rationale: str = "validated by engineer",
    ) -> EquivalenceDecision:
        decided_at = self.decided_at if revision == 1 else datetime(2026, 1, 2, 12, 0, 0)
        return EquivalenceDecision(
            decision_id=EntityId.from_seed(
                "equivalence.test.decision",
                f"{self.mention_id}:{self.catalog_entity_id}:{revision}:{status.value}:{evidence}:{rationale}",
            ),
            mention_id=self.mention_id,
            catalog_entity_id=self.catalog_entity_id,
            status=status,
            evidence=evidence,
            rationale=rationale,
            decided_by="qa.engineer",
            decided_at=decided_at,
            source_trace=self.source_trace,
            revision=revision,
        )
