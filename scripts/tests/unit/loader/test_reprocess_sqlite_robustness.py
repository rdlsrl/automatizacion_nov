from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.loader.artifact_registry import ArtifactRegistry, DispatchRequest, DownloadedArtifact
from drilling_knowledge.loader.knowledge_query import SQLiteKnowledgeQueryService
from drilling_knowledge.loader.pipeline_dispatcher import PipelineDispatcher


_RUNNER_PATH = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/run_reprocess_local_corpus.py")
_SPEC = importlib.util.spec_from_file_location("run_reprocess_local_corpus", _RUNNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
LocalCorpusReprocessor = _MODULE.LocalCorpusReprocessor


class ReprocessSqliteRobustnessTests(unittest.TestCase):
    def test_sequential_runner_closes_sqlite_writes_and_keeps_results_queryable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "loader.sqlite"
            report_path = root / "report.json"
            downloads = root / "downloads"
            downloads.mkdir()
            registry = ArtifactRegistry.create(database_path)

            fixture_text = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/tests/fixtures/extraction/explicit_extraction.md").read_text(encoding="utf-8")

            persisted_artifact, persisted_path = self._register_markdown_artifact(registry, downloads, "persisted", fixture_text)
            seeded_dispatcher = PipelineDispatcher.create_default(database_path=database_path)
            seeded_result = seeded_dispatcher.dispatch(self._dispatch_request(persisted_artifact, persisted_path, "persisted"))
            self.assertEqual(seeded_result.status, "dispatched")
            registry.record_dispatch_result(seeded_result)

            for index in range(18):
                self._register_markdown_artifact(registry, downloads, f"doc-{index:02d}", fixture_text + f"\n\nartifact-seq-{index:02d}\n")

            corrupt_pdf = downloads / "corrupt.pdf"
            corrupt_pdf.write_bytes(b"%PDF-1.7\nnot-a-real-pdf")
            registry.register_downloaded_artifact(
                DownloadedArtifact(
                    artifact_id=EntityId.from_seed("test.artifact", "corrupt-pdf"),
                    source_name="seq",
                    original_url="https://example.test/corrupt.pdf",
                    canonical_url="https://example.test/corrupt.pdf",
                    local_path=str(corrupt_pdf),
                    content_type="application/pdf",
                    size_bytes=corrupt_pdf.stat().st_size,
                    downloaded_at=_MODULE.datetime(2026, 1, 1, tzinfo=_MODULE.UTC),
                )
            )

            runner = LocalCorpusReprocessor(
                database_path=database_path,
                report_path=report_path,
                dispatcher_factory=lambda db_path: PipelineDispatcher.create_default(database_path=db_path),
            )

            exit_code = runner.run()

            self.assertEqual(exit_code, 1)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["total_candidates"], 20)
            self.assertEqual(report["processed"], 18)
            self.assertEqual(report["skipped"], 1)
            self.assertEqual(report["failed"], 1)
            self.assertEqual(report["status"], "completed_with_errors")

            with sqlite3.connect(database_path, timeout=5.0) as connection:
                connection.execute("PRAGMA busy_timeout = 5000")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE load_runs SET summary_json = summary_json")
                connection.commit()

                load_run = connection.execute(
                    "SELECT status, finished_at FROM load_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                self.assertIsNotNone(load_run)
                self.assertEqual(load_run[0], "completed_with_errors")
                self.assertIsNotNone(load_run[1])

                dispatch_rows = connection.execute(
                    "SELECT artifact_id, status, error_code FROM dispatch_results ORDER BY artifact_id"
                ).fetchall()

                journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()

            by_status = {row[0]: (row[1], row[2]) for row in dispatch_rows}
            self.assertIn(("failed", "dispatch_failed"), by_status.values())
            self.assertNotIn(("skipped", "dispatch_failed"), by_status.values())
            self.assertIn(("skipped", "already_persisted"), by_status.values())
            self.assertEqual(journal_mode, "wal")

            reopened_hits = SQLiteKnowledgeQueryService.create(database_path).search("psi")
            self.assertTrue(reopened_hits)
            self.assertTrue(any(hit.document.metadata.source == "seq" for hit in reopened_hits))

            second_runner = LocalCorpusReprocessor(
                database_path=database_path,
                report_path=root / "report-second.json",
                dispatcher_factory=lambda db_path: PipelineDispatcher.create_default(database_path=db_path),
            )
            second_exit_code = second_runner.run()
            self.assertEqual(second_exit_code, 1)
            second_report = json.loads((root / "report-second.json").read_text(encoding="utf-8"))
            self.assertEqual(second_report["processed"], 0)
            self.assertGreaterEqual(second_report["skipped"], 19)
            self.assertEqual(second_report["failed"], 1)

    def _register_markdown_artifact(self, registry: ArtifactRegistry, downloads: Path, stem: str, text: str) -> tuple[EntityId, Path]:
        artifact_id = EntityId.from_seed("test.artifact", stem)
        path = downloads / f"{stem}.md"
        path.write_text(text, encoding="utf-8")
        registry.register_downloaded_artifact(
            DownloadedArtifact(
                artifact_id=artifact_id,
                source_name="seq",
                original_url=f"https://example.test/{stem}.md",
                canonical_url=f"https://example.test/{stem}.md",
                local_path=str(path),
                content_type="text/markdown",
                size_bytes=path.stat().st_size,
                downloaded_at=_MODULE.datetime(2026, 1, 1, tzinfo=_MODULE.UTC),
            )
        )
        return artifact_id, path

    def _dispatch_request(self, artifact_id: EntityId, file_path: Path, stem: str) -> DispatchRequest:
        return DispatchRequest(
            artifact_id=artifact_id,
            file_path=str(file_path),
            source_name="seq",
            manufacturer_name="seq",
            document_metadata=(("document_type", "manual"), ("authority_level", "reference"), ("language", "en")),
            provenance=(("original_url", f"https://example.test/{stem}.md"), ("canonical_url", f"https://example.test/{stem}.md"), ("mode", "seed-test")),
        )