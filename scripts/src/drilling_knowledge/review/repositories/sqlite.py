"""SQLite repository for review queues and human decisions."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.review.domain import ReviewDecision, ReviewDecisionAction, ReviewQueueItem, ReviewQueueStatus, ReviewTargetType
from drilling_knowledge.review.repositories.contracts import ReviewRepository
from drilling_knowledge.review.repositories.memory import InMemoryReviewRepository

_SCHEMA_VERSION = 1


class SQLiteReviewRepository(ReviewRepository):
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteReviewRepository":
        return cls(database_path)

    def get_queue(self, queue_id: EntityId) -> ReviewQueueItem | None:
        return next((queue for queue in self.list_queues() if queue.queue_id == queue_id), None)

    def get_open_queue(self, target_type: ReviewTargetType, target_id: EntityId) -> ReviewQueueItem | None:
        return next((queue for queue in self.list_open_queues() if queue.target_type == target_type and queue.target_id == target_id), None)

    def list_queues(self) -> tuple[ReviewQueueItem, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM review_queue ORDER BY priority DESC, created_at, target_id, queue_id").fetchall()
            decisions = tuple(self._hydrate_decision(row) for row in connection.execute("SELECT * FROM review_decision ORDER BY decided_at, review_queue_id, decision_id").fetchall())
        return InMemoryReviewRepository(tuple(self._hydrate_queue(row) for row in rows), decisions).list_queues()

    def list_open_queues(self) -> tuple[ReviewQueueItem, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM review_queue ORDER BY priority DESC, created_at, target_id, queue_id").fetchall()
            decisions = tuple(self._hydrate_decision(row) for row in connection.execute("SELECT * FROM review_decision ORDER BY decided_at, review_queue_id, decision_id").fetchall())
        return InMemoryReviewRepository(tuple(self._hydrate_queue(row) for row in rows), decisions).list_open_queues()

    def get_decision(self, decision_id: EntityId) -> ReviewDecision | None:
        return next((decision for decision in self.list_decisions() if decision.decision_id == decision_id), None)

    def get_queue_decision(self, queue_id: EntityId) -> ReviewDecision | None:
        return next((decision for decision in self.list_decisions() if decision.review_queue_id == queue_id), None)

    def list_decisions(self) -> tuple[ReviewDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM review_decision ORDER BY decided_at, review_queue_id, decision_id").fetchall()
            queues = tuple(self._hydrate_queue(row) for row in connection.execute("SELECT * FROM review_queue ORDER BY priority DESC, created_at, target_id, queue_id").fetchall())
        return InMemoryReviewRepository(queues, tuple(self._hydrate_decision(row) for row in rows)).list_decisions()

    def append_queue(self, queue: ReviewQueueItem) -> "SQLiteReviewRepository":
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO review_queue (
                        queue_id, queue_type, target_type, target_id, reference_table, priority, review_reason,
                        status, assigned_to, created_at, updated_at, created_by, updated_by, provenance, policy_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(queue.queue_id),
                        queue.queue_type,
                        queue.target_type.value,
                        str(queue.target_id),
                        queue.reference_table,
                        queue.priority,
                        queue.review_reason,
                        queue.status.value,
                        queue.assigned_to,
                        queue.created_at.isoformat(),
                        queue.updated_at.isoformat(),
                        queue.created_by,
                        queue.updated_by,
                        self._serialize_pairs(queue.provenance),
                        queue.policy_version,
                    ),
                )
                self._validate_connection_state(connection)
            except (sqlite3.IntegrityError, ValueError) as exc:
                connection.rollback()
                raise ValueError(str(exc)) from exc
            connection.commit()
        return self

    def append_decision(self, decision: ReviewDecision) -> "SQLiteReviewRepository":
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO review_decision (
                        decision_id, review_queue_id, target_type, target_id, action, reason, decided_by, decided_at,
                        provenance, previous_state, resulting_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(decision.decision_id),
                        str(decision.review_queue_id),
                        decision.target_type.value,
                        str(decision.target_id),
                        decision.action.value,
                        decision.reason,
                        decision.decided_by,
                        decision.decided_at.isoformat(),
                        self._serialize_pairs(decision.provenance),
                        decision.previous_state,
                        decision.resulting_state,
                    ),
                )
                self._validate_connection_state(connection)
            except (sqlite3.IntegrityError, ValueError) as exc:
                connection.rollback()
                raise ValueError(str(exc)) from exc
            connection.commit()
        return self

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_queue (
                    queue_id TEXT PRIMARY KEY,
                    queue_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reference_table TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    review_reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_to TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    policy_version TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_decision (
                    decision_id TEXT PRIMARY KEY,
                    review_queue_id TEXT NOT NULL UNIQUE,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    decided_by TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    previous_state TEXT NOT NULL,
                    resulting_state TEXT NOT NULL,
                    FOREIGN KEY(review_queue_id) REFERENCES review_queue(queue_id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_review_queue_target ON review_queue (target_type, target_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue (queue_type, status, priority DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_review_decision_target ON review_decision (target_type, target_id)")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            elif version != _SCHEMA_VERSION:
                raise ValueError(f"Unsupported review repository schema version: {version}")
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_connection_state(self, connection: sqlite3.Connection) -> None:
        queues = tuple(self._hydrate_queue(row) for row in connection.execute("SELECT * FROM review_queue").fetchall())
        decisions = tuple(self._hydrate_decision(row) for row in connection.execute("SELECT * FROM review_decision").fetchall())
        InMemoryReviewRepository(queues, decisions)

    def _hydrate_queue(self, row: sqlite3.Row) -> ReviewQueueItem:
        return ReviewQueueItem(
            queue_id=EntityId.from_string(row["queue_id"]),
            queue_type=row["queue_type"],
            target_type=ReviewTargetType(row["target_type"]),
            target_id=EntityId.from_string(row["target_id"]),
            reference_table=row["reference_table"],
            priority=int(row["priority"]),
            review_reason=row["review_reason"],
            status=ReviewQueueStatus(row["status"]),
            assigned_to=row["assigned_to"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            provenance=tuple((str(left), str(right)) for left, right in json.loads(row["provenance"])),
            policy_version=row["policy_version"],
        )

    def _hydrate_decision(self, row: sqlite3.Row) -> ReviewDecision:
        return ReviewDecision(
            decision_id=EntityId.from_string(row["decision_id"]),
            review_queue_id=EntityId.from_string(row["review_queue_id"]),
            target_type=ReviewTargetType(row["target_type"]),
            target_id=EntityId.from_string(row["target_id"]),
            action=ReviewDecisionAction(row["action"]),
            reason=row["reason"],
            decided_by=row["decided_by"],
            decided_at=datetime.fromisoformat(row["decided_at"]),
            provenance=tuple((str(left), str(right)) for left, right in json.loads(row["provenance"])),
            previous_state=row["previous_state"],
            resulting_state=row["resulting_state"],
        )

    @staticmethod
    def _serialize_pairs(pairs: tuple[tuple[str, str], ...]) -> str:
        return json.dumps(list(pairs), sort_keys=True, separators=(",", ":"))