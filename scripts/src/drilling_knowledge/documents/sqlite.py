"""SQLite persistence for structural document snapshots."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from drilling_knowledge.common.serialization import from_json, to_json
from drilling_knowledge.documents.domain import Document, DocumentKnowledgeSnapshot, DocumentSection, DocumentVersion, Figure, GlossaryTerm, Reference, Table

_SCHEMA_VERSION = 1
_SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteDocumentRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteDocumentRepository":
        return cls(database_path)

    def merge(self, snapshot: DocumentKnowledgeSnapshot) -> "SQLiteDocumentRepository":
        with self._connect() as connection:
            try:
                self._replace_version_scope_if_needed(connection, snapshot)
                self._upsert(connection, "dk_documents", "document_id", str(snapshot.document.entity_id), to_json(snapshot.document))
                self._upsert(connection, "dk_document_versions", "version_id", str(snapshot.version.entity_id), to_json(snapshot.version))
                for section in snapshot.sections:
                    self._upsert(connection, "dk_document_sections", "section_id", str(section.entity_id), to_json(section))
                for fragment in snapshot.fragments:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO dk_document_fragments (
                            fragment_id, document_id, version_id, fragment_type, normalized_text, text_content, page_number, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(fragment.entity_id),
                            str(fragment.trace.document_id),
                            str(fragment.trace.document_version_id),
                            fragment.fragment_type,
                            fragment.normalized_text,
                            fragment.text_content,
                            fragment.trace.page_number,
                            to_json(fragment),
                        ),
                    )
                for table in snapshot.tables:
                    self._upsert(connection, "dk_document_tables", "table_id", str(table.entity_id), to_json(table))
                for figure in snapshot.figures:
                    self._upsert(connection, "dk_document_figures", "figure_id", str(figure.entity_id), to_json(figure))
                for reference in snapshot.references:
                    self._upsert(connection, "dk_document_references", "reference_id", str(reference.entity_id), to_json(reference))
                for glossary_term in snapshot.glossary_terms:
                    self._upsert(connection, "dk_document_glossary_terms", "glossary_term_id", str(glossary_term.entity_id), to_json(glossary_term))
                self._validate_connection_state(connection, str(snapshot.version.entity_id))
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return self

    def get_snapshot(self, version_id: str) -> DocumentKnowledgeSnapshot | None:
        with self._connect() as connection:
            version_row = connection.execute("SELECT payload_json FROM dk_document_versions WHERE version_id = ?", (version_id,)).fetchone()
            if version_row is None:
                return None
            version = from_json(version_row["payload_json"], DocumentVersion)
            document_row = connection.execute("SELECT payload_json FROM dk_documents WHERE document_id = ?", (str(version.document_id),)).fetchone()
            if document_row is None:
                return None
            return self._hydrate_snapshot(connection, document_row["payload_json"], version_row["payload_json"])

    def list_fragment_rows(self, query_text: str, *, limit: int = 20) -> tuple[sqlite3.Row, ...]:
        needle = f"%{query_text.strip().lower()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT fragment_id, document_id, version_id, text_content, normalized_text, page_number, payload_json
                FROM dk_document_fragments
                WHERE lower(normalized_text) LIKE ? OR lower(text_content) LIKE ?
                ORDER BY version_id, page_number, fragment_id
                LIMIT ?
                """,
                (needle, needle, limit),
            ).fetchall()
        return tuple(rows)

    def _hydrate_snapshot(self, connection: sqlite3.Connection, document_payload: str, version_payload: str) -> DocumentKnowledgeSnapshot:
        from drilling_knowledge.documents.domain import DocumentFragment

        version = from_json(version_payload, DocumentVersion)
        return DocumentKnowledgeSnapshot(
            document=from_json(document_payload, Document),
            version=version,
            sections=tuple(
                from_json(row["payload_json"], DocumentSection)
                for row in connection.execute("SELECT payload_json FROM dk_document_sections WHERE version_id = ? ORDER BY section_id", (str(version.entity_id),)).fetchall()
            ),
            fragments=tuple(
                from_json(row["payload_json"], DocumentFragment)
                for row in connection.execute("SELECT payload_json FROM dk_document_fragments WHERE version_id = ? ORDER BY fragment_id", (str(version.entity_id),)).fetchall()
            ),
            figures=tuple(
                from_json(row["payload_json"], Figure)
                for row in connection.execute("SELECT payload_json FROM dk_document_figures WHERE version_id = ? ORDER BY figure_id", (str(version.entity_id),)).fetchall()
            ),
            tables=tuple(
                from_json(row["payload_json"], Table)
                for row in connection.execute("SELECT payload_json FROM dk_document_tables WHERE version_id = ? ORDER BY table_id", (str(version.entity_id),)).fetchall()
            ),
            references=tuple(
                from_json(row["payload_json"], Reference)
                for row in connection.execute("SELECT payload_json FROM dk_document_references WHERE version_id = ? ORDER BY reference_id", (str(version.entity_id),)).fetchall()
            ),
            glossary_terms=tuple(
                from_json(row["payload_json"], GlossaryTerm)
                for row in connection.execute("SELECT payload_json FROM dk_document_glossary_terms WHERE version_id = ? ORDER BY glossary_term_id", (str(version.entity_id),)).fetchall()
            ),
        )

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_documents (document_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_document_versions (version_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_document_sections (section_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS dk_document_fragments (fragment_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_id TEXT NOT NULL, fragment_type TEXT NOT NULL, normalized_text TEXT NOT NULL, text_content TEXT NOT NULL, page_number INTEGER NULL, payload_json TEXT NOT NULL)"
            )
            connection.execute("CREATE TABLE IF NOT EXISTS dk_document_tables (table_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_document_figures (figure_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_document_references (reference_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dk_document_glossary_terms (glossary_term_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload_json TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_sections_version ON dk_document_sections (version_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_fragments_version ON dk_document_fragments (version_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_fragments_text ON dk_document_fragments (normalized_text)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_tables_version ON dk_document_tables (version_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_figures_version ON dk_document_figures (version_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_references_version ON dk_document_references (version_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dk_document_glossary_terms_version ON dk_document_glossary_terms (version_id)")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            elif version < _SCHEMA_VERSION:
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

    def _upsert(self, connection: sqlite3.Connection, table_name: str, key_name: str, key_value: str, payload_json: str) -> None:
        existing = connection.execute(f"SELECT payload_json FROM {table_name} WHERE {key_name} = ?", (key_value,)).fetchone()
        if existing is not None:
            if existing["payload_json"] != payload_json:
                raise ValueError(f"Conflicting persisted payload for {table_name}:{key_value}")
            return
        if table_name == "dk_document_versions":
            document = from_json(payload_json, DocumentVersion)
            connection.execute(
                f"INSERT INTO {table_name} ({key_name}, document_id, payload_json) VALUES (?, ?, ?)",
                (key_value, str(document.document_id), payload_json),
            )
            return
        if table_name in {"dk_document_sections", "dk_document_tables", "dk_document_figures", "dk_document_references", "dk_document_glossary_terms"}:
            expected_type = {
                "dk_document_sections": DocumentSection,
                "dk_document_tables": Table,
                "dk_document_figures": Figure,
                "dk_document_references": Reference,
                "dk_document_glossary_terms": GlossaryTerm,
            }[table_name]
            item = from_json(payload_json, expected_type=expected_type)
            version_id = str(item.document_version_id if hasattr(item, "document_version_id") else item.trace.document_version_id)
            connection.execute(
                f"INSERT INTO {table_name} ({key_name}, version_id, payload_json) VALUES (?, ?, ?)",
                (key_value, version_id, payload_json),
            )
            return
        connection.execute(f"INSERT INTO {table_name} ({key_name}, payload_json) VALUES (?, ?)", (key_value, payload_json))

    def _replace_version_scope_if_needed(self, connection: sqlite3.Connection, snapshot: DocumentKnowledgeSnapshot) -> None:
        version_id = str(snapshot.version.entity_id)
        document_id = str(snapshot.document.entity_id)
        incoming_version = to_json(snapshot.version)
        persisted_version = connection.execute(
            "SELECT payload_json, document_id FROM dk_document_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if persisted_version is None:
            return
        if persisted_version["document_id"] != document_id:
            raise ValueError(f"Conflicting persisted document version owner for dk_document_versions:{version_id}")

        persisted_document = connection.execute(
            "SELECT payload_json FROM dk_documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        incoming_document = to_json(snapshot.document)

        same_document_and_version = (
            persisted_version["payload_json"] == incoming_version
            and (persisted_document is None or persisted_document["payload_json"] == incoming_document)
        )

        if same_document_and_version:
            persisted_snapshot = self._hydrate_snapshot(
                connection,
                persisted_document["payload_json"] if persisted_document is not None else incoming_document,
                persisted_version["payload_json"],
            )

            def keyed_payloads(items):
                return {
                    str(item.entity_id): to_json(item)
                    for item in items
                }

            structure_unchanged = (
                keyed_payloads(persisted_snapshot.sections) == keyed_payloads(snapshot.sections)
                and keyed_payloads(persisted_snapshot.fragments) == keyed_payloads(snapshot.fragments)
                and keyed_payloads(persisted_snapshot.tables) == keyed_payloads(snapshot.tables)
                and keyed_payloads(persisted_snapshot.figures) == keyed_payloads(snapshot.figures)
                and keyed_payloads(persisted_snapshot.references) == keyed_payloads(snapshot.references)
                and keyed_payloads(persisted_snapshot.glossary_terms) == keyed_payloads(snapshot.glossary_terms)
            )

            if structure_unchanged:
                return

        self._delete_version_scope(connection, document_id=document_id, version_id=version_id)

    def _delete_version_scope(self, connection: sqlite3.Connection, *, document_id: str, version_id: str) -> None:
        fragment_ids = tuple(
            row["fragment_id"]
            for row in connection.execute(
                "SELECT fragment_id FROM dk_document_fragments WHERE version_id = ?",
                (version_id,),
            ).fetchall()
        )
        link_ids = tuple(
            row["link_id"]
            for row in connection.execute(
                "SELECT link_id FROM dk_assertion_evidence_links WHERE document_version_id = ?",
                (version_id,),
            ).fetchall()
        )
        assertion_ids = tuple(
            row["assertion_id"]
            for row in connection.execute(
                "SELECT DISTINCT assertion_id FROM dk_assertion_evidence_links WHERE document_version_id = ?",
                (version_id,),
            ).fetchall()
        )
        support_ids = tuple(
            row["fact_support_id"]
            for row in connection.execute(
                f"SELECT DISTINCT fact_support_id FROM dk_fact_support_evidence_links WHERE link_id IN ({self._placeholders(link_ids)})",
                link_ids,
            ).fetchall()
        ) if link_ids else ()
        fact_ids = tuple(
            row["fact_id"]
            for row in connection.execute(
                f"SELECT DISTINCT fact_id FROM dk_fact_supports WHERE fact_support_id IN ({self._placeholders(support_ids)})",
                support_ids,
            ).fetchall()
        ) if support_ids else ()

        self._delete_where_in(connection, "dk_fact_support_evidence_links", "fact_support_id", support_ids)
        self._delete_where_in(connection, "dk_fact_supports", "fact_support_id", support_ids)
        self._delete_where_in(connection, "dk_fact_run_evidence_links", "link_id", link_ids)
        self._delete_where_in(connection, "dk_fact_run_assertions", "assertion_id", assertion_ids)
        self._delete_where_in(connection, "dk_assertion_validation_logs", "assertion_id", assertion_ids)
        self._delete_where_in(connection, "dk_assertion_evidence_links", "link_id", link_ids)
        self._delete_where_in(connection, "dk_evidence_assertions", "assertion_id", assertion_ids)

        if fact_ids:
            orphan_fact_ids = tuple(
                row["fact_id"]
                for row in connection.execute(
                    f"SELECT fact_id FROM dk_consolidated_facts WHERE fact_id IN ({self._placeholders(fact_ids)}) AND fact_id NOT IN (SELECT DISTINCT fact_id FROM dk_fact_supports)",
                    fact_ids,
                ).fetchall()
            )
            self._delete_where_in(connection, "dk_consolidated_facts", "fact_id", orphan_fact_ids)

        self._delete_search_documents(connection, document_id=document_id, fragment_ids=fragment_ids, assertion_ids=assertion_ids, fact_ids=fact_ids)

        connection.execute("DELETE FROM dk_document_sections WHERE version_id = ?", (version_id,))
        connection.execute("DELETE FROM dk_document_tables WHERE version_id = ?", (version_id,))
        connection.execute("DELETE FROM dk_document_figures WHERE version_id = ?", (version_id,))
        connection.execute("DELETE FROM dk_document_references WHERE version_id = ?", (version_id,))
        connection.execute("DELETE FROM dk_document_glossary_terms WHERE version_id = ?", (version_id,))
        connection.execute("DELETE FROM dk_document_fragments WHERE version_id = ?", (version_id,))
        connection.execute("DELETE FROM dk_document_versions WHERE version_id = ?", (version_id,))
        connection.execute(
            "DELETE FROM dk_documents WHERE document_id = ? AND NOT EXISTS (SELECT 1 FROM dk_document_versions WHERE document_id = ?)",
            (document_id, document_id),
        )
        self._delete_orphan_batches(connection)
        self._delete_orphan_runs(connection)

    @staticmethod
    def _placeholders(values: tuple[str, ...]) -> str:
        return ", ".join("?" for _ in values)

    def _delete_where_in(self, connection: sqlite3.Connection, table_name: str, key_name: str, values: tuple[str, ...]) -> None:
        if not values:
            return
        connection.execute(
            f"DELETE FROM {table_name} WHERE {key_name} IN ({self._placeholders(values)})",
            values,
        )

    def _delete_search_documents(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        fragment_ids: tuple[str, ...],
        assertion_ids: tuple[str, ...],
        fact_ids: tuple[str, ...],
    ) -> None:
        connection.execute(
            "DELETE FROM dk_search_documents WHERE source_type = 'document' AND source_entity_id = ?",
            (document_id,),
        )
        self._delete_search_documents_for_ids(connection, source_type="fragment", source_ids=fragment_ids)
        self._delete_search_documents_for_ids(connection, source_type="assertion", source_ids=assertion_ids)
        self._delete_search_documents_for_ids(connection, source_type="fact", source_ids=fact_ids)

    def _delete_search_documents_for_ids(self, connection: sqlite3.Connection, *, source_type: str, source_ids: tuple[str, ...]) -> None:
        if not source_ids:
            return
        connection.execute(
            f"DELETE FROM dk_search_documents WHERE source_type = ? AND source_entity_id IN ({self._placeholders(source_ids)})",
            (source_type, *source_ids),
        )

    @staticmethod
    def _delete_orphan_batches(connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM dk_search_projection_batches WHERE projection_batch_id NOT IN (SELECT DISTINCT projection_batch_id FROM dk_search_documents)"
        )

    @staticmethod
    def _delete_orphan_runs(connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM dk_assertion_generation_runs WHERE run_id NOT IN (SELECT DISTINCT run_id FROM dk_evidence_assertions UNION SELECT DISTINCT run_id FROM dk_assertion_evidence_links UNION SELECT DISTINCT run_id FROM dk_assertion_validation_logs)"
        )
        connection.execute(
            "DELETE FROM dk_fact_consolidation_runs WHERE run_id NOT IN (SELECT DISTINCT run_id FROM dk_consolidated_facts UNION SELECT DISTINCT run_id FROM dk_fact_supports UNION SELECT DISTINCT run_id FROM dk_fact_run_assertions UNION SELECT DISTINCT run_id FROM dk_fact_run_evidence_links)"
        )

    def _validate_connection_state(self, connection: sqlite3.Connection, version_id: str) -> None:
        version_row = connection.execute("SELECT payload_json FROM dk_document_versions WHERE version_id = ?", (version_id,)).fetchone()
        if version_row is None:
            raise ValueError(f"Missing persisted document version: {version_id}")
        version = from_json(version_row["payload_json"], DocumentVersion)
        document_row = connection.execute("SELECT payload_json FROM dk_documents WHERE document_id = ?", (str(version.document_id),)).fetchone()
        if document_row is None:
            raise ValueError(f"Missing persisted document for version: {version_id}")
        snapshot = self._hydrate_snapshot(connection, document_row["payload_json"], version_row["payload_json"])
        snapshot.validate().require_valid(code="sqlite_document_snapshot_validation_failed")