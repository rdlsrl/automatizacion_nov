"""SQLite repository for search projection batches with basic text query support."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.common.serialization import from_json, to_json
from drilling_knowledge.projections.search.domain import SearchDocument, SearchProjectionBatch
from drilling_knowledge.projections.search.repositories.contracts import SearchProjectionBatchRepository
from drilling_knowledge.projections.search.repositories.memory import InMemorySearchProjectionBatchRepository

_SCHEMA_VERSION = 1
_SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteSearchProjectionBatchRepository(SearchProjectionBatchRepository):
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteSearchProjectionBatchRepository":
        return cls(database_path)

    def get_batch(self, projection_batch_id: EntityId) -> SearchProjectionBatch | None:
        return next((batch for batch in self.list_batches() if batch.projection_batch_id == projection_batch_id), None)

    def list_batches(self) -> tuple[SearchProjectionBatch, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM dk_search_projection_batches ORDER BY projection_batch_id").fetchall()
        return InMemorySearchProjectionBatchRepository(tuple(from_json(row["payload_json"], SearchProjectionBatch) for row in rows)).list_batches()

    def append_batch(self, batch: SearchProjectionBatch) -> "SQLiteSearchProjectionBatchRepository":
        with self._connect() as connection:
            batch_row = (str(batch.projection_batch_id), to_json(batch))
            document_rows = tuple(
                (
                    str(document.search_document_id),
                    str(batch.projection_batch_id),
                    document.source_type,
                    str(document.source_entity_id),
                    document.index_name,
                    document.index_text,
                    to_json(document),
                )
                for document in batch.documents
            )

            self._validate_increment(batch)
            self._ensure_unique_rows(connection, "dk_search_projection_batches", "projection_batch_id", ((batch_row[0], batch_row[-1]),))
            self._ensure_unique_rows(connection, "dk_search_documents", "search_document_id", tuple((row[0], row[-1]) for row in document_rows))
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_search_projection_batches (projection_batch_id, payload_json) VALUES (?, ?)",
                (batch_row,),
            )
            self._insert_missing_rows(
                connection,
                "INSERT OR IGNORE INTO dk_search_documents (search_document_id, projection_batch_id, source_type, source_entity_id, index_name, index_text, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                document_rows,
            )
        return self

    def search(self, text: str, *, source_type: str | None = None, limit: int = 20) -> tuple[SearchDocument, ...]:
        needle = f"%{text.strip().lower()}%"
        query = "SELECT payload_json FROM dk_search_documents WHERE lower(index_text) LIKE ?"
        parameters: list[object] = [needle]
        if source_type is not None:
            query += " AND source_type = ?"
            parameters.append(source_type.strip().lower())
        query += " ORDER BY index_name, source_entity_id LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return tuple(from_json(row["payload_json"], SearchDocument) for row in rows)

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_search_projection_batches (projection_batch_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_search_documents (search_document_id TEXT PRIMARY KEY, projection_batch_id TEXT NOT NULL, source_type TEXT NOT NULL, source_entity_id TEXT NOT NULL, index_name TEXT NOT NULL, index_text TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_search_documents_batch ON dk_search_documents (projection_batch_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_search_documents_lookup ON dk_search_documents (source_type, index_name)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_search_documents_text ON dk_search_documents (index_text)")
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

    def _validate_increment(self, batch: SearchProjectionBatch) -> None:
        InMemorySearchProjectionBatchRepository((batch,))