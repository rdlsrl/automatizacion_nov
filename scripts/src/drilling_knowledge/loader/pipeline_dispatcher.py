"""Pipeline dispatcher using only public platform contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.catalog.seeds.loader import SeedCatalogsAndIdkbBackboneLoader
from drilling_knowledge.documents.domain import DocumentMetadata
from drilling_knowledge.documents.sqlite import SQLiteDocumentRepository
from drilling_knowledge.loader.artifact_registry import DispatchRequest, DispatchResult, ENERGISTICS_EXTRACTOR_VERSION, ENERGISTICS_STRUCTURED_PREDICATES
from drilling_knowledge.projections.search import EmbeddingRequest, EmbeddingResult
from drilling_knowledge.projections.search.repositories.sqlite import SQLiteSearchProjectionBatchRepository
from drilling_knowledge.review import ReviewPolicyCatalogLoader
from drilling_knowledge.assertions.repositories.sqlite import SQLiteAssertionGenerationRunRepository
from drilling_knowledge.assertions.consolidation.repositories.sqlite import SQLiteFactConsolidationRunRepository
from drilling_knowledge.workflows import AcquisitionWorkflowOrchestrator


_GRAPH_PROJECTABLE_LABELS = {
    "EngineeringUnit",
    "EquipmentClass",
    "InstrumentClass",
    "LocationClass",
    "MeasurementPrinciple",
    "OriginClass",
    "PhysicalQuantity",
    "ProcessClass",
    "SensorClass",
    "SubsystemClass",
    "SystemClass",
    "Variable",
    "VariableClassification",
}


class _DeterministicEmbeddingProvider:
    def project_batch(self, requests: tuple[EmbeddingRequest, ...]) -> tuple[EmbeddingResult, ...]:
        return tuple(
            EmbeddingResult(source_type=request.source_type, source_entity_id=request.source_entity_id, vector=(float(index + 1), float(len(request.text))))
            for index, request in enumerate(requests)
        )


@dataclass(slots=True)
class PipelineDispatcher:
    workflow: AcquisitionWorkflowOrchestrator

    @staticmethod
    def _is_energistics_request(request: DispatchRequest) -> bool:
        name = Path(request.file_path).name.upper()
        return request.source_name == "energistics" or "WITSML" in name or "RESQML" in name or "PRODML" in name

    @staticmethod
    def _structured_fact_count(result) -> int:
        facts = getattr(result, "facts", ()) or ()
        return sum(1 for fact in facts if getattr(fact, "predicate_code", None) in ENERGISTICS_STRUCTURED_PREDICATES)

    @classmethod
    def _energistics_compatible_ready(cls, result) -> bool:
        return (
            cls._structured_fact_count(result) > 0
            or cls._metric_length(result, "facts") > 0
            or cls._metric_length(result, "assertions") > 0
            or cls._metric_length(result, "fragments") > 0
        )

    @staticmethod
    def _step_metric(result, step_name: str, key: str) -> int:
        pipeline_run = getattr(result, "pipeline_run", None)
        step_runs = getattr(pipeline_run, "step_runs", ()) if pipeline_run is not None else ()
        for step in step_runs:
            if step.step_name != step_name:
                continue
            for metric_key, metric_value in step.output_json:
                if metric_key == key:
                    return int(metric_value)
        return 0

    @staticmethod
    def _metric_length(result, attribute_name: str) -> int:
        value = getattr(result, attribute_name, ())
        return len(value) if value is not None else 0

    @staticmethod
    def _filtered(repository: InMemoryEntityRepository) -> InMemoryEntityRepository:
        return InMemoryEntityRepository(
            tuple(entity for entity in repository.list_all() if entity.__class__.__name__ in _GRAPH_PROJECTABLE_LABELS)
        )

    @classmethod
    def create_default(cls, *, database_path: str | Path | None = None) -> "PipelineDispatcher":
        root = Path(__file__).resolve().parents[3]
        persistence_path = Path(database_path) if database_path is not None else root / "var" / "loader" / "loader.sqlite"
        seeded = SeedCatalogsAndIdkbBackboneLoader().load().catalog
        catalog = InMemoryCatalogRepository(
            units=cls._filtered(seeded.units),
            quantities=cls._filtered(seeded.quantities),
            principles=cls._filtered(seeded.principles),
            quantity_unit_compatibilities=InMemoryEntityRepository(()),
            classifications=cls._filtered(seeded.classifications),
            origins=cls._filtered(seeded.origins),
            publishers=InMemoryEntityRepository(()),
            systems=cls._filtered(seeded.systems),
            subsystems=cls._filtered(seeded.subsystems),
            processes=cls._filtered(seeded.processes),
            operational_contexts=InMemoryEntityRepository(()),
            locations=cls._filtered(seeded.locations),
            sensors=cls._filtered(seeded.sensors),
            instruments=cls._filtered(seeded.instruments),
            equipment=cls._filtered(seeded.equipment),
            variables=cls._filtered(seeded.variables),
        )
        policies = ReviewPolicyCatalogLoader.load(root / "db" / "review")
        return cls(
            workflow=AcquisitionWorkflowOrchestrator.create(
                catalog_repository=catalog,
                embedding_provider=_DeterministicEmbeddingProvider(),
                review_policy_catalog=policies,
                document_repository=SQLiteDocumentRepository.create(persistence_path),
                assertion_repository=SQLiteAssertionGenerationRunRepository.create(persistence_path),
                fact_repository=SQLiteFactConsolidationRunRepository.create(persistence_path),
                search_repository=SQLiteSearchProjectionBatchRepository.create(persistence_path),
            )
        )

    def dispatch(self, request: DispatchRequest) -> DispatchResult:
        metadata_dict = dict(request.document_metadata)
        metadata = DocumentMetadata(
            author=metadata_dict.get("author"),
            manufacturer=request.manufacturer_name,
            model=metadata_dict.get("model"),
            version_label=metadata_dict.get("version_label"),
            language=metadata_dict.get("language", "und"),
            authority_level=metadata_dict.get("authority_level", "reference"),
            document_type=metadata_dict.get("document_type", "manual"),
            source=request.source_name,
            license_name=metadata_dict.get("license_name"),
        )
        try:
            result = self.workflow.run(document_path=request.file_path, metadata=metadata, created_by="industrial-knowledge-loader")
        except Exception as exc:
            return DispatchResult(
                artifact_id=request.artifact_id,
                status="failed",
                error_code="dispatch_failed",
                error_message=str(exc),
            )
        return DispatchResult(
            artifact_id=request.artifact_id,
            status="dispatched",
            document_id=result.document.entity_id,
            workflow_run_id=result.pipeline_run.pipeline_run_id,
            processor_family="energistics" if self._is_energistics_request(request) else "default",
            processor_version=ENERGISTICS_EXTRACTOR_VERSION if self._is_energistics_request(request) else "1",
            compatible_ready=self._energistics_compatible_ready(result) if self._is_energistics_request(request) else True,
            semantic_metrics=(
                ("fragments", self._metric_length(result, "fragments")),
                ("assertions", self._metric_length(result, "assertions")),
                ("facts", self._metric_length(result, "facts")),
                ("structured_facts", self._structured_fact_count(result)),
                ("ontology_proposals", self._step_metric(result, "ontology_proposals", "proposal_count")),
                ("graph_nodes", 0 if getattr(result, "graph_projection", None) is None else len(result.graph_projection.nodes)),
                ("graph_relationships", 0 if getattr(result, "graph_projection", None) is None else len(result.graph_projection.relationships)),
                ("search_documents", 0 if getattr(result, "search_projection", None) is None else len(result.search_projection.documents)),
            ),
        )