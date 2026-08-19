"""Deterministic knowledge graph builder."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence.domain import EquivalenceDecision, EquivalenceDecisionStatus
from drilling_knowledge.extraction.domain import ExtractedEntity, ExtractionRun, ExtractionSourceTrace
from drilling_knowledge.knowledge_graph.domain import (
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphEdgeType,
    KnowledgeGraphMetrics,
    KnowledgeGraphNode,
    KnowledgeGraphNodeType,
)
from drilling_knowledge.resolution.domain import CandidateConcept, MentionResolution, ResolutionRun


@dataclass(slots=True)
class KnowledgeGraphBuilder:
    @classmethod
    def create(cls) -> "KnowledgeGraphBuilder":
        return cls()

    def build(
        self,
        extraction_runs: tuple[ExtractionRun, ...] | list[ExtractionRun],
        resolution_runs: tuple[ResolutionRun, ...] | list[ResolutionRun],
        equivalence_decisions: tuple[EquivalenceDecision, ...] | list[EquivalenceDecision],
    ) -> KnowledgeGraph:
        extraction_runs = tuple(extraction_runs)
        resolution_runs = tuple(resolution_runs)
        equivalence_decisions = tuple(equivalence_decisions)

        mentions_by_id = self._collect_mentions(extraction_runs, resolution_runs)
        documents = self._collect_documents(extraction_runs, mentions_by_id)
        fragment_traces = self._collect_fragment_traces(mentions_by_id)
        concept_metadata = self._collect_concept_metadata(resolution_runs)
        concept_traces = self._collect_concept_traces(resolution_runs, equivalence_decisions)

        node_map: dict[tuple[KnowledgeGraphNodeType, EntityId], KnowledgeGraphNode] = {}
        edge_map: dict[tuple[KnowledgeGraphEdgeType, EntityId, EntityId], KnowledgeGraphEdge] = {}

        for document_key in sorted(documents, key=self._document_key_sort_key):
            node = self._build_document_node(document_key, documents[document_key])
            self._insert_node(node_map, node)

        for fragment_id, traces in sorted(fragment_traces.items(), key=lambda item: str(item[0])):
            mention = self._first_mention_for_fragment(fragment_id, mentions_by_id)
            fragment_external_id = self._fragment_external_id(mention)
            node = self._build_fragment_node(fragment_external_id, mention.fragment_id, mention.document_id, mention.version_id, traces)
            self._insert_node(node_map, node)
            edge = self._build_edge(
                KnowledgeGraphEdgeType.DOCUMENT_TO_FRAGMENT,
                self._document_node_id(mention.document_id, mention.version_id),
                node.node_id,
                traces,
                attributes=(("document_id", str(mention.document_id)), ("version_id", str(mention.version_id))),
            )
            self._insert_edge(edge_map, edge)

        for mention in sorted(mentions_by_id.values(), key=self._mention_sort_key):
            node = self._build_mention_node(mention)
            self._insert_node(node_map, node)
            fragment_node_id = self._fragment_node_id(mention)
            edge = self._build_edge(
                KnowledgeGraphEdgeType.FRAGMENT_TO_MENTION,
                fragment_node_id,
                node.node_id,
                (mention.source_trace,),
                attributes=(("entity_type", mention.entity_type.value),),
            )
            self._insert_edge(edge_map, edge)

        for resolution in self._sorted_resolutions(resolution_runs):
            for candidate in self._deduplicated_candidates(resolution.candidates):
                traces = concept_traces.get(candidate.catalog_entity_id, (resolution.mention.source_trace,))
                node = self._build_concept_node(candidate.catalog_entity_id, concept_metadata.get(candidate.catalog_entity_id, ()), traces)
                self._insert_node(node_map, node)
                edge = self._build_edge(
                    KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE,
                    self._node_id(KnowledgeGraphNodeType.MENTION, resolution.mention.entity_id),
                    node.node_id,
                    (resolution.mention.source_trace,),
                    attributes=(
                        ("rank", candidate.rank),
                        ("resolution_status", resolution.status.value),
                    ),
                )
                self._insert_edge(edge_map, edge)

        for decision in sorted(equivalence_decisions, key=self._decision_sort_key):
            decision_node = self._build_decision_node(decision)
            self._insert_node(node_map, decision_node)
            mention_node_id = self._node_id(KnowledgeGraphNodeType.MENTION, decision.mention_id)
            if (KnowledgeGraphNodeType.MENTION, decision.mention_id) in node_map:
                edge = self._build_edge(
                    KnowledgeGraphEdgeType.MENTION_TO_EQUIVALENCE_DECISION,
                    mention_node_id,
                    decision_node.node_id,
                    (decision.source_trace,),
                    attributes=(("status", decision.status.value), ("revision", decision.revision)),
                )
                self._insert_edge(edge_map, edge)

            if decision.status == EquivalenceDecisionStatus.APPROVED:
                traces = concept_traces.get(decision.catalog_entity_id, (decision.source_trace,))
                concept_node = self._build_concept_node(decision.catalog_entity_id, concept_metadata.get(decision.catalog_entity_id, ()), traces)
                self._insert_node(node_map, concept_node)
                edge = self._build_edge(
                    KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT,
                    decision_node.node_id,
                    concept_node.node_id,
                    (decision.source_trace,),
                    attributes=(("status", decision.status.value), ("revision", decision.revision)),
                )
                self._insert_edge(edge_map, edge)

        nodes = tuple(sorted(node_map.values(), key=self._node_sort_key))
        edges = tuple(sorted(edge_map.values(), key=self._edge_sort_key))
        self._validate_referential_integrity(nodes, edges)
        decision_nodes = [node for node in nodes if node.node_type == KnowledgeGraphNodeType.EQUIVALENCE_DECISION]
        mention_to_candidate_sources = {
            edge.source_node_id for edge in edges if edge.edge_type == KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE
        }
        mention_nodes = [node for node in nodes if node.node_type == KnowledgeGraphNodeType.MENTION]
        metrics = KnowledgeGraphMetrics(
            node_counts_by_type=dict(Counter(node.node_type.value for node in nodes)),
            relation_counts_by_type=dict(Counter(edge.edge_type.value for edge in edges)),
            documents_processed=len({node.external_id for node in nodes if node.node_type == KnowledgeGraphNodeType.DOCUMENT}),
            mentions_without_candidates=sum(1 for node in mention_nodes if node.node_id not in mention_to_candidate_sources),
            approved_decisions=sum(1 for node in decision_nodes if self._node_attribute(node, "status") == EquivalenceDecisionStatus.APPROVED.value),
            rejected_decisions=sum(1 for node in decision_nodes if self._node_attribute(node, "status") == EquivalenceDecisionStatus.REJECTED.value),
            pending_decisions=sum(1 for node in decision_nodes if self._node_attribute(node, "status") == EquivalenceDecisionStatus.PENDING.value),
        )
        return KnowledgeGraph(nodes=nodes, edges=edges, metrics=metrics)

    def _collect_mentions(
        self,
        extraction_runs: tuple[ExtractionRun, ...],
        resolution_runs: tuple[ResolutionRun, ...],
    ) -> dict[EntityId, ExtractedEntity]:
        mentions: dict[EntityId, ExtractedEntity] = {}
        for extraction_run in extraction_runs:
            for mention in extraction_run.entities:
                self._merge_mention(mentions, mention)
        for resolution_run in resolution_runs:
            for resolution in resolution_run.mention_resolutions:
                self._merge_mention(mentions, resolution.mention)
        return mentions

    def _collect_documents(
        self,
        extraction_runs: tuple[ExtractionRun, ...],
        mentions_by_id: dict[EntityId, ExtractedEntity],
    ) -> dict[tuple[EntityId, EntityId], tuple[ExtractionSourceTrace, ...]]:
        traces_by_document_version: dict[tuple[EntityId, EntityId], list[ExtractionSourceTrace]] = {}
        for extraction_run in extraction_runs:
            traces_by_document_version.setdefault((extraction_run.document_id, extraction_run.version_id), [])
        for mention in mentions_by_id.values():
            traces_by_document_version.setdefault((mention.document_id, mention.version_id), []).append(mention.source_trace)
        return {
            document_key: self._unique_traces(values)
            for document_key, values in traces_by_document_version.items()
        }

    def _collect_fragment_traces(self, mentions_by_id: dict[EntityId, ExtractedEntity]) -> dict[EntityId, tuple[ExtractionSourceTrace, ...]]:
        traces: dict[EntityId, list[ExtractionSourceTrace]] = {}
        for mention in mentions_by_id.values():
            traces.setdefault(mention.fragment_id, []).append(mention.source_trace)
        return {fragment_id: self._unique_traces(values) for fragment_id, values in traces.items()}

    def _collect_concept_metadata(self, resolution_runs: tuple[ResolutionRun, ...]) -> dict[EntityId, tuple[tuple[str, object], ...]]:
        metadata: dict[EntityId, tuple[tuple[str, object], ...]] = {}
        for resolution in self._sorted_resolutions(resolution_runs):
            for candidate in resolution.candidates:
                candidate_metadata = self._concept_attributes(candidate)
                existing = metadata.get(candidate.catalog_entity_id)
                if existing is None:
                    metadata[candidate.catalog_entity_id] = candidate_metadata
                elif existing != candidate_metadata:
                    raise ValueError("Conflicting concept metadata detected for knowledge graph construction")
        return metadata

    def _collect_concept_traces(
        self,
        resolution_runs: tuple[ResolutionRun, ...],
        equivalence_decisions: tuple[EquivalenceDecision, ...],
    ) -> dict[EntityId, tuple[ExtractionSourceTrace, ...]]:
        traces: dict[EntityId, list[ExtractionSourceTrace]] = {}
        for resolution in self._sorted_resolutions(resolution_runs):
            for candidate in resolution.candidates:
                traces.setdefault(candidate.catalog_entity_id, []).append(resolution.mention.source_trace)
        for decision in equivalence_decisions:
            if decision.status == EquivalenceDecisionStatus.APPROVED:
                traces.setdefault(decision.catalog_entity_id, []).append(decision.source_trace)
        return {concept_id: self._unique_traces(values) for concept_id, values in traces.items()}

    def _build_document_node(
        self,
        document_key: tuple[EntityId, EntityId],
        traces: tuple[ExtractionSourceTrace, ...],
    ) -> KnowledgeGraphNode:
        document_id, version_id = document_key
        external_id = self._document_external_id(document_id, version_id)
        return KnowledgeGraphNode(
            node_id=self._node_id(KnowledgeGraphNodeType.DOCUMENT, external_id),
            node_type=KnowledgeGraphNodeType.DOCUMENT,
            external_id=external_id,
            source_traces=traces,
            attributes=(("document_id", str(document_id)), ("version_id", str(version_id))),
        )

    def _build_fragment_node(
        self,
        fragment_external_id: EntityId,
        fragment_id: EntityId,
        document_id: EntityId,
        version_id: EntityId,
        traces: tuple[ExtractionSourceTrace, ...],
    ) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=self._node_id(KnowledgeGraphNodeType.FRAGMENT, fragment_external_id),
            node_type=KnowledgeGraphNodeType.FRAGMENT,
            external_id=fragment_external_id,
            source_traces=traces,
            attributes=(("fragment_id", str(fragment_id)), ("document_id", str(document_id)), ("version_id", str(version_id))),
        )

    def _build_mention_node(self, mention: ExtractedEntity) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=self._node_id(KnowledgeGraphNodeType.MENTION, mention.entity_id),
            node_type=KnowledgeGraphNodeType.MENTION,
            external_id=mention.entity_id,
            source_traces=(mention.source_trace,),
            attributes=(
                ("entity_type", mention.entity_type.value),
                ("document_id", str(mention.document_id)),
                ("version_id", str(mention.version_id)),
                ("fragment_id", str(mention.fragment_id)),
                ("original_text", mention.original_text),
                ("normalized_text", mention.normalized_text),
                ("document_position", mention.document_position),
            ),
        )

    def _build_concept_node(
        self,
        catalog_entity_id: EntityId,
        attributes: tuple[tuple[str, object], ...],
        traces: tuple[ExtractionSourceTrace, ...],
    ) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=self._node_id(KnowledgeGraphNodeType.CONCEPT, catalog_entity_id),
            node_type=KnowledgeGraphNodeType.CONCEPT,
            external_id=catalog_entity_id,
            source_traces=traces,
            attributes=attributes,
        )

    def _build_decision_node(self, decision: EquivalenceDecision) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=self._node_id(KnowledgeGraphNodeType.EQUIVALENCE_DECISION, decision.decision_id),
            node_type=KnowledgeGraphNodeType.EQUIVALENCE_DECISION,
            external_id=decision.decision_id,
            source_traces=(decision.source_trace,),
            attributes=(
                ("mention_id", str(decision.mention_id)),
                ("catalog_entity_id", str(decision.catalog_entity_id)),
                ("status", decision.status.value),
                ("revision", decision.revision),
                ("decided_by", decision.decided_by),
                ("decided_at", decision.decided_at.isoformat()),
                ("evidence", decision.evidence),
                ("rationale", decision.rationale),
            ),
        )

    def _build_edge(
        self,
        edge_type: KnowledgeGraphEdgeType,
        source_node_id: EntityId,
        target_node_id: EntityId,
        traces: tuple[ExtractionSourceTrace, ...],
        *,
        attributes: tuple[tuple[str, object], ...] = (),
    ) -> KnowledgeGraphEdge:
        return KnowledgeGraphEdge(
            edge_id=EntityId.from_seed("knowledge_graph.edge", f"{edge_type.value}:{source_node_id}:{target_node_id}"),
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            source_traces=self._unique_traces(traces),
            attributes=attributes,
        )

    def _concept_attributes(self, candidate: CandidateConcept) -> tuple[tuple[str, object], ...]:
        return (
            ("catalog_entity_type", candidate.catalog_entity_type),
            ("catalog_code", candidate.catalog_code),
            ("canonical_name", candidate.canonical_name),
        )

    def _deduplicated_candidates(self, candidates: tuple[CandidateConcept, ...]) -> tuple[CandidateConcept, ...]:
        deduplicated: dict[EntityId, CandidateConcept] = {}
        for candidate in candidates:
            existing = deduplicated.get(candidate.catalog_entity_id)
            if existing is None:
                deduplicated[candidate.catalog_entity_id] = candidate
                continue
            if self._concept_attributes(existing) != self._concept_attributes(candidate):
                raise ValueError("Conflicting candidate concept metadata detected for the same concept identity")
            if candidate.rank < existing.rank:
                deduplicated[candidate.catalog_entity_id] = candidate
        return tuple(sorted(deduplicated.values(), key=lambda candidate: (candidate.rank, str(candidate.catalog_entity_id))))

    def _merge_mention(self, mentions: dict[EntityId, ExtractedEntity], mention: ExtractedEntity) -> None:
        existing = mentions.get(mention.entity_id)
        if existing is None:
            mentions[mention.entity_id] = mention
            return
        if existing != mention:
            raise ValueError("Conflicting mention payload detected for knowledge graph construction")

    def _insert_node(
        self,
        node_map: dict[tuple[KnowledgeGraphNodeType, EntityId], KnowledgeGraphNode],
        node: KnowledgeGraphNode,
    ) -> None:
        key = (node.node_type, node.external_id)
        existing = node_map.get(key)
        if existing is None:
            node_map[key] = node
            return
        if existing != node:
            raise ValueError("Conflicting knowledge graph node detected for the same identity")

    def _insert_edge(
        self,
        edge_map: dict[tuple[KnowledgeGraphEdgeType, EntityId, EntityId], KnowledgeGraphEdge],
        edge: KnowledgeGraphEdge,
    ) -> None:
        key = (edge.edge_type, edge.source_node_id, edge.target_node_id)
        existing = edge_map.get(key)
        if existing is None:
            edge_map[key] = edge
            return
        if existing != edge:
            raise ValueError("Conflicting knowledge graph edge detected for the same identity")

    def _first_mention_for_fragment(self, fragment_id: EntityId, mentions_by_id: dict[EntityId, ExtractedEntity]) -> ExtractedEntity:
        return min(
            (mention for mention in mentions_by_id.values() if mention.fragment_id == fragment_id),
            key=self._mention_sort_key,
        )

    def _sorted_resolutions(self, resolution_runs: tuple[ResolutionRun, ...]) -> tuple[MentionResolution, ...]:
        resolutions = [resolution for run in resolution_runs for resolution in run.mention_resolutions]
        return tuple(sorted(resolutions, key=lambda resolution: self._mention_sort_key(resolution.mention)))

    def _unique_traces(self, traces: tuple[ExtractionSourceTrace, ...] | list[ExtractionSourceTrace]) -> tuple[ExtractionSourceTrace, ...]:
        unique: dict[tuple[object, ...], ExtractionSourceTrace] = {}
        for trace in traces:
            unique.setdefault(self._trace_key(trace), trace)
        return tuple(unique[key] for key in sorted(unique))

    def _trace_key(self, trace: ExtractionSourceTrace) -> tuple[object, ...]:
        return (
            trace.page_number,
            str(trace.section_id) if trace.section_id is not None else "",
            str(trace.table_id) if trace.table_id is not None else "",
            str(trace.figure_id) if trace.figure_id is not None else "",
            trace.paragraph_ordinal,
            trace.start_offset,
            trace.end_offset,
        )

    def _document_external_id(self, document_id: EntityId, version_id: EntityId) -> EntityId:
        return EntityId.from_seed("knowledge_graph.document", f"{document_id}:{version_id}")

    def _document_node_id(self, document_id: EntityId, version_id: EntityId) -> EntityId:
        return self._node_id(KnowledgeGraphNodeType.DOCUMENT, self._document_external_id(document_id, version_id))

    def _fragment_external_id(self, mention: ExtractedEntity) -> EntityId:
        return EntityId.from_seed("knowledge_graph.fragment", f"{mention.fragment_id}:{mention.document_id}:{mention.version_id}")

    def _fragment_node_id(self, mention: ExtractedEntity) -> EntityId:
        return self._node_id(KnowledgeGraphNodeType.FRAGMENT, self._fragment_external_id(mention))

    def _node_id(self, node_type: KnowledgeGraphNodeType, external_id: EntityId) -> EntityId:
        return EntityId.from_seed("knowledge_graph.node", f"{node_type.value}:{external_id}")

    def _document_key_sort_key(self, document_key: tuple[EntityId, EntityId]) -> tuple[str, str]:
        return (str(document_key[0]), str(document_key[1]))

    def _node_sort_key(self, node: KnowledgeGraphNode) -> tuple[str, str, str]:
        return (node.node_type.value, str(node.external_id), str(node.node_id))

    def _edge_sort_key(self, edge: KnowledgeGraphEdge) -> tuple[str, str, str, str]:
        return (edge.edge_type.value, str(edge.source_node_id), str(edge.target_node_id), str(edge.edge_id))

    def _mention_sort_key(self, mention: ExtractedEntity) -> tuple[str, str, int | None, int | None, str]:
        return (
            str(mention.document_id),
            str(mention.fragment_id),
            mention.source_trace.start_offset,
            mention.source_trace.end_offset,
            str(mention.entity_id),
        )

    def _decision_sort_key(self, decision: EquivalenceDecision) -> tuple[str, str, int, str]:
        return (
            str(decision.mention_id),
            str(decision.catalog_entity_id),
            decision.revision,
            str(decision.decision_id),
        )

    def _node_attribute(self, node: KnowledgeGraphNode, name: str) -> object | None:
        for key, value in node.attributes:
            if key == name:
                return value
        return None

    def _validate_referential_integrity(
        self,
        nodes: tuple[KnowledgeGraphNode, ...],
        edges: tuple[KnowledgeGraphEdge, ...],
    ) -> None:
        node_ids = {node.node_id for node in nodes}
        for edge in edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                raise ValueError("Knowledge graph edge references a missing node")
