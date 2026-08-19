from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions import (
    AssertionConflictResolver,
    AssertionGenerationRun,
    AssertionReviewState,
    AssertionStatus,
    ConflictResolutionRun,
    EvidenceAssertionEngine,
    InMemoryConflictResolutionRunRepository,
)
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import SemanticResolutionEngine


class AssertionConflictResolutionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.semantic_engine = SemanticResolutionEngine.create(self.catalog)
        self.assertion_engine = EvidenceAssertionEngine.create()
        self.resolver = AssertionConflictResolver.create()

    def test_save_get_and_full_recovery(self) -> None:
        run = self._conflict_run(same_version=True)
        repository = InMemoryConflictResolutionRunRepository().append_run(run)

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.list_conflict_sets(run.run_id), run.conflict_sets)
        self.assertEqual(repository.list_members(run.run_id), run.members)
        self.assertEqual(repository.list_contexts(run.run_id), run.contexts)
        self.assertEqual(repository.list_review_queue_items(run.run_id), run.review_queue_items)
        self.assertEqual(repository.list_evidence_links(run.run_id), run.evidence_links)

    def test_idempotent_append_for_same_run(self) -> None:
        run = self._conflict_run(same_version=True)
        repository = InMemoryConflictResolutionRunRepository().append_run(run)

        self.assertIs(repository.append_run(run), repository)

    def test_invalid_collision_is_rejected(self) -> None:
        run = self._conflict_run(same_version=True)
        conflicting = ConflictResolutionRun(
            run_id=run.run_id,
            assertion_run_id=RunId.from_seed("assertions.conflict.assertion_run", "other"),
            rule_pack_version=run.rule_pack_version,
            started_at=run.started_at,
            finished_at=run.finished_at,
            conflict_sets=run.conflict_sets,
            members=run.members,
            contexts=run.contexts,
            review_queue_items=run.review_queue_items,
            evidence_links=run.evidence_links,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryConflictResolutionRunRepository((run, conflicting))

    def test_referential_integrity_is_enforced(self) -> None:
        run = self._conflict_run(same_version=True)
        bad_member = replace(run.members[0], conflict_set_id=EntityId.from_seed("assertions.conflict.set", "missing"))
        bad_run = ConflictResolutionRun(
            run_id=run.run_id,
            assertion_run_id=run.assertion_run_id,
            rule_pack_version=run.rule_pack_version,
            started_at=run.started_at,
            finished_at=run.finished_at,
            conflict_sets=run.conflict_sets,
            members=(bad_member, *run.members[1:]),
            contexts=run.contexts,
            review_queue_items=run.review_queue_items,
            evidence_links=run.evidence_links,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryConflictResolutionRunRepository((bad_run,))

    def test_recovery_requires_full_evidence_chain(self) -> None:
        run = self._conflict_run(same_version=True)
        bad_run = ConflictResolutionRun(
            run_id=run.run_id,
            assertion_run_id=run.assertion_run_id,
            rule_pack_version=run.rule_pack_version,
            started_at=run.started_at,
            finished_at=run.finished_at,
            conflict_sets=run.conflict_sets,
            members=run.members,
            contexts=run.contexts,
            review_queue_items=run.review_queue_items,
            evidence_links=run.evidence_links[1:],
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryConflictResolutionRunRepository((bad_run,))

    def _conflict_run(self, *, same_version: bool) -> ConflictResolutionRun:
        first = self._assertion("4 mA = 0 psi", version_seed="v1")
        second = self._assertion("4 mA = 10 psi", version_seed="v1" if same_version else "v2")
        assertion_run = AssertionGenerationRun(
            run_id=RunId.from_seed("assertions.conflict.assertion_run", f"{same_version}"),
            semantic_run_id=RunId.from_seed("assertions.conflict.semantic_run", f"{same_version}"),
            rule_pack_version="assertion.rules.v1",
            threshold=0.5,
            started_at=first.created_at,
            finished_at=first.created_at,
            assertions=(first, second),
            evidence_links=(),
            validation_logs=(),
            errors=(),
        )
        return self.resolver.resolve(assertion_run)

    def _assertion(self, text: str, *, version_seed: str):
        run = self._extraction_run(text, version_seed=version_seed)
        normalization_run = self.normalization_engine.normalize(run)
        semantic_run = self.semantic_engine.resolve(normalization_run)
        assertion = next(item for item in self.assertion_engine.build(semantic_run).assertions if item.predicate_code == "explicit_scaling")
        return replace(assertion, status=AssertionStatus.SUPPORTED, review_state=AssertionReviewState.AUTO)

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.contract.conflict.unit", "psi"),
                        code=CatalogCode("psi"),
                        names=LocalizedName("PSI"),
                        description="Pressure unit.",
                        scope=scope,
                        symbol="psi",
                        dimension_code="pressure",
                    ),
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.contract.conflict.unit", "ma"),
                        code=CatalogCode("ma"),
                        names=LocalizedName("mA"),
                        description="Current unit.",
                        scope=scope,
                        symbol="mA",
                        dimension_code="current",
                    ),
                )
            ),
            quantities=InMemoryEntityRepository(
                (
                    PhysicalQuantity(
                        entity_id=EntityId.from_seed("assertions.contract.conflict.quantity", "pressure"),
                        code=CatalogCode("pressure"),
                        names=LocalizedName("Pressure"),
                        description="Pressure quantity.",
                        scope=scope,
                        quantity_family="hydraulic",
                        dimension_code="pressure",
                        canonical_unit_code=CatalogCode("psi"),
                    ),
                )
            ),
            principles=InMemoryEntityRepository(()),
            quantity_unit_compatibilities=InMemoryEntityRepository(
                (
                    QuantityUnitCompatibility(
                        entity_id=EntityId.from_seed("assertions.contract.conflict.compatibility", "pressure.psi"),
                        code=CatalogCode("pressure.psi"),
                        names=LocalizedName("pressure to psi"),
                        description="Allowed pressure to psi.",
                        scope=scope,
                        quantity_code=CatalogCode("pressure"),
                        unit_code=CatalogCode("psi"),
                    ),
                )
            ),
            classifications=InMemoryEntityRepository(()),
            origins=InMemoryEntityRepository(()),
            publishers=InMemoryEntityRepository(()),
            systems=InMemoryEntityRepository(()),
            subsystems=InMemoryEntityRepository(()),
            processes=InMemoryEntityRepository(()),
            operational_contexts=InMemoryEntityRepository(()),
            locations=InMemoryEntityRepository(()),
            sensors=InMemoryEntityRepository(()),
            instruments=InMemoryEntityRepository(()),
            equipment=InMemoryEntityRepository(()),
            variables=InMemoryEntityRepository(
                (
                    Variable(
                        entity_id=EntityId.from_seed("assertions.contract.conflict.variable", "standpipe_pressure"),
                        code=CatalogCode("standpipe_pressure"),
                        names=LocalizedName("Standpipe Pressure"),
                        description="Standpipe pressure variable.",
                        scope=scope,
                        physical_quantity_code=CatalogCode("pressure"),
                        canonical_unit_code=CatalogCode("psi"),
                    ),
                )
            ),
        )

    def _extraction_run(self, text: str, *, version_seed: str) -> ExtractionRun:
        left, right = [part.strip() for part in text.split("=")]
        raw_value, raw_unit = left.split()
        engineering_value, engineering_unit = right.split()
        observation = ExtractedObservation(
            observation_id=EntityId.from_seed("assertions.contract.conflict.observation", f"{text}:{version_seed}"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text=text,
            normalized_text=text.lower(),
            document_position="fragment=atomic|page=1|section=section-1|paragraph=1|span=0:12",
            fragment_id=EntityId.from_seed("assertions.contract.conflict.fragment", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("assertions.contract.conflict.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.contract.conflict.version", version_seed),
            extraction_confidence=1.0,
            extraction_rule="assertions.contract.conflict.scaling",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=len(text)),
            context_window=ContextWindow(match_text=text),
            attributes=(("raw_value", raw_value), ("raw_unit", raw_unit), ("engineering_value", engineering_value), ("engineering_unit", engineering_unit)),
        )
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("assertions.contract.conflict.extraction", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("assertions.contract.conflict.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.contract.conflict.version", version_seed),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=(),
            observations=(observation,),
            metrics=ExtractionMetrics(total_entities=0, entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )