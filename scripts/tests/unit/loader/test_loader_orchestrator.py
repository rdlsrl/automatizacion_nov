from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from drilling_knowledge.loader import ArtifactRegistry, LASAdapter, LoadOrchestrator, LoadPolicy, PipelineDispatcher, SourceAdapter, SourceDefinition


class LoadOrchestratorTests(unittest.TestCase):
    def test_load_source_dry_run_summarizes_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            listing = root / "index.html"
            document = root / "manual.md"
            document.write_text("# Manual\n", encoding="utf-8")
            listing.write_text(f'<html><body><a href="{document.as_uri()}">manual</a></body></html>', encoding="utf-8")
            orchestrator = LoadOrchestrator(
                source_adapter=SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root),
                las_adapter=LASAdapter(),
                artifact_registry=ArtifactRegistry.create(root / "loader.sqlite"),
                pipeline_dispatcher=PipelineDispatcher(workflow=_StubWorkflow()),
            )

            summary = orchestrator.load_source("nov", LoadPolicy(dry_run=True))

            self.assertEqual(summary.discovered, 1)
            self.assertEqual(summary.dispatched, 0)

    def test_load_source_resume_continues_after_last_processed_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_document = root / "a-manual.md"
            second_document = root / "b-manual.md"
            first_document.write_text("# Manual A\n", encoding="utf-8")
            second_document.write_text("# Manual B\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{first_document.as_uri()}">manual-a</a><a href="{second_document.as_uri()}">manual-b</a></body></html>',
                encoding="utf-8",
            )
            orchestrator = LoadOrchestrator(
                source_adapter=SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root),
                las_adapter=LASAdapter(),
                artifact_registry=ArtifactRegistry.create(root / "loader.sqlite"),
                pipeline_dispatcher=PipelineDispatcher(workflow=_StubWorkflow()),
            )

            first = orchestrator.load_source("nov", LoadPolicy(max_documents_per_run=1))
            second = orchestrator.load_source("nov", LoadPolicy(max_documents_per_run=1, resume=True))

            self.assertEqual(first.discovered, 1)
            self.assertEqual(second.discovered, 1)
            self.assertEqual(second.resumed_from_document_url, first.last_processed_document_url)
            self.assertNotEqual(second.last_processed_document_url, first.last_processed_document_url)

    def test_load_source_finishes_run_as_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(f'<html><body><a href="{document.as_uri()}">manual</a></body></html>', encoding="utf-8")
            database_path = root / "loader.sqlite"
            orchestrator = LoadOrchestrator(
                source_adapter=SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root),
                las_adapter=LASAdapter(),
                artifact_registry=ArtifactRegistry.create(database_path),
                pipeline_dispatcher=PipelineDispatcher(workflow=_StubWorkflow()),
            )

            summary = orchestrator.load_source("nov", LoadPolicy())

            connection = sqlite3.connect(database_path)
            row = connection.execute("select status, finished_at, summary_json from load_runs where load_run_id = ?", (str(summary.load_run_id),)).fetchone()
            self.assertEqual(row[0], "completed")
            self.assertIsNotNone(row[1])
            payload = json.loads(row[2])
            self.assertEqual(payload["last_processed_document_url"], summary.last_processed_document_url)

    def test_load_source_marks_run_failed_when_registry_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_document = root / "a-manual.md"
            second_document = root / "b-manual.md"
            first_document.write_text("# Manual A\n", encoding="utf-8")
            second_document.write_text("# Manual B\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{first_document.as_uri()}">manual-a</a><a href="{second_document.as_uri()}">manual-b</a></body></html>',
                encoding="utf-8",
            )
            database_path = root / "loader.sqlite"
            registry = _FailingRegistry.create(database_path, failure=RuntimeError("registry exploded"), fail_on_call=2)
            orchestrator = LoadOrchestrator(
                source_adapter=SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root),
                las_adapter=LASAdapter(),
                artifact_registry=registry,
                pipeline_dispatcher=PipelineDispatcher(workflow=_StubWorkflow()),
            )

            with self.assertRaises(RuntimeError):
                orchestrator.load_source("nov", LoadPolicy())

            connection = sqlite3.connect(database_path)
            row = connection.execute("select status, finished_at, summary_json from load_runs order by started_at desc limit 1").fetchone()
            self.assertEqual(row[0], "failed")
            payload = json.loads(row[2])
            self.assertEqual(payload["last_processed_document_url"], first_document.as_uri())
            self.assertEqual(payload["error_type"], "RuntimeError")

    def test_load_source_marks_run_interrupted_on_keyboard_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_document = root / "a-manual.md"
            second_document = root / "b-manual.md"
            first_document.write_text("# Manual A\n", encoding="utf-8")
            second_document.write_text("# Manual B\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{first_document.as_uri()}">manual-a</a><a href="{second_document.as_uri()}">manual-b</a></body></html>',
                encoding="utf-8",
            )
            database_path = root / "loader.sqlite"
            registry = _FailingRegistry.create(database_path, failure=KeyboardInterrupt(), fail_on_call=2)
            orchestrator = LoadOrchestrator(
                source_adapter=SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root),
                las_adapter=LASAdapter(),
                artifact_registry=registry,
                pipeline_dispatcher=PipelineDispatcher(workflow=_StubWorkflow()),
            )

            with self.assertRaises(KeyboardInterrupt):
                orchestrator.load_source("nov", LoadPolicy())

            connection = sqlite3.connect(database_path)
            row = connection.execute("select status, finished_at, summary_json from load_runs order by started_at desc limit 1").fetchone()
            self.assertEqual(row[0], "interrupted")
            payload = json.loads(row[2])
            self.assertEqual(payload["last_processed_document_url"], first_document.as_uri())
            self.assertEqual(payload["error_type"], "KeyboardInterrupt")

    def test_load_source_continues_after_document_download_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_document = root / "a-manual.md"
            second_document = root / "b-manual.md"
            first_document.write_text("# Manual A\n", encoding="utf-8")
            second_document.write_text("# Manual B\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(
                f'<html><body><a href="{first_document.as_uri()}">manual-a</a><a href="{second_document.as_uri()}">manual-b</a></body></html>',
                encoding="utf-8",
            )
            database_path = root / "loader.sqlite"
            source_adapter = _FailingDownloadSourceAdapter(
                (SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),),
                root,
                failing_url=first_document.as_uri(),
            )
            orchestrator = LoadOrchestrator(
                source_adapter=source_adapter,
                las_adapter=LASAdapter(),
                artifact_registry=ArtifactRegistry.create(database_path),
                pipeline_dispatcher=PipelineDispatcher(workflow=_StubWorkflow()),
            )

            summary = orchestrator.load_source("nov", LoadPolicy())

            self.assertEqual(summary.discovered, 2)
            self.assertEqual(summary.dispatched, 1)
            self.assertEqual(summary.failed, 1)
            self.assertEqual(summary.last_processed_document_url, second_document.as_uri())
            connection = sqlite3.connect(database_path)
            row = connection.execute("select status, summary_json from load_runs where load_run_id = ?", (str(summary.load_run_id),)).fetchone()
            self.assertEqual(row[0], "completed_with_errors")
            payload = json.loads(row[1])
            self.assertEqual(payload["failed"], 1)


