from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import math
import unittest

from drilling_knowledge.assertions import AssertionEvidenceLink, AssertionReviewState, AssertionStatus, EvidenceAssertionEngine, InMemoryAssertionGenerationRunRepository
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import SemanticResolutionEngine
from drilling_knowledge.resolution.domain import HypothesisSupport, HypothesisSupportKind, SemanticHypothesis, SemanticHypothesisStatus, SemanticResolutionRun


class EvidenceAssertionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.semantic_engine = SemanticResolutionEngine.create(self.catalog)
        self.engine = EvidenceAssertionEngine.create()

    def test_builds_multiple_evidence_links_from_supported_entity_hypothesis(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self._semantic_run((mention,), ())

        result = self.engine.build(semantic_run)

        assertion = result.assertions[0]
        self.assertEqual(assertion.status, AssertionStatus.SUPPORTED)
        self.assertEqual(assertion.review_state, AssertionReviewState.AUTO)
        self.assertEqual(assertion.predicate_code, "denotes_catalog_entity")
        self.assertEqual(len(assertion.source_supports), 2)
        self.assertEqual(len(result.evidence_links), 2)
        self.assertEqual({link.link_id for link in result.evidence_links}, set(assertion.evidence_link_ids))
        self.assertTrue(all(link.fragment_id == mention.fragment_id for link in result.evidence_links))
        self.assertEqual(result.evidence_links, tuple(sorted(result.evidence_links, key=lambda link: (str(link.assertion_id), str(link.link_id)))))

    def test_ids_and_provenance_are_idempotent_for_same_assertion(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self._semantic_run((mention,), ())

        first = self.engine.build(semantic_run)
        second = self.engine.build(semantic_run)

        self.assertEqual(first.assertions[0].assertion_id, second.assertions[0].assertion_id)
        self.assertEqual(first.assertions[0].status, second.assertions[0].status)
        self.assertEqual(first.assertions[0].evidence_link_ids, second.assertions[0].evidence_link_ids)
        self.assertEqual(first.assertions[0].source_supports, second.assertions[0].source_supports)
        self.assertEqual(first.evidence_links, second.evidence_links)
        self.assertEqual(first.evidence_links[0].document_id, second.evidence_links[0].document_id)

    def test_rejects_assertion_link_without_document_id(self) -> None:
        with self.assertRaises(ValueError):
            self._assertion_link(document_id=None)

    def test_rejects_assertion_link_without_document_version_id(self) -> None:
        with self.assertRaises(ValueError):
            self._assertion_link(document_version_id=None)

    def test_rejects_assertion_link_without_fragment_id(self) -> None:
        with self.assertRaises(ValueError):
            self._assertion_link(fragment_id=None)

    def test_rejects_duplicate_evidence_link_ids(self) -> None:
        built = self.engine.build(self._semantic_run((self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY),), ())).assertions[0]

        with self.assertRaises(ValueError):
            replace(built, evidence_link_ids=(built.evidence_link_ids[0], built.evidence_link_ids[0]))

    def test_rejects_candidate_evidence_without_weight(self) -> None:
        with self.assertRaises(ValueError):
            self._assertion_link(weight=None)

    def test_rejects_invalid_link_weights(self) -> None:
        for invalid_weight in (-0.1, math.nan, math.inf):
            with self.subTest(invalid_weight=invalid_weight):
                with self.assertRaises(ValueError):
                    self._assertion_link(weight=invalid_weight)

    def test_explicit_scaling_linear_simple_becomes_supported(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("4 mA = 0 psi", "4", "mA", "0", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.SUPPORTED)
        self.assertEqual(assertion.review_state, AssertionReviewState.AUTO)

    def test_explicit_scaling_inverted_becomes_supported(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("20 mA = 0 psi", "20", "mA", "0", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.SUPPORTED)

    def test_explicit_scaling_offset_becomes_supported(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("12 mA = 150 psi", "12", "mA", "150", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.SUPPORTED)

    def test_explicit_scaling_incompatible_units_require_review(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("1000 psi = 68.95 psi", "1000", "psi", "68.95", "psi", normalized_raw_unit_code="psi", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.CANDIDATE)
        self.assertEqual(assertion.review_state, AssertionReviewState.PENDING_HUMAN)

    def test_explicit_scaling_composite_is_queued_for_review(self) -> None:
        semantic_run = self._composite_scaling_semantic_run()

        result = self.engine.build(semantic_run)

        assertion = result.assertions[0]
        self.assertEqual(assertion.status, AssertionStatus.CANDIDATE)
        self.assertEqual(assertion.review_state, AssertionReviewState.PENDING_HUMAN)
        self.assertIn("composite_fact_requires_review", assertion.reason_codes)

    def test_explicit_scaling_table_of_calibration_is_queued_for_review(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("table: 4 mA = 0 psi; 20 mA = 300 psi", "4", "mA", "0", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.CANDIDATE)
        self.assertEqual(assertion.review_state, AssertionReviewState.PENDING_HUMAN)

    def test_explicit_scaling_multiple_entries_is_queued_for_review(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("4 mA = 0 psi, 20 mA = 300 psi", "4", "mA", "0", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.CANDIDATE)
        self.assertEqual(assertion.review_state, AssertionReviewState.PENDING_HUMAN)

    def test_explicit_scaling_formula_is_queued_for_review(self) -> None:
        assertion = self.engine.build(self._atomic_scaling_semantic_run("formula: 4 mA = 0 psi", "4", "mA", "0", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi")).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.CANDIDATE)
        self.assertEqual(assertion.review_state, AssertionReviewState.PENDING_HUMAN)

    def test_negative_support_prevents_automatic_support(self) -> None:
        semantic_run = self._atomic_scaling_semantic_run("4 mA = 0 psi", "4", "mA", "0", "psi", normalized_raw_unit_code="ma", normalized_engineering_unit_code="psi", include_negative_support=True)

        assertion = self.engine.build(semantic_run).assertions[0]

        self.assertEqual(assertion.status, AssertionStatus.CANDIDATE)
        self.assertEqual(assertion.review_state, AssertionReviewState.PENDING_HUMAN)
        self.assertIn("conflicting_evidence_roles", assertion.reason_codes)

    def test_build_and_persist_round_trips_end_to_end(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self._semantic_run((mention,), ())

        run, repository = self.engine.build_and_persist(semantic_run, InMemoryAssertionGenerationRunRepository())

        self.assertEqual(repository.get_run(run.run_id), run)
        self.assertEqual(repository.list_assertions(run.run_id), run.assertions)
        self.assertEqual(repository.list_evidence_links(run.run_id), run.evidence_links)
        self.assertEqual(repository.list_validation_logs(run.run_id), run.validation_logs)

    def test_build_is_idempotent_for_same_semantic_run(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self._semantic_run((mention,), ())

        first = self.engine.build(semantic_run)
        second = self.engine.build(semantic_run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.assertions, second.assertions)
        self.assertEqual(first.evidence_links, second.evidence_links)

    def test_builder_preserves_input_immutability(self) -> None:
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self._semantic_run((mention,), ())
        original_hypothesis = semantic_run.hypotheses[0]
        original_supports = semantic_run.supports

        result = self.engine.build(semantic_run)

        self.assertIs(result.assertions[0].source_hypothesis, original_hypothesis)
        self.assertEqual(semantic_run.hypotheses[0], original_hypothesis)
        self.assertEqual(semantic_run.supports, original_supports)
        self.assertEqual(result.assertions[0].source_supports, original_supports)

    def test_allows_valid_lifecycle_transitions(self) -> None:
        assertion = self._candidate_assertion()

        supported = assertion.transition_to(AssertionStatus.SUPPORTED)
        accepted = supported.transition_to(AssertionStatus.ACCEPTED)
        superseded = accepted.transition_to(
            AssertionStatus.SUPERSEDED,
            supersedes_id=EntityId.from_seed("assertions.supersedes", "prior"),
            reason_code="replacement_published",
        )
        invalidated = accepted.transition_to(
            AssertionStatus.INVALIDATED,
            invalidates_id=EntityId.from_seed("assertions.invalidates", "rule-failed"),
            reason_code="invalidated_by_review",
        )

        self.assertEqual(supported.status, AssertionStatus.SUPPORTED)
        self.assertEqual(accepted.status, AssertionStatus.ACCEPTED)
        self.assertEqual(superseded.status, AssertionStatus.SUPERSEDED)
        self.assertIsNotNone(superseded.supersedes_id)
        self.assertEqual(invalidated.status, AssertionStatus.INVALIDATED)
        self.assertIsNotNone(invalidated.invalidates_id)

    def test_rejects_invalid_lifecycle_transitions(self) -> None:
        assertion = self._candidate_assertion()
        rejected = assertion.transition_to(AssertionStatus.REJECTED)
        accepted = assertion.transition_to(AssertionStatus.SUPPORTED).transition_to(AssertionStatus.ACCEPTED)
        invalidated = accepted.transition_to(AssertionStatus.INVALIDATED, invalidates_id=EntityId.from_seed("assertions.invalidates", "x"))
        superseded = accepted.transition_to(AssertionStatus.SUPERSEDED, supersedes_id=EntityId.from_seed("assertions.supersedes", "x"))

        with self.assertRaises(ValueError):
            assertion.transition_to(AssertionStatus.ACCEPTED)

        with self.assertRaises(ValueError):
            rejected.transition_to(AssertionStatus.SUPPORTED)

        with self.assertRaises(ValueError):
            accepted.transition_to(AssertionStatus.CANDIDATE)

        with self.assertRaises(ValueError):
            accepted.transition_to(AssertionStatus.SUPPORTED)

        with self.assertRaises(ValueError):
            invalidated.transition_to(AssertionStatus.SUPPORTED)

        with self.assertRaises(ValueError):
            superseded.transition_to(AssertionStatus.ACCEPTED)

    def test_rejects_self_referential_lifecycle_pointers(self) -> None:
        assertion = self._candidate_assertion()

        with self.assertRaises(ValueError):
            replace(assertion, status=AssertionStatus.SUPERSEDED, supersedes_id=assertion.assertion_id)

        with self.assertRaises(ValueError):
            replace(assertion, status=AssertionStatus.INVALIDATED, invalidates_id=assertion.assertion_id)

    def test_rejected_assertion_keeps_full_evidence(self) -> None:
        semantic_run = self._self_referential_semantic_run()

        result = self.engine.build(semantic_run)

        assertion = result.assertions[0]
        self.assertEqual(assertion.status, AssertionStatus.REJECTED)
        self.assertTrue(assertion.evidence_link_ids)
        self.assertTrue(assertion.source_supports)
        self.assertEqual(len(result.evidence_links), 2)

    def test_engine_never_constructs_accepted_assertions_automatically(self) -> None:
        result = self.engine.build(self._semantic_run((self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY),), ()))

        self.assertNotEqual(result.assertions[0].status, AssertionStatus.ACCEPTED)
        self.assertNotEqual(result.assertions[0].review_state, AssertionReviewState.APPROVED)

    def _semantic_run(self, entities: tuple[ExtractedEntity, ...], observations: tuple[ExtractedObservation, ...]):
        extraction_run = self._extraction_run(entities, observations)
        normalization_run = self.normalization_engine.normalize(extraction_run)
        return self.semantic_engine.resolve(normalization_run)

    def _composite_scaling_semantic_run(self) -> SemanticResolutionRun:
        observation = ExtractedObservation(
            observation_id=EntityId.from_seed("assertions.observation", "composite-scaling"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text="4 mA = 0 psi and 20 mA = 300 psi",
            normalized_text="4 ma = 0 psi and 20 ma = 300 psi",
            document_position="fragment=composite|page=1|section=section-1|paragraph=1|span=0:34",
            fragment_id=EntityId.from_seed("assertions.fragment", "composite"),
            document_id=EntityId.from_seed("assertions.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="assertions.scaling.composite",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=34),
            context_window=ContextWindow(match_text="4 mA = 0 psi and 20 mA = 300 psi"),
            attributes=(
                ("raw_value", "4"),
                ("raw_unit", "mA"),
                ("engineering_value", "0"),
                ("engineering_unit", "psi"),
                ("normalized_engineering_unit_code", "psi"),
            ),
        )
        relation_candidate = self.normalization_engine._normalize_explicit_scaling(
            observation,
            datetime(2026, 1, 1, tzinfo=UTC),
            self.normalization_engine._build_indexes(),
            RunId.from_seed("assertions.extraction", "run-composite"),
        )[0]
        hypothesis = SemanticHypothesis(
            hypothesis_id=EntityId.from_seed("assertions.hypothesis", "composite-scaling"),
            source_candidate_id=relation_candidate.candidate_id,
            source_candidate_kind="relation_candidate",
            subject_table=relation_candidate.normalized_subject_table,
            subject_id=relation_candidate.normalized_subject_id,
            predicate_code=relation_candidate.predicate_code,
            object_table=relation_candidate.normalized_object_table,
            object_id=relation_candidate.normalized_object_id,
            status=SemanticHypothesisStatus.SUPPORTED,
            score=0.9,
            score_breakdown=(("normalization_score", 0.9),),
            reason_codes=(),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_relation_candidate=relation_candidate,
        )
        supports = (
            self._support(hypothesis.hypothesis_id, relation_candidate.candidate_id, HypothesisSupportKind.CANDIDATE, "SEM-RULE-003", "explicit_scaling", observation.original_text),
            self._support(hypothesis.hypothesis_id, relation_candidate.candidate_id, HypothesisSupportKind.RULE, "SEM-RULE-003", "candidate_binding", "Composite scaling remains under review"),
        )
        return SemanticResolutionRun(
            run_id=RunId.from_seed("assertions.semantic", "composite-scaling"),
            normalization_run_id=RunId.from_seed("assertions.normalization", "composite-scaling"),
            rule_pack_version="semantic.rules.v1",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            finished_at=datetime(2026, 1, 1, tzinfo=UTC),
            hypotheses=(hypothesis,),
            supports=supports,
            execution_logs=(),
            errors=(),
        )

    def _atomic_scaling_semantic_run(
        self,
        original_text: str,
        raw_value: str,
        raw_unit: str,
        engineering_value: str,
        engineering_unit: str,
        *,
        normalized_raw_unit_code: str | None = None,
        normalized_engineering_unit_code: str | None = None,
        include_negative_support: bool = False,
    ) -> SemanticResolutionRun:
        observation = ExtractedObservation(
            observation_id=EntityId.from_seed("assertions.observation", original_text),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text=original_text,
            normalized_text=original_text.lower(),
            document_position="fragment=atomic|page=1|section=section-1|paragraph=1|span=0:32",
            fragment_id=EntityId.from_seed("assertions.fragment", original_text),
            document_id=EntityId.from_seed("assertions.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="assertions.scaling.atomic",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=len(original_text)),
            context_window=ContextWindow(match_text=original_text),
            attributes=tuple(
                pair
                for pair in (
                    ("raw_value", raw_value),
                    ("raw_unit", raw_unit),
                    ("engineering_value", engineering_value),
                    ("engineering_unit", engineering_unit),
                    ("normalized_raw_unit_code", normalized_raw_unit_code),
                    ("normalized_engineering_unit_code", normalized_engineering_unit_code),
                )
                if pair[1] is not None
            ),
        )
        relation_candidate = self.normalization_engine._normalize_explicit_scaling(
            observation,
            datetime(2026, 1, 1, tzinfo=UTC),
            self.normalization_engine._build_indexes(),
            RunId.from_seed("assertions.extraction", original_text),
        )[0]
        hypothesis = SemanticHypothesis(
            hypothesis_id=EntityId.from_seed("assertions.hypothesis", original_text),
            source_candidate_id=relation_candidate.candidate_id,
            source_candidate_kind="relation_candidate",
            subject_table=relation_candidate.normalized_subject_table,
            subject_id=relation_candidate.normalized_subject_id,
            predicate_code=relation_candidate.predicate_code,
            object_table=relation_candidate.normalized_object_table,
            object_id=relation_candidate.normalized_object_id,
            status=SemanticHypothesisStatus.SUPPORTED,
            score=0.9,
            score_breakdown=(("normalization_score", 0.9),),
            reason_codes=(),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_relation_candidate=relation_candidate,
        )
        supports = [
            self._support(hypothesis.hypothesis_id, relation_candidate.candidate_id, HypothesisSupportKind.CANDIDATE, "SEM-RULE-003", "explicit_scaling", original_text),
            self._support(hypothesis.hypothesis_id, relation_candidate.candidate_id, HypothesisSupportKind.RULE, "SEM-RULE-003", "candidate_binding", "Scaling candidate bound deterministically"),
        ]
        if include_negative_support:
            supports.append(
                self._support(hypothesis.hypothesis_id, relation_candidate.candidate_id, HypothesisSupportKind.FILTER, "SEM-FILTER-NEG", "conflict_detected", "Negative support requires review")
            )
        return SemanticResolutionRun(
            run_id=RunId.from_seed("assertions.semantic", original_text),
            normalization_run_id=RunId.from_seed("assertions.normalization", original_text),
            rule_pack_version="semantic.rules.v1",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            finished_at=datetime(2026, 1, 1, tzinfo=UTC),
            hypotheses=(hypothesis,),
            supports=tuple(supports),
            execution_logs=(),
            errors=(),
        )

    def _self_referential_semantic_run(self) -> SemanticResolutionRun:
        scaling_run = self._atomic_scaling_semantic_run(
            "4 mA = 0 psi",
            "4",
            "mA",
            "0",
            "psi",
            normalized_raw_unit_code="ma",
            normalized_engineering_unit_code="psi",
        )
        relation_hypothesis = scaling_run.hypotheses[0]
        hypothesis = replace(
            relation_hypothesis,
            subject_table="catalog.engineering_unit",
            subject_id=EntityId.from_seed("assertions.same", "same"),
            predicate_code="self_binding",
            object_table="catalog.engineering_unit",
            object_id=EntityId.from_seed("assertions.same", "same"),
        )
        return SemanticResolutionRun(
            run_id=RunId.from_seed("assertions.semantic", "self-ref"),
            normalization_run_id=RunId.from_seed("assertions.normalization", "self-ref"),
            rule_pack_version="semantic.rules.v1",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            finished_at=datetime(2026, 1, 1, tzinfo=UTC),
            hypotheses=(hypothesis,),
            supports=scaling_run.supports,
            execution_logs=(),
            errors=(),
        )

    def _candidate_assertion(self):
        mention = self._mention("Pressure", ExtractedEntityType.PHYSICAL_QUANTITY)
        semantic_run = self._semantic_run((mention,), ())
        built = self.engine.build(semantic_run).assertions[0]
        return replace(built, status=AssertionStatus.CANDIDATE, review_state=AssertionReviewState.AUTO, reason_codes=())

    def _assertion_link(
        self,
        *,
        document_id=EntityId.from_seed("assertions.document", "doc-1"),
        document_version_id=EntityId.from_seed("assertions.version", "ver-1"),
        fragment_id=EntityId.from_seed("assertions.fragment", "fragment-1"),
        weight=0.9,
    ) -> AssertionEvidenceLink:
        return AssertionEvidenceLink(
            link_id=EntityId.from_seed("assertions.link", f"{document_id}:{document_version_id}:{fragment_id}"),
            assertion_id=EntityId.from_seed("assertions.assertion", "a-1"),
            hypothesis_id=EntityId.from_seed("assertions.hypothesis", "h-1"),
            support_id=EntityId.from_seed("assertions.support", "s-1"),
            document_id=document_id,
            document_version_id=document_version_id,
            fragment_id=fragment_id,
            evidence_role="candidate",
            weight=weight,
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=8),
            original_text="Pressure",
            normalized_text="pressure",
        )

    def _support(
        self,
        hypothesis_id: EntityId,
        source_candidate_id: EntityId,
        support_kind: HypothesisSupportKind,
        rule_code: str,
        reason_code: str,
        detail: str,
    ) -> HypothesisSupport:
        return HypothesisSupport(
            support_id=EntityId.from_seed("assertions.support", f"{hypothesis_id}:{support_kind.value}:{reason_code}:{detail}"),
            hypothesis_id=hypothesis_id,
            support_kind=support_kind,
            source_candidate_id=source_candidate_id,
            rule_code=rule_code,
            reason_code=reason_code,
            detail=detail,
        )

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("assertions.unit", "psi"),
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
                        entity_id=EntityId.from_seed("assertions.quantity", "pressure"),
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
                        entity_id=EntityId.from_seed("assertions.compatibility", "pressure.psi"),
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
                        entity_id=EntityId.from_seed("assertions.variable", "standpipe_pressure"),
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

    def _mention(self, text: str, entity_type: ExtractedEntityType, *, start_offset: int = 0) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("assertions.mention", f"{entity_type.value}:{text}:{start_offset}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=" ".join(text.split()).strip().lower(),
            document_position=f"fragment=fragment-1|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("assertions.fragment", "fragment-1"),
            document_id=EntityId.from_seed("assertions.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="assertions.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _scaling_observation(self) -> ExtractedObservation:
        return ExtractedObservation(
            observation_id=EntityId.from_seed("assertions.observation", "scaling"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text="1000 psi = 68.95 psi",
            normalized_text="1000 psi = 68.95 psi",
            document_position="fragment=scaling|page=1|section=section-1|paragraph=1|span=0:18",
            fragment_id=EntityId.from_seed("assertions.fragment", "scaling"),
            document_id=EntityId.from_seed("assertions.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.version", "ver-1"),
            extraction_confidence=1.0,
            extraction_rule="assertions.scaling",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=18),
            context_window=ContextWindow(match_text="1000 psi = 68.95 psi"),
            attributes=(("raw_value", "1000"), ("raw_unit", "psi"), ("engineering_value", "68.95"), ("engineering_unit", "psi")),
        )

    def _extraction_run(self, entities: tuple[ExtractedEntity, ...], observations: tuple[ExtractedObservation, ...]) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("assertions.extraction", "run-1"),
            document_id=EntityId.from_seed("assertions.document", "doc-1"),
            version_id=EntityId.from_seed("assertions.version", "ver-1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=entities,
            observations=observations,
            metrics=ExtractionMetrics(total_entities=len(entities), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )