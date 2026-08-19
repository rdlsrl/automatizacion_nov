from __future__ import annotations

import json
import importlib.util
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import sys
import time
from typing import Callable

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.loader.artifact_registry import ArtifactRegistry, DispatchRequest, DispatchResult, ENERGISTICS_EXTRACTOR_VERSION, LoadPolicy
from drilling_knowledge.loader.pipeline_dispatcher import PipelineDispatcher


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".html", ".htm", ".md", ".markdown", ".txt", ".log"}
DEPENDENCY_BY_SUFFIX = {".pdf": "pypdf", ".docx": "docx", ".xlsx": "openpyxl"}


@dataclass(frozen=True, slots=True)
class LocalArtifactCandidate:
    artifact_id: EntityId
    sha256: str | None
    source_name: str
    manufacturer_name: str
    original_url: str
    canonical_url: str
    local_path: str
    content_type: str
    existing_status: str | None
    existing_error_code: str | None
    persisted_ready: bool
    energistics_reprocess_required: bool
    canonical_artifact_id: EntityId | None
    sha256_has_persisted_content: bool


@dataclass(slots=True)
class RunCounters:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    fragments: int = 0
    assertions: int = 0
    facts: int = 0


class LocalCorpusReprocessor:
    def __init__(
        self,
        *,
        database_path: str | Path,
        report_path: str | Path,
        dispatcher_factory: Callable[[Path], PipelineDispatcher] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.report_path = Path(report_path)
        self.registry = ArtifactRegistry.create(self.database_path)
        self.dispatcher_factory = dispatcher_factory or (lambda db_path: PipelineDispatcher.create_default(database_path=db_path))

    def run(self) -> int:
        started_at = self._utc_now()
        candidates = self._load_candidates()
        run_id = self.registry.start_run(mode="document", target="local_corpus", policy=LoadPolicy(resume=True))
        counters = RunCounters()
        status = "running"
        dispatcher = self.dispatcher_factory(self.database_path)
        try:
            self._write_report(
                total_candidates=len(candidates),
                counters=counters,
                start_time=started_at,
                last_processed=None,
                status=status,
            )
            for index, candidate in enumerate(candidates, start=1):
                result, category = self._process_candidate(candidate, dispatcher)
                metrics = dict(result.semantic_metrics)
                if category == "processed":
                    counters.processed += 1
                    counters.fragments += int(metrics.get("fragments", 0))
                    counters.assertions += int(metrics.get("assertions", 0))
                    counters.facts += int(metrics.get("facts", 0))
                    print(
                        f"[{index}/{len(candidates)}] {candidate.source_name.upper()} - {Path(candidate.local_path).name} - OK - "
                        f"{int(metrics.get('fragments', 0))} fragments - {int(metrics.get('facts', 0))} facts"
                    )
                elif category == "skipped":
                    counters.skipped += 1
                    reason = result.error_code or candidate.existing_status or "skipped"
                    print(f"[{index}/{len(candidates)}] {candidate.source_name.upper()} - {Path(candidate.local_path).name} - SKIPPED - {reason}")
                else:
                    counters.failed += 1
                    detail = result.error_code or "dispatch_failed"
                    print(f"[{index}/{len(candidates)}] {candidate.source_name.upper()} - {Path(candidate.local_path).name} - FAILED: {detail}")

                elapsed = int(time.monotonic() - time.monotonic() + (self._utc_now() - started_at).total_seconds())
                print(
                    f"totals processed={counters.processed} skipped={counters.skipped} failed={counters.failed} "
                    f"fragments={counters.fragments} assertions={counters.assertions} facts={counters.facts} elapsed={elapsed}s"
                )
                summary = {
                    "total_candidates": len(candidates),
                    "processed": counters.processed,
                    "skipped": counters.skipped,
                    "failed": counters.failed,
                    "fragments": counters.fragments,
                    "assertions": counters.assertions,
                    "facts": counters.facts,
                    "start_time": started_at.isoformat(),
                    "last_update": self._utc_now().isoformat(),
                    "last_processed": candidate.local_path,
                    "status": status,
                }
                self.registry.update_run_progress(run_id, summary=summary)
                self._write_report(
                    total_candidates=len(candidates),
                    counters=counters,
                    start_time=started_at,
                    last_processed=candidate.local_path,
                    status=status,
                )
            status = "completed_with_errors" if counters.failed else "completed"
            return 0 if counters.failed == 0 else 1
        except BaseException:
            status = "interrupted"
            raise
        finally:
            final_summary = {
                "total_candidates": len(candidates),
                "processed": counters.processed,
                "skipped": counters.skipped,
                "failed": counters.failed,
                "fragments": counters.fragments,
                "assertions": counters.assertions,
                "facts": counters.facts,
                "start_time": started_at.isoformat(),
                "last_update": self._utc_now().isoformat(),
                "last_processed": None if not candidates else self._last_processed_from_report(),
                "status": status,
            }
            self.registry.finish_run(run_id, status=status, summary=final_summary)
            self._write_report(
                total_candidates=len(candidates),
                counters=counters,
                start_time=started_at,
                last_processed=final_summary["last_processed"],
                status=status,
            )

    def _process_candidate(self, candidate: LocalArtifactCandidate, dispatcher: PipelineDispatcher) -> tuple[DispatchResult, str]:
        path = Path(candidate.local_path)
        if candidate.persisted_ready:
            result = DispatchResult(candidate.artifact_id, "skipped", error_code="already_persisted", error_message=path.name)
            self.registry.record_dispatch_result(result)
            return result, "skipped"
        if candidate.sha256_has_persisted_content and not candidate.energistics_reprocess_required:
            result = DispatchResult(
                candidate.artifact_id,
                "skipped",
                error_code="duplicate_content",
                error_message=f"sha256={candidate.sha256};persisted_content=true",
            )
            self.registry.record_dispatch_result(result)
            return result, "skipped"
        if candidate.canonical_artifact_id is not None and candidate.canonical_artifact_id != candidate.artifact_id:
            result = DispatchResult(
                candidate.artifact_id,
                "skipped",
                error_code="duplicate_content",
                error_message=f"sha256={candidate.sha256};canonical_artifact_id={candidate.canonical_artifact_id}",
            )
            self.registry.record_dispatch_result(result)
            return result, "skipped"
        if not path.exists():
            result = DispatchResult(candidate.artifact_id, "skipped", error_code="missing_local_file", error_message=candidate.local_path)
            self.registry.record_dispatch_result(result)
            return result, "skipped"
        unsupported_reason = self._unsupported_reason_for(path.suffix.lower())
        if unsupported_reason is not None:
            result = DispatchResult(candidate.artifact_id, "skipped", error_code=unsupported_reason[0], error_message=unsupported_reason[1])
            self.registry.record_dispatch_result(result)
            return result, "skipped"

        request = DispatchRequest(
            artifact_id=candidate.artifact_id,
            file_path=candidate.local_path,
            source_name=candidate.source_name,
            manufacturer_name=candidate.manufacturer_name,
            document_metadata=(("document_type", self._document_type_for(candidate.local_path)), ("authority_level", "reference"), ("language", "en")),
            provenance=(("original_url", candidate.original_url), ("canonical_url", candidate.canonical_url), ("mode", "reprocess_local_corpus")),
        )
        result = dispatcher.dispatch(request)
        self.registry.record_dispatch_result(result)
        return result, ("processed" if result.status == "dispatched" else "failed")

    def _load_candidates(self) -> list[LocalArtifactCandidate]:
        query = """
        SELECT
            da.artifact_id,
            af.sha256,
            da.source_name,
            COALESCE(sd.manufacturer_name, da.source_name) AS manufacturer_name,
            da.original_url,
            da.canonical_url,
            da.local_path,
            da.content_type,
            dr.status AS existing_status,
            dr.error_code AS existing_error_code,
            CASE
                WHEN da.source_name = 'energistics' THEN 1
                WHEN UPPER(da.local_path) LIKE '%WITSML%' OR UPPER(da.local_path) LIKE '%RESQML%' OR UPPER(da.local_path) LIKE '%PRODML%' THEN 1
                ELSE 0
            END AS is_energistics,
            CASE
                WHEN (da.source_name = 'energistics' OR UPPER(da.local_path) LIKE '%WITSML%' OR UPPER(da.local_path) LIKE '%RESQML%' OR UPPER(da.local_path) LIKE '%PRODML%')
                     AND persisted_document.document_id IS NOT NULL AND energy_state.artifact_id IS NULL THEN 1
                WHEN energy_state.artifact_id IS NOT NULL AND COALESCE(energy_state.compatible_ready, 0) = 0 THEN 1
                WHEN energy_state.artifact_id IS NOT NULL AND energy_state.processor_version IS NOT NULL AND energy_state.processor_version <> ? THEN 1
                ELSE 0
            END AS energistics_reprocess_required,
            duplicate_groups.canonical_artifact_id,
            duplicate_groups.has_compatible_persisted_content,
            CASE
                WHEN (da.source_name = 'energistics' OR UPPER(da.local_path) LIKE '%WITSML%' OR UPPER(da.local_path) LIKE '%RESQML%' OR UPPER(da.local_path) LIKE '%PRODML%') THEN CASE
                    WHEN COALESCE(energy_state.compatible_ready, 0) = 1 AND energy_state.processor_version = ? THEN 1
                    ELSE 0
                END
                WHEN persisted_document.document_id IS NULL THEN 0
                WHEN fragment_counts.fragment_count IS NULL OR fragment_counts.fragment_count <= 0 THEN 0
                WHEN knowledge_counts.assertion_count IS NULL AND knowledge_counts.fact_count IS NULL THEN 1
                WHEN COALESCE(knowledge_counts.assertion_count, 0) > 0 OR COALESCE(knowledge_counts.fact_count, 0) > 0 THEN 1
                ELSE 0
            END AS persisted_ready
        FROM downloaded_artifacts AS da
        LEFT JOIN artifact_fingerprints AS af ON af.artifact_id = da.artifact_id
        LEFT JOIN source_definitions AS sd ON sd.source_name = da.source_name
        LEFT JOIN dispatch_results AS dr ON dr.artifact_id = da.artifact_id
        LEFT JOIN semantic_document_metrics AS sdm ON sdm.artifact_id = da.artifact_id
        LEFT JOIN semantic_processing_state AS energy_state ON energy_state.artifact_id = da.artifact_id AND energy_state.processor_family = 'energistics'
        LEFT JOIN (
            SELECT
                fingerprint.sha256,
                MIN(CASE WHEN persisted.document_id IS NULL THEN fingerprint.artifact_id END) AS canonical_unpersisted_artifact_id,
                MIN(CASE WHEN persisted.document_id IS NOT NULL THEN fingerprint.artifact_id END) AS canonical_persisted_artifact_id,
                MAX(CASE WHEN persisted.document_id IS NOT NULL THEN 1 ELSE 0 END) AS has_persisted_content,
                MAX(
                    CASE
                        WHEN duplicate_artifact.source_name = 'energistics' OR UPPER(duplicate_artifact.local_path) LIKE '%WITSML%' OR UPPER(duplicate_artifact.local_path) LIKE '%RESQML%' OR UPPER(duplicate_artifact.local_path) LIKE '%PRODML%'
                            THEN CASE
                                WHEN processing.processor_family = 'energistics' AND processing.processor_version = ? AND COALESCE(processing.compatible_ready, 0) = 1 THEN 1
                                ELSE 0
                            END
                        WHEN processing.processor_family IS NULL AND persisted.document_id IS NOT NULL THEN 1
                        ELSE 0
                    END
                ) AS has_compatible_persisted_content,
                COALESCE(
                    MIN(CASE WHEN persisted.document_id IS NULL THEN fingerprint.artifact_id END),
                    MIN(CASE WHEN persisted.document_id IS NOT NULL THEN fingerprint.artifact_id END)
                ) AS canonical_artifact_id
            FROM artifact_fingerprints AS fingerprint
            LEFT JOIN downloaded_artifacts AS duplicate_artifact ON duplicate_artifact.artifact_id = fingerprint.artifact_id
            LEFT JOIN dispatch_results AS duplicate_dispatch ON duplicate_dispatch.artifact_id = fingerprint.artifact_id
            LEFT JOIN semantic_document_metrics AS duplicate_metrics ON duplicate_metrics.artifact_id = fingerprint.artifact_id
            LEFT JOIN semantic_processing_state AS processing ON processing.artifact_id = fingerprint.artifact_id
            LEFT JOIN (
                SELECT DISTINCT document_id FROM dk_documents
            ) AS persisted ON persisted.document_id = COALESCE(duplicate_metrics.document_id, duplicate_dispatch.document_id)
            GROUP BY fingerprint.sha256
        ) AS duplicate_groups ON duplicate_groups.sha256 = af.sha256
        LEFT JOIN (
            SELECT DISTINCT document_id
            FROM dk_documents
        ) AS persisted_document ON persisted_document.document_id = COALESCE(sdm.document_id, dr.document_id)
        LEFT JOIN (
            SELECT document_id, COUNT(*) AS fragment_count
            FROM dk_document_fragments
            GROUP BY document_id
        ) AS fragment_counts ON fragment_counts.document_id = persisted_document.document_id
        LEFT JOIN (
            SELECT link.document_id, COUNT(DISTINCT assertion.assertion_id) AS assertion_count, COUNT(DISTINCT fact.fact_id) AS fact_count
            FROM dk_assertion_evidence_links AS link
            LEFT JOIN dk_evidence_assertions AS assertion ON assertion.assertion_id = link.assertion_id
            LEFT JOIN dk_fact_support_evidence_links AS support_link ON support_link.link_id = link.link_id
            LEFT JOIN dk_fact_supports AS support ON support.fact_support_id = support_link.fact_support_id
            LEFT JOIN dk_consolidated_facts AS fact ON fact.fact_id = support.fact_id
            GROUP BY link.document_id
        ) AS knowledge_counts ON knowledge_counts.document_id = persisted_document.document_id
        ORDER BY da.source_name, da.original_url, da.local_path, da.artifact_id
        """
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, (ENERGISTICS_EXTRACTOR_VERSION, ENERGISTICS_EXTRACTOR_VERSION, ENERGISTICS_EXTRACTOR_VERSION)).fetchall()
        candidates = []
        for row in rows:
            local_path = str(row["local_path"])
            suffix = Path(local_path).suffix.lower()
            if suffix == ".las":
                continue
            candidates.append(
                LocalArtifactCandidate(
                    artifact_id=EntityId.from_string(str(row["artifact_id"])),
                    sha256=None if row["sha256"] is None else str(row["sha256"]),
                    source_name=str(row["source_name"]),
                    manufacturer_name=str(row["manufacturer_name"]),
                    original_url=str(row["original_url"]),
                    canonical_url=str(row["canonical_url"]),
                    local_path=local_path,
                    content_type=str(row["content_type"]),
                    existing_status=None if row["existing_status"] is None else str(row["existing_status"]),
                    existing_error_code=None if row["existing_error_code"] is None else str(row["existing_error_code"]),
                    energistics_reprocess_required=bool(int(row["energistics_reprocess_required"] or 0)),
                    persisted_ready=bool(int(row["persisted_ready"])),
                    canonical_artifact_id=None if row["canonical_artifact_id"] is None else EntityId.from_string(str(row["canonical_artifact_id"])),
                    sha256_has_persisted_content=bool(int(row["has_compatible_persisted_content"] or 0)),
                )
            )
        return candidates

    def _write_report(
        self,
        *,
        total_candidates: int,
        counters: RunCounters,
        start_time: datetime,
        last_processed: str | None,
        status: str,
    ) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total_candidates": total_candidates,
            "processed": counters.processed,
            "skipped": counters.skipped,
            "failed": counters.failed,
            "fragments": counters.fragments,
            "assertions": counters.assertions,
            "facts": counters.facts,
            "start_time": start_time.isoformat(),
            "last_update": self._utc_now().isoformat(),
            "last_processed": last_processed,
            "status": status,
        }
        self.report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _last_processed_from_report(self) -> str | None:
        if not self.report_path.exists():
            return None
        payload = json.loads(self.report_path.read_text(encoding="utf-8"))
        value = payload.get("last_processed")
        return None if value is None else str(value)

    @staticmethod
    def _unsupported_reason_for(suffix: str) -> tuple[str, str] | None:
        if suffix not in SUPPORTED_SUFFIXES:
            return ("unsupported_format", suffix)
        dependency = DEPENDENCY_BY_SUFFIX.get(suffix)
        if dependency is None:
            return None
        if importlib.util.find_spec(dependency) is not None:
            return None
        return ("missing_parser_dependency", dependency)

    @staticmethod
    def _document_type_for(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        mapping = {".pdf": "datasheet", ".docx": "manual", ".xlsx": "catalog", ".xls": "catalog", ".html": "manual", ".htm": "manual", ".md": "manual", ".markdown": "manual", ".txt": "manual", ".log": "manual"}
        return mapping.get(suffix, "manual")

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    workspace = Path(__file__).resolve().parent
    runner = LocalCorpusReprocessor(
        database_path=workspace / "var" / "loader" / "loader.sqlite",
        report_path=workspace / "var" / "reprocess_local_corpus_report.json",
    )
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))