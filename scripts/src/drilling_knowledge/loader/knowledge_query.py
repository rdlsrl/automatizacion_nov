"""SQLite query service for persisted document-derived knowledge with provenance."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactSupport
from drilling_knowledge.assertions.domain import AssertionEvidenceLink
from drilling_knowledge.common.serialization import from_json
from drilling_knowledge.documents.domain import Document, DocumentFragment


@dataclass(frozen=True, slots=True)
class PersistedKnowledgeHit:
    fact: ConsolidatedFact
    support: FactSupport
    evidence_link: AssertionEvidenceLink
    fragment: DocumentFragment
    document: Document


class SQLiteKnowledgeQueryService:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    @classmethod
    def create(cls, database_path: str | Path) -> "SQLiteKnowledgeQueryService":
        return cls(database_path)

    def search(self, text: str, *, limit: int = 20) -> tuple[PersistedKnowledgeHit, ...]:
        needle = f"%{text.strip().lower()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT
                    fact.payload_json AS fact_json,
                    support.payload_json AS support_json,
                    link.payload_json AS link_json,
                    fragment.payload_json AS fragment_json,
                    document.payload_json AS document_json
                FROM dk_consolidated_facts AS fact
                JOIN dk_fact_supports AS support ON support.fact_id = fact.fact_id
                JOIN dk_fact_support_evidence_links AS support_link ON support_link.fact_support_id = support.fact_support_id
                JOIN dk_assertion_evidence_links AS link ON link.link_id = support_link.link_id
                JOIN dk_document_fragments AS fragment ON fragment.fragment_id = link.fragment_id
                JOIN dk_documents AS document ON document.document_id = link.document_id
                WHERE lower(fact.claim_key) LIKE ?
                   OR lower(link.normalized_text) LIKE ?
                   OR lower(fragment.normalized_text) LIKE ?
                   OR lower(fragment.text_content) LIKE ?
                ORDER BY fact.claim_key, fragment.page_number, fragment.fragment_id
                LIMIT ?
                """,
                (needle, needle, needle, needle, limit),
            ).fetchall()
        return tuple(
            PersistedKnowledgeHit(
                fact=from_json(row["fact_json"], ConsolidatedFact),
                support=from_json(row["support_json"], FactSupport),
                evidence_link=from_json(row["link_json"], AssertionEvidenceLink),
                fragment=from_json(row["fragment_json"], DocumentFragment),
                document=from_json(row["document_json"], Document),
            )
            for row in rows
        )

    @contextmanager
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()