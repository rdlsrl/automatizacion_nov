"""Deterministic acquisition workflow orchestration over existing contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

from drilling_knowledge.assertions.conflict_resolution import AssertionConflictResolver
from drilling_knowledge.assertions.consolidation import FactConsolidator
from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus, EvidenceAssertion
from drilling_knowledge.assertions.engine import EvidenceAssertionEngine
from drilling_knowledge.catalog.domain import KnowledgeEntity, Variable
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository
from drilling_knowledge.catalog.services.ontology_proposals import OntologyProposalGenerator
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.documents import DocumentKnowledgeAcquisitionEngine, DocumentMetadata
from drilling_knowledge.documents.domain import Document, DocumentFragment
from drilling_knowledge.documents.sqlite import SQLiteDocumentRepository
from drilling_knowledge.extraction.engine import KnowledgeExtractionEngine
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.projections.graph import GraphProjector
from drilling_knowledge.projections.search.repositories.contracts import SearchProjectionBatchRepository
from drilling_knowledge.projections.search import EmbeddingProvider, SearchProjector
from drilling_knowledge.reasoning import ExplanationAssembler, ReasoningAppliedRule, ReasoningQuestionType, ReasoningQueryPlanner, ReasoningRequest, StructuredAnswerStatement
from drilling_knowledge.resolution import SemanticResolutionEngine
from drilling_knowledge.review import ReviewDecisionApplier, ReviewPolicyCatalog, ReviewQueueService, ReviewTargetType
from drilling_knowledge.assertions.repositories.contracts import AssertionGenerationRunRepository
from drilling_knowledge.assertions.consolidation.repositories.contracts import FactConsolidationRunRepository
from drilling_knowledge.workflows.domain import (
    PipelineRun,
    PipelineRunStatus,
    PipelineStepRun,
    PipelineStepStatus,
    WorkflowAuditReport,
    WorkflowHumanDecision,
)
from drilling_knowledge.workflows.repositories import InMemoryWorkflowRunRepository


@dataclass(frozen=True, slots=True)
class AcquisitionWorkflowResult:
    pipeline_run: PipelineRun
    audit_report: WorkflowAuditReport
    document: Document
    fragments: tuple[DocumentFragment, ...]
    assertions: tuple[EvidenceAssertion, ...]
    facts: tuple[object, ...]
    review_queue_count: int
    conflict_review_task_count: int
    reasoning_response: object | None
    graph_projection: object | None
    search_projection: object | None

    def as_serializable(self) -> dict[str, object]:
        return {
            "pipeline_run": self.pipeline_run.as_serializable(),
            "audit_report": self.audit_report.as_serializable(),
            "document_id": str(self.document.entity_id),
            "fragment_ids": [str(fragment.entity_id) for fragment in self.fragments],
            "assertion_ids": [str(assertion.assertion_id) for assertion in self.assertions],
            "fact_ids": [str(fact.fact_id) for fact in self.facts],
            "review_queue_count": self.review_queue_count,
            "conflict_review_task_count": self.conflict_review_task_count,
            "reasoning": None if self.reasoning_response is None else self.reasoning_response.as_serializable(),
            "graph_projection": None if self.graph_projection is None else self.graph_projection.as_serializable(),
            "search_projection": None if self.search_projection is None else self.search_projection.as_serializable(),
        }


class Pipeline(Protocol):
    def run(self, *args, **kwargs) -> AcquisitionWorkflowResult:
        ...


class PipelineStep(Protocol):
    def as_serializable(self) -> dict[str, object]:
        ...


@dataclass(slots=True)
class AcquisitionWorkflowOrchestrator:
    catalog_repository: CatalogRepository
    embedding_provider: EmbeddingProvider
    review_policy_catalog: ReviewPolicyCatalog
    repository: InMemoryWorkflowRunRepository
    document_repository: SQLiteDocumentRepository | None = None
    assertion_repository: AssertionGenerationRunRepository | None = None
    fact_repository: FactConsolidationRunRepository | None = None
    search_repository: SearchProjectionBatchRepository | None = None
    pipeline_name: str = "document_to_ikc"
    pipeline_version: str = "workflow.v1"

    @classmethod
    def create(
        cls,
        *,
        catalog_repository: CatalogRepository,
        embedding_provider: EmbeddingProvider,
        review_policy_catalog: ReviewPolicyCatalog,
        repository: InMemoryWorkflowRunRepository | None = None,
        document_repository: SQLiteDocumentRepository | None = None,
        assertion_repository: AssertionGenerationRunRepository | None = None,
        fact_repository: FactConsolidationRunRepository | None = None,
        search_repository: SearchProjectionBatchRepository | None = None,
        pipeline_version: str = "workflow.v1",
    ) -> "AcquisitionWorkflowOrchestrator":
        return cls(
            catalog_repository=catalog_repository,
            embedding_provider=embedding_provider,
            review_policy_catalog=review_policy_catalog,
            repository=repository or InMemoryWorkflowRunRepository.empty(),
            document_repository=document_repository,
            assertion_repository=assertion_repository,
            fact_repository=fact_repository,
            search_repository=search_repository,
            pipeline_version=pipeline_version,
        )

    def run(
        self,
        *,
        document_path: str | Path,
        metadata: DocumentMetadata,
        created_by: str,
        trigger_type: str = "manual",
        human_decisions: tuple[WorkflowHumanDecision, ...] = (),
        require_manual_fact_review: bool = False,
    ) -> AcquisitionWorkflowResult:
        created_by = created_by.strip()
        normalized_decisions = tuple(sorted(human_decisions, key=lambda item: (item.target_type.value, str(item.target_id))))
        document_engine = DocumentKnowledgeAcquisitionEngine.create()
        extraction_engine = KnowledgeExtractionEngine.create()
        normalization_engine = NormalizationEngine.create(self.catalog_repository)
        semantic_engine = SemanticResolutionEngine.create(self.catalog_repository)
        assertion_engine = EvidenceAssertionEngine.create()
        review_queue_service = ReviewQueueService.create(self._review_repository(), self.review_policy_catalog)
        review_applier = ReviewDecisionApplier.create(review_queue_service.repository, self.review_policy_catalog)
        conflict_resolver = AssertionConflictResolver.create()
        consolidator = FactConsolidator.create()
        proposal_generator = OntologyProposalGenerator.create()
        graph_projector = GraphProjector.create()
        search_projector = SearchProjector.create(self.embedding_provider)
        planner = ReasoningQueryPlanner.create()
        assembler = ExplanationAssembler.create()
        step_runs: list[PipelineStepRun] = []
        errors: list[str] = []

        acquisition = document_engine.ingest(document_path, metadata)
        snapshot = acquisition.snapshot
        if self.document_repository is not None:
            self.document_repository.merge(snapshot)
        pipeline_run_id = RunId.from_seed(
            "workflow.pipeline_run",
            "|".join(
                (
                    self.pipeline_name,
                    self.pipeline_version,
                    str(snapshot.version.entity_id),
                    trigger_type.strip().lower(),
                    "|".join(
                        f"{decision.target_type.value}:{decision.target_id}:{decision.action.value}:{decision.reason}:{decision.decided_by}:{decision.decided_at.isoformat()}"
                        for decision in normalized_decisions
                    ),
                )
            ),
        )
        started_at = self._base_timestamp_for(str(pipeline_run_id))
        step_runs.append(
            self._step(
                pipeline_run_id,
                1,
                "document_ingestion",
                created_by,
                input_json=(("document_path", str(document_path)), ("trigger_type", trigger_type.strip().lower())),
                output_json=(("document_id", str(snapshot.document.entity_id)), ("version_id", str(snapshot.version.entity_id)), ("fragment_count", len(snapshot.fragments))),
            )
        )

        extraction_run = extraction_engine.extract(snapshot)
        step_runs.append(
            self._step(
                pipeline_run_id,
                2,
                "extraction",
                created_by,
                input_json=(("fragment_count", len(snapshot.fragments)),),
                output_json=(("entity_count", len(extraction_run.entities)), ("observation_count", len(extraction_run.observations))),
            )
        )
        normalization_run = normalization_engine.normalize(extraction_run)
        step_runs.append(
            self._step(
                pipeline_run_id,
                3,
                "normalization",
                created_by,
                input_json=(("entity_count", len(extraction_run.entities)), ("observation_count", len(extraction_run.observations))),
                output_json=(("entity_candidate_count", len(normalization_run.entity_candidates)), ("relation_candidate_count", len(normalization_run.relation_candidates))),
            )
        )
        semantic_run = semantic_engine.resolve(normalization_run)
        step_runs.append(
            self._step(
                pipeline_run_id,
                4,
                "semantic_resolution",
                created_by,
                input_json=(("entity_candidate_count", len(normalization_run.entity_candidates)),),
                output_json=(("hypothesis_count", len(semantic_run.hypotheses)), ("support_count", len(semantic_run.supports))),
            )
        )
        if self.assertion_repository is None:
            assertion_run = assertion_engine.build(semantic_run)
        else:
            assertion_run, _ = assertion_engine.build_and_persist(semantic_run, self.assertion_repository)
        step_runs.append(
            self._step(
                pipeline_run_id,
                5,
                "assertion_generation",
                created_by,
                input_json=(("hypothesis_count", len(semantic_run.hypotheses)),),
                output_json=(("assertion_count", len(assertion_run.assertions)), ("pending_human_count", sum(1 for assertion in assertion_run.assertions if assertion.review_state == AssertionReviewState.PENDING_HUMAN))),
            )
        )

        step_runs.append(
            self._step(
                pipeline_run_id,
                6,
                "review_pre_consolidation",
                created_by,
                input_json=(("pending_human_count", sum(1 for assertion in assertion_run.assertions if assertion.review_state == AssertionReviewState.PENDING_HUMAN)),),
                output_json=(("applied_decision_count", 0), ("open_review_queue_count", len(review_queue_service.list_open_queues()))),
            )
        )
        assertion_run = replace(assertion_run, assertions=self._promote_consolidable_assertions(assertion_run.assertions))

        conflict_run = conflict_resolver.resolve(assertion_run)
        step_runs.append(
            self._step(
                pipeline_run_id,
                7,
                "conflict_resolution",
                created_by,
                input_json=(("assertion_count", len(assertion_run.assertions)),),
                output_json=(("conflict_set_count", len(conflict_run.conflict_sets)), ("conflict_review_task_count", len(conflict_run.review_queue_items))),
            )
        )

        if self.fact_repository is None:
            fact_run = consolidator.consolidate(assertion_run, conflict_run)
        else:
            fact_run, _ = consolidator.consolidate_and_persist(assertion_run, conflict_run, self.fact_repository)
        step_runs.append(
            self._step(
                pipeline_run_id,
                8,
                "fact_consolidation",
                created_by,
                input_json=(("accepted_assertion_count", sum(1 for assertion in assertion_run.assertions if assertion.status == AssertionStatus.ACCEPTED)),),
                output_json=(("fact_count", len(fact_run.facts)), ("support_count", len(fact_run.support_links))),
            )
        )
        proposal_run = proposal_generator.generate(fact_run, conflict_run, normalization_run=normalization_run)
        step_runs.append(
            self._step(
                pipeline_run_id,
                9,
                "ontology_proposals",
                created_by,
                input_json=(("fact_count", len(fact_run.facts)),),
                output_json=(("proposal_count", len(proposal_run.proposals)), ("proposal_outcome", proposal_run.outcome.value)),
            )
        )

        reviewed_facts = {}
        if require_manual_fact_review:
            for fact in fact_run.facts:
                queue = review_queue_service.create_queue(
                    queue_type="fact_manual_review",
                    target_type=ReviewTargetType.FACT,
                    target_id=fact.fact_id,
                    reference_table="semantic.consolidated_fact",
                    priority=85,
                    review_reason="weak_evidence_only",
                    created_by=created_by,
                    created_at=fact.created_at,
                    provenance=(("pipeline_run_id", str(pipeline_run_id)), ("source", "workflow.fact_review")),
                )
                decision = self._decision_for(normalized_decisions, ReviewTargetType.FACT, fact.fact_id)
                if decision is not None:
                    review_applier.repository = review_queue_service.repository
                    result = review_applier.apply_fact_decision(
                        queue_id=queue.queue_id,
                        fact=fact,
                        action=decision.action,
                        reason=decision.reason,
                        decided_by=decision.decided_by,
                        decided_at=decision.decided_at,
                        provenance=decision.provenance,
                    )
                    review_queue_service.repository = review_applier.repository
                    reviewed_facts[fact.fact_id] = result.updated_fact
        if reviewed_facts:
            fact_run = replace(fact_run, facts=tuple(reviewed_facts.get(fact.fact_id, fact) for fact in fact_run.facts))

        open_review_tasks = len(review_queue_service.list_open_queues()) + len(conflict_run.review_queue_items)
        if open_review_tasks > 0:
            finished_at = started_at + timedelta(seconds=len(step_runs) + 1)
            pipeline_run = PipelineRun(
                pipeline_run_id=pipeline_run_id,
                pipeline_name=self.pipeline_name,
                pipeline_version=self.pipeline_version,
                trigger_type=trigger_type,
                status=PipelineRunStatus.AWAITING_REVIEW,
                input_ref_json=(("document_id", str(snapshot.document.entity_id)), ("document_version_id", str(snapshot.version.entity_id))),
                started_at=started_at,
                finished_at=finished_at,
                created_by=created_by,
                step_runs=tuple(step_runs),
                errors=(),
            )
            self.repository = self.repository.append_run(pipeline_run)
            report = WorkflowAuditReport(
                pipeline_run_id=pipeline_run_id,
                final_status=PipelineRunStatus.AWAITING_REVIEW,
                open_review_tasks=open_review_tasks,
                completed_steps=len(step_runs),
                failed_steps=0,
                errors=(),
            )
            return AcquisitionWorkflowResult(
                pipeline_run=pipeline_run,
                audit_report=report,
                document=snapshot.document,
                fragments=snapshot.fragments,
                assertions=fact_run.assertions,
                facts=fact_run.facts,
                review_queue_count=len(review_queue_service.repository.list_queues()),
                conflict_review_task_count=len(conflict_run.review_queue_items),
                reasoning_response=None,
                graph_projection=None,
                search_projection=None,
            )

        variables = self._variables_for_facts(fact_run.facts)
        reasoning_response = self._reasoning_response(planner, assembler, fact_run)
        step_runs.append(
            self._step(
                pipeline_run_id,
                10,
                "reasoning",
                created_by,
                input_json=(("fact_count", len(fact_run.facts)),),
                output_json=(("has_reasoning_response", reasoning_response is not None),),
            )
        )
        catalog_entities = self._catalog_entities()
        projectable_assertions, projectable_facts = self._graph_projection_inputs(catalog_entities, fact_run.assertions, fact_run.facts)
        graph_projection = graph_projector.project(
            catalog_entities=catalog_entities,
            assertions=projectable_assertions,
            facts=projectable_facts,
        )
        step_runs.append(
            self._step(
                pipeline_run_id,
                11,
                "graph_projection",
                created_by,
                input_json=(("fact_count", len(fact_run.facts)),),
                output_json=(("node_count", len(graph_projection.nodes)), ("relationship_count", len(graph_projection.relationships))),
            )
        )
        search_projection = search_projector.project(
            variables=variables,
            documents=(snapshot.document,),
            fragments=snapshot.fragments,
            assertions=fact_run.assertions,
            facts=fact_run.facts,
        )
        if self.search_repository is not None:
            self.search_repository.append_batch(search_projection)
        step_runs.append(
            self._step(
                pipeline_run_id,
                12,
                "search_projection",
                created_by,
                input_json=(("document_count", 1), ("fragment_count", len(snapshot.fragments))),
                output_json=(("search_document_count", len(search_projection.documents)),),
            )
        )

        final_open_review_tasks = len(review_queue_service.list_open_queues()) + len(conflict_run.review_queue_items)
        final_status = PipelineRunStatus.AWAITING_REVIEW if final_open_review_tasks else PipelineRunStatus.COMPLETED
        finished_at = started_at + timedelta(seconds=len(step_runs) + 1)
        pipeline_run = PipelineRun(
            pipeline_run_id=pipeline_run_id,
            pipeline_name=self.pipeline_name,
            pipeline_version=self.pipeline_version,
            trigger_type=trigger_type,
            status=final_status,
            input_ref_json=(("document_id", str(snapshot.document.entity_id)), ("document_version_id", str(snapshot.version.entity_id))),
            started_at=started_at,
            finished_at=finished_at,
            created_by=created_by,
            step_runs=tuple(step_runs),
            errors=tuple(errors),
        )
        self.repository = self.repository.append_run(pipeline_run)
        report = WorkflowAuditReport(
            pipeline_run_id=pipeline_run_id,
            final_status=final_status,
            open_review_tasks=final_open_review_tasks,
            completed_steps=len([step for step in step_runs if step.status == PipelineStepStatus.COMPLETED]),
            failed_steps=len([step for step in step_runs if step.status == PipelineStepStatus.FAILED]),
            errors=tuple(errors),
        )
        return AcquisitionWorkflowResult(
            pipeline_run=pipeline_run,
            audit_report=report,
            document=snapshot.document,
            fragments=snapshot.fragments,
            assertions=fact_run.assertions,
            facts=fact_run.facts,
            review_queue_count=len(review_queue_service.repository.list_queues()),
            conflict_review_task_count=len(conflict_run.review_queue_items),
            reasoning_response=reasoning_response,
            graph_projection=graph_projection,
            search_projection=search_projection,
        )

    def _review_repository(self):
        from drilling_knowledge.review import InMemoryReviewRepository

        return InMemoryReviewRepository.empty()

    def _step(
        self,
        pipeline_run_id: RunId,
        order: int,
        name: str,
        created_by: str,
        *,
        input_json: tuple[tuple[str, object], ...],
        output_json: tuple[tuple[str, object], ...],
        status: PipelineStepStatus = PipelineStepStatus.COMPLETED,
        error_json: tuple[tuple[str, object], ...] | None = None,
    ) -> PipelineStepRun:
        timestamp = self._base_timestamp_for(str(pipeline_run_id)) + timedelta(seconds=order)
        return PipelineStepRun(
            step_run_id=RunId.from_seed("workflow.pipeline_step", f"{pipeline_run_id}:{order}:{name}"),
            pipeline_run_id=pipeline_run_id,
            step_name=name,
            step_order=order,
            status=status,
            input_json=input_json,
            output_json=output_json,
            error_json=error_json,
            started_at=timestamp,
            finished_at=timestamp,
            created_by=created_by,
        )

    def _decision_for(
        self,
        decisions: tuple[WorkflowHumanDecision, ...],
        target_type: ReviewTargetType,
        target_id: EntityId,
    ) -> WorkflowHumanDecision | None:
        for decision in decisions:
            if decision.target_type == target_type and decision.target_id == target_id:
                return decision
        return None

    def _promote_consolidable_assertions(self, assertions: tuple[EvidenceAssertion, ...]) -> tuple[EvidenceAssertion, ...]:
        promoted = []
        for assertion in assertions:
            if assertion.status == AssertionStatus.SUPPORTED and assertion.review_state in {AssertionReviewState.AUTO, AssertionReviewState.APPROVED}:
                promoted.append(assertion.transition_to(AssertionStatus.ACCEPTED, review_state=assertion.review_state))
                continue
            promoted.append(assertion)
        return tuple(promoted)

    def _base_timestamp_for(self, base_seed: str) -> datetime:
        seed_uuid = UUID(str(RunId.from_seed("workflow.timestamp", base_seed)))
        offset_seconds = seed_uuid.int % (365 * 24 * 60 * 60)
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset_seconds)

    def _variables_for_facts(self, facts: tuple[object, ...]) -> tuple[Variable, ...]:
        variable_ids = {fact.subject_id for fact in facts}
        return tuple(sorted((variable for variable in self.catalog_repository.variables.list_all() if variable.entity_id in variable_ids), key=lambda item: str(item.entity_id)))

    def _catalog_entities(self) -> tuple[KnowledgeEntity, ...]:
        repositories = (
            self.catalog_repository.units,
            self.catalog_repository.quantities,
            self.catalog_repository.principles,
            self.catalog_repository.classifications,
            self.catalog_repository.origins,
            self.catalog_repository.publishers,
            self.catalog_repository.systems,
            self.catalog_repository.subsystems,
            self.catalog_repository.processes,
            self.catalog_repository.operational_contexts,
            self.catalog_repository.locations,
            self.catalog_repository.sensors,
            self.catalog_repository.instruments,
            self.catalog_repository.equipment,
            self.catalog_repository.variables,
        )
        entities = []
        for repository in repositories:
            entities.extend(repository.list_all())
        return tuple(sorted(entities, key=lambda entity: str(entity.entity_id)))

    def _graph_projection_inputs(
        self,
        catalog_entities: tuple[KnowledgeEntity, ...],
        assertions: tuple[EvidenceAssertion, ...],
        facts: tuple[object, ...],
    ) -> tuple[tuple[EvidenceAssertion, ...], tuple[object, ...]]:
        catalog_ids = {entity.entity_id for entity in catalog_entities}
        projectable_assertions = tuple(
            assertion
            for assertion in assertions
            if assertion.subject_id in catalog_ids and (assertion.object_id is None or assertion.object_id in catalog_ids)
        )
        projectable_facts = tuple(
            fact
            for fact in facts
            if fact.subject_id in catalog_ids and (fact.object_id is None or fact.object_id in catalog_ids)
        )
        return projectable_assertions, projectable_facts

    def _reasoning_response(self, planner: ReasoningQueryPlanner, assembler: ExplanationAssembler, fact_run) -> object | None:
        active_facts = tuple(fact for fact in fact_run.facts if fact.active_revision)
        if not active_facts:
            return None
        target_fact = active_facts[0]
        request = ReasoningRequest(
            target_entity_id=target_fact.subject_id,
            question_type=ReasoningQuestionType.CLASSIFICATION_JUSTIFICATION,
            context_scope=target_fact.scope,
            requested_confidence_threshold=0.5,
        )
        plan = planner.build_plan(request)
        return assembler.assemble(
            plan,
            answer_statement=StructuredAnswerStatement(
                statement_text=f"{target_fact.claim_key} remains supported by consolidated evidence.",
                answer_kind="justification",
                target_entity_id=target_fact.subject_id,
            ),
            supporting_facts=(target_fact,),
            supporting_assertions=fact_run.assertions,
            supporting_fragments=fact_run.evidence_links,
            applied_rules=(ReasoningAppliedRule(rule_code="WF-REASON-001", rule_summary="Workflow summary from consolidated evidence", rule_priority=1),),
            confidence=1.0,
        )

    @staticmethod
    def _proposal_review_reason(proposal_type: str) -> str:
        mapping = {
            "recurring_pattern": "new_canonical_variable_concept",
            "recurring_conflict": "hierarchy_semantic_change",
            "repeated_manual_decision": "alias_collision",
        }
        return mapping.get(proposal_type, "new_subsystem_or_process_concept")