from __future__ import annotations

from pathlib import Path
import unittest


class WorkflowSchemaContractsTests(unittest.TestCase):
    def test_workflow_migration_declares_pipeline_and_step_tables(self) -> None:
        migration = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/db/workflow/migrations/001_create_workflow_tables.sql")

        self.assertTrue(migration.exists())
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS workflow.pipeline_run", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS workflow.pipeline_step_run", sql)
        self.assertIn("UNIQUE (pipeline_run_id, step_order)", sql)