from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence import EquivalenceDecision, EquivalenceDecisionStatus
from drilling_knowledge.extraction.domain import (
    ContextWindow,
    ExtractedEntity,
    ExtractedEntityType,
    ExtractionMetrics,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionSourceTrace,
)
from drilling_knowledge.knowledge_graph import KnowledgeGraphBuilder, KnowledgeGraphEdgeType, KnowledgeGraphNodeType
from drilling_knowledge.resolution.domain import (
    CandidateConcept,
    CandidateEvidence,
    MentionResolution,
    ResolutionEvidenceType,
    ResolutionRun,
    ResolutionStatus,
)


class KnowledgeGraphBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = KnowledgeGraphBuilder.create()

    def test_builds_graph_with_explicit_nodes_edges_and_metrics(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        extraction_run = self._extraction_run("doc-1", "ver-1", mention)
        resolution_run = self._resolution_run(
            mention,
            self._resolution(
                mention,
                self._candidate("concept-1", code="hook_load", name="Hook Load", rank=1),
            ),
        )
        decision = self._decision(mention, "concept-1", EquivalenceDecisionStatus.APPROVED, revision=1)

        graph = self.builder.build((extraction_run,), (resolution_run,), (decision,))

        self.assertEqual(graph.metrics.node_counts_by_type[KnowledgeGraphNodeType.DOCUMENT.value], 1)
        self.assertEqual(graph.metrics.node_counts_by_type[KnowledgeGraphNodeType.FRAGMENT.value], 1)
        self.assertEqual(graph.metrics.node_counts_by_type[KnowledgeGraphNodeType.MENTION.value], 1)
        self.assertEqual(graph.metrics.node_counts_by_type[KnowledgeGraphNodeType.CONCEPT.value], 1)
        self.assertEqual(graph.metrics.node_counts_by_type[KnowledgeGraphNodeType.EQUIVALENCE_DECISION.value], 1)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.DOCUMENT_TO_FRAGMENT.value], 1)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.FRAGMENT_TO_MENTION.value], 1)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE.value], 1)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.MENTION_TO_EQUIVALENCE_DECISION.value], 1)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT.value], 1)
        self.assertEqual(graph.metrics.approved_decisions, 1)
        self.assertEqual(graph.metrics.mentions_without_candidates, 0)
        self.assertTrue(all(edge.source_traces for edge in graph.edges))

    def test_graph_order_is_stable(self) -> None:
        mention_a = self._mention("Hookload", document_seed="doc-a", fragment_seed="frag-a", start_offset=20)
        mention_b = self._mention("PSI", document_seed="doc-b", fragment_seed="frag-b", start_offset=5, entity_type=ExtractedEntityType.ENGINEERING_UNIT)
        graph_a = self.builder.build(
            (self._extraction_run("doc-b", "ver-1", mention_b), self._extraction_run("doc-a", "ver-1", mention_a)),
            (self._resolution_run(mention_b, self._resolution(mention_b)), self._resolution_run(mention_a, self._resolution(mention_a))),
            (),
        )
        graph_b = self.builder.build(
            (self._extraction_run("doc-a", "ver-1", mention_a), self._extraction_run("doc-b", "ver-1", mention_b)),
            (self._resolution_run(mention_a, self._resolution(mention_a)), self._resolution_run(mention_b, self._resolution(mention_b))),
            (),
        )

        self.assertEqual(graph_a, graph_b)

    def test_graph_build_is_idempotent(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        extraction_run = self._extraction_run("doc-1", "ver-1", mention)
        resolution_run = self._resolution_run(mention, self._resolution(mention))

        first = self.builder.build((extraction_run,), (resolution_run,), ())
        second = self.builder.build((extraction_run,), (resolution_run,), ())

        self.assertEqual(first, second)

    def test_empty_document_still_creates_document_node(self) -> None:
        extraction_run = self._extraction_run("doc-empty", "ver-1")

        graph = self.builder.build((extraction_run,), (), ())

        self.assertEqual(graph.metrics.documents_processed, 1)
        self.assertEqual(graph.metrics.node_counts_by_type, {KnowledgeGraphNodeType.DOCUMENT.value: 1})
        self.assertEqual(graph.edges, ())

    def test_mentions_without_candidates_are_counted(self) -> None:
        mention = self._mention("Unknown", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        graph = self.builder.build(
            (self._extraction_run("doc-1", "ver-1", mention),),
            (self._resolution_run(mention, self._resolution(mention)),),
            (),
        )

        self.assertEqual(graph.metrics.mentions_without_candidates, 1)
        self.assertNotIn(KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE.value, graph.metrics.relation_counts_by_type)

    def test_pending_decision_creates_no_decision_to_concept_edge(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        decision = self._decision(mention, "concept-1", EquivalenceDecisionStatus.PENDING, revision=1)
        graph = self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (), (decision,))

        self.assertEqual(graph.metrics.pending_decisions, 1)
        self.assertNotIn(KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT.value, graph.metrics.relation_counts_by_type)

    def test_rejected_decision_creates_no_decision_to_concept_edge(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        decision = self._decision(mention, "concept-1", EquivalenceDecisionStatus.REJECTED, revision=1)
        graph = self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (), (decision,))

        self.assertEqual(graph.metrics.rejected_decisions, 1)
        self.assertNotIn(KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT.value, graph.metrics.relation_counts_by_type)

    def test_multiple_documents_are_supported(self) -> None:
        mention_a = self._mention("Hookload", document_seed="doc-a", fragment_seed="frag-a", start_offset=10)
        mention_b = self._mention("PSI", document_seed="doc-b", fragment_seed="frag-b", start_offset=5, entity_type=ExtractedEntityType.ENGINEERING_UNIT)
        graph = self.builder.build(
            (self._extraction_run("doc-a", "ver-1", mention_a), self._extraction_run("doc-b", "ver-1", mention_b)),
            (self._resolution_run(mention_a, self._resolution(mention_a)), self._resolution_run(mention_b, self._resolution(mention_b))),
            (),
        )

        self.assertEqual(graph.metrics.documents_processed, 2)
        self.assertEqual(graph.metrics.node_counts_by_type[KnowledgeGraphNodeType.DOCUMENT.value], 2)

    def test_different_versions_of_same_document_do_not_collide(self) -> None:
        mention_v1 = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        mention_v2 = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1-v2", start_offset=12)
        graph = self.builder.build(
            (self._extraction_run("doc-1", "ver-1", mention_v1), self._extraction_run("doc-1", "ver-2", mention_v2)),
            (),
            (),
        )

        document_nodes = [node for node in graph.nodes if node.node_type == KnowledgeGraphNodeType.DOCUMENT]
        self.assertEqual(len(document_nodes), 2)
        self.assertEqual(graph.metrics.documents_processed, 2)

    def test_duplicate_decision_node_identity_with_different_content_raises(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        original = self._decision(mention, "concept-1", EquivalenceDecisionStatus.PENDING, revision=1)
        conflicting = EquivalenceDecision(
            decision_id=original.decision_id,
            mention_id=original.mention_id,
            catalog_entity_id=original.catalog_entity_id,
            status=EquivalenceDecisionStatus.REJECTED,
            evidence=original.evidence,
            rationale=original.rationale,
            decided_by=original.decided_by,
            decided_at=original.decided_at,
            source_trace=original.source_trace,
            revision=original.revision,
        )

        with self.assertRaises(ValueError):
            self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (), (original, conflicting))

    def test_multiple_decision_revisions_are_kept_separate(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        first = self._decision(mention, "concept-1", EquivalenceDecisionStatus.PENDING, revision=1)
        second = self._decision(mention, "concept-1", EquivalenceDecisionStatus.APPROVED, revision=2)

        graph = self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (), (first, second))

        decision_nodes = [node for node in graph.nodes if node.node_type == KnowledgeGraphNodeType.EQUIVALENCE_DECISION]
        self.assertEqual(len(decision_nodes), 2)
        self.assertEqual(graph.metrics.pending_decisions, 1)
        self.assertEqual(graph.metrics.approved_decisions, 1)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.MENTION_TO_EQUIVALENCE_DECISION.value], 2)
        self.assertEqual(graph.metrics.relation_counts_by_type[KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT.value], 1)

    def test_metrics_are_based_on_deduplicated_graph(self) -> None:
        mention = self._mention("Unknown", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        extraction_run = self._extraction_run("doc-1", "ver-1", mention)
        resolution_run = self._resolution_run(mention, self._resolution(mention))

        graph = self.builder.build((extraction_run, extraction_run), (resolution_run, resolution_run), ())

        self.assertEqual(graph.metrics.documents_processed, 1)
        self.assertEqual(graph.metrics.mentions_without_candidates, 1)

    def test_builder_does_not_modify_input_objects(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        extraction_run = self._extraction_run("doc-1", "ver-1", mention)
        resolution_run = self._resolution_run(mention, self._resolution(mention))
        decision = self._decision(mention, "concept-1", EquivalenceDecisionStatus.PENDING, revision=1)
        snapshot = (extraction_run, resolution_run, decision)

        self.builder.build((extraction_run,), (resolution_run,), (decision,))

        self.assertEqual((extraction_run, resolution_run, decision), snapshot)

    def test_source_trace_remains_complete_and_stable(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        decision = self._decision(mention, "concept-1", EquivalenceDecisionStatus.APPROVED, revision=1)
        graph = self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (), (decision,))

        mention_node = next(node for node in graph.nodes if node.node_type == KnowledgeGraphNodeType.MENTION)
        decision_edge = next(
            edge for edge in graph.edges if edge.edge_type == KnowledgeGraphEdgeType.MENTION_TO_EQUIVALENCE_DECISION
        )
        self.assertEqual(mention_node.source_traces, (mention.source_trace,))
        self.assertEqual(decision_edge.source_traces, (decision.source_trace,))

    def test_edges_have_referential_integrity(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        graph = self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (), ())

        node_ids = {node.node_id for node in graph.nodes}
        for edge in graph.edges:
            self.assertIn(edge.source_node_id, node_ids)
            self.assertIn(edge.target_node_id, node_ids)

    def test_graph_contains_no_duplicate_nodes(self) -> None:
        mention = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        resolution = self._resolution(
            mention,
            self._candidate("concept-1", code="hook_load", name="Hook Load", rank=1),
            self._candidate("concept-1", code="hook_load", name="Hook Load", rank=2),
        )
        graph = self.builder.build((self._extraction_run("doc-1", "ver-1", mention),), (self._resolution_run(mention, resolution),), ())

        self.assertEqual(len(graph.nodes), len({node.node_id for node in graph.nodes}))

    def test_graph_is_equivalent_across_input_orders(self) -> None:
        mention_a = self._mention("Hookload", document_seed="doc-a", fragment_seed="frag-a", start_offset=10)
        mention_b = self._mention("Flow", document_seed="doc-b", fragment_seed="frag-b", start_offset=4, entity_type=ExtractedEntityType.PHYSICAL_QUANTITY)
        decision_a = self._decision(mention_a, "concept-a", EquivalenceDecisionStatus.APPROVED, revision=1)
        decision_b = self._decision(mention_b, "concept-b", EquivalenceDecisionStatus.PENDING, revision=1)
        resolution_a = self._resolution(mention_a, self._candidate("concept-a", code="hook_load", name="Hook Load", rank=1))
        resolution_b = self._resolution(mention_b)

        first = self.builder.build(
            (self._extraction_run("doc-a", "ver-1", mention_a), self._extraction_run("doc-b", "ver-1", mention_b)),
            (self._resolution_run(mention_a, resolution_a), self._resolution_run(mention_b, resolution_b)),
            (decision_a, decision_b),
        )
        second = self.builder.build(
            (self._extraction_run("doc-b", "ver-1", mention_b), self._extraction_run("doc-a", "ver-1", mention_a)),
            (self._resolution_run(mention_b, resolution_b), self._resolution_run(mention_a, resolution_a)),
            (decision_b, decision_a),
        )

        self.assertEqual(first, second)

    def _mention(
        self,
        text: str,
        *,
        document_seed: str,
        fragment_seed: str,
        start_offset: int,
        entity_type: ExtractedEntityType = ExtractedEntityType.VARIABLE,
    ) -> ExtractedEntity:
        return ExtractedEntity(
            entity_id=EntityId.from_seed("knowledge_graph.test.mention", f"{document_seed}:{fragment_seed}:{text}:{start_offset}:{entity_type.value}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=text.lower(),
            document_position=f"fragment={fragment_seed}|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("knowledge_graph.test.fragment", fragment_seed),
            document_id=EntityId.from_seed("knowledge_graph.test.document", document_seed),
            version_id=EntityId.from_seed("knowledge_graph.test.version", f"{document_seed}:ver-1"),
            extraction_confidence=1.0,
            extraction_rule="test.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _extraction_run(self, document_seed: str, version_seed: str, *mentions: ExtractedEntity) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, 0, 0, 0)
        document_id = EntityId.from_seed("knowledge_graph.test.document", document_seed)
        version_id = EntityId.from_seed("knowledge_graph.test.version", f"{document_seed}:{version_seed}")
        normalized_mentions = tuple(
            mention if mention.version_id == version_id else ExtractedEntity(
                entity_id=mention.entity_id,
                entity_type=mention.entity_type,
                original_text=mention.original_text,
                normalized_text=mention.normalized_text,
                document_position=mention.document_position,
                fragment_id=mention.fragment_id,
                document_id=document_id,
                version_id=version_id,
                extraction_confidence=mention.extraction_confidence,
                extraction_rule=mention.extraction_rule,
                source_trace=mention.source_trace,
                context_window=mention.context_window,
            )
            for mention in mentions
        )
        return ExtractionRun(
            run_id=EntityId.from_seed("knowledge_graph.test.run", f"{document_seed}:{version_seed}"),
            document_id=document_id,
            version_id=version_id,
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=normalized_mentions,
            metrics=ExtractionMetrics(total_entities=len(normalized_mentions), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0),
        )

    def _candidate(self, concept_seed: str, *, code: str, name: str, rank: int) -> CandidateConcept:
        concept_id = EntityId.from_seed("knowledge_graph.test.concept", concept_seed)
        evidence = CandidateEvidence(
            evidence_type=ResolutionEvidenceType.EXACT_NAME,
            matched_text=name,
            normalized_matched_text=name.lower(),
            source_field="canonical_name",
            explanation="exact name match",
        )
        return CandidateConcept(
            candidate_id=EntityId.from_seed("knowledge_graph.test.candidate", f"{concept_seed}:{rank}"),
            catalog_entity_id=concept_id,
            catalog_entity_type="Variable",
            catalog_code=code,
            canonical_name=name,
            rank=rank,
            evidence=evidence,
            supporting_evidences=(evidence,),
        )

    def _resolution(self, mention: ExtractedEntity, *candidates: CandidateConcept) -> MentionResolution:
        status = ResolutionStatus.UNRESOLVED if not candidates else ResolutionStatus.RESOLVED_CANDIDATE
        return MentionResolution(
            resolution_id=EntityId.from_seed("knowledge_graph.test.resolution", f"{mention.entity_id}:{status.value}"),
            mention=mention,
            status=status,
            candidates=tuple(candidates),
        )

    def _resolution_run(self, mention: ExtractedEntity, *resolutions: MentionResolution) -> ResolutionRun:
        run_time = datetime(2026, 1, 1, 0, 0, 0)
        return ResolutionRun(
            run_id=EntityId.from_seed("knowledge_graph.test.resolution_run", str(mention.document_id)),
            started_at=run_time,
            finished_at=run_time,
            mention_resolutions=tuple(resolutions),
            errors=(),
        )

    def _decision(
        self,
        mention: ExtractedEntity,
        concept_seed: str,
        status: EquivalenceDecisionStatus,
        *,
        revision: int,
    ) -> EquivalenceDecision:
        concept_id = EntityId.from_seed("knowledge_graph.test.concept", concept_seed)
        return EquivalenceDecision(
            decision_id=EntityId.from_seed("knowledge_graph.test.decision", f"{mention.entity_id}:{concept_id}:{revision}:{status.value}"),
            mention_id=mention.entity_id,
            catalog_entity_id=concept_id,
            status=status,
            evidence="manual-review",
            rationale="validated",
            decided_by="qa.engineer",
            decided_at=datetime(2026, 1, 1, 12, 0, 0),
            source_trace=mention.source_trace,
            revision=revision,
        )