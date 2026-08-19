from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.loader.artifact_registry import ArtifactRegistry, DispatchResult, ENERGISTICS_EXTRACTOR_VERSION
from drilling_knowledge.documents.sqlite import SQLiteDocumentRepository
from drilling_knowledge.assertions.repositories.sqlite import SQLiteAssertionGenerationRunRepository
from drilling_knowledge.assertions.consolidation.repositories.sqlite import SQLiteFactConsolidationRunRepository


_RUNNER_PATH = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/run_reprocess_local_corpus.py")
_SPEC = importlib.util.spec_from_file_location("run_reprocess_local_corpus", _RUNNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
LocalCorpusReprocessor = _MODULE.LocalCorpusReprocessor


class LocalCorpusReprocessorTests(unittest.TestCase):
    def test_runner_deduplicates_by_sha256_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "loader.sqlite"
            report_path = root / "report.json"
            registry = ArtifactRegistry.create(db_path)
            SQLiteDocumentRepository.create(db_path)
            SQLiteAssertionGenerationRunRepository.create(db_path)
            SQLiteFactConsolidationRunRepository.create(db_path)

            duplicate_payload = "shared duplicate content\n"
            case_dup_a = root / "dup-a.md"
            case_dup_b = root / "dup-b.md"
            case_unique = root / "unique.md"
            case_persisted_a = root / "persisted-a.md"
            case_persisted_b = root / "persisted-b.md"
            case_dup_a.write_text(duplicate_payload, encoding="utf-8")
            case_dup_b.write_text(duplicate_payload, encoding="utf-8")
            case_unique.write_text("unique content\n", encoding="utf-8")
            case_persisted_a.write_text("persisted duplicate\n", encoding="utf-8")
            case_persisted_b.write_text("persisted duplicate\n", encoding="utf-8")

            artifact_dup_a = EntityId.from_seed("test.artifact", "dup-a")
            artifact_dup_b = EntityId.from_seed("test.artifact", "dup-b")
            artifact_unique = EntityId.from_seed("test.artifact", "unique")
            artifact_persisted_a = EntityId.from_seed("test.artifact", "persisted-a")
            artifact_persisted_b = EntityId.from_seed("test.artifact", "persisted-b")
            canonical_duplicate = artifact_dup_a if str(artifact_dup_a) < str(artifact_dup_b) else artifact_dup_b
            duplicate_shadow = artifact_dup_b if canonical_duplicate == artifact_dup_a else artifact_dup_a

            self._insert_artifact(registry, artifact_id=artifact_dup_a, source_name="slb", local_path=case_dup_a, original_url="https://example.test/dup-a")
            self._insert_artifact(registry, artifact_id=artifact_dup_b, source_name="slb", local_path=case_dup_b, original_url="https://example.test/dup-b")
            self._insert_artifact(registry, artifact_id=artifact_unique, source_name="slb", local_path=case_unique, original_url="https://example.test/unique")
            self._insert_artifact(registry, artifact_id=artifact_persisted_a, source_name="slb", local_path=case_persisted_a, original_url="https://example.test/persisted-a")
            self._insert_artifact(registry, artifact_id=artifact_persisted_b, source_name="slb", local_path=case_persisted_b, original_url="https://example.test/persisted-b")

            persisted_document_id = self._insert_persisted_dk_state(db_path, artifact_persisted_a)
            registry.record_dispatch_result(
                DispatchResult(
                    artifact_persisted_a,
                    "dispatched",
                    document_id=persisted_document_id,
                    workflow_run_id=RunId.from_seed("test.run", "persisted-a"),
                    semantic_metrics=(("fragments", 1), ("assertions", 1), ("facts", 1)),
                )
            )

            dispatcher = _FakeDispatcher(
                responses={
                    str(canonical_duplicate): DispatchResult(
                        canonical_duplicate,
                        "dispatched",
                        document_id=EntityId.from_seed("test.document", "dup-canonical"),
                        workflow_run_id=RunId.from_seed("test.run", "dup-canonical"),
                        semantic_metrics=(("fragments", 2), ("assertions", 1), ("facts", 1)),
                    ),
                    str(artifact_unique): DispatchResult(
                        artifact_unique,
                        "dispatched",
                        document_id=EntityId.from_seed("test.document", "unique"),
                        workflow_run_id=RunId.from_seed("test.run", "unique"),
                        semantic_metrics=(("fragments", 1), ("assertions", 1), ("facts", 1)),
                    ),
                }
            )

            runner = LocalCorpusReprocessor(database_path=db_path, report_path=report_path, dispatcher_factory=lambda _: dispatcher)
            exit_code = runner.run()

            self.assertEqual(exit_code, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["total_candidates"], 5)
            self.assertEqual(report["processed"], 2)
            self.assertEqual(report["skipped"], 3)
            self.assertEqual(report["failed"], 0)

            self.assertEqual(dispatcher.calls, [str(canonical_duplicate), str(artifact_unique)])

            with sqlite3.connect(db_path) as connection:
                rows = connection.execute("SELECT artifact_id, status, error_code FROM dispatch_results ORDER BY artifact_id").fetchall()
            by_id = {row[0]: (row[1], row[2]) for row in rows}
            self.assertEqual(by_id[str(canonical_duplicate)][0], "dispatched")
            self.assertEqual(by_id[str(duplicate_shadow)], ("skipped", "duplicate_content"))
            self.assertEqual(by_id[str(artifact_unique)][0], "dispatched")
            self.assertEqual(by_id[str(artifact_persisted_a)], ("skipped", "already_persisted"))
            self.assertEqual(by_id[str(artifact_persisted_b)], ("skipped", "duplicate_content"))

    def test_runner_uses_dk_persistence_for_resume_and_skips_unsupported_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "loader.sqlite"
            report_path = root / "report.json"
            registry = ArtifactRegistry.create(db_path)
            SQLiteDocumentRepository.create(db_path)
            SQLiteAssertionGenerationRunRepository.create(db_path)
            SQLiteFactConsolidationRunRepository.create(db_path)
            case_a = root / "historical-dispatched-no-dk.html"
            case_a.write_text("<html><body><p>standpipe pressure</p></body></html>", encoding="utf-8")
            case_b = root / "already-persisted.html"
            case_b.write_text("<html><body><p>standpipe pressure persisted</p></body></html>", encoding="utf-8")
            case_c = root / "installer.exe"
            case_c.write_bytes(b"MZ")

            artifact_a = EntityId.from_seed("test.artifact", "historical-no-dk")
            artifact_b = EntityId.from_seed("test.artifact", "already-persisted")
            artifact_c = EntityId.from_seed("test.artifact", "unsupported-exe")

            self._insert_artifact(registry, artifact_id=artifact_a, source_name="slb", local_path=case_a, original_url="https://example.test/a")
            self._insert_artifact(registry, artifact_id=artifact_b, source_name="slb", local_path=case_b, original_url="https://example.test/b")
            self._insert_artifact(registry, artifact_id=artifact_c, source_name="slb", local_path=case_c, original_url="https://example.test/c")

            registry.record_dispatch_result(DispatchResult(artifact_a, "dispatched", document_id=EntityId.from_seed("test.document", "a"), workflow_run_id=RunId.from_seed("test.run", "a")))

            persisted_document_id = self._insert_persisted_dk_state(db_path, artifact_b)
            registry.record_dispatch_result(
                DispatchResult(
                    artifact_b,
                    "dispatched",
                    document_id=persisted_document_id,
                    workflow_run_id=RunId.from_seed("test.run", "b"),
                    semantic_metrics=(("fragments", 1), ("assertions", 1), ("facts", 1)),
                )
            )

            dispatcher = _FakeDispatcher(
                responses={
                    str(artifact_a): DispatchResult(
                        artifact_a,
                        "dispatched",
                        document_id=EntityId.from_seed("test.document", "a-new"),
                        workflow_run_id=RunId.from_seed("test.run", "a-new"),
                        semantic_metrics=(("fragments", 5), ("assertions", 2), ("facts", 1)),
                    )
                }
            )
            runner = LocalCorpusReprocessor(database_path=db_path, report_path=report_path, dispatcher_factory=lambda _: dispatcher)
            exit_code = runner.run()

            self.assertEqual(exit_code, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["total_candidates"], 3)
            self.assertEqual(report["processed"], 1)
            self.assertEqual(report["skipped"], 2)
            self.assertEqual(report["failed"], 0)
            self.assertEqual(report["status"], "completed")

            self.assertEqual(dispatcher.calls, [str(artifact_a)])

            with sqlite3.connect(db_path) as connection:
                rows = connection.execute("SELECT artifact_id, status, error_code FROM dispatch_results ORDER BY artifact_id").fetchall()
            by_id = {row[0]: (row[1], row[2]) for row in rows}
            self.assertEqual(by_id[str(artifact_a)][0], "dispatched")
            self.assertEqual(by_id[str(artifact_b)], ("skipped", "already_persisted"))
            self.assertEqual(by_id[str(artifact_c)], ("skipped", "unsupported_format"))

    def test_runner_reprocesses_old_energistics_but_skips_current_compatible_energistics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "loader.sqlite"
            report_path = root / "report.json"
            registry = ArtifactRegistry.create(db_path)
            SQLiteDocumentRepository.create(db_path)
            SQLiteAssertionGenerationRunRepository.create(db_path)
            SQLiteFactConsolidationRunRepository.create(db_path)

            old_doc = root / "old-WITSML-500-152-0-R-sv2000.html"
            current_doc = root / "current-RESQML-500-305-0-R-sv2010.html"
            old_doc.write_text("<html><body>old energistics</body></html>", encoding="utf-8")
            current_doc.write_text("<html><body>current energistics</body></html>", encoding="utf-8")

            old_artifact = EntityId.from_seed("test.artifact", "old-energistics")
            current_artifact = EntityId.from_seed("test.artifact", "current-energistics")

            self._insert_artifact(registry, artifact_id=old_artifact, source_name="energistics", local_path=old_doc, original_url="https://example.test/old-witsml")
            self._insert_artifact(registry, artifact_id=current_artifact, source_name="energistics", local_path=current_doc, original_url="https://example.test/current-resqml")

            old_document_id = self._insert_persisted_dk_state(db_path, old_artifact)
            current_document_id = self._insert_persisted_dk_state(db_path, current_artifact)
            registry.record_dispatch_result(
                DispatchResult(
                    old_artifact,
                    "dispatched",
                    document_id=old_document_id,
                    workflow_run_id=RunId.from_seed("test.run", "old-energistics"),
                    semantic_metrics=(("fragments", 1), ("assertions", 0), ("facts", 0), ("structured_facts", 0)),
                    processor_family="energistics",
                    processor_version="1",
                    compatible_ready=False,
                )
            )
            registry.record_dispatch_result(
                DispatchResult(
                    current_artifact,
                    "dispatched",
                    document_id=current_document_id,
                    workflow_run_id=RunId.from_seed("test.run", "current-energistics"),
                    semantic_metrics=(("fragments", 10), ("assertions", 5), ("facts", 5), ("structured_facts", 3)),
                    processor_family="energistics",
                    processor_version=ENERGISTICS_EXTRACTOR_VERSION,
                    compatible_ready=True,
                )
            )

            dispatcher = _FakeDispatcher(
                responses={
                    str(old_artifact): DispatchResult(
                        old_artifact,
                        "dispatched",
                        document_id=old_document_id,
                        workflow_run_id=RunId.from_seed("test.run", "old-energistics-rerun"),
                        semantic_metrics=(("fragments", 10), ("assertions", 6), ("facts", 6), ("structured_facts", 4)),
                        processor_family="energistics",
                        processor_version=ENERGISTICS_EXTRACTOR_VERSION,
                        compatible_ready=True,
                    )
                }
            )

            runner = LocalCorpusReprocessor(database_path=db_path, report_path=report_path, dispatcher_factory=lambda _: dispatcher)
            exit_code = runner.run()

            self.assertEqual(exit_code, 0)
            self.assertEqual(dispatcher.calls, [str(old_artifact)])

            with sqlite3.connect(db_path) as connection:
                rows = connection.execute("SELECT artifact_id, status, error_code FROM dispatch_results ORDER BY artifact_id").fetchall()
            by_id = {row[0]: (row[1], row[2]) for row in rows}
            self.assertEqual(by_id[str(old_artifact)][0], "dispatched")
            self.assertEqual(by_id[str(current_artifact)], ("skipped", "already_persisted"))

    def _insert_persisted_dk_state(self, db_path: Path, artifact_id: EntityId) -> EntityId:
        with sqlite3.connect(db_path) as connection:
            version_row = connection.execute("SELECT version_id FROM document_versions WHERE artifact_id = ?", (str(artifact_id),)).fetchone()
            assert version_row is not None
            version_id = str(version_row[0])
            document_id = EntityId.from_seed("test.dk.document", version_id)
            fragment_id = str(EntityId.from_seed("test.dk.fragment", version_id))
            assertion_id = str(EntityId.from_seed("test.dk.assertion", version_id))
            fact_id = str(EntityId.from_seed("test.dk.fact", version_id))
            support_id = str(EntityId.from_seed("test.dk.support", version_id))
            link_id = str(EntityId.from_seed("test.dk.link", version_id))
            connection.execute("INSERT INTO dk_documents (document_id, payload_json) VALUES (?, ?)", (str(document_id), '{}'))
            connection.execute("INSERT INTO dk_document_versions (version_id, document_id, payload_json) VALUES (?, ?, ?)", (version_id, str(document_id), '{}'))
            connection.execute(
                "INSERT INTO dk_document_fragments (fragment_id, document_id, version_id, fragment_type, normalized_text, text_content, page_number, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (fragment_id, str(document_id), version_id, 'paragraph', 'standpipe pressure', 'standpipe pressure', None, '{}'),
            )
            connection.execute(
                "INSERT INTO dk_evidence_assertions (assertion_id, run_id, status, predicate_code, subject_id, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (assertion_id, str(RunId.from_seed('test.dk.run', version_id)), 'accepted', 'denotes_catalog_entity', str(EntityId.from_seed('test.subject', version_id)), '{}'),
            )
            connection.execute(
                "INSERT INTO dk_assertion_evidence_links (link_id, run_id, assertion_id, document_id, document_version_id, fragment_id, normalized_text, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (link_id, str(RunId.from_seed('test.dk.run', version_id)), assertion_id, str(document_id), version_id, fragment_id, 'standpipe pressure', '{}'),
            )
            connection.execute(
                "INSERT INTO dk_consolidated_facts (fact_id, run_id, claim_key, predicate_code, subject_id, lifecycle, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fact_id, str(RunId.from_seed('test.dk.fact.run', version_id)), 'claim', 'denotes_catalog_entity', str(EntityId.from_seed('test.subject', version_id)), 'active', '{}'),
            )
            connection.execute(
                "INSERT INTO dk_fact_supports (fact_support_id, run_id, fact_id, assertion_id, payload_json) VALUES (?, ?, ?, ?, ?)",
                (support_id, str(RunId.from_seed('test.dk.fact.run', version_id)), fact_id, assertion_id, '{}'),
            )
            connection.execute(
                "INSERT INTO dk_fact_support_evidence_links (fact_support_id, link_id) VALUES (?, ?)",
                (support_id, link_id),
            )
            connection.commit()
        return document_id

    def _insert_artifact(self, registry: ArtifactRegistry, *, artifact_id: EntityId, source_name: str, local_path: Path, original_url: str) -> None:
        from drilling_knowledge.loader.artifact_registry import DownloadedArtifact
        from datetime import UTC, datetime

        if not local_path.exists():
            with sqlite3.connect(registry.database_path) as connection:
                connection.execute(
                    "INSERT INTO downloaded_artifacts (artifact_id, source_name, original_url, canonical_url, local_path, content_type, size_bytes, downloaded_at, archive_parent_artifact_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(artifact_id),
                        source_name,
                        original_url,
                        original_url,
                        str(local_path),
                        "text/html",
                        0,
                        datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                        None,
                    ),
                )
                connection.commit()
            return

        registry.register_downloaded_artifact(
            DownloadedArtifact(
                artifact_id=artifact_id,
                source_name=source_name,
                original_url=original_url,
                canonical_url=original_url,
                local_path=str(local_path),
                content_type="text/html" if local_path.suffix == ".html" else "application/octet-stream",
                size_bytes=(local_path.stat().st_size if local_path.exists() else 0),
                downloaded_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )


class _FakeDispatcher:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def dispatch(self, request):
        self.calls.append(str(request.artifact_id))
        if str(request.artifact_id) not in self.responses:
            raise AssertionError(f"Unexpected dispatch call for {request.artifact_id}")
        return self.responses[str(request.artifact_id)]