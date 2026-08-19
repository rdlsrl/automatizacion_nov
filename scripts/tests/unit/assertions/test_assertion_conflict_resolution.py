from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions import (
    AssertionConflictResolver,
    AssertionGenerationRun,
    AssertionReviewState,
    AssertionStatus,
    ConflictDecisionType,
    ConflictMemberRole,
    EvidenceAssertionEngine,
)
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import SemanticResolutionEngine


class AssertionConflictResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.semantic_engine = SemanticResolutionEngine.create(self.catalog)
        self.assertion_engine = EvidenceAssertionEngine.create()
        self.resolver = AssertionConflictResolver.create()

    def test_groups_conflicting_assertions_by_claim_key(self) -> None:
        run = self._assertion_run(
            self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1"),
            self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1"),
            run_seed="same-scope-conflict",
        )

        result = self.resolver.resolve(run)

        self.assertEqual(len(result.conflict_sets), 1)
        conflict_set = result.conflict_sets[0]
        self.assertEqual(conflict_set.claim_key, "explicit_scaling:4:mA:PSI")
        self.assertEqual(conflict_set.scope_key, str(EntityId.from_seed("assertions.conflict.document", "doc-1")))
        self.assertEqual(conflict_set.decision_type, ConflictDecisionType.REVIEW_REQUIRED)
        self.assertTrue(conflict_set.requires_human_review)
        self.assertEqual(len(conflict_set.members), 2)

    def test_splits_conflicts_by_document_version_context(self) -> None:
        run = self._assertion_run(
            self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1"),
            self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v2"),
            run_seed="split-contexts",
        )

        result = self.resolver.resolve(run)

        self.assertEqual(result.conflict_sets[0].decision_type, ConflictDecisionType.COEXISTENCE_SPLIT)
        self.assertEqual(result.conflict_sets[0].status.value, "closed")
        self.assertEqual(len(result.conflict_sets[0].contexts), 2)
        self.assertEqual(result.review_queue_items, ())

    def test_does_not_group_corroborating_assertions(self) -> None:
        assertion = self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1")
        corroborating = replace(
            assertion,
            assertion_id=EntityId.from_seed("assertions.conflict.assertion", "corroborating"),
            evidence_link_ids=tuple(EntityId.from_seed("assertions.conflict.link", f"corroborating:{index}") for index, _ in enumerate(assertion.evidence_link_ids, start=1)),
        )
        run = AssertionGenerationRun(
            run_id=RunId.from_seed("assertions.conflict.run", "corroborating"),
            semantic_run_id=RunId.from_seed("assertions.semantic.run", "corroborating"),
            rule_pack_version="assertion.rules.v1",
            threshold=0.5,
            started_at=assertion.created_at,
            finished_at=assertion.created_at,
            assertions=(assertion, corroborating),
            evidence_links=(),
            validation_logs=(),
            errors=(),
        )

        result = self.resolver.resolve(run)

        self.assertEqual(result.conflict_sets, ())

    def test_resolution_is_idempotent_and_deterministic(self) -> None:
        run = self._assertion_run(
            self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1"),
            self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1"),
            run_seed="same-input",
        )

        first = self.resolver.resolve(run)
        second = self.resolver.resolve(run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.conflict_sets, second.conflict_sets)
        self.assertEqual(first.members, second.members)
        self.assertEqual(first.contexts, second.contexts)
        self.assertEqual(first.review_queue_items, second.review_queue_items)
        self.assertEqual(first.evidence_links, second.evidence_links)

    def test_accepts_current_accepted_member_deterministically(self) -> None:
        accepted = self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        supported = self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1")

        result = self.resolver.resolve(self._assertion_run(accepted, supported, run_seed="accepted-member"))

        conflict_set = result.conflict_sets[0]
        self.assertEqual(conflict_set.decision_type, ConflictDecisionType.ACCEPTED_MEMBER)
        self.assertEqual(len([member for member in conflict_set.members if member.member_role == ConflictMemberRole.ACCEPTED_MEMBER]), 1)
        self.assertEqual(len([member for member in conflict_set.members if member.member_role == ConflictMemberRole.REJECTED_MEMBER]), 1)

    def test_rejects_current_member_against_existing_accepted_assertion(self) -> None:
        current = self._assertion_run(
            self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1"),
            run_seed="rejected-current",
        )
        existing = (self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED),)

        result = self.resolver.resolve(current, existing_assertions=existing)

        conflict_set = result.conflict_sets[0]
        self.assertEqual(conflict_set.decision_type, ConflictDecisionType.REJECTED_MEMBER)
        self.assertEqual(len([member for member in conflict_set.members if member.member_role == ConflictMemberRole.REJECTED_MEMBER]), 1)

    def test_existing_active_assertions_are_included_in_detection(self) -> None:
        run = self._single_assertion_run("4 mA = 0 psi", version_seed="v1")
        existing = (self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1"),)

        result = self.resolver.resolve(run, existing_assertions=existing)

        self.assertEqual(len(result.conflict_sets), 1)

    def test_multiple_scopes_split_into_independent_contexts(self) -> None:
        run = self._assertion_run(
            self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1"),
            self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v2"),
            self._atomic_scaling_assertion("4 mA = 20 psi", version_seed="v3"),
            run_seed="three-contexts",
        )

        result = self.resolver.resolve(run)

        self.assertEqual(len(result.conflict_sets[0].contexts), 3)

    def test_reversed_input_order_produces_same_result(self) -> None:
        first_assertion = self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1")
        second_assertion = self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1")
        forward = self._assertion_run(first_assertion, second_assertion, run_seed="forward")
        reverse = self._assertion_run(second_assertion, first_assertion, run_seed="reverse")

        forward_result = self.resolver.resolve(forward)
        reverse_result = self.resolver.resolve(reverse)

        self.assertEqual(forward_result.conflict_sets, reverse_result.conflict_sets)
        self.assertEqual(forward_result.members, reverse_result.members)
        self.assertEqual(forward_result.contexts, reverse_result.contexts)
        self.assertEqual(forward_result.review_queue_items, reverse_result.review_queue_items)
        self.assertEqual(forward_result.evidence_links, reverse_result.evidence_links)

    def test_review_required_preserves_full_evidence_chain(self) -> None:
        run = self._assertion_run(
            self._atomic_scaling_assertion("4 mA = 0 psi", version_seed="v1"),
            self._atomic_scaling_assertion("4 mA = 10 psi", version_seed="v1"),
            run_seed="review-trace",
        )

        result = self.resolver.resolve(run)

        review_item = result.review_queue_items[0]
        conflict_set = next(item for item in result.conflict_sets if item.conflict_set_id == review_item.conflict_set_id)
        persisted_link_ids = {link.link_id for link in result.evidence_links}
        for member in conflict_set.members:
            self.assertTrue(set(member.source_assertion.evidence_link_ids).issubset(persisted_link_ids))
            self.assertTrue(member.source_assertion.source_supports)

    def _single_assertion_run(self, original_text: str, *, version_seed: str) -> AssertionGenerationRun:
        assertion = self._atomic_scaling_assertion(original_text, version_seed=version_seed)
        return self._assertion_run(assertion, run_seed=original_text)

    def _assertion_run(self, *assertions, run_seed: str) -> AssertionGenerationRun:
        created_at = assertions[0].created_at
        return AssertionGenerationRun(
            run_id=RunId.from_seed("assertions.conflict.run", run_seed),
            semantic_run_id=RunId.from_seed("assertions.semantic.run", run_seed),
            rule_pack_version="assertion.rules.v1",
            threshold=0.5,
            started_at=created_at,
            finished_at=created_at,
            assertions=tuple(assertions),
            evidence_links=(),
            validation_logs=(),
            errors=(),
        )

    def _atomic_scaling_assertion(self, original_text: str, *, version_seed: str, status: AssertionStatus = AssertionStatus.SUPPORTED):
        extraction_run = self._extraction_run(original_text, version_seed=version_seed)
        normalization_run = self.normalization_engine.normalize(extraction_run)
        semantic_run = self.semantic_engine.resolve(normalization_run)
        assertion = next(item for item in self.assertion_engine.build(semantic_run).assertions if item.predicate_code == "explicit_scaling")
        return replace(assertion, status=status, review_state=AssertionReviewState.AUTO)

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.conflict.unit", "psi"),
                        code=CatalogCode("psi"),
                        names=LocalizedName("PSI"),
                        description="Pressure unit.",
                        scope=scope,
                        symbol="psi",
                        dimension_code="pressure",
                    ),
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.conflict.unit", "ma"),
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
                        entity_id=EntityId.from_seed("assertions.conflict.quantity", "pressure"),
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
                        entity_id=EntityId.from_seed("assertions.conflict.compatibility", "pressure.psi"),
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
                        entity_id=EntityId.from_seed("assertions.conflict.variable", "standpipe_pressure"),
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
            observation_id=EntityId.from_seed("assertions.conflict.observation", f"{text}:{version_seed}"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text=text,
            normalized_text=text.lower(),
            document_position="fragment=atomic|page=1|section=section-1|paragraph=1|span=0:12",
            fragment_id=EntityId.from_seed("assertions.conflict.fragment", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("assertions.conflict.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.conflict.version", version_seed),
            extraction_confidence=1.0,
            extraction_rule="assertions.conflict.scaling",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=len(text)),
            context_window=ContextWindow(match_text=text),
            attributes=(("raw_value", raw_value), ("raw_unit", raw_unit), ("engineering_value", engineering_value), ("engineering_unit", engineering_unit)),
        )
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("assertions.conflict.extraction", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("assertions.conflict.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.conflict.version", version_seed),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=(),
            observations=(observation,),
            metrics=ExtractionMetrics(total_entities=0, entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )