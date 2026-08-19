"""Load orchestrator for the Industrial Knowledge Loader."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
import tempfile

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.loader.artifact_registry import ArtifactRegistry, DispatchRequest, DispatchResult, LoadPolicy
from drilling_knowledge.loader.las_adapter import LASAdapter
from drilling_knowledge.loader.pipeline_dispatcher import PipelineDispatcher
from drilling_knowledge.loader.source_adapter import SourceAdapter


@dataclass(frozen=True, slots=True)
class LoadRunSummary:
    load_run_id: RunId
    mode: str
    target: str
    discovered: int
    downloaded: int
    duplicates: int
    new_versions: int
    dispatched: int
    failed: int
    gaps_detected: int
    resumed_from_document_url: str | None = None
    last_processed_document_url: str | None = None
    last_processed_artifact_url: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class LoadOrchestrator:
    source_adapter: SourceAdapter
    las_adapter: LASAdapter
    artifact_registry: ArtifactRegistry
    pipeline_dispatcher: PipelineDispatcher

    @classmethod
    def create_default(cls, *, database_path: str | Path | None = None, workspace_root: str | Path | None = None) -> "LoadOrchestrator":
        root = Path(__file__).resolve().parents[3]
        workspace = Path(workspace_root) if workspace_root is not None else root / "var" / "loader"
        database = Path(database_path) if database_path is not None else workspace / "loader.sqlite"
        source_adapter = SourceAdapter.create_default(workspace)
        registry = ArtifactRegistry.create(database)
        for definition in source_adapter.definitions:
            registry.record_source_definition(definition)
        return cls(
            source_adapter=source_adapter,
            las_adapter=LASAdapter(),
            artifact_registry=registry,
            pipeline_dispatcher=PipelineDispatcher.create_default(database_path=database),
        )

    def load_source(self, source_name: str, policy: LoadPolicy | None = None) -> LoadRunSummary:
        effective_policy = policy or LoadPolicy()
        run_id = self.artifact_registry.start_run(mode="document", target=source_name, policy=effective_policy)
        resumed_from_document_url = effective_policy.start_after_document_url
        discovered = ()
        downloaded_count = 0
        duplicates = 0
        new_versions = 0
        dispatched = 0
        failed = 0
        last_processed_document_url = None
        last_processed_artifact_url = None
        final_status = "failed"
        summary = LoadRunSummary(run_id, "document", source_name, 0, 0, 0, 0, 0, 0, 0, resumed_from_document_url, None, None)
        if resumed_from_document_url is None and effective_policy.resume:
            resumed_from_document_url = self.artifact_registry.latest_document_checkpoint(source_name)
        try:
            discovery_policy = replace(effective_policy, max_documents_per_run=None, resume=False, start_after_document_url=None)
            discovered = self.source_adapter.discover(source_name, discovery_policy)
            if resumed_from_document_url is not None:
                discovered = tuple(document for document in discovered if document.document_url > resumed_from_document_url)
            if effective_policy.max_documents_per_run is not None:
                discovered = discovered[: effective_policy.max_documents_per_run]
            self.artifact_registry.record_discovered_documents(run_id, discovered)
            summary = LoadRunSummary(run_id, "document", source_name, len(discovered), 0, 0, 0, 0, 0, 0, resumed_from_document_url, last_processed_document_url, last_processed_artifact_url)
            self.artifact_registry.update_run_progress(run_id, summary=asdict(summary))
            if effective_policy.dry_run:
                final_status = "completed"
                return summary
            manufacturer_name = self.source_adapter.definition_for(source_name).manufacturer_name
            for document in discovered:
                try:
                    document_artifacts = self.source_adapter.download((document,), effective_policy)
                except BaseException as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    failed += 1
                    last_processed_document_url = document.document_url
                    last_processed_artifact_url = document.document_url
                    summary = LoadRunSummary(
                        run_id,
                        "document",
                        source_name,
                        len(discovered),
                        downloaded_count,
                        duplicates,
                        new_versions,
                        dispatched,
                        failed,
                        0,
                        resumed_from_document_url,
                        last_processed_document_url,
                        last_processed_artifact_url,
                    )
                    self.artifact_registry.update_run_progress(run_id, summary=asdict(summary))
                    if effective_policy.fail_fast:
                        break
                    continue
                downloaded_count += len(document_artifacts)
                for artifact in document_artifacts:
                    _, decision = self.artifact_registry.register_downloaded_artifact(artifact)
                    if decision.dedup_status != "new":
                        duplicates += 1
                    if decision.version_status == "new_version":
                        new_versions += 1
                    if not decision.dispatchable:
                        self.artifact_registry.record_dispatch_result(DispatchResult(artifact.artifact_id, "skipped"))
                    elif not self._is_processable_artifact(artifact.local_path):
                        self.artifact_registry.record_dispatch_result(DispatchResult(artifact.artifact_id, "skipped"))
                    else:
                        dispatch_request = DispatchRequest(
                            artifact_id=artifact.artifact_id,
                            file_path=artifact.local_path,
                            source_name=artifact.source_name,
                            manufacturer_name=manufacturer_name,
                            document_metadata=(("document_type", self._document_type_for(artifact.local_path)), ("authority_level", "reference"), ("language", "en")),
                            provenance=(("original_url", artifact.original_url), ("canonical_url", artifact.canonical_url), ("sha256_source", "artifact_registry")),
                        )
                        result = self.pipeline_dispatcher.dispatch(dispatch_request)
                        self.artifact_registry.record_dispatch_result(result)
                        if result.status == "dispatched":
                            dispatched += 1
                        else:
                            failed += 1
                            if effective_policy.fail_fast:
                                break
                    last_processed_document_url = artifact.original_url
                    last_processed_artifact_url = artifact.original_url
                if effective_policy.fail_fast and failed > 0:
                    summary = LoadRunSummary(
                        run_id,
                        "document",
                        source_name,
                        len(discovered),
                        downloaded_count,
                        duplicates,
                        new_versions,
                        dispatched,
                        failed,
                        0,
                        resumed_from_document_url,
                        last_processed_document_url,
                        last_processed_artifact_url,
                    )
                    self.artifact_registry.update_run_progress(run_id, summary=asdict(summary))
                    break
                summary = LoadRunSummary(
                    run_id,
                    "document",
                    source_name,
                    len(discovered),
                    downloaded_count,
                    duplicates,
                    new_versions,
                    dispatched,
                    failed,
                    0,
                    resumed_from_document_url,
                    last_processed_document_url,
                    last_processed_artifact_url,
                )
                self.artifact_registry.update_run_progress(run_id, summary=asdict(summary))
            final_status = "completed" if failed == 0 else "completed_with_errors"
            return summary
        except BaseException as exc:
            final_status = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed"
            summary = LoadRunSummary(
                run_id,
                "document",
                source_name,
                len(discovered),
                downloaded_count,
                duplicates,
                new_versions,
                dispatched,
                failed,
                0,
                resumed_from_document_url,
                last_processed_document_url,
                last_processed_artifact_url,
                type(exc).__name__,
                str(exc) or None,
            )
            raise
        finally:
            self.artifact_registry.finish_run(run_id, status=final_status, summary=asdict(summary))

    def load_las(self, folder: str | Path, policy: LoadPolicy | None = None) -> LoadRunSummary:
        effective_policy = policy or LoadPolicy()
        run_id = self.artifact_registry.start_run(mode="las", target=str(folder), policy=effective_policy)
        records = ()
        gaps = ()
        dispatched = 0
        failed = 0
        final_status = "failed"
        summary = LoadRunSummary(run_id, "las", str(folder), 0, 0, 0, 0, 0, 0, 0)
        try:
            records = self.las_adapter.scan(folder, recursive=effective_policy.recursive)
            for record, observations in records:
                self.artifact_registry.register_las_file(record, observations)
            gaps = self.artifact_registry.build_gap_candidates()
            summary = LoadRunSummary(run_id, "las", str(folder), 0, len(records), 0, 0, 0, 0, len(gaps))
            self.artifact_registry.update_run_progress(run_id, summary=asdict(summary))
            if effective_policy.dry_run:
                final_status = "completed"
                return summary
            if gaps:
                artifact_id = EntityId.from_seed("loader.artifact", f"las-gap-summary:{folder}:{len(gaps)}")
                existing_result = self.artifact_registry.get_dispatch_result(artifact_id)
                if existing_result is not None and existing_result.status == "dispatched":
                    final_status = "completed"
                    return summary
                evidence_path = self._write_las_gap_summary(records, gaps)
                request = DispatchRequest(
                    artifact_id=artifact_id,
                    file_path=evidence_path,
                    source_name="las",
                    manufacturer_name="LAS",
                    document_metadata=(("document_type", "report"), ("authority_level", "reference"), ("language", "en")),
                    provenance=(("folder", str(folder)), ("gap_count", str(len(gaps))), ("mode", "load-las")),
                )
                result = self.pipeline_dispatcher.dispatch(request)
                self.artifact_registry.record_dispatch_result(result)
                if result.status == "dispatched":
                    dispatched = 1
                else:
                    failed = 1
            summary = LoadRunSummary(run_id, "las", str(folder), 0, len(records), 0, 0, dispatched, failed, len(gaps))
            final_status = "completed" if failed == 0 else "completed_with_errors"
            return summary
        except BaseException as exc:
            final_status = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed"
            summary = LoadRunSummary(
                run_id,
                "las",
                str(folder),
                0,
                len(records),
                0,
                0,
                dispatched,
                failed,
                len(gaps),
                error_type=type(exc).__name__,
                error_message=str(exc) or None,
            )
            raise
        finally:
            self.artifact_registry.finish_run(run_id, status=final_status, summary=asdict(summary))

    @staticmethod
    def _document_type_for(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        mapping = {".pdf": "datasheet", ".docx": "manual", ".xlsx": "catalog", ".xls": "catalog", ".html": "manual", ".htm": "manual", ".md": "manual", ".txt": "manual"}
        return mapping.get(suffix, "manual")

    @staticmethod
    def _is_processable_artifact(file_path: str) -> bool:
        return Path(file_path).suffix.lower() in {".pdf", ".docx", ".xlsx", ".xls", ".html", ".htm", ".md", ".markdown", ".txt", ".log"}

    @staticmethod
    def _write_las_gap_summary(records, gaps) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        with handle as stream:
            stream.write("# LAS Knowledge Gaps\n\n")
            stream.write(f"Files scanned: {len(records)}\n\n")
            for gap in gaps:
                stream.write(f"## {gap.gap_type}:{gap.normalized_mnemonic}\n")
                stream.write(f"aliases: {', '.join(gap.candidate_aliases) or 'n/a'}\n")
                stream.write(f"units: {', '.join(gap.observed_units) or 'n/a'}\n")
                stream.write(f"evidence_count: {gap.evidence_count}\n\n")
        return handle.name