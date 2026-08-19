from __future__ import annotations

from pathlib import Path
from collections import Counter
import json
import sqlite3
import tempfile
import unittest
import zipfile

from drilling_knowledge.loader import ArtifactRegistry, LoadOrchestrator, LoadPolicy, SourceDefinition, SourceAdapter


class LoaderIntegrationTests(unittest.TestCase):
    def test_document_load_processes_new_and_duplicate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n\n4 mA = 0 psi\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(f'<html><body><a href="{document.as_uri()}">manual</a></body></html>', encoding="utf-8")
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)
            orchestrator.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            orchestrator.artifact_registry.record_source_definition(orchestrator.source_adapter.definition_for("nov"))

            first = orchestrator.load_source("nov", LoadPolicy())
            second = orchestrator.load_source("nov", LoadPolicy())

            self.assertEqual(first.dispatched, 1)
            self.assertGreaterEqual(second.duplicates, 1)

    def test_document_load_resume_processes_next_batch_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_document = root / "a-manual.md"
            second_document = root / "b-manual.md"
            first_document.write_text("# Manual A\n\n4 mA = 0 psi\n", encoding="utf-8")
            second_document.write_text("# Manual B\n\n20 mA = 5000 psi\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{first_document.as_uri()}">manual-a</a><a href="{second_document.as_uri()}">manual-b</a></body></html>',
                encoding="utf-8",
            )
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)
            orchestrator.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            orchestrator.artifact_registry.record_source_definition(orchestrator.source_adapter.definition_for("nov"))

            first = orchestrator.load_source("nov", LoadPolicy(max_documents_per_run=1))
            second = orchestrator.load_source("nov", LoadPolicy(max_documents_per_run=1, resume=True))
            third = orchestrator.load_source("nov", LoadPolicy(max_documents_per_run=1, resume=True))

            self.assertEqual(first.dispatched, 1)
            self.assertEqual(second.dispatched, 1)
            self.assertEqual(second.duplicates, 0)
            self.assertEqual(second.resumed_from_document_url, first.last_processed_document_url)
            self.assertEqual(third.discovered, 0)

    def test_las_load_generates_gap_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            las = root / "sample.las"
            las.write_text("~Curve\nSPP.PSI : Standpipe Pressure\nSPP.BAR : Pump Pressure\n~A\n", encoding="utf-8")
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)

            summary = orchestrator.load_las(root, LoadPolicy())

            self.assertGreaterEqual(summary.gaps_detected, 1)
            self.assertEqual(summary.dispatched, 1)

    def test_document_load_skips_non_processable_archive_members_without_failing_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n\n4 mA = 0 psi\n", encoding="utf-8")
            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("installer.msi", "binary payload")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{document.as_uri()}">manual</a><a href="{archive.as_uri()}">archive</a></body></html>',
                encoding="utf-8",
            )
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)
            orchestrator.source_adapter = SourceAdapter((SourceDefinition("pason", "Pason", (listing.as_uri(),), ("",), (".md", ".zip"), "html_listing"),), root)
            orchestrator.artifact_registry.record_source_definition(orchestrator.source_adapter.definition_for("pason"))

            summary = orchestrator.load_source("pason", LoadPolicy())

            self.assertEqual(summary.dispatched, 1)
            self.assertEqual(summary.failed, 0)
            connection = sqlite3.connect(root / "loader.sqlite")
            statuses = connection.execute("select status from dispatch_results order by artifact_id").fetchall()
            self.assertEqual(Counter(row[0] for row in statuses), Counter({"skipped": 2, "dispatched": 1}))

    def test_las_second_run_is_idempotent_and_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            las = root / "sample.las"
            las.write_text("~Curve\nSPP.PSI : Standpipe Pressure\nSPP.BAR : Pump Pressure\n~A\n", encoding="utf-8")
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)

            first = orchestrator.load_las(root, LoadPolicy())
            second = orchestrator.load_las(root, LoadPolicy())

            self.assertEqual(first.failed, 0)
            self.assertEqual(second.failed, 0)
            self.assertEqual(second.dispatched, 0)

    def test_resume_after_interruption_uses_last_valid_checkpoint_without_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_document = root / "a-manual.md"
            second_document = root / "b-manual.md"
            first_document.write_text("# Manual A\n\n4 mA = 0 psi\n", encoding="utf-8")
            second_document.write_text("# Manual B\n\n20 mA = 5000 psi\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{first_document.as_uri()}">manual-a</a><a href="{second_document.as_uri()}">manual-b</a></body></html>',
                encoding="utf-8",
            )
            database_path = root / "loader.sqlite"
            first = LoadOrchestrator.create_default(database_path=database_path, workspace_root=root)
            first.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            first.artifact_registry = _InterruptingRegistry(database_path, fail_on_call=2)
            first.artifact_registry.record_source_definition(first.source_adapter.definition_for("nov"))

            with self.assertRaises(KeyboardInterrupt):
                first.load_source("nov", LoadPolicy())

            second = LoadOrchestrator.create_default(database_path=database_path, workspace_root=root)
            second.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            second.artifact_registry.record_source_definition(second.source_adapter.definition_for("nov"))

            resumed = second.load_source("nov", LoadPolicy(resume=True, max_documents_per_run=1))

            self.assertEqual(resumed.dispatched, 1)
            self.assertEqual(resumed.resumed_from_document_url, first_document.as_uri())
            connection = sqlite3.connect(database_path)
            dispatched = connection.execute("select count(*) from dispatch_results where status = 'dispatched'").fetchone()[0]
            self.assertEqual(dispatched, 2)

    def test_new_run_marks_orphaned_runs_interrupted_before_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n\n4 mA = 0 psi\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(f'<html><body><a href="{document.as_uri()}">manual</a></body></html>', encoding="utf-8")
            database_path = root / "loader.sqlite"
            registry = ArtifactRegistry.create(database_path)
            stale_run = registry.start_run(mode="document", target="nov", policy=LoadPolicy())
            other_stale_run = registry.start_run(mode="document", target="nov", policy=LoadPolicy())
            connection = sqlite3.connect(database_path)
            stale_summary = json.dumps({"process_id": 999999, "last_processed_document_url": document.as_uri()})
            connection.execute("update load_runs set summary_json = ?, finished_at = null, status = 'running' where load_run_id = ?", (stale_summary, str(stale_run)))
            connection.execute("update load_runs set summary_json = ?, finished_at = null, status = 'running' where load_run_id = ?", (stale_summary, str(other_stale_run)))
            connection.commit()

            orchestrator = LoadOrchestrator.create_default(database_path=database_path, workspace_root=root)
            orchestrator.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            orchestrator.artifact_registry.record_source_definition(orchestrator.source_adapter.definition_for("nov"))

            summary = orchestrator.load_source("nov", LoadPolicy(resume=True, max_documents_per_run=1))

            rows = connection.execute(
                "select load_run_id, status, finished_at, summary_json from load_runs where target = 'nov' order by started_at"
            ).fetchall()
            interrupted = [row for row in rows if row[1] == "interrupted"]
            self.assertEqual(len(interrupted), 2)
            for row in interrupted:
                payload = json.loads(row[3])
                self.assertTrue(payload["stale_recovered"])
                self.assertIsNotNone(row[2])
            self.assertEqual(summary.resumed_from_document_url, document.as_uri())
            self.assertEqual(summary.discovered, 0)

    def test_document_load_persists_semantic_metrics_per_dispatched_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n\n4 mA = 0 psi\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(f'<html><body><a href="{document.as_uri()}">manual</a></body></html>', encoding="utf-8")
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)
            orchestrator.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            orchestrator.artifact_registry.record_source_definition(orchestrator.source_adapter.definition_for("nov"))

            summary = orchestrator.load_source("nov", LoadPolicy())

            self.assertEqual(summary.dispatched, 1)
            metrics = orchestrator.artifact_registry.list_semantic_metrics("nov")
            self.assertEqual(len(metrics), 1)
            self.assertGreaterEqual(metrics[0].fragments, 1)
            self.assertGreaterEqual(metrics[0].search_documents, 1)


class _InterruptingRegistry(ArtifactRegistry):
    def __init__(self, database_path: str | Path, *, fail_on_call: int) -> None:
        super().__init__(database_path)
        self._fail_on_call = fail_on_call
        self._register_calls = 0

    def register_downloaded_artifact(self, artifact):
        self._register_calls += 1
        if self._register_calls == self._fail_on_call:
            raise KeyboardInterrupt()
        return super().register_downloaded_artifact(artifact)