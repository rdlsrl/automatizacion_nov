"""SQLite append-only repository for explicit equivalence decisions."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence.domain import EquivalenceDecision, EquivalenceDecisionStatus
from drilling_knowledge.equivalence.repositories.contracts import EquivalenceDecisionRepository
from drilling_knowledge.equivalence.repositories.memory import InMemoryEquivalenceDecisionRepository
from drilling_knowledge.extraction.domain import ExtractionSourceTrace

_SCHEMA_VERSION = 1
_TABLE_NAME = "equivalence_decisions"
_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
    decision_id TEXT PRIMARY KEY,
    mention_id TEXT NOT NULL,
    catalog_entity_id TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence TEXT NOT NULL,
    rationale TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    source_trace TEXT NOT NULL,
    revision INTEGER NOT NULL,
    UNIQUE (mention_id, catalog_entity_id, revision)
)
"""


class SQLiteEquivalenceDecisionRepository(EquivalenceDecisionRepository):
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._ensure_schema()

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteEquivalenceDecisionRepository":
        return cls(database_path)

    def get_active(self, mention_id: EntityId, catalog_entity_id: EntityId) -> EquivalenceDecision | None:
        history = self.list_history(mention_id, catalog_entity_id)
        return history[-1] if history else None

    def list_history(self, mention_id: EntityId, catalog_entity_id: EntityId) -> tuple[EquivalenceDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT decision_id, mention_id, catalog_entity_id, status, evidence, rationale, decided_by, decided_at, source_trace, revision
                FROM {_TABLE_NAME}
                WHERE mention_id = ? AND catalog_entity_id = ?
                ORDER BY mention_id, catalog_entity_id, revision, decided_at, decision_id
                """,
                (str(mention_id), str(catalog_entity_id)),
            ).fetchall()
        decisions = tuple(self._hydrate_row(row) for row in rows)
        return self._validate_subset(decisions, mention_id, catalog_entity_id)

    def list_all(self) -> tuple[EquivalenceDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT decision_id, mention_id, catalog_entity_id, status, evidence, rationale, decided_by, decided_at, source_trace, revision
                FROM {_TABLE_NAME}
                ORDER BY mention_id, catalog_entity_id, revision, decided_at, decision_id
                """
            ).fetchall()
        decisions = tuple(self._hydrate_row(row) for row in rows)
        return self._validate_all(decisions)

    def append(self, decision: EquivalenceDecision) -> "SQLiteEquivalenceDecisionRepository":
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            connection.execute(
                f"""
                INSERT INTO {_TABLE_NAME} (
                    decision_id,
                    mention_id,
                    catalog_entity_id,
                    status,
                    evidence,
                    rationale,
                    decided_by,
                    decided_at,
                    source_trace,
                    revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(decision.decision_id),
                    str(decision.mention_id),
                    str(decision.catalog_entity_id),
                    decision.status.value,
                    self._serialize_evidence(decision.evidence),
                    decision.rationale,
                    decision.decided_by,
                    decision.decided_at.isoformat(),
                    self._serialize_source_trace(decision.source_trace),
                    decision.revision,
                ),
            )
            self._validate_all(self._fetch_all_decisions(connection))
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ValueError("SQLite equivalence decision uniqueness constraint violated") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, _SCHEMA_VERSION):
                raise ValueError(f"Unsupported equivalence schema version: {version}")
            connection.execute(_CREATE_TABLE_SQL)
            connection.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{_TABLE_NAME}_pair_revision ON {_TABLE_NAME} (mention_id, catalog_entity_id, revision)")
            connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE_NAME}_pair_order ON {_TABLE_NAME} (mention_id, catalog_entity_id, revision, decided_at, decision_id)")
            connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE_NAME}_all_order ON {_TABLE_NAME} (mention_id, catalog_entity_id, revision, decided_at, decision_id)")
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._validate_schema(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(f"PRAGMA table_info('{_TABLE_NAME}')").fetchall()
        actual = tuple((row[1], row[2], row[3], row[5]) for row in rows)
        expected = (
            ("decision_id", "TEXT", 0, 1),
            ("mention_id", "TEXT", 1, 0),
            ("catalog_entity_id", "TEXT", 1, 0),
            ("status", "TEXT", 1, 0),
            ("evidence", "TEXT", 1, 0),
            ("rationale", "TEXT", 1, 0),
            ("decided_by", "TEXT", 1, 0),
            ("decided_at", "TEXT", 1, 0),
            ("source_trace", "TEXT", 1, 0),
            ("revision", "INTEGER", 1, 0),
        )
        if actual != expected:
            raise ValueError("Corrupt or incompatible equivalence SQLite schema detected")

    def _fetch_history_rows(
        self,
        connection: sqlite3.Connection,
        mention_id: EntityId,
        catalog_entity_id: EntityId,
    ) -> tuple[sqlite3.Row, ...]:
        return tuple(
            connection.execute(
                f"""
                SELECT decision_id, mention_id, catalog_entity_id, status, evidence, rationale, decided_by, decided_at, source_trace, revision
                FROM {_TABLE_NAME}
                WHERE mention_id = ? AND catalog_entity_id = ?
                ORDER BY mention_id, catalog_entity_id, revision, decided_at, decision_id
                """,
                (str(mention_id), str(catalog_entity_id)),
            ).fetchall()
        )

    def _fetch_all_decisions(self, connection: sqlite3.Connection) -> tuple[EquivalenceDecision, ...]:
        rows = connection.execute(
            f"""
            SELECT decision_id, mention_id, catalog_entity_id, status, evidence, rationale, decided_by, decided_at, source_trace, revision
            FROM {_TABLE_NAME}
            ORDER BY mention_id, catalog_entity_id, revision, decided_at, decision_id
            """
        ).fetchall()
        return tuple(self._hydrate_row(row) for row in rows)

    def _hydrate_row(self, row: sqlite3.Row) -> EquivalenceDecision:
        try:
            return EquivalenceDecision(
                decision_id=EntityId.from_string(row["decision_id"]),
                mention_id=EntityId.from_string(row["mention_id"]),
                catalog_entity_id=EntityId.from_string(row["catalog_entity_id"]),
                status=EquivalenceDecisionStatus(row["status"]),
                evidence=self._deserialize_evidence(row["evidence"]),
                rationale=row["rationale"],
                decided_by=row["decided_by"],
                decided_at=self._deserialize_datetime(row["decided_at"]),
                source_trace=self._deserialize_source_trace(row["source_trace"]),
                revision=int(row["revision"]),
            )
        except Exception as exc:
            raise ValueError(f"Corrupt equivalence decision row detected: {exc}") from exc

    def _validate_all(self, decisions: tuple[EquivalenceDecision, ...]) -> tuple[EquivalenceDecision, ...]:
        return InMemoryEquivalenceDecisionRepository(decisions).list_all()

    def _validate_subset(
        self,
        decisions: tuple[EquivalenceDecision, ...],
        mention_id: EntityId,
        catalog_entity_id: EntityId,
    ) -> tuple[EquivalenceDecision, ...]:
        validated = InMemoryEquivalenceDecisionRepository(decisions).list_history(mention_id, catalog_entity_id)
        return validated

    def _serialize_evidence(self, evidence: str) -> str:
        return evidence.strip()

    def _deserialize_evidence(self, evidence: str) -> str:
        return evidence.strip()

    def _serialize_source_trace(self, source_trace: ExtractionSourceTrace) -> str:
        payload = {
            "end_offset": source_trace.end_offset,
            "figure_id": str(source_trace.figure_id) if source_trace.figure_id is not None else None,
            "page_number": source_trace.page_number,
            "paragraph_ordinal": source_trace.paragraph_ordinal,
            "section_id": str(source_trace.section_id) if source_trace.section_id is not None else None,
            "start_offset": source_trace.start_offset,
            "table_id": str(source_trace.table_id) if source_trace.table_id is not None else None,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _deserialize_source_trace(self, raw: str) -> ExtractionSourceTrace:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("source_trace payload must be a JSON object")
        return ExtractionSourceTrace(
            page_number=payload.get("page_number"),
            section_id=self._optional_entity_id(payload.get("section_id")),
            table_id=self._optional_entity_id(payload.get("table_id")),
            figure_id=self._optional_entity_id(payload.get("figure_id")),
            paragraph_ordinal=payload.get("paragraph_ordinal"),
            start_offset=payload.get("start_offset"),
            end_offset=payload.get("end_offset"),
        )

    def _optional_entity_id(self, raw: str | None) -> EntityId | None:
        return EntityId.from_string(raw) if raw is not None else None

    def _deserialize_datetime(self, raw: str):
        from datetime import datetime

        return datetime.fromisoformat(raw)
