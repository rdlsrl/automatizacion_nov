from __future__ import annotations

from pathlib import Path
import unittest


class ReviewSchemaContractsTests(unittest.TestCase):
    def test_review_migration_declares_queue_and_decision_tables(self) -> None:
        migration = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review/migrations/001_create_review_tables.sql")

        self.assertTrue(migration.exists())
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS review.review_queue", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS review.review_decision", sql)
        self.assertIn("decision_payload_json JSONB NOT NULL", sql)