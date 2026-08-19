"""SQLite-backed artifact registry for the Industrial Knowledge Loader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

from drilling_knowledge.common.ids import EntityId, RunId

_SCHEMA_VERSION = 2
_SQLITE_BUSY_TIMEOUT_MS = 5000
ENERGISTICS_EXTRACTOR_VERSION = "2"
ENERGISTICS_STRUCTURED_PREDICATES = frozenset(
    {
        "has_property",
        "measurement_type",
        "has_relationship",
        "derived_from",
        "has_unit",
        "quantity_class",
        "parent_object",
        "belongs_to",
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("URL cannot be empty")
    if "#" in normalized:
        normalized = normalized.split("#", 1)[0]
    if "?" in normalized:
        normalized = normalized.split("?", 1)[0]
    return normalized.rstrip("/")


def _normalized_filename(value: str) -> str:
    return Path(value.strip()).name.casefold()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _looks_like_energistics_reference(*values: str | None) -> bool:
    for value in values:
        if value is None:
            continue
        normalized = value.strip().upper()
        if "WITSML" in normalized or "RESQML" in normalized or "PRODML" in normalized:
            return True
    return False


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_name: str
    manufacturer_name: str
    seed_urls: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    allowed_formats: tuple[str, ...]
    discovery_mode: str
    credentials_ref: str | None = None
    default_metadata: tuple[tuple[str, str], ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        source_name = self.source_name.strip().lower()
        manufacturer_name = self.manufacturer_name.strip()
        discovery_mode = self.discovery_mode.strip().lower()
        if not source_name:
            raise ValueError("SourceDefinition.source_name cannot be empty")
        if not manufacturer_name:
            raise ValueError("SourceDefinition.manufacturer_name cannot be empty")
        if not self.seed_urls:
            raise ValueError("SourceDefinition.seed_urls cannot be empty")
        if not self.allowed_domains:
            raise ValueError("SourceDefinition.allowed_domains cannot be empty")
        if not self.allowed_formats:
            raise ValueError("SourceDefinition.allowed_formats cannot be empty")
        if discovery_mode not in {"html_listing", "direct_files", "zip_catalog", "mixed"}:
            raise ValueError("SourceDefinition.discovery_mode is invalid")
        object.__setattr__(self, "source_name", source_name)
        object.__setattr__(self, "manufacturer_name", manufacturer_name)
        object.__setattr__(self, "seed_urls", tuple(url.strip() for url in self.seed_urls if url.strip()))
        object.__setattr__(self, "allowed_domains", tuple(domain.strip().lower() for domain in self.allowed_domains if domain.strip()))
        object.__setattr__(self, "allowed_formats", tuple(extension.strip().lower() for extension in self.allowed_formats if extension.strip()))
        object.__setattr__(self, "discovery_mode", discovery_mode)
        object.__setattr__(self, "credentials_ref", None if self.credentials_ref is None else self.credentials_ref.strip() or None)
        object.__setattr__(self, "default_metadata", tuple(sorted((str(key), str(value)) for key, value in self.default_metadata)))


@dataclass(frozen=True, slots=True)
class LoadPolicy:
    max_documents_per_run: int | None = None
    since_date: str | None = None
    resume: bool = False
    start_after_document_url: str | None = None
    follow_subpaths: bool = True
    expand_archives: bool = True
    fail_fast: bool = False
    dry_run: bool = False
    recursive: bool = False

    def __post_init__(self) -> None:
        if self.max_documents_per_run is not None and self.max_documents_per_run <= 0:
            raise ValueError("LoadPolicy.max_documents_per_run must be positive when present")
        if self.since_date is not None and not self.since_date.strip():
            raise ValueError("LoadPolicy.since_date cannot be blank")
        if self.since_date is not None:
            object.__setattr__(self, "since_date", self.since_date.strip())
        if self.start_after_document_url is not None and not self.start_after_document_url.strip():
            raise ValueError("LoadPolicy.start_after_document_url cannot be blank")
        if self.start_after_document_url is not None:
            object.__setattr__(self, "start_after_document_url", _canonical_url(self.start_after_document_url))


@dataclass(frozen=True, slots=True)
class DiscoveredDocument:
    source_name: str
    manufacturer_name: str
    document_url: str
    referrer_url: str | None
    detected_format: str
    discovered_at: datetime

    def __post_init__(self) -> None:
        source_name = self.source_name.strip().lower()
        manufacturer_name = self.manufacturer_name.strip()
        document_url = _canonical_url(self.document_url)
        detected_format = self.detected_format.strip().lower()
        if not source_name:
            raise ValueError("DiscoveredDocument.source_name cannot be empty")
        if not manufacturer_name:
            raise ValueError("DiscoveredDocument.manufacturer_name cannot be empty")
        if not detected_format:
            raise ValueError("DiscoveredDocument.detected_format cannot be empty")
        object.__setattr__(self, "source_name", source_name)
        object.__setattr__(self, "manufacturer_name", manufacturer_name)
        object.__setattr__(self, "document_url", document_url)
        object.__setattr__(self, "referrer_url", None if self.referrer_url is None else _canonical_url(self.referrer_url))
        object.__setattr__(self, "detected_format", detected_format)


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    artifact_id: EntityId
    source_name: str
    original_url: str
    canonical_url: str
    local_path: str
    content_type: str
    size_bytes: int
    downloaded_at: datetime
    archive_parent_artifact_id: EntityId | None = None

    def __post_init__(self) -> None:
        source_name = self.source_name.strip().lower()
        content_type = self.content_type.strip().lower()
        local_path = self.local_path.strip()
        if not source_name:
            raise ValueError("DownloadedArtifact.source_name cannot be empty")
        if not local_path:
            raise ValueError("DownloadedArtifact.local_path cannot be empty")
        if not content_type:
            raise ValueError("DownloadedArtifact.content_type cannot be empty")
        if self.size_bytes < 0:
            raise ValueError("DownloadedArtifact.size_bytes cannot be negative")
        object.__setattr__(self, "source_name", source_name)
        object.__setattr__(self, "original_url", _canonical_url(self.original_url))
        object.__setattr__(self, "canonical_url", _canonical_url(self.canonical_url))
        object.__setattr__(self, "local_path", local_path)
        object.__setattr__(self, "content_type", content_type)


@dataclass(frozen=True, slots=True)
class ArtifactFingerprint:
    artifact_id: EntityId
    sha256: str
    canonical_url: str
    normalized_filename: str

    def __post_init__(self) -> None:
        sha256 = self.sha256.strip().lower()
        normalized_filename = self.normalized_filename.strip().casefold()
        if len(sha256) != 64:
            raise ValueError("ArtifactFingerprint.sha256 must be a 64-character SHA-256 hex digest")
        if not normalized_filename:
            raise ValueError("ArtifactFingerprint.normalized_filename cannot be empty")
        object.__setattr__(self, "sha256", sha256)
        object.__setattr__(self, "canonical_url", _canonical_url(self.canonical_url))
        object.__setattr__(self, "normalized_filename", normalized_filename)


@dataclass(frozen=True, slots=True)
class ArtifactDecision:
    artifact_id: EntityId
    lineage_id: EntityId
    dedup_status: str
    version_status: str
    dispatchable: bool
    reason: str

    def __post_init__(self) -> None:
        dedup_status = self.dedup_status.strip().lower()
        version_status = self.version_status.strip().lower()
        reason = self.reason.strip()
        if dedup_status not in {"new", "duplicate_exact", "duplicate_url"}:
            raise ValueError("ArtifactDecision.dedup_status is invalid")
        if version_status not in {"new_document", "new_version", "unchanged"}:
            raise ValueError("ArtifactDecision.version_status is invalid")
        if not reason:
            raise ValueError("ArtifactDecision.reason cannot be empty")
        object.__setattr__(self, "dedup_status", dedup_status)
        object.__setattr__(self, "version_status", version_status)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True, slots=True)
class DispatchRequest:
    artifact_id: EntityId
    file_path: str
    source_name: str
    manufacturer_name: str
    document_metadata: tuple[tuple[str, str], ...]
    provenance: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        file_path = self.file_path.strip()
        source_name = self.source_name.strip().lower()
        manufacturer_name = self.manufacturer_name.strip()
        if not file_path:
            raise ValueError("DispatchRequest.file_path cannot be empty")
        if not source_name:
            raise ValueError("DispatchRequest.source_name cannot be empty")
        if not manufacturer_name:
            raise ValueError("DispatchRequest.manufacturer_name cannot be empty")
        if not self.provenance:
            raise ValueError("DispatchRequest.provenance cannot be empty")
        object.__setattr__(self, "file_path", file_path)
        object.__setattr__(self, "source_name", source_name)
        object.__setattr__(self, "manufacturer_name", manufacturer_name)
        object.__setattr__(self, "document_metadata", tuple(sorted((str(key), str(value)) for key, value in self.document_metadata)))
        object.__setattr__(self, "provenance", tuple(sorted((str(key), str(value)) for key, value in self.provenance)))


@dataclass(frozen=True, slots=True)
class DispatchResult:
    artifact_id: EntityId
    status: str
    document_id: EntityId | None = None
    workflow_run_id: RunId | None = None
    error_code: str | None = None
    error_message: str | None = None
    semantic_metrics: tuple[tuple[str, int], ...] = ()
    processor_family: str | None = None
    processor_version: str | None = None
    compatible_ready: bool | None = None

    def __post_init__(self) -> None:
        status = self.status.strip().lower()
        if status not in {"dispatched", "failed", "skipped"}:
            raise ValueError("DispatchResult.status is invalid")
        if status == "failed" and (self.error_code is None or self.error_message is None):
            raise ValueError("DispatchResult failed values require error_code and error_message")
        processor_family = None if self.processor_family is None else self.processor_family.strip().lower() or None
        processor_version = None if self.processor_version is None else self.processor_version.strip() or None
        if (processor_family is None) != (processor_version is None):
            raise ValueError("DispatchResult processor_family and processor_version must both be set or both be null")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "error_code", None if self.error_code is None else self.error_code.strip() or None)
        object.__setattr__(self, "error_message", None if self.error_message is None else self.error_message.strip() or None)
        object.__setattr__(self, "semantic_metrics", tuple(sorted((str(key), int(value)) for key, value in self.semantic_metrics)))
        object.__setattr__(self, "processor_family", processor_family)
        object.__setattr__(self, "processor_version", processor_version)
        object.__setattr__(self, "compatible_ready", None if self.compatible_ready is None else bool(self.compatible_ready))


@dataclass(frozen=True, slots=True)
class SemanticDocumentMetrics:
    artifact_id: EntityId
    document_id: EntityId
    workflow_run_id: RunId
    fragments: int
    assertions: int
    facts: int
    ontology_proposals: int
    graph_nodes: int
    graph_relationships: int
    search_documents: int

    def __post_init__(self) -> None:
        for field_name in (
            "fragments",
            "assertions",
            "facts",
            "ontology_proposals",
            "graph_nodes",
            "graph_relationships",
            "search_documents",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"SemanticDocumentMetrics.{field_name} cannot be negative")


@dataclass(frozen=True, slots=True)
class LasFileRecord:
    las_file_id: EntityId
    file_path: str
    sha256: str
    well_name: str | None
    service_company: str | None
    parsed_at: datetime

    def __post_init__(self) -> None:
        file_path = self.file_path.strip()
        sha256 = self.sha256.strip().lower()
        if not file_path:
            raise ValueError("LasFileRecord.file_path cannot be empty")
        if len(sha256) != 64:
            raise ValueError("LasFileRecord.sha256 must be a SHA-256 digest")
        object.__setattr__(self, "file_path", file_path)
        object.__setattr__(self, "sha256", sha256)
        object.__setattr__(self, "well_name", None if self.well_name is None else self.well_name.strip() or None)
        object.__setattr__(self, "service_company", None if self.service_company is None else self.service_company.strip() or None)


@dataclass(frozen=True, slots=True)
class MnemonicObservation:
    las_file_id: EntityId
    mnemonic: str
    unit: str | None
    description: str | None
    depth_curve_flag: bool
    count: int

    def __post_init__(self) -> None:
        mnemonic = self.mnemonic.strip().upper()
        if not mnemonic:
            raise ValueError("MnemonicObservation.mnemonic cannot be empty")
        if self.count <= 0:
            raise ValueError("MnemonicObservation.count must be positive")
        object.__setattr__(self, "mnemonic", mnemonic)
        object.__setattr__(self, "unit", None if self.unit is None else self.unit.strip() or None)
        object.__setattr__(self, "description", None if self.description is None else self.description.strip() or None)


@dataclass(frozen=True, slots=True)
class MnemonicAggregate:
    normalized_mnemonic: str
    observed_aliases: tuple[str, ...]
    observed_units: tuple[str, ...]
    occurrence_count: int
    source_files: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized_mnemonic = self.normalized_mnemonic.strip().upper()
        if not normalized_mnemonic:
            raise ValueError("MnemonicAggregate.normalized_mnemonic cannot be empty")
        if self.occurrence_count <= 0:
            raise ValueError("MnemonicAggregate.occurrence_count must be positive")
        if not self.source_files:
            raise ValueError("MnemonicAggregate.source_files cannot be empty")
        object.__setattr__(self, "normalized_mnemonic", normalized_mnemonic)
        object.__setattr__(self, "observed_aliases", tuple(sorted({alias.strip().upper() for alias in self.observed_aliases if alias.strip()})))
        object.__setattr__(self, "observed_units", tuple(sorted({unit.strip() for unit in self.observed_units if unit and unit.strip()})))
        object.__setattr__(self, "source_files", tuple(sorted({path.strip() for path in self.source_files if path.strip()})))


@dataclass(frozen=True, slots=True)
class GapCandidate:
    gap_id: EntityId
    gap_type: str
    normalized_mnemonic: str
    candidate_aliases: tuple[str, ...]
    observed_units: tuple[str, ...]
    evidence_count: int
    evidence_files: tuple[str, ...]
    dispatchable: bool

    def __post_init__(self) -> None:
        gap_type = self.gap_type.strip().lower()
        normalized_mnemonic = self.normalized_mnemonic.strip().upper()
        if gap_type not in {"unknown_variable", "potential_alias", "unknown_unit_binding", "ambiguous_mnemonic"}:
            raise ValueError("GapCandidate.gap_type is invalid")
        if not normalized_mnemonic:
            raise ValueError("GapCandidate.normalized_mnemonic cannot be empty")
        if self.evidence_count <= 0:
            raise ValueError("GapCandidate.evidence_count must be positive")
        if not self.evidence_files:
            raise ValueError("GapCandidate.evidence_files cannot be empty")
        object.__setattr__(self, "gap_type", gap_type)
        object.__setattr__(self, "normalized_mnemonic", normalized_mnemonic)
        object.__setattr__(self, "candidate_aliases", tuple(sorted({alias.strip().upper() for alias in self.candidate_aliases if alias.strip()})))
        object.__setattr__(self, "observed_units", tuple(sorted({unit.strip() for unit in self.observed_units if unit.strip()})))
        object.__setattr__(self, "evidence_files", tuple(sorted({path.strip() for path in self.evidence_files if path.strip()})))


class ArtifactRegistry:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    @classmethod
    def create(cls, database_path: str | Path) -> "ArtifactRegistry":
        return cls(database_path)

    def start_run(self, *, mode: str, target: str, policy: LoadPolicy) -> RunId:
        run_id = RunId.from_seed("loader.run", f"{mode}:{target}:{_utc_now().isoformat()}")
        with self._connect() as connection:
            self._mark_stale_runs(connection, mode=mode, target=target)
            connection.execute(
                "INSERT INTO load_runs (load_run_id, mode, target, started_at, finished_at, status, summary_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(run_id),
                    mode,
                    target,
                    _utc_now().isoformat(),
                    None,
                    "running",
                    _json({"policy": self._policy_dict(policy), "process_id": os.getpid()}),
                ),
            )
            connection.commit()
        return run_id

    def update_run_progress(self, run_id: RunId, *, summary: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE load_runs SET summary_json = ? WHERE load_run_id = ?",
                (_json(summary), str(run_id)),
            )
            connection.commit()

    def finish_run(self, run_id: RunId, *, status: str, summary: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE load_runs SET finished_at = ?, status = ?, summary_json = ? WHERE load_run_id = ?",
                (_utc_now().isoformat(), status, _json(summary), str(run_id)),
            )
            connection.commit()

    def record_source_definition(self, definition: SourceDefinition) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO source_definitions (source_name, manufacturer_name, seed_urls, allowed_domains, allowed_formats, discovery_mode, credentials_ref, default_metadata, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    definition.source_name,
                    definition.manufacturer_name,
                    _json(list(definition.seed_urls)),
                    _json(list(definition.allowed_domains)),
                    _json(list(definition.allowed_formats)),
                    definition.discovery_mode,
                    definition.credentials_ref,
                    _json(list(definition.default_metadata)),
                    1 if definition.active else 0,
                ),
            )
            connection.commit()

    def record_discovered_documents(self, run_id: RunId, documents: tuple[DiscoveredDocument, ...]) -> None:
        with self._connect() as connection:
            for document in documents:
                connection.execute(
                    "INSERT INTO discovered_documents (load_run_id, source_name, manufacturer_name, document_url, referrer_url, detected_format, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(run_id),
                        document.source_name,
                        document.manufacturer_name,
                        document.document_url,
                        document.referrer_url,
                        document.detected_format,
                        document.discovered_at.isoformat(),
                    ),
                )
            connection.commit()

    def latest_document_checkpoint(self, source_name: str) -> str | None:
        normalized = source_name.strip().lower()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT summary_json FROM load_runs WHERE mode = ? AND target = ? AND status IN (?, ?, ?, ?) AND finished_at IS NOT NULL ORDER BY finished_at DESC",
                ("document", normalized, "completed", "completed_with_errors", "interrupted", "failed"),
            ).fetchall()
        for row in rows:
            summary = json.loads(str(row["summary_json"]))
            checkpoint = summary.get("last_processed_document_url")
            if checkpoint:
                return _canonical_url(str(checkpoint))
        return None

    def register_downloaded_artifact(self, artifact: DownloadedArtifact) -> tuple[ArtifactFingerprint, ArtifactDecision]:
        sha256 = __import__("hashlib").sha256(Path(artifact.local_path).read_bytes()).hexdigest()
        fingerprint = ArtifactFingerprint(
            artifact_id=artifact.artifact_id,
            sha256=sha256,
            canonical_url=artifact.canonical_url,
            normalized_filename=_normalized_filename(artifact.local_path),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO downloaded_artifacts (artifact_id, source_name, original_url, canonical_url, local_path, content_type, size_bytes, downloaded_at, archive_parent_artifact_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(artifact.artifact_id),
                    artifact.source_name,
                    artifact.original_url,
                    artifact.canonical_url,
                    artifact.local_path,
                    artifact.content_type,
                    artifact.size_bytes,
                    artifact.downloaded_at.isoformat(),
                    None if artifact.archive_parent_artifact_id is None else str(artifact.archive_parent_artifact_id),
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO artifact_fingerprints (artifact_id, sha256, canonical_url, normalized_filename) VALUES (?, ?, ?, ?)",
                (str(fingerprint.artifact_id), fingerprint.sha256, fingerprint.canonical_url, fingerprint.normalized_filename),
            )
            existing_sha = connection.execute(
                "SELECT artifact_id FROM artifact_fingerprints WHERE sha256 = ? AND artifact_id <> ? ORDER BY artifact_id LIMIT 1",
                (fingerprint.sha256, str(fingerprint.artifact_id)),
            ).fetchone()
            existing_url = connection.execute(
                "SELECT artifact_id FROM artifact_fingerprints WHERE canonical_url = ? AND artifact_id <> ? ORDER BY artifact_id LIMIT 1",
                (fingerprint.canonical_url, str(fingerprint.artifact_id)),
            ).fetchone()
            lineage_id = EntityId.from_seed("loader.lineage", f"{artifact.source_name}:{fingerprint.canonical_url}:{fingerprint.normalized_filename}")
            row = connection.execute("SELECT version_number, sha256 FROM document_versions WHERE lineage_id = ? ORDER BY version_number DESC LIMIT 1", (str(lineage_id),)).fetchone()
            dedup_status = "new"
            version_status = "new_document"
            dispatchable = True
            reason = "First document observed for lineage"
            if existing_sha is not None:
                dedup_status = "duplicate_exact"
                version_status = "unchanged"
                dispatchable = False
                reason = "Binary SHA-256 already exists"
            elif existing_url is not None:
                dedup_status = "duplicate_url"
                version_status = "unchanged"
                dispatchable = False
                reason = "Canonical URL already exists"
            elif row is not None:
                version_status = "new_version" if row["sha256"] != fingerprint.sha256 else "unchanged"
                dispatchable = version_status == "new_version"
                reason = "New version observed for lineage" if dispatchable else "Lineage unchanged"
            connection.execute(
                "INSERT OR IGNORE INTO document_lineages (lineage_id, source_name, manufacturer_name, canonical_identity, document_title_hint) VALUES (?, ?, ?, ?, ?)",
                (str(lineage_id), artifact.source_name, artifact.source_name, f"{artifact.source_name}:{fingerprint.canonical_url}", fingerprint.normalized_filename),
            )
            if dedup_status == "new" and version_status in {"new_document", "new_version"}:
                previous_version = connection.execute("SELECT COALESCE(MAX(version_number), 0) AS value FROM document_versions WHERE lineage_id = ?", (str(lineage_id),)).fetchone()["value"]
                connection.execute(
                    "INSERT INTO document_versions (version_id, lineage_id, artifact_id, version_number, sha256, first_seen_at, dispatch_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(EntityId.from_seed("loader.version", f"{lineage_id}:{previous_version + 1}:{fingerprint.sha256}")),
                        str(lineage_id),
                        str(artifact.artifact_id),
                        previous_version + 1,
                        fingerprint.sha256,
                        artifact.downloaded_at.isoformat(),
                        "pending" if dispatchable else "skipped",
                    ),
                )
            connection.commit()
        return fingerprint, ArtifactDecision(
            artifact_id=artifact.artifact_id,
            lineage_id=lineage_id,
            dedup_status=dedup_status,
            version_status=version_status,
            dispatchable=dispatchable,
            reason=reason,
        )

    def record_dispatch_result(self, result: DispatchResult) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO dispatch_results (artifact_id, status, document_id, workflow_run_id, error_code, error_message) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(result.artifact_id),
                    result.status,
                    None if result.document_id is None else str(result.document_id),
                    None if result.workflow_run_id is None else str(result.workflow_run_id),
                    result.error_code,
                    result.error_message,
                ),
            )
            connection.execute(
                "UPDATE document_versions SET dispatch_status = ? WHERE artifact_id = ?",
                (result.status, str(result.artifact_id)),
            )
            if result.status == "dispatched" and result.document_id is not None and result.workflow_run_id is not None:
                metrics = dict(result.semantic_metrics)
                connection.execute(
                    "INSERT OR REPLACE INTO semantic_document_metrics (artifact_id, document_id, workflow_run_id, fragments, assertions, facts, ontology_proposals, graph_nodes, graph_relationships, search_documents) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(result.artifact_id),
                        str(result.document_id),
                        str(result.workflow_run_id),
                        int(metrics.get("fragments", 0)),
                        int(metrics.get("assertions", 0)),
                        int(metrics.get("facts", 0)),
                        int(metrics.get("ontology_proposals", 0)),
                        int(metrics.get("graph_nodes", 0)),
                        int(metrics.get("graph_relationships", 0)),
                        int(metrics.get("search_documents", 0)),
                    ),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO semantic_processing_state (artifact_id, document_id, workflow_run_id, processor_family, processor_version, compatible_ready, structured_fact_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(result.artifact_id),
                        str(result.document_id),
                        str(result.workflow_run_id),
                        result.processor_family,
                        result.processor_version,
                        None if result.compatible_ready is None else int(result.compatible_ready),
                        int(metrics.get("structured_facts", 0)),
                    ),
                )
            connection.commit()

    def list_semantic_metrics(self, source_name: str | None = None) -> tuple[SemanticDocumentMetrics, ...]:
        query = (
            "SELECT sdm.artifact_id, sdm.document_id, sdm.workflow_run_id, sdm.fragments, sdm.assertions, sdm.facts, "
            "sdm.ontology_proposals, sdm.graph_nodes, sdm.graph_relationships, sdm.search_documents "
            "FROM semantic_document_metrics sdm "
            "JOIN downloaded_artifacts da ON da.artifact_id = sdm.artifact_id"
        )
        params: tuple[object, ...] = ()
        if source_name is not None:
            query += " WHERE da.source_name = ?"
            params = (source_name.strip().lower(),)
        query += " ORDER BY da.source_name, sdm.workflow_run_id, sdm.document_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(
            SemanticDocumentMetrics(
                artifact_id=EntityId(str(row["artifact_id"])),
                document_id=EntityId(str(row["document_id"])),
                workflow_run_id=RunId(str(row["workflow_run_id"])),
                fragments=int(row["fragments"]),
                assertions=int(row["assertions"]),
                facts=int(row["facts"]),
                ontology_proposals=int(row["ontology_proposals"]),
                graph_nodes=int(row["graph_nodes"]),
                graph_relationships=int(row["graph_relationships"]),
                search_documents=int(row["search_documents"]),
            )
            for row in rows
        )

    def get_dispatch_result(self, artifact_id: EntityId) -> DispatchResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, document_id, workflow_run_id, error_code, error_message FROM dispatch_results WHERE artifact_id = ?",
                (str(artifact_id),),
            ).fetchone()
        if row is None:
            return None
        return DispatchResult(
            artifact_id=artifact_id,
            status=str(row["status"]),
            document_id=None if row["document_id"] is None else EntityId(row["document_id"]),
            workflow_run_id=None if row["workflow_run_id"] is None else RunId(row["workflow_run_id"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    def register_las_file(self, record: LasFileRecord, observations: tuple[MnemonicObservation, ...]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO las_files (las_file_id, file_path, sha256, well_name, service_company, parsed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(record.las_file_id), record.file_path, record.sha256, record.well_name, record.service_company, record.parsed_at.isoformat()),
            )
            connection.execute("DELETE FROM las_mnemonic_observations WHERE las_file_id = ?", (str(record.las_file_id),))
            for observation in observations:
                connection.execute(
                    "INSERT INTO las_mnemonic_observations (las_file_id, mnemonic, unit, description, depth_curve_flag, count) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(observation.las_file_id),
                        observation.mnemonic,
                        observation.unit,
                        observation.description,
                        1 if observation.depth_curve_flag else 0,
                        observation.count,
                    ),
                )
            connection.commit()

    def list_mnemonic_aggregates(self) -> tuple[MnemonicAggregate, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT mnemonic, unit, description, file_path, count FROM las_mnemonic_observations JOIN las_files USING(las_file_id) ORDER BY mnemonic, file_path"
            ).fetchall()
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            mnemonic = str(row["mnemonic"]).strip().upper()
            entry = grouped.setdefault(mnemonic, {"aliases": set(), "units": set(), "count": 0, "files": set()})
            entry["aliases"].add(mnemonic)
            if row["description"]:
                entry["aliases"].add(str(row["description"]).strip().upper())
            if row["unit"]:
                entry["units"].add(str(row["unit"]).strip())
            entry["count"] = int(entry["count"]) + int(row["count"])
            entry["files"].add(str(row["file_path"]))
        return tuple(
            MnemonicAggregate(
                normalized_mnemonic=mnemonic,
                observed_aliases=tuple(sorted(entry["aliases"])),
                observed_units=tuple(sorted(entry["units"])),
                occurrence_count=int(entry["count"]),
                source_files=tuple(sorted(entry["files"])),
            )
            for mnemonic, entry in sorted(grouped.items())
        )

    def build_gap_candidates(self) -> tuple[GapCandidate, ...]:
        aggregates = self.list_mnemonic_aggregates()
        gaps: list[GapCandidate] = []
        for aggregate in aggregates:
            gap_types = ["unknown_variable"]
            if len(aggregate.observed_aliases) > 1:
                gap_types.append("potential_alias")
            if len(aggregate.observed_units) > 1:
                gap_types.append("ambiguous_mnemonic")
            if not aggregate.observed_units:
                gap_types.append("unknown_unit_binding")
            for gap_type in gap_types:
                gaps.append(
                    GapCandidate(
                        gap_id=EntityId.from_seed("loader.gap", f"{gap_type}:{aggregate.normalized_mnemonic}:{'|'.join(aggregate.source_files)}"),
                        gap_type=gap_type,
                        normalized_mnemonic=aggregate.normalized_mnemonic,
                        candidate_aliases=aggregate.observed_aliases,
                        observed_units=aggregate.observed_units,
                        evidence_count=aggregate.occurrence_count,
                        evidence_files=aggregate.source_files,
                        dispatchable=True,
                    )
                )
        with self._connect() as connection:
            connection.execute("DELETE FROM gap_candidates")
            for gap in gaps:
                connection.execute(
                    "INSERT INTO gap_candidates (gap_id, gap_type, normalized_mnemonic, candidate_aliases, observed_units, evidence_count, evidence_files, dispatchable) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(gap.gap_id),
                        gap.gap_type,
                        gap.normalized_mnemonic,
                        _json(list(gap.candidate_aliases)),
                        _json(list(gap.observed_units)),
                        gap.evidence_count,
                        _json(list(gap.evidence_files)),
                        1 if gap.dispatchable else 0,
                    ),
                )
            connection.commit()
        return tuple(gaps)

    def list_tables(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
        return tuple(str(row["name"]) for row in rows)

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS source_definitions (source_name TEXT PRIMARY KEY, manufacturer_name TEXT NOT NULL, seed_urls TEXT NOT NULL, allowed_domains TEXT NOT NULL, allowed_formats TEXT NOT NULL, discovery_mode TEXT NOT NULL, credentials_ref TEXT NULL, default_metadata TEXT NOT NULL, active INTEGER NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS load_runs (load_run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, target TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NULL, status TEXT NOT NULL, summary_json TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS discovered_documents (load_run_id TEXT NOT NULL, source_name TEXT NOT NULL, manufacturer_name TEXT NOT NULL, document_url TEXT NOT NULL, referrer_url TEXT NULL, detected_format TEXT NOT NULL, discovered_at TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS downloaded_artifacts (artifact_id TEXT PRIMARY KEY, source_name TEXT NOT NULL, original_url TEXT NOT NULL, canonical_url TEXT NOT NULL, local_path TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, downloaded_at TEXT NOT NULL, archive_parent_artifact_id TEXT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS artifact_fingerprints (artifact_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, canonical_url TEXT NOT NULL, normalized_filename TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS document_lineages (lineage_id TEXT PRIMARY KEY, source_name TEXT NOT NULL, manufacturer_name TEXT NOT NULL, canonical_identity TEXT NOT NULL, document_title_hint TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS document_versions (version_id TEXT PRIMARY KEY, lineage_id TEXT NOT NULL, artifact_id TEXT NOT NULL UNIQUE, version_number INTEGER NOT NULL, sha256 TEXT NOT NULL, first_seen_at TEXT NOT NULL, dispatch_status TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS dispatch_results (artifact_id TEXT PRIMARY KEY, status TEXT NOT NULL, document_id TEXT NULL, workflow_run_id TEXT NULL, error_code TEXT NULL, error_message TEXT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS semantic_document_metrics (artifact_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, workflow_run_id TEXT NOT NULL, fragments INTEGER NOT NULL, assertions INTEGER NOT NULL, facts INTEGER NOT NULL, ontology_proposals INTEGER NOT NULL, graph_nodes INTEGER NOT NULL, graph_relationships INTEGER NOT NULL, search_documents INTEGER NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS semantic_processing_state (artifact_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, workflow_run_id TEXT NOT NULL, processor_family TEXT NULL, processor_version TEXT NULL, compatible_ready INTEGER NULL, structured_fact_count INTEGER NOT NULL DEFAULT 0)")
            connection.execute("CREATE TABLE IF NOT EXISTS las_files (las_file_id TEXT PRIMARY KEY, file_path TEXT NOT NULL, sha256 TEXT NOT NULL, well_name TEXT NULL, service_company TEXT NULL, parsed_at TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS las_mnemonic_observations (las_file_id TEXT NOT NULL, mnemonic TEXT NOT NULL, unit TEXT NULL, description TEXT NULL, depth_curve_flag INTEGER NOT NULL, count INTEGER NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS gap_candidates (gap_id TEXT PRIMARY KEY, gap_type TEXT NOT NULL, normalized_mnemonic TEXT NOT NULL, candidate_aliases TEXT NOT NULL, observed_units TEXT NOT NULL, evidence_count INTEGER NOT NULL, evidence_files TEXT NOT NULL, dispatchable INTEGER NOT NULL)")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            elif version == 1:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            elif version != _SCHEMA_VERSION:
                raise ValueError(f"Unsupported loader schema version: {version}")
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

    def _mark_stale_runs(self, connection: sqlite3.Connection, *, mode: str, target: str) -> None:
        rows = connection.execute(
            "SELECT load_run_id, summary_json FROM load_runs WHERE mode = ? AND target = ? AND status = ? AND finished_at IS NULL ORDER BY started_at",
            (mode, target, "running"),
        ).fetchall()
        for row in rows:
            summary = json.loads(str(row["summary_json"]))
            process_id = summary.get("process_id")
            if process_id is not None and self._process_exists(int(process_id)):
                continue
            summary["stale_recovered"] = True
            summary["stale_recovered_at"] = _utc_now().isoformat()
            summary["stale_reason"] = "orphaned_running_run_detected_on_new_start"
            connection.execute(
                "UPDATE load_runs SET finished_at = ?, status = ?, summary_json = ? WHERE load_run_id = ?",
                (_utc_now().isoformat(), "interrupted", _json(summary), str(row["load_run_id"])),
            )

    @staticmethod
    def _process_exists(process_id: int) -> bool:
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _policy_dict(policy: LoadPolicy) -> dict[str, object]:
        return {
            "max_documents_per_run": policy.max_documents_per_run,
            "since_date": policy.since_date,
            "resume": policy.resume,
            "start_after_document_url": policy.start_after_document_url,
            "follow_subpaths": policy.follow_subpaths,
            "expand_archives": policy.expand_archives,
            "fail_fast": policy.fail_fast,
            "dry_run": policy.dry_run,
            "recursive": policy.recursive,
        }