class _StubWorkflow:
    def run(self, **kwargs):
        from drilling_knowledge.common.ids import EntityId, RunId

        return type(
            "WorkflowResult",
            (),
            {
                "document": type("Document", (), {"entity_id": EntityId.from_seed("loader.document", "dry-run")})(),
                "pipeline_run": type("PipelineRun", (), {"pipeline_run_id": RunId.from_seed("loader.run", "dry-run")})(),
            },
        )()


class _FailingRegistry(ArtifactRegistry):
    def __init__(self, database_path: str | Path, *, failure: BaseException, fail_on_call: int) -> None:
        super().__init__(database_path)
        self._failure = failure
        self._fail_on_call = fail_on_call
        self._register_calls = 0

    @classmethod
    def create(cls, database_path: str | Path, *, failure: BaseException, fail_on_call: int) -> "_FailingRegistry":
        return cls(database_path, failure=failure, fail_on_call=fail_on_call)

    def register_downloaded_artifact(self, artifact):
        self._register_calls += 1
        if self._register_calls == self._fail_on_call:
            raise self._failure
        return super().register_downloaded_artifact(artifact)


class _FailingDownloadSourceAdapter(SourceAdapter):
    def __init__(self, definitions, workspace_root: Path, *, failing_url: str) -> None:
        super().__init__(definitions, workspace_root)
        self._failing_url = failing_url

    def download(self, documents, policy):
        if len(documents) == 1 and documents[0].document_url == self._failing_url:
            raise RuntimeError("download failed")
        return super().download(documents, policy)