from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
import unittest

from drilling_knowledge.assertions.consolidation import FactConsolidator
from drilling_knowledge.assertions.conflict_resolution import AssertionConflictResolver, ConflictResolutionRun
from drilling_knowledge.assertions.conflict_resolution.domain import (
    AssertionConflictMember,
    AssertionConflictSet,
    ConflictDecisionType,
    ConflictMemberRole,
    ConflictReviewQueueItem,
    ConflictSetStatus,
    ConflictType,
)
from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionGenerationRun, AssertionReviewState, AssertionStatus
from drilling_knowledge.assertions.engine import EvidenceAssertionEngine
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ContextWindow, ExtractedEntity, ExtractedEntityType, ExtractedObservation, ExtractedObservationType, ExtractionMetrics, ExtractionRun, ExtractionRunStatus, ExtractionSourceTrace
from drilling_knowledge.normalization import NormalizationEngine
from drilling_knowledge.resolution import SemanticResolutionEngine


class FactConsolidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = self._catalog_repository()
        self.normalization_engine = NormalizationEngine.create(self.catalog)
        self.semantic_engine = SemanticResolutionEngine.create(self.catalog)
        self.assertion_engine = EvidenceAssertionEngine.create()
        self.conflict_resolver = AssertionConflictResolver.create()
        self.consolidator = FactConsolidator.create()

    def test_creates_fact_from_accepted_assertion(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self._assertion_run((accepted,), run_seed="accepted")
        conflict_run = self.conflict_resolver.resolve(assertion_run)

        result = self.consolidator.consolidate(assertion_run, conflict_run)

        self.assertEqual(len(result.facts), 1)
        self.assertEqual(len(result.support_links), 1)
        self.assertEqual(result.facts[0].version, 1)
        self.assertTrue(result.facts[0].active_revision)

    def test_creates_facts_from_coexistence_split(self) -> None:
        first = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        second = self._assertion("4 mA = 10 psi", version_seed="v2", status=AssertionStatus.ACCEPTED)
        assertion_run = self._assertion_run((first, second), run_seed="split")
        conflict_run = self.conflict_resolver.resolve(assertion_run)

        result = self.consolidator.consolidate(assertion_run, conflict_run)

        self.assertEqual(len(result.facts), 2)
        self.assertEqual({support.support_role.value for support in result.support_links}, {"coexistence_context"})

    def test_multiple_contexts_remain_separate(self) -> None:
        assertions = (
            self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED),
            self._assertion("4 mA = 10 psi", version_seed="v2", status=AssertionStatus.ACCEPTED),
            self._assertion("4 mA = 20 psi", version_seed="v3", status=AssertionStatus.ACCEPTED),
        )
        assertion_run = self._assertion_run(assertions, run_seed="three-contexts")
        conflict_run = self.conflict_resolver.resolve(assertion_run)

        result = self.consolidator.consolidate(assertion_run, conflict_run)

        self.assertEqual(len(result.facts), 3)
        self.assertEqual(len({fact.scope for fact in result.facts}), 3)

    def test_skips_when_no_accepted_assertions_exist(self) -> None:
        supported = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.SUPPORTED)
        assertion_run = self._assertion_run((supported,), run_seed="no-accepted")
        conflict_run = self.conflict_resolver.resolve(assertion_run)

        result = self.consolidator.consolidate(assertion_run, conflict_run)

        self.assertEqual(result.facts, ())
        self.assertEqual(result.support_links, ())

    def test_open_conflict_blocks_fact_creation(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self._assertion_run((accepted,), run_seed="open-conflict")
        conflict_run = self._open_conflict_run(assertion_run)

        with self.assertRaises(ConflictError):
            self.consolidator.consolidate(assertion_run, conflict_run)

    def test_append_only_versioning_creates_new_revision(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        first_run = self._assertion_run((accepted,), run_seed="version-1")
        first_conflict = self.conflict_resolver.resolve(first_run)
        first_result = self.consolidator.consolidate(first_run, first_conflict)

        second_run, _ = self._revision_run(first_run, accepted, run_seed="version-2", revision_seed="revision-2")
        second_conflict = self.conflict_resolver.resolve(second_run)

        second_result = self.consolidator.consolidate(
            second_run,
            second_conflict,
            existing_facts=first_result.facts,
            existing_support_links=first_result.support_links,
        )

        self.assertEqual(len(second_result.facts), 2)
        previous_revision = next(fact for fact in second_result.facts if fact.version == 1)
        current_revision = next(fact for fact in second_result.facts if fact.version == 2)
        self.assertEqual(previous_revision.lifecycle.value, "superseded")
        self.assertFalse(previous_revision.active_revision)
        self.assertTrue(current_revision.active_revision)
        self.assertEqual(current_revision.supersedes_fact_id, previous_revision.fact_id)

    def test_rejects_two_active_revisions_for_same_lineage(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self._assertion_run((accepted,), run_seed="duplicate-active")
        conflict_run = self.conflict_resolver.resolve(assertion_run)
        first_result = self.consolidator.consolidate(assertion_run, conflict_run)
        duplicate_active = replace(
            first_result.facts[0],
            fact_id=EntityId.from_seed("semantic.consolidated_fact", "duplicate-active"),
            version=2,
            supersedes_fact_id=first_result.facts[0].fact_id,
        )

        with self.assertRaises(ConflictError):
            self.consolidator.consolidate(
                assertion_run,
                conflict_run,
                existing_facts=(first_result.facts[0], duplicate_active),
                existing_support_links=first_result.support_links,
            )

    def test_idempotent_against_persisted_state_does_not_create_v3(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        first_run = self._assertion_run((accepted,), run_seed="persisted-v1")
        first_conflict = self.conflict_resolver.resolve(first_run)
        first_result = self.consolidator.consolidate(first_run, first_conflict)

        second_run, _ = self._revision_run(first_run, accepted, run_seed="persisted-v2", revision_seed="persisted-v2")
        second_conflict = self.conflict_resolver.resolve(second_run)
        second_result = self.consolidator.consolidate(
            second_run,
            second_conflict,
            existing_facts=first_result.facts,
            existing_support_links=first_result.support_links,
        )

        repeated = self.consolidator.consolidate(
            second_run,
            second_conflict,
            existing_facts=second_result.facts,
            existing_support_links=second_result.support_links,
        )

        self.assertEqual(repeated.facts, second_result.facts)
        self.assertEqual(repeated.support_links, second_result.support_links)

    def test_revision_chain_is_explicit(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        first_run = self._assertion_run((accepted,), run_seed="chain-v1")
        first_conflict = self.conflict_resolver.resolve(first_run)
        first_result = self.consolidator.consolidate(first_run, first_conflict)

        second_run, _ = self._revision_run(first_run, accepted, run_seed="chain-v2", revision_seed="chain-v2")
        second_result = self.consolidator.consolidate(
            second_run,
            self.conflict_resolver.resolve(second_run),
            existing_facts=first_result.facts,
            existing_support_links=first_result.support_links,
        )

        third_run, _ = self._revision_run(first_run, accepted, run_seed="chain-v3", revision_seed="chain-v3")
        third_result = self.consolidator.consolidate(
            third_run,
            self.conflict_resolver.resolve(third_run),
            existing_facts=second_result.facts,
            existing_support_links=second_result.support_links,
        )

        facts_by_version = {fact.version: fact for fact in third_result.facts}
        self.assertIsNone(facts_by_version[1].supersedes_fact_id)
        self.assertEqual(facts_by_version[2].supersedes_fact_id, facts_by_version[1].fact_id)
        self.assertEqual(facts_by_version[3].supersedes_fact_id, facts_by_version[2].fact_id)

    def test_historical_support_is_preserved_across_versions(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        first_run = self._assertion_run((accepted,), run_seed="history-v1")
        first_result = self.consolidator.consolidate(first_run, self.conflict_resolver.resolve(first_run))

        second_run, _ = self._revision_run(first_run, accepted, run_seed="history-v2", revision_seed="history-v2")
        second_result = self.consolidator.consolidate(
            second_run,
            self.conflict_resolver.resolve(second_run),
            existing_facts=first_result.facts,
            existing_support_links=first_result.support_links,
        )

        self.assertEqual(len(second_result.facts), 2)
        self.assertEqual(len(second_result.support_links), 2)
        self.assertEqual({support.fact_id for support in second_result.support_links}, {fact.fact_id for fact in second_result.facts})

    def test_resolution_is_idempotent(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self._assertion_run((accepted,), run_seed="same-input")
        conflict_run = self.conflict_resolver.resolve(assertion_run)

        first = self.consolidator.consolidate(assertion_run, conflict_run)
        second = self.consolidator.consolidate(assertion_run, conflict_run)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.facts, second.facts)
        self.assertEqual(first.support_links, second.support_links)

    def test_explicit_has_property_relations_do_not_conflict_with_each_other(self) -> None:
        owner = self._mention("SurfaceEquipment", ExtractedEntityType.EQUIPMENT, extraction_rule="energistics.schema.class.v1")
        first_property = self._mention("IdStandpipe", ExtractedEntityType.IDENTIFIER, start_offset=10, extraction_rule="energistics.schema.property.v1")
        second_property = self._mention("IdKelly", ExtractedEntityType.IDENTIFIER, start_offset=20, extraction_rule="energistics.schema.property.v1")
        observations = (
            self._explicit_relation(owner, first_property, ExtractedObservationType.HAS_PROPERTY, "SurfaceEquipment has property IdStandpipe"),
            self._explicit_relation(owner, second_property, ExtractedObservationType.HAS_PROPERTY, "SurfaceEquipment has property IdKelly"),
        )
        extraction_run = self._schema_extraction_run((owner, first_property, second_property), observations)
        normalization_run = self.normalization_engine.normalize(extraction_run)
        semantic_run = self.semantic_engine.resolve(normalization_run)
        assertion_run = self.assertion_engine.build(semantic_run)
        assertion_run = AssertionGenerationRun(
            run_id=assertion_run.run_id,
            semantic_run_id=assertion_run.semantic_run_id,
            rule_pack_version=assertion_run.rule_pack_version,
            threshold=assertion_run.threshold,
            started_at=assertion_run.started_at,
            finished_at=assertion_run.finished_at,
            assertions=tuple(assertion.transition_to(AssertionStatus.ACCEPTED, review_state=AssertionReviewState.AUTO) for assertion in assertion_run.assertions),
            evidence_links=assertion_run.evidence_links,
            validation_logs=assertion_run.validation_logs,
            errors=assertion_run.errors,
        )

        conflict_run = self.conflict_resolver.resolve(assertion_run)
        result = self.consolidator.consolidate(assertion_run, conflict_run)

        self.assertEqual(Counter(fact.predicate_code for fact in result.facts)["has_property"], 2)
        self.assertFalse(any(conflict.status == ConflictSetStatus.OPEN for conflict in conflict_run.conflict_sets))

    def test_reversed_input_order_is_stable(self) -> None:
        first_assertion = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        second_assertion = self._assertion("4 mA = 10 psi", version_seed="v2", status=AssertionStatus.ACCEPTED)
        forward = self._assertion_run((first_assertion, second_assertion), run_seed="forward")
        reverse = self._assertion_run((second_assertion, first_assertion), run_seed="reverse")
        forward_conflict = self.conflict_resolver.resolve(forward)
        reverse_conflict = self.conflict_resolver.resolve(reverse)

        forward_result = self.consolidator.consolidate(forward, forward_conflict)
        reverse_result = self.consolidator.consolidate(reverse, reverse_conflict)

        self.assertEqual(forward_result.facts, reverse_result.facts)
        self.assertEqual(forward_result.support_links, reverse_result.support_links)

    def test_full_traceability_is_preserved(self) -> None:
        accepted = self._assertion("4 mA = 0 psi", version_seed="v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self._assertion_run((accepted,), run_seed="trace")
        conflict_run = self.conflict_resolver.resolve(assertion_run)

        result = self.consolidator.consolidate(assertion_run, conflict_run)

        support = result.support_links[0]
        self.assertEqual(support.assertion_id, support.source_assertion.assertion_id)
        self.assertEqual(set(support.assertion_evidence_link_ids), {link.link_id for link in result.evidence_links})
        self.assertEqual(set(support.hypothesis_support_ids), {item.support_id for item in support.source_assertion.source_supports})

    def _assertion_run(self, assertions: tuple, *, run_seed: str) -> AssertionGenerationRun:
        created_at = assertions[0].created_at if assertions else datetime(2026, 1, 1, tzinfo=UTC)
        evidence_links: list[AssertionEvidenceLink] = []
        for assertion in assertions:
            evidence_links.extend(self._links_for_assertion(assertion))
        return AssertionGenerationRun(
            run_id=RunId.from_seed("fact.consolidation.assertion_run", run_seed),
            semantic_run_id=RunId.from_seed("fact.consolidation.semantic_run", run_seed),
            rule_pack_version="assertion.rules.v1",
            threshold=0.5,
            started_at=created_at,
            finished_at=created_at,
            assertions=assertions,
            evidence_links=tuple(sorted(evidence_links, key=lambda item: str(item.link_id))),
            validation_logs=(),
            errors=(),
        )

    def _assertion(self, text: str, *, version_seed: str, status: AssertionStatus):
        extraction_run = self._extraction_run(text, version_seed=version_seed)
        normalization_run = self.normalization_engine.normalize(extraction_run)
        semantic_run = self.semantic_engine.resolve(normalization_run)
        built_run = self.assertion_engine.build(semantic_run)
        assertion = next(item for item in built_run.assertions if item.predicate_code == "explicit_scaling")
        return replace(assertion, status=status, review_state=AssertionReviewState.AUTO)

    def _links_for_assertion(self, assertion) -> tuple[AssertionEvidenceLink, ...]:
        if assertion.source_hypothesis.source_entity_candidate is not None:
            mention = assertion.source_hypothesis.source_entity_candidate.source_mention
            document_id = mention.document_id
            document_version_id = mention.version_id
            fragment_id = mention.fragment_id
            original_text = mention.original_text
            normalized_text = mention.normalized_text
            source_trace = mention.source_trace
        else:
            observation = assertion.source_hypothesis.source_relation_candidate.source_observation
            document_id = observation.document_id
            document_version_id = observation.version_id
            fragment_id = observation.fragment_id
            original_text = observation.original_text
            normalized_text = observation.normalized_text
            source_trace = observation.source_trace
        return tuple(
            AssertionEvidenceLink(
                link_id=link_id,
                assertion_id=assertion.assertion_id,
                hypothesis_id=assertion.source_hypothesis_id,
                support_id=support.support_id,
                document_id=document_id,
                document_version_id=document_version_id,
                fragment_id=fragment_id,
                evidence_role=support.support_kind.value,
                weight=assertion.score if support.support_kind.value == "candidate" else None,
                source_trace=source_trace,
                original_text=original_text,
                normalized_text=normalized_text,
            )
            for link_id, support in zip(assertion.evidence_link_ids, assertion.source_supports, strict=True)
        )

    def _revision_run(self, base_run: AssertionGenerationRun, assertion, *, run_seed: str, revision_seed: str) -> tuple[AssertionGenerationRun, object]:
        revised_link_ids = tuple(
            EntityId.from_seed("fact.consolidation.link", f"{revision_seed}:{index}")
            for index, _ in enumerate(assertion.source_supports, start=1)
        )
        revised_assertion = replace(
            assertion,
            assertion_id=EntityId.from_seed("fact.consolidation.assertion", revision_seed),
            evidence_link_ids=revised_link_ids,
        )
        revised_run = AssertionGenerationRun(
            run_id=RunId.from_seed("fact.consolidation.assertion_run", run_seed),
            semantic_run_id=base_run.semantic_run_id,
            rule_pack_version=base_run.rule_pack_version,
            threshold=base_run.threshold,
            started_at=base_run.started_at,
            finished_at=base_run.finished_at,
            assertions=(revised_assertion,),
            evidence_links=self._links_for_assertion(revised_assertion),
            validation_logs=(),
            errors=(),
        )
        return revised_run, revised_assertion

    def _open_conflict_run(self, assertion_run: AssertionGenerationRun) -> ConflictResolutionRun:
        accepted = assertion_run.assertions[0]
        conflict_set_id = EntityId.from_seed("semantic.assertion_conflict_set", "open-conflict")
        member = AssertionConflictMember(
            member_id=EntityId.from_seed("semantic.assertion_conflict_member", "open-conflict-member"),
            conflict_set_id=conflict_set_id,
            assertion_id=accepted.assertion_id,
            member_role=ConflictMemberRole.REVIEW_CANDIDATE,
            member_score=accepted.score,
            scope_key=f"{EntityId.from_seed('fact.consolidation.document', 'doc-1')}:{EntityId.from_seed('fact.consolidation.version', 'v1')}",
            value_key="0:PSI",
            created_at=assertion_run.finished_at,
            source_assertion=accepted,
        )
        review_item = ConflictReviewQueueItem(
            review_item_id=EntityId.from_seed("semantic.assertion_conflict_review_item", "open-conflict-review"),
            conflict_set_id=conflict_set_id,
            queue_type="assertion_conflict",
            review_reason="contradictory_active_assertions",
            created_at=assertion_run.finished_at,
        )
        conflict_set = AssertionConflictSet(
            conflict_set_id=conflict_set_id,
            claim_key="explicit_scaling:4:mA:PSI",
            scope_key=str(EntityId.from_seed("fact.consolidation.document", "doc-1")),
            conflict_type=ConflictType.INCOMPATIBLE_ASSERTION,
            status=ConflictSetStatus.OPEN,
            decision_type=ConflictDecisionType.REVIEW_REQUIRED,
            decision_reason="contradictory_active_assertions",
            requires_human_review=True,
            opened_at=assertion_run.finished_at,
            closed_at=None,
            members=(member,),
            contexts=(),
            review_item=review_item,
        )
        return ConflictResolutionRun(
            run_id=RunId.from_seed("semantic.assertion_conflict.run", "open-conflict"),
            assertion_run_id=assertion_run.run_id,
            rule_pack_version="conflict.rules.v1",
            started_at=assertion_run.finished_at,
            finished_at=assertion_run.finished_at,
            conflict_sets=(conflict_set,),
            members=(member,),
            contexts=(),
            review_queue_items=(review_item,),
            evidence_links=assertion_run.evidence_links,
            errors=(),
        )

    def _catalog_repository(self) -> InMemoryCatalogRepository:
        scope = CatalogScope()
        return InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("fact.consolidation.unit", "psi"),
                        code=CatalogCode("psi"),
                        names=LocalizedName("PSI"),
                        description="Pressure unit.",
                        scope=scope,
                        symbol="psi",
                        dimension_code="pressure",
                    ),
                    EngineeringUnit(
                        entity_id=EntityId.from_seed("fact.consolidation.unit", "ma"),
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
                        entity_id=EntityId.from_seed("fact.consolidation.quantity", "pressure"),
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
                        entity_id=EntityId.from_seed("fact.consolidation.compatibility", "pressure.psi"),
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
                        entity_id=EntityId.from_seed("fact.consolidation.variable", "standpipe_pressure"),
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
            observation_id=EntityId.from_seed("fact.consolidation.observation", f"{text}:{version_seed}"),
            observation_type=ExtractedObservationType.EXPLICIT_SCALING,
            original_text=text,
            normalized_text=text.lower(),
            document_position="fragment=atomic|page=1|section=section-1|paragraph=1|span=0:12",
            fragment_id=EntityId.from_seed("fact.consolidation.fragment", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("fact.consolidation.document", "doc-1"),
            version_id=EntityId.from_seed("fact.consolidation.version", version_seed),
            extraction_confidence=1.0,
            extraction_rule="fact.consolidation.scaling",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=len(text)),
            context_window=ContextWindow(match_text=text),
            attributes=(("raw_value", raw_value), ("raw_unit", raw_unit), ("engineering_value", engineering_value), ("engineering_unit", engineering_unit)),
        )
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("fact.consolidation.extraction", f"{text}:{version_seed}"),
            document_id=EntityId.from_seed("fact.consolidation.document", "doc-1"),
            version_id=EntityId.from_seed("fact.consolidation.version", version_seed),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=(),
            observations=(observation,),
            metrics=ExtractionMetrics(total_entities=0, entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )

    def _schema_extraction_run(self, entities: tuple[ExtractedEntity, ...], observations: tuple[ExtractedObservation, ...]) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, tzinfo=UTC)
        return ExtractionRun(
            run_id=RunId.from_seed("fact.consolidation.extraction", "schema-relations"),
            document_id=EntityId.from_seed("fact.consolidation.document", "doc-1"),
            version_id=EntityId.from_seed("fact.consolidation.version", "schema-v1"),
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=entities,
            observations=observations,
            metrics=ExtractionMetrics(total_entities=len(entities), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0, errors=()),
        )

    def _mention(
        self,
        text: str,
        entity_type: ExtractedEntityType,
        *,
        start_offset: int = 0,
        extraction_rule: str = "fact.consolidation.mention",
    ) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("fact.consolidation.entity", f"{entity_type}:{text}:{start_offset}:{extraction_rule}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=text.lower(),
            document_position=f"fragment=schema|page=1|section=section-1|paragraph=1|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("fact.consolidation.fragment", "schema-fragment"),
            document_id=EntityId.from_seed("fact.consolidation.document", "doc-1"),
            version_id=EntityId.from_seed("fact.consolidation.version", "schema-v1"),
            extraction_confidence=1.0,
            extraction_rule=extraction_rule,
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _explicit_relation(
        self,
        source: ExtractedEntity,
        target: ExtractedEntity,
        observation_type: ExtractedObservationType,
        text: str,
    ) -> ExtractedObservation:
        return ExtractedObservation(
            observation_id=EntityId.from_seed("fact.consolidation.observation", f"{observation_type}:{source.entity_id}:{target.entity_id}"),
            observation_type=observation_type,
            original_text=text,
            normalized_text=text.lower(),
            document_position=source.document_position,
            fragment_id=source.fragment_id,
            document_id=source.document_id,
            version_id=source.version_id,
            extraction_confidence=1.0,
            extraction_rule=f"energistics.schema.{observation_type.value.lower()}.v1",
            source_trace=source.source_trace,
            context_window=ContextWindow(match_text=text),
            source_entity_id=source.entity_id,
            target_entity_id=target.entity_id,
        )