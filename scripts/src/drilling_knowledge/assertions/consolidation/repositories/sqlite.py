"""SQLite repository for fact consolidation runs."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactConsolidationRun, FactSupport
from drilling_knowledge.assertions.consolidation.repositories.contracts import FactConsolidationRunRepository
from drilling_knowledge.assertions.consolidation.repositories.memory import InMemoryFactConsolidationRunRepository
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, EvidenceAssertion
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.common.serialization import from_json, to_json

_SCHEMA_VERSION = 1
_SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteFactConsolidationRunRepository(FactConsolidationRunRepository):
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteFactConsolidationRunRepository":
        return cls(database_path)

    def get_run(self, run_id: RunId) -> FactConsolidationRun | None:
        return next((run for run in self.list_runs() if run.run_id == run_id), None)

    def list_runs(self) -> tuple[FactConsolidationRun, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_fact_consolidation_runs ORDER BY run_id").fetchall()
        return InMemoryFactConsolidationRunRepository(tuple(from_json(row["payload_json"], FactConsolidationRun) for row in rows)).list_runs()

    def list_assertions(self, run_id: RunId) -> tuple[EvidenceAssertion, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_fact_run_assertions WHERE run_id = ? ORDER BY assertion_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], EvidenceAssertion) for row in rows)

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_fact_run_evidence_links WHERE run_id = ? ORDER BY link_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], AssertionEvidenceLink) for row in rows)

    def list_facts(self, run_id: RunId) -> tuple[ConsolidatedFact, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_consolidated_facts WHERE run_id = ? ORDER BY fact_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], ConsolidatedFact) for row in rows)

    def list_support_links(self, run_id: RunId) -> tuple[FactSupport, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_fact_supports WHERE run_id = ? ORDER BY fact_support_id", (str(run_id),)).fetchall()
        return tuple(from_json(row["payload_json"], FactSupport) for row in rows)

    def get_fact(self, fact_id: EntityId) -> ConsolidatedFact | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM dk_consolidated_facts WHERE fact_id = ?", (str(fact_id),)).fetchone()
        return None if row is None else from_json(row["payload_json"], ConsolidatedFact)

    def append_run(self, run: FactConsolidationRun) -> "SQLiteFactConsolidationRunRepository":
        with self._connect() as connection:
            run_row = (str(run.run_id), str(run.assertion_run_id), to_json(run))
            assertion_rows = tuple((str(assertion.assertion_id), str(run.run_id), to_json(assertion)) for assertion in run.assertions)
            link_rows = tuple((str(link.link_id), str(run.run_id), str(link.assertion_id), str(link.fragment_id), to_json(link)) for link in run.evidence_links)
            fact_rows = tuple(
                (
                    str(fact.fact_id),
                    str(run.run_id),
                    fact.claim_key,
                    fact.predicate_code,
                    str(fact.subject_id),
                    fact.lifecycle.value,
                    to_json(fact),
                )
                for fact in run.facts
            )
            support_rows = tuple(
                (str(support.fact_support_id), str(run.run_id), str(support.fact_id), str(support.assertion_id), to_json(support))
                for support in run.support_links
            )
            support_link_rows = tuple(
                (str(support.fact_support_id), str(link_id))
                for support in run.support_links
                for link_id in support.assertion_evidence_link_ids
            )

            self._validate_increment(connection, run)
            self._ensure_unique_rows(connection, "dk_fact_consolidation_runs", "run_id", ((run_row[0], run_row[-1]),))
            self._ensure_unique_rows(connection, "dk_fact_run_assertions", "assertion_id", tuple((row[0], row[-1]) for row in assertion_rows))
            self._ensure_unique_rows(connection, "dk_fact_run_evidence_links", "link_id", tuple((row[0], row[-1]) for row in link_rows))
            self._ensure_unique_rows(connection, "dk_consolidated_facts", "fact_id", tuple((row[0], row[-1]) for row in fact_rows))
            self._ensure_unique_rows(connection, "dk_fact_supports", "fact_support_id", tuple((row[0], row[-1]) for row in support_rows))

            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_fact_consolidation_runs (run_id, assertion_run_id, payload_json) VALUES (?, ?, ?)",
                (run_row,),
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_fact_run_assertions (assertion_id, run_id, payload_json) VALUES (?, ?, ?)",
                assertion_rows,
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_fact_run_evidence_links (link_id, run_id, assertion_id, fragment_id, payload_json) VALUES (?, ?, ?, ?, ?)",
                link_rows,
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_consolidated_facts (fact_id, run_id, claim_key, predicate_code, subject_id, lifecycle, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                fact_rows,
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_fact_supports (fact_support_id, run_id, fact_id, assertion_id, payload_json) VALUES (?, ?, ?, ?, ?)",
                support_rows,
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_fact_support_evidence_links (fact_support_id, link_id) VALUES (?, ?)",
                support_link_rows,
            )
        return self

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_fact_consolidation_runs (run_id TEXT PRIMARY KEY, assertion_run_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_fact_run_assertions (assertion_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_fact_run_evidence_links (link_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, assertion_id TEXT NOT NULL, fragment_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_consolidated_facts (fact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, claim_key TEXT NOT NULL, predicate_code TEXT NOT NULL, subject_id TEXT NOT NULL, lifecycle TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_fact_supports (fact_support_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, fact_id TEXT NOT NULL, assertion_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_fact_support_evidence_links (fact_support_id TEXT NOT NULL, link_id TEXT NOT NULL, PRIMARY KEY (fact_support_id, link_id))")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_fact_run_assertions_run ON dk_fact_run_assertions (run_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_fact_run_evidence_links_run ON dk_fact_run_evidence_links (run_id, assertion_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_consolidated_facts_run ON dk_consolidated_facts (run_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_consolidated_facts_claim ON dk_consolidated_facts (claim_key, predicate_code)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_consolidated_facts_lineage ON dk_consolidated_facts (claim_key, subject_id, predicate_code)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_fact_supports_fact ON dk_fact_supports (fact_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_fact_supports_run ON dk_fact_supports (run_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_fact_support_evidence_links_support ON dk_fact_support_evidence_links (fact_support_id)")
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

    def _validate_increment(self, connection: sqlite3.Connection, run: FactConsolidationRun) -> None:
        InMemoryFactConsolidationRunRepository((run,))
        fact_ids = tuple(sorted(str(fact.fact_id) for fact in run.facts))
        if fact_ids:
            placeholders = ", ".join("?" for _ in fact_ids)
            existing_facts = tuple(
                from_json(row["payload_json"], ConsolidatedFact)
                for row in connection.execute(
                    f"SELECT payload_json FROM dk_consolidated_facts WHERE fact_id IN ({placeholders})",
                    fact_ids,
                ).fetchall()
            )
            for fact in run.facts:
                previous = next((item for item in existing_facts if item.fact_id == fact.fact_id), None)
                if previous is not None:
                    InMemoryFactConsolidationRunRepository._validate_fact_transition(previous, fact)

        lineage_keys = {(fact.claim_key, str(fact.subject_id), fact.predicate_code) for fact in run.facts}
        for claim_key, subject_id, predicate_code in lineage_keys:
            existing_lineage = tuple(
                from_json(row["payload_json"], ConsolidatedFact)
                for row in connection.execute(
                    "SELECT payload_json FROM dk_consolidated_facts WHERE claim_key = ? AND subject_id = ? AND predicate_code = ?",
                    (claim_key, subject_id, predicate_code),
                ).fetchall()
            )
            combined_lineage: dict[str, ConsolidatedFact] = {
                str(fact.fact_id): fact
                for fact in existing_lineage
            }
            for fact in run.facts:
                if fact.claim_key == claim_key and str(fact.subject_id) == subject_id and fact.predicate_code == predicate_code:
                    combined_lineage[str(fact.fact_id)] = fact
            InMemoryFactConsolidationRunRepository._validate_active_lineages(tuple(combined_lineage.values()))