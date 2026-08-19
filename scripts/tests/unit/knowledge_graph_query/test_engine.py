from __future__ import annotations

from dataclasses import replace
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
from drilling_knowledge.knowledge_graph import KnowledgeGraph, KnowledgeGraphBuilder, KnowledgeGraphEdge, KnowledgeGraphEdgeType, KnowledgeGraphNode, KnowledgeGraphNodeType
from drilling_knowledge.knowledge_graph_query import KnowledgeGraphQueryEngine
from drilling_knowledge.resolution.domain import (
    CandidateConcept,
    CandidateEvidence,
    MentionResolution,
    ResolutionEvidenceType,
    ResolutionRun,
    ResolutionStatus,
)


class KnowledgeGraphQueryEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = KnowledgeGraphBuilder.create()

    def test_empty_graph_queries(self) -> None:
        engine = KnowledgeGraphQueryEngine.create(KnowledgeGraph())

        self.assertIsNone(engine.get_node(EntityId.from_seed("query.test", "missing")))
        self.assertEqual(engine.list_nodes_by_type(KnowledgeGraphNodeType.MENTION), ())
        self.assertEqual(engine.list_edges_by_type(KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE), ())
        self.assertEqual(engine.mentions_without_candidates(), ())

    def test_nonexistent_node_raises_for_neighbor_queries(self) -> None:
        engine = KnowledgeGraphQueryEngine.create(KnowledgeGraph())

        with self.assertRaises(ValueError):
            engine.outgoing_neighbors(EntityId.from_seed("query.test", "missing"))

    def test_list_queries_by_type_are_stable(self) -> None:
        graph, mention_a, mention_b, _, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)

        mentions = engine.list_nodes_by_type(KnowledgeGraphNodeType.MENTION)
        self.assertEqual([node.external_id for node in mentions], sorted([mention_a.entity_id, mention_b.entity_id], key=str))

    def test_incoming_and_outgoing_neighbors(self) -> None:
        graph, mention_a, _, _, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)
        mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id)

        outgoing_types = [node.node_type for node in engine.outgoing_neighbors(mention_node_id)]
        incoming_types = [node.node_type for node in engine.incoming_neighbors(mention_node_id)]

        self.assertIn(KnowledgeGraphNodeType.CONCEPT, outgoing_types)
        self.assertIn(KnowledgeGraphNodeType.EQUIVALENCE_DECISION, outgoing_types)
        self.assertIn(KnowledgeGraphNodeType.FRAGMENT, incoming_types)

    def test_documents_and_versions_related_to_mention(self) -> None:
        graph, mention_a, _, _, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)
        mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id)

        context = engine.mention_documents_and_versions(mention_node_id)
        self.assertEqual(context.mention.external_id, mention_a.entity_id)
        self.assertEqual(len(context.documents), 1)
        self.assertEqual(len(context.fragments), 1)

    def test_fragments_candidates_and_decisions_for_mention(self) -> None:
        graph, mention_a, _, _, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)
        mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id)

        self.assertEqual(len(engine.fragments_for_mention(mention_node_id)), 1)
        self.assertEqual(len(engine.candidates_for_mention(mention_node_id)), 1)
        self.assertEqual(len(engine.equivalence_decisions_for_mention(mention_node_id)), 2)

    def test_approved_concept_for_mention(self) -> None:
        graph, mention_a, _, concept_a, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)

        approved = engine.approved_concept_for_mention(self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id))
        self.assertIsNotNone(approved)
        self.assertEqual(approved.external_id, concept_a.catalog_entity_id)

    def test_mentions_for_concept(self) -> None:
        graph, mention_a, mention_b, concept_a, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)

        mentions = engine.mentions_for_concept(self._node_id(KnowledgeGraphNodeType.CONCEPT, concept_a.catalog_entity_id))
        self.assertEqual([node.external_id for node in mentions], [mention_a.entity_id])

    def test_mentions_without_candidates(self) -> None:
        graph, _, mention_b, _, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)

        mentions = engine.mentions_without_candidates()
        self.assertEqual([node.external_id for node in mentions], [mention_b.entity_id])

    def test_decisions_by_status(self) -> None:
        graph, _, _, _, decision_rejected = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)

        self.assertEqual(len(engine.decisions_by_status(EquivalenceDecisionStatus.APPROVED)), 1)
        self.assertEqual(len(engine.decisions_by_status(EquivalenceDecisionStatus.PENDING)), 1)
        rejected = engine.decisions_by_status(EquivalenceDecisionStatus.REJECTED)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].external_id, decision_rejected.decision_id)

    def test_traceability_from_mention_and_concept(self) -> None:
        graph, mention_a, _, concept_a, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)

        mention_trace = engine.traceability_for_mention(self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id))
        concept_trace = engine.traceability_for_concept(self._node_id(KnowledgeGraphNodeType.CONCEPT, concept_a.catalog_entity_id))

        self.assertTrue(any(node.node_type == KnowledgeGraphNodeType.DOCUMENT for node in mention_trace.nodes))
        self.assertTrue(any(node.node_type == KnowledgeGraphNodeType.FRAGMENT for node in mention_trace.nodes))
        self.assertTrue(any(node.node_type == KnowledgeGraphNodeType.MENTION for node in concept_trace.nodes))
        self.assertTrue(any(node.node_type == KnowledgeGraphNodeType.DOCUMENT for node in concept_trace.nodes))

    def test_multiple_versions_of_same_document_are_preserved(self) -> None:
        mention_v1 = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-1", start_offset=10)
        mention_v2 = self._mention("Hookload", document_seed="doc-1", fragment_seed="frag-2", start_offset=20)
        graph = self.builder.build(
            (self._extraction_run("doc-1", "ver-1", mention_v1), self._extraction_run("doc-1", "ver-2", mention_v2)),
            (),
            (),
        )
        engine = KnowledgeGraphQueryEngine.create(graph)

        documents = engine.list_nodes_by_type(KnowledgeGraphNodeType.DOCUMENT)
        self.assertEqual(len(documents), 2)

    def test_cycles_do_not_loop_infinitely(self) -> None:
        graph, mention_a, _, _, _ = self._graph_fixture()
        mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id)
        mention_node = next(node for node in graph.nodes if node.node_id == mention_node_id)
        cycle_edge = KnowledgeGraphEdge(
            edge_id=EntityId.from_seed("query.test.edge", "cycle"),
            edge_type=KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE,
            source_node_id=mention_node_id,
            target_node_id=mention_node_id,
            source_traces=mention_node.source_traces,
            attributes=(("rank", 0),),
        )
        cyclic_graph = KnowledgeGraph(nodes=graph.nodes, edges=graph.edges + (cycle_edge,), metrics=graph.metrics)
        engine = KnowledgeGraphQueryEngine.create(cyclic_graph)

        traversal = engine.traceability_for_mention(mention_node_id, max_depth=4)
        self.assertTrue(any(node.node_id == mention_node_id for node in traversal.nodes))

    def test_traversal_depth_limit(self) -> None:
        graph, mention_a, _, concept_a, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph, max_traversal_depth=1)

        traversal = engine.traceability_for_concept(self._node_id(KnowledgeGraphNodeType.CONCEPT, concept_a.catalog_entity_id))
        self.assertFalse(any(node.node_type == KnowledgeGraphNodeType.DOCUMENT for node in traversal.nodes if node.node_id != traversal.root.node_id))

    def test_order_stability_and_idempotence(self) -> None:
        graph, mention_a, _, _, _ = self._graph_fixture()
        engine = KnowledgeGraphQueryEngine.create(graph)
        mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id)

        first = engine.traceability_for_mention(mention_node_id)
        second = engine.traceability_for_mention(mention_node_id)
        self.assertEqual(first, second)

    def test_results_are_deduplicated(self) -> None:
        graph, mention_a, _, _, _ = self._graph_fixture()
        mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id)
        duplicate_edge = next(edge for edge in graph.edges if edge.edge_type == KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE)
        duplicate_graph = KnowledgeGraph(nodes=graph.nodes, edges=graph.edges + (duplicate_edge,), metrics=graph.metrics)
        engine = KnowledgeGraphQueryEngine.create(duplicate_graph)

        self.assertEqual(len(engine.candidates_for_mention(mention_node_id)), 1)

    def test_graph_is_not_mutated_by_queries(self) -> None:
        graph, mention_a, _, concept_a, _ = self._graph_fixture()
        snapshot = (graph.nodes, graph.edges, graph.metrics)
        engine = KnowledgeGraphQueryEngine.create(graph)

        engine.traceability_for_mention(self._node_id(KnowledgeGraphNodeType.MENTION, mention_a.entity_id))
        engine.traceability_for_concept(self._node_id(KnowledgeGraphNodeType.CONCEPT, concept_a.catalog_entity_id))

        self.assertEqual((graph.nodes, graph.edges, graph.metrics), snapshot)

    def test_invalid_graph_references_raise_explicitly(self) -> None:
        node = KnowledgeGraphNode(
            node_id=EntityId.from_seed("query.test.node", "a"),
            node_type=KnowledgeGraphNodeType.MENTION,
            external_id=EntityId.from_seed("query.test.external", "a"),
        )
        edge = KnowledgeGraphEdge(
            edge_id=EntityId.from_seed("query.test.edge", "broken"),
            edge_type=KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE,
            source_node_id=node.node_id,
            target_node_id=EntityId.from_seed("query.test.node", "missing"),
        )
        with self.assertRaises(ValueError):
            KnowledgeGraphQueryEngine.create(KnowledgeGraph(nodes=(node,), edges=(edge,)))

    def _graph_fixture(self):
        mention_a = self._mention("Hookload", document_seed="doc-a", fragment_seed="frag-a", start_offset=10)
        mention_b = self._mention("Flow", document_seed="doc-b", fragment_seed="frag-b", start_offset=4, entity_type=ExtractedEntityType.PHYSICAL_QUANTITY)
        concept_a = self._candidate("concept-a", code="hook_load", name="Hook Load", rank=1)
        decision_approved = self._decision(mention_a, "concept-a", EquivalenceDecisionStatus.APPROVED, revision=2)
        decision_pending = self._decision(mention_a, "concept-a", EquivalenceDecisionStatus.PENDING, revision=1)
        decision_rejected = self._decision(mention_b, "concept-a", EquivalenceDecisionStatus.REJECTED, revision=1)
        graph = self.builder.build(
            (self._extraction_run("doc-a", "ver-1", mention_a), self._extraction_run("doc-b", "ver-1", mention_b)),
            (
                self._resolution_run(mention_a, self._resolution(mention_a, concept_a)),
                self._resolution_run(mention_b, self._resolution(mention_b)),
            ),
            (decision_pending, decision_approved, decision_rejected),
        )
        return graph, mention_a, mention_b, concept_a, decision_rejected

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
            entity_id=EntityId.from_seed("knowledge_graph_query.test.mention", f"{document_seed}:{fragment_seed}:{text}:{start_offset}:{entity_type.value}"),
            entity_type=entity_type,
            original_text=text,
            normalized_text=text.lower(),
            document_position=f"fragment={fragment_seed}|span={start_offset}:{start_offset + len(text)}",
            fragment_id=EntityId.from_seed("knowledge_graph_query.test.fragment", fragment_seed),
            document_id=EntityId.from_seed("knowledge_graph_query.test.document", document_seed),
            version_id=EntityId.from_seed("knowledge_graph_query.test.version", f"{document_seed}:ver-1"),
            extraction_confidence=1.0,
            extraction_rule="test.rule",
            source_trace=ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=start_offset, end_offset=start_offset + len(text)),
            context_window=ContextWindow(match_text=text),
        )

    def _extraction_run(self, document_seed: str, version_seed: str, *mentions: ExtractedEntity) -> ExtractionRun:
        run_time = datetime(2026, 1, 1, 0, 0, 0)
        document_id = EntityId.from_seed("knowledge_graph_query.test.document", document_seed)
        version_id = EntityId.from_seed("knowledge_graph_query.test.version", f"{document_seed}:{version_seed}")
        normalized_mentions = tuple(
            mention if mention.version_id == version_id else replace(
                mention,
                document_id=document_id,
                version_id=version_id,
            )
            for mention in mentions
        )
        return ExtractionRun(
            run_id=EntityId.from_seed("knowledge_graph_query.test.run", f"{document_seed}:{version_seed}"),
            document_id=document_id,
            version_id=version_id,
            started_at=run_time,
            finished_at=run_time,
            status=ExtractionRunStatus.COMPLETED,
            entities=normalized_mentions,
            metrics=ExtractionMetrics(total_entities=len(normalized_mentions), entity_counts_by_type={}, entity_counts_by_rule={}, document_counts={}, records=(), duration_ms=0.0),
        )

    def _candidate(self, concept_seed: str, *, code: str, name: str, rank: int) -> CandidateConcept:
        concept_id = EntityId.from_seed("knowledge_graph_query.test.concept", concept_seed)
        evidence = CandidateEvidence(
            evidence_type=ResolutionEvidenceType.EXACT_NAME,
            matched_text=name,
            normalized_matched_text=name.lower(),
            source_field="canonical_name",
            explanation="exact name match",
        )
        return CandidateConcept(
            candidate_id=EntityId.from_seed("knowledge_graph_query.test.candidate", f"{concept_seed}:{rank}"),
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
            resolution_id=EntityId.from_seed("knowledge_graph_query.test.resolution", f"{mention.entity_id}:{status.value}"),
            mention=mention,
            status=status,
            candidates=tuple(candidates),
        )

    def _resolution_run(self, mention: ExtractedEntity, *resolutions: MentionResolution) -> ResolutionRun:
        run_time = datetime(2026, 1, 1, 0, 0, 0)
        return ResolutionRun(
            run_id=EntityId.from_seed("knowledge_graph_query.test.resolution_run", str(mention.document_id)),
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
        concept_id = EntityId.from_seed("knowledge_graph_query.test.concept", concept_seed)
        return EquivalenceDecision(
            decision_id=EntityId.from_seed("knowledge_graph_query.test.decision", f"{mention.entity_id}:{concept_id}:{revision}:{status.value}"),
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

    def _node_id(self, node_type: KnowledgeGraphNodeType, external_id: EntityId) -> EntityId:
        return EntityId.from_seed("knowledge_graph.node", f"{node_type.value}:{external_id}")