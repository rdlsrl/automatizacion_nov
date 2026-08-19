from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions import AssertionGenerationRun, EvidenceAssertionEngine, InMemoryAssertionGenerationRunRepository
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import SemanticResolutionEngine


class EvidenceAssertionEngineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.semantic_engine = SemanticResolutionEngine.create(self.catalog)
        self.engine = EvidenceAssertionEngine.create()

    def test_save_get_and_full_recovery(self) -> None:
        run = self._assertion_run()
        repository = InMemoryAssertionGenerationRunRepository().append_run(run)

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.list_assertions(run.run_id), run.assertions)
        self.assertEqual(repository.list_evidence_links(run.run_id), run.evidence_links)
        self.assertEqual(repository.list_validation_logs(run.run_id), run.validation_logs)

    def test_idempotent_append_for_same_run(self) -> None:
        run = self._assertion_run()
        repository = InMemoryAssertionGenerationRunRepository().append_run(run)

        self.assertIs(repository.append_run(run), repository)

    def test_invalid_collision_is_rejected(self) -> None:
        run = self._assertion_run()
        conflicting = self.engine.build(self._semantic_run(rule_pack_version="semantic.rules.v2"))
        conflicting = AssertionGenerationRun(
            run_id=run.run_id,
            semantic_run_id=conflicting.semantic_run_id,
            rule_pack_version=conflicting.rule_pack_version,
            threshold=conflicting.threshold,
            started_at=conflicting.started_at,
            finished_at=conflicting.finished_at,
            assertions=conflicting.assertions,
            evidence_links=conflicting.evidence_links,
            validation_logs=conflicting.validation_logs,
            errors=conflicting.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryAssertionGenerationRunRepository((run, conflicting))

    def test_referential_integrity_rejects_unknown_support_id(self) -> None:
        run = self._assertion_run()
        bad_link = replace(run.evidence_links[0], support_id=EntityId.from_seed("bad.support", "missing"))
        bad_run = AssertionGenerationRun(
            run_id=run.run_id,
            semantic_run_id=run.semantic_run_id,
            rule_pack_version=run.rule_pack_version,
            threshold=run.threshold,
            started_at=run.started_at,
            finished_at=run.finished_at,
            assertions=run.assertions,
            evidence_links=(bad_link,),
            validation_logs=run.validation_logs,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryAssertionGenerationRunRepository((bad_run,))

    def test_persistence_requires_complete_link_integrity(self) -> None:
        run = self._assertion_run()
        with self.assertRaises(ValueError):
            broken_assertion = replace(run.assertions[0], evidence_link_ids=())
            AssertionGenerationRun(
                run_id=run.run_id,
                semantic_run_id=run.semantic_run_id,
                rule_pack_version=run.rule_pack_version,
                threshold=run.threshold,
                started_at=run.started_at,
                finished_at=run.finished_at,
                assertions=(broken_assertion,),
                evidence_links=run.evidence_links,
                validation_logs=run.validation_logs,
                errors=run.errors,
            )

    def test_repository_rejects_manual_provenance_overwrite(self) -> None:
        run = self._assertion_run()
        bad_link = replace(
            run.evidence_links[0],
            document_id=EntityId.from_seed("assertions.contract.document", "other-doc"),
        )
        bad_run = AssertionGenerationRun(
            run_id=run.run_id,
            semantic_run_id=run.semantic_run_id,
            rule_pack_version=run.rule_pack_version,
            threshold=run.threshold,
            started_at=run.started_at,
            finished_at=run.finished_at,
            assertions=run.assertions,
            evidence_links=(bad_link, *run.evidence_links[1:]),
            validation_logs=run.validation_logs,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryAssertionGenerationRunRepository((bad_run,))

    def test_repository_rejects_duplicate_support_links(self) -> None:
        run = self._assertion_run()
        duplicate_support_link = replace(
            run.evidence_links[1],
            support_id=run.evidence_links[0].support_id,
            link_id=EntityId.from_seed("assertions.contract.link", "duplicate-support"),
        )
        bad_run = AssertionGenerationRun(
            run_id=run.run_id,
            semantic_run_id=run.semantic_run_id,
            rule_pack_version=run.rule_pack_version,
            threshold=run.threshold,
            started_at=run.started_at,
            finished_at=run.finished_at,
            assertions=run.assertions,
            evidence_links=(run.evidence_links[0], duplicate_support_link),
            validation_logs=run.validation_logs,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryAssertionGenerationRunRepository((bad_run,))

    def test_repository_rejects_supersession_cycle(self) -> None:
        run = self._assertion_run()
        first, second = run.assertions[0], replace(
            run.assertions[0],
            assertion_id=EntityId.from_seed("assertions.contract.assertion", "second"),
            evidence_link_ids=(EntityId.from_seed("assertions.contract.link", "second-candidate"), EntityId.from_seed("assertions.contract.link", "second-rule")),
        )
        first_link_a, first_link_b = run.evidence_links
        second_links = (
            replace(first_link_a, link_id=second.evidence_link_ids[0], assertion_id=second.assertion_id),
            replace(first_link_b, link_id=second.evidence_link_ids[1], assertion_id=second.assertion_id),
        )
        cycle_run = AssertionGenerationRun(
            run_id=RunId.from_seed("assertions.contract.run", "cycle"),
            semantic_run_id=run.semantic_run_id,
            rule_pack_version=run.rule_pack_version,
            threshold=run.threshold,
            started_at=run.started_at,
            finished_at=run.finished_at,
            assertions=(
                replace(first, status=first.status.SUPERSEDED, supersedes_id=second.assertion_id),
                replace(second, status=second.status.SUPERSEDED, supersedes_id=first.assertion_id),
            ),
            evidence_links=(first_link_a, first_link_b, *second_links),
            validation_logs=run.validation_logs,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            InMemoryAssertionGenerationRunRepository((cycle_run,))

    def test_failed_append_does_not_partially_persist(self) -> None:
        repository = InMemoryAssertionGenerationRunRepository()
        run = self._assertion_run()
        bad_link = replace(run.evidence_links[0], support_id=EntityId.from_seed("bad.support", "missing"))
        bad_run = AssertionGenerationRun(
            run_id=run.run_id,
            semantic_run_id=run.semantic_run_id,
            rule_pack_version=run.rule_pack_version,
            threshold=run.threshold,
            started_at=run.started_at,
            finished_at=run.finished_at,
            assertions=run.assertions,
            evidence_links=(bad_link, *run.evidence_links[1:]),
            validation_logs=run.validation_logs,
            errors=run.errors,
        )

        with self.assertRaises(ConflictError):
            repository.append_run(bad_run)

        self.assertEqual(repository.list_runs(), ())

    def _assertion_run(self) -> AssertionGenerationRun:
        return self.engine.build(self._semantic_run())

    def _semantic_run(self, *, rule_pack_version: str = "semantic.rules.v1"):
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        extraction_run = self._extraction_run((mention,))
        normalization_run = self.normalization_engine.normalize(extraction_run)
        return SemanticResolutionEngine.create(self.catalog, rule_pack_version=rule_pack_version).resolve(normalization_run)

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.contract.unit", "psi"),
                        code=CatalogCode("psi"),
                        names=LocalizedName("PSI"),
                        description="Pressure unit.",
                        scope=scope,
                        symbol="psi",
                        dimension_code="pressure",
                    ),
                )
            ),
            quantities=InMemoryEntityRepository(
                (
                    PhysicalQuantity(
                        entity_id=EntityId.from_seed("assertions.contract.quantity", "pressure"),
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
                        entity_id=EntityId.from_seed("assertions.contract.compatibility", "pressure.psi"),
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
                        entity_id=EntityId.from_seed("assertions.contract.variable", "standpipe_pressure"),
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

    def _mention(self, text: str, entity_type: ExtractedEntityType) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("assertions.contract.mention", f"{entity_type.value}:{text}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=text.lower(),
            document_position="fragment=fragment-1|page=1|section=section-1|paragraph=1|span=0:8",
            fragment_id=EntityId.from_seed("assertions.contract.fragment", "fragment-1"),
            document_id=EntityId.from_seed("assertions.contract.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.contract.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="assertions.contract.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _extraction_run(self, mentions: tuple[ExtractedEntity, ...]) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("assertions.contract.extraction", "run-1"),
            document_id=EntityId.from_seed("assertions.contract.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.contract.version", "ver-1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=mentions,
            observations=(),
            metrics=ExtractionMetrics(total_entities=len(mentions), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )