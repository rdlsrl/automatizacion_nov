"""SQLite repository for evidence assertion runs."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionGenerationRun, AssertionValidationLog, EvidenceAssertion
from drilling_knowledge.assertions.repositories.contracts import AssertionGenerationRunRepository
from drilling_knowledge.assertions.repositories.memory import InMemoryAssertionGenerationRunRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.common.serialization import from_json, to_json

_SCHEMA_VERSION = 1
_SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteAssertionGenerationRunRepository(AssertionGenerationRunRepository):
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteAssertionGenerationRunRepository":
        return cls(database_path)

    def get_run(self, run_id: RunId) -> AssertionGenerationRun | None:
        return next((run for run in self.list_runs() if run.run_id == run_id), None)

    def list_runs(self) -> tuple[AssertionGenerationRun, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_assertion_generation_runs ORDER BY run_id").fetchall()
        return InMemoryAssertionGenerationRunRepository(tuple(from_json(row["payload_json"], AssertionGenerationRun) for row in rows)).list_runs()

    def list_assertions(self, run_id: RunId) -> tuple[EvidenceAssertion, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_evidence_assertions WHERE run_id = ? ORDER BY assertion_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], EvidenceAssertion) for row in rows)

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_assertion_evidence_links WHERE run_id = ? ORDER BY link_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], AssertionEvidenceLink) for row in rows)

    def list_validation_logs(self, run_id: RunId) -> tuple[AssertionValidationLog, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_assertion_validation_logs WHERE run_id = ? ORDER BY log_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], AssertionValidationLog) for row in rows)

    def get_assertion(self, assertion_id: EntityId) -> EvidenceAssertion | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM dk_evidence_assertions WHERE assertion_id = ?", (str(assertion_id),)).fetchone()
        return None if row is None else from_json(row["payload_json"], EvidenceAssertion)

    def append_run(self, run: AssertionGenerationRun) -> "SQLiteAssertionGenerationRunRepository":
        with self._connect() as connection:
            run_row = (str(run.run_id), str(run.semantic_run_id), to_json(run))
            assertion_rows = tuple(
                (
                    str(assertion.assertion_id),
                    str(run.run_id),
                    assertion.status.value,
                    assertion.predicate_code,
                    str(assertion.subject_id),
                    to_json(assertion),
                )
                for assertion in run.assertions
            )
            link_rows = tuple(
                (
                    str(link.link_id),
                    str(run.run_id),
                    str(link.assertion_id),
                    str(link.document_id),
                    str(link.document_version_id),
                    str(link.fragment_id),
                    link.normalized_text,
                    to_json(link),
                )
                for link in run.evidence_links
            )
            log_rows = tuple((str(log.log_id), str(run.run_id), str(log.assertion_id), to_json(log)) for log in run.validation_logs)

            self._validate_increment(connection, run)
            self._ensure_unique_rows(connection, "dk_assertion_generation_runs", "run_id", ((run_row[0], run_row[-1]),))
            self._ensure_unique_rows(connection, "dk_evidence_assertions", "assertion_id", tuple((row[0], row[-1]) for row in assertion_rows))
            self._ensure_unique_rows(connection, "dk_assertion_evidence_links", "link_id", tuple((row[0], row[-1]) for row in link_rows))
            self._ensure_unique_rows(connection, "dk_assertion_validation_logs", "log_id", tuple((row[0], row[-1]) for row in log_rows))

            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_assertion_generation_runs (run_id, semantic_run_id, payload_json) VALUES (?, ?, ?)",
                (run_row,),
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_evidence_assertions (assertion_id, run_id, status, predicate_code, subject_id, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                assertion_rows,
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_assertion_evidence_links (link_id, run_id, assertion_id, document_id, document_version_id, fragment_id, normalized_text, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                link_rows,
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_assertion_validation_logs (log_id, run_id, assertion_id, payload_json) VALUES (?, ?, ?, ?)",
                log_rows,
            )
        return self

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_assertion_generation_runs (run_id TEXT PRIMARY KEY, semantic_run_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_evidence_assertions (assertion_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL, predicate_code TEXT NOT NULL, subject_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_assertion_evidence_links (link_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, assertion_id TEXT NOT NULL, document_id TEXT NOT NULL, document_version_id TEXT NOT NULL, fragment_id TEXT NOT NULL, normalized_text TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_assertion_validation_logs (log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, assertion_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_evidence_assertions_run ON dk_evidence_assertions (run_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_assertion_links_run ON dk_assertion_evidence_links (run_id, assertion_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_assertion_validation_logs_run ON dk_assertion_validation_logs (run_id)")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.commit()

    @contextmanager
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=_SQLITE_BUSY_TIMEOUT_MS / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MS}")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ensure_unique_rows(self, connection: sqlite3.Connection, table: str, key_name: str, rows: tuple[tuple[str, str], ...]) -> None:
        if not rows:
            return
        keys = tuple(key for key, _ in rows)
        placeholders = ", ".join("?" for _ in keys)
        existing = {
            row[key_name]: row["payload_json"]
            for row in connection.execute(f"SELECT {key_name}, payload_json FROM {table} WHERE {key_name} IN ({placeholders})", keys).fetchall()
        }
        for key, payload_json in rows:
            persisted = existing.get(key)
            if persisted is not None and persisted != payload_json:
                raise ValueError(f"Conflicting persisted payload for {table}:{key}")

    def _insert_missing_rows(self, connection: sqlite3.Connection, sql: str, rows: tuple[tuple[object, ...], ...]) -> None:
        if rows:
            connection.executemany(sql, rows)

    def _validate_increment(self, connection: sqlite3.Connection, run: AssertionGenerationRun) -> None:
        InMemoryAssertionGenerationRunRepository((run,))
        referenced_ids = tuple(
            sorted(
                {
                    str(target_id)
                    for assertion in run.assertions
                    for target_id in (assertion.supersedes_id, assertion.invalidates_id)
                    if target_id is not None
                }
            )
        )
        if not referenced_ids:
            return
        placeholders = ", ".join("?" for _ in referenced_ids)
        rows = connection.execute(
            f"SELECT assertion_id, payload_json FROM dk_evidence_assertions WHERE assertion_id IN ({placeholders})",
            referenced_ids,
        ).fetchall()
        existing_assertions = {row["assertion_id"]: from_json(row["payload_json"], EvidenceAssertion) for row in rows}
        missing = [assertion_id for assertion_id in referenced_ids if assertion_id not in existing_assertions]
        if missing:
            raise ValueError(f"Conflicting persisted payload for dk_evidence_assertions:{missing[0]}")