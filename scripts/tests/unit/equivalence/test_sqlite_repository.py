from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence import (
    EquivalenceDecisionService,
    EquivalenceDecisionStatus,
    InMemoryEquivalenceDecisionRepository,
    SQLiteEquivalenceDecisionRepository,
)
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class SQLiteEquivalenceDecisionRepositoryTests(unittest.TestCase):
    def test_persists_decisions_between_reopens(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "equivalence.db"
            first_service = self._sqlite_service(database_path)
            recorded = self._record(first_service, EquivalenceDecisionStatus.APPROVED)

            reopened_service = self._sqlite_service(database_path)
            reloaded = reopened_service.get_active(self._mention_id(), self._catalog_entity_id())

            self.assertEqual(reloaded, recorded)

    def test_records_approved_rejected_and_pending_with_sqlite(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = self._sqlite_service(Path(temp_dir) / "equivalence.db")

            approved = self._record(service, EquivalenceDecisionStatus.APPROVED)
            rejected = self._record(
                service,
                EquivalenceDecisionStatus.REJECTED,
                evidence="manual-review-v2",
                rationale="rejected after verification",
                decided_at=datetime(2026, 1, 2, 12, 0, 0),
            )
            pending = self._record(
                service,
                EquivalenceDecisionStatus.PENDING,
                evidence="manual-review-v3",
                rationale="awaiting final review",
                decided_at=datetime(2026, 1, 3, 12, 0, 0),
            )

            self.assertEqual((approved.status, rejected.status, pending.status), (
                EquivalenceDecisionStatus.APPROVED,
                EquivalenceDecisionStatus.REJECTED,
                EquivalenceDecisionStatus.PENDING,
            ))
            self.assertEqual([decision.revision for decision in service.list_history(self._mention_id(), self._catalog_entity_id())], [1, 2, 3])

    def test_append_only_history_is_preserved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = self._sqlite_service(Path(temp_dir) / "equivalence.db")
            first = self._record(service, EquivalenceDecisionStatus.PENDING)
            second = self._record(
                service,
                EquivalenceDecisionStatus.APPROVED,
                evidence="manual-review-v2",
                rationale="confirmed",
                decided_at=datetime(2026, 1, 2, 12, 0, 0),
            )

            self.assertEqual(service.list_history(self._mention_id(), self._catalog_entity_id()), (first, second))

    def test_service_idempotence_is_preserved_with_sqlite(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = self._sqlite_service(Path(temp_dir) / "equivalence.db")
            first = self._record(service, EquivalenceDecisionStatus.APPROVED)
            second = self._record(service, EquivalenceDecisionStatus.APPROVED)

            self.assertEqual(first, second)
            self.assertEqual(len(service.list_all()), 1)

    def test_duplicate_decision_id_rolls_back_invalid_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = SQLiteEquivalenceDecisionRepository.create(Path(temp_dir) / "equivalence.db")
            service = EquivalenceDecisionService.create(repository)
            valid = self._record(service, EquivalenceDecisionStatus.APPROVED)

            duplicate = self._build_direct_decision(
                decision_id=valid.decision_id,
                revision=2,
                status=EquivalenceDecisionStatus.REJECTED,
                evidence="duplicate-id",
                rationale="should fail",
            )

            with self.assertRaises(ValueError):
                repository.append(duplicate)

            self.assertEqual(repository.list_all(), (valid,))

    def test_append_rolls_back_when_database_contains_unrelated_invalid_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "equivalence.db"
            repository = SQLiteEquivalenceDecisionRepository.create(database_path)
            valid = self._build_pair_decision("mention-valid", "catalog-valid", revision=1)
            unrelated_invalid = self._build_pair_decision("mention-other", "catalog-other", revision=3)

            repository.append(valid)
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO equivalence_decisions (
                        decision_id, mention_id, catalog_entity_id, status, evidence, rationale, decided_by, decided_at, source_trace, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(unrelated_invalid.decision_id),
                        str(unrelated_invalid.mention_id),
                        str(unrelated_invalid.catalog_entity_id),
                        unrelated_invalid.status.value,
                        unrelated_invalid.evidence,
                        unrelated_invalid.rationale,
                        unrelated_invalid.decided_by,
                        unrelated_invalid.decided_at.isoformat(),
                        repository._serialize_source_trace(unrelated_invalid.source_trace),
                        unrelated_invalid.revision,
                    ),
                )

            with self.assertRaises(ValueError):
                repository.append(self._build_pair_decision("mention-new", "catalog-new", revision=1))

            with self.assertRaises(ValueError):
                repository.list_all()

    def test_contradictory_revision_rolls_back_invalid_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = SQLiteEquivalenceDecisionRepository.create(Path(temp_dir) / "equivalence.db")
            service = EquivalenceDecisionService.create(repository)
            valid = self._record(service, EquivalenceDecisionStatus.APPROVED)

            contradictory = self._build_direct_decision(
                decision_id=EntityId.from_seed("equivalence.sqlite.test.decision", "contradictory"),
                revision=1,
                status=EquivalenceDecisionStatus.REJECTED,
                evidence="contradictory-revision",
                rationale="same pair same revision",
            )

            with self.assertRaises(ValueError):
                repository.append(contradictory)

            self.assertEqual(repository.list_all(), (valid,))

    def test_repository_order_is_stable_independent_of_physical_insert_order(self) -> None:
        with TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.db"
            second_path = Path(temp_dir) / "second.db"

            first_repo = SQLiteEquivalenceDecisionRepository.create(first_path)
            second_repo = SQLiteEquivalenceDecisionRepository.create(second_path)

            decision_a = self._build_pair_decision("mention-a", "catalog-a", revision=1)
            decision_b = self._build_pair_decision("mention-b", "catalog-b", revision=1)

            first_repo.append(decision_b)
            first_repo.append(decision_a)
            second_repo.append(decision_a)
            second_repo.append(decision_b)

            self.assertEqual(first_repo.list_all(), second_repo.list_all())

    def test_empty_database_returns_no_decisions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = SQLiteEquivalenceDecisionRepository.create(Path(temp_dir) / "equivalence.db")

            self.assertEqual(repository.list_all(), ())
            self.assertIsNone(repository.get_active(self._mention_id(), self._catalog_entity_id()))

    def test_corrupt_row_is_detected_explicitly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "equivalence.db"
            repository = SQLiteEquivalenceDecisionRepository.create(database_path)
            self._record(EquivalenceDecisionService.create(repository), EquivalenceDecisionStatus.APPROVED)

            with sqlite3.connect(database_path) as connection:
                connection.execute("UPDATE equivalence_decisions SET status = 'BROKEN' WHERE revision = 1")

            with self.assertRaises(ValueError):
                repository.list_all()

    def test_existing_schema_is_reused_on_reopen(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "equivalence.db"
            first = SQLiteEquivalenceDecisionRepository.create(database_path)
            second = SQLiteEquivalenceDecisionRepository.create(database_path)

            self.assertEqual(first.list_all(), second.list_all())
            with sqlite3.connect(database_path) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_behavior_matches_in_memory_repository(self) -> None:
        with TemporaryDirectory() as temp_dir:
            memory_service = EquivalenceDecisionService.create(InMemoryEquivalenceDecisionRepository.empty())
            sqlite_service = self._sqlite_service(Path(temp_dir) / "equivalence.db")

            operations = (
                (EquivalenceDecisionStatus.PENDING, "manual-review", "awaiting review", datetime(2026, 1, 1, 12, 0, 0)),
                (EquivalenceDecisionStatus.APPROVED, "manual-review-v2", "approved after review", datetime(2026, 1, 2, 12, 0, 0)),
            )
            for status, evidence, rationale, decided_at in operations:
                self._record(memory_service, status, evidence=evidence, rationale=rationale, decided_at=decided_at)
                self._record(sqlite_service, status, evidence=evidence, rationale=rationale, decided_at=decided_at)

            self.assertEqual(sqlite_service.list_all(), memory_service.list_all())
            self.assertEqual(
                sqlite_service.list_history(self._mention_id(), self._catalog_entity_id()),
                memory_service.list_history(self._mention_id(), self._catalog_entity_id()),
            )
            self.assertEqual(
                sqlite_service.get_active(self._mention_id(), self._catalog_entity_id()),
                memory_service.get_active(self._mention_id(), self._catalog_entity_id()),
            )

    def _sqlite_service(self, database_path: Path) -> EquivalenceDecisionService:
        return EquivalenceDecisionService.create(SQLiteEquivalenceDecisionRepository.create(database_path))

    def _record(
        self,
        service: EquivalenceDecisionService,
        status: EquivalenceDecisionStatus,
        *,
        evidence: str = "manual-review",
        rationale: str = "validated by engineer",
        decided_at: datetime | None = None,
    ):
        return service.record(
            mention_id=self._mention_id(),
            catalog_entity_id=self._catalog_entity_id(),
            status=status,
            evidence=evidence,
            rationale=rationale,
            decided_by="qa.engineer",
            decided_at=decided_at or datetime(2026, 1, 1, 12, 0, 0),
            source_trace=self._source_trace(),
        )

    def _build_direct_decision(
        self,
        *,
        decision_id: EntityId,
        revision: int,
        status: EquivalenceDecisionStatus,
        evidence: str,
        rationale: str,
    ):
        from drilling_knowledge.equivalence import EquivalenceDecision

        return EquivalenceDecision(
            decision_id=decision_id,
            mention_id=self._mention_id(),
            catalog_entity_id=self._catalog_entity_id(),
            status=status,
            evidence=evidence,
            rationale=rationale,
            decided_by="qa.engineer",
            decided_at=datetime(2026, 1, 2, 12, 0, 0),
            source_trace=self._source_trace(),
            revision=revision,
        )

    def _build_pair_decision(self, mention_seed: str, catalog_seed: str, *, revision: int):
        from drilling_knowledge.equivalence import EquivalenceDecision

        mention_id = EntityId.from_seed("equivalence.sqlite.test.mention", mention_seed)
        catalog_entity_id = EntityId.from_seed("equivalence.sqlite.test.catalog", catalog_seed)
        return EquivalenceDecision(
            decision_id=EntityId.from_seed("equivalence.sqlite.test.decision", f"{mention_seed}:{catalog_seed}:{revision}"),
            mention_id=mention_id,
            catalog_entity_id=catalog_entity_id,
            status=EquivalenceDecisionStatus.APPROVED,
            evidence="manual-review",
            rationale="validated by engineer",
            decided_by="qa.engineer",
            decided_at=datetime(2026, 1, 1, 12, 0, 0),
            source_trace=self._source_trace(),
            revision=revision,
        )

    def _mention_id(self) -> EntityId:
        return EntityId.from_seed("equivalence.sqlite.test.mention", "mention-1")

    def _catalog_entity_id(self) -> EntityId:
        return EntityId.from_seed("equivalence.sqlite.test.catalog", "catalog-1")

    def _source_trace(self) -> ExtractionSourceTrace:
        return ExtractionSourceTrace(page_number=1, paragraph_ordinal=2, start_offset=10, end_offset=18)