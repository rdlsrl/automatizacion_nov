"""Deterministic read-only query engine for knowledge graphs."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence.domain import EquivalenceDecisionStatus
from drilling_knowledge.knowledge_graph.domain import (
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphEdgeType,
    KnowledgeGraphNode,
    KnowledgeGraphNodeType,
)
from drilling_knowledge.knowledge_graph_query.domain import (
    KnowledgeGraphQueryReport,
    KnowledgeGraphTraversal,
    MentionDocumentContext,
)


@dataclass(slots=True)
class KnowledgeGraphQueryEngine:
    graph: KnowledgeGraph
    max_traversal_depth: int = 8
    _nodes_by_id: dict[EntityId, KnowledgeGraphNode] = field(init=False, default_factory=dict)
    _nodes_by_type: dict[KnowledgeGraphNodeType, tuple[KnowledgeGraphNode, ...]] = field(init=False, default_factory=dict)
    _edges_by_id: dict[EntityId, KnowledgeGraphEdge] = field(init=False, default_factory=dict)
    _edges_by_type: dict[KnowledgeGraphEdgeType, tuple[KnowledgeGraphEdge, ...]] = field(init=False, default_factory=dict)
    _outgoing: dict[EntityId, tuple[KnowledgeGraphEdge, ...]] = field(init=False, default_factory=dict)
    _incoming: dict[EntityId, tuple[KnowledgeGraphEdge, ...]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_traversal_depth < 0:
            raise ValueError("max_traversal_depth must be >= 0")
        self._build_indexes()

    @classmethod
    def create(cls, graph: KnowledgeGraph, *, max_traversal_depth: int = 8) -> "KnowledgeGraphQueryEngine":
        return cls(graph=graph, max_traversal_depth=max_traversal_depth)

    def get_node(self, node_id: EntityId) -> KnowledgeGraphNode | None:
        return self._nodes_by_id.get(node_id)

    def list_nodes_by_type(self, node_type: KnowledgeGraphNodeType) -> tuple[KnowledgeGraphNode, ...]:
        return self._nodes_by_type.get(node_type, ())

    def list_edges_by_type(self, edge_type: KnowledgeGraphEdgeType) -> tuple[KnowledgeGraphEdge, ...]:
        return self._edges_by_type.get(edge_type, ())

    def outgoing_neighbors(self, node_id: EntityId) -> tuple[KnowledgeGraphNode, ...]:
        self._require_node(node_id)
        return self._deduplicated_nodes_by_edge_order(self._outgoing.get(node_id, ()), target=True)

    def incoming_neighbors(self, node_id: EntityId) -> tuple[KnowledgeGraphNode, ...]:
        self._require_node(node_id)
        return self._deduplicated_nodes_by_edge_order(self._incoming.get(node_id, ()), target=False)

    def mention_documents_and_versions(self, mention_id: EntityId) -> MentionDocumentContext:
        mention = self._require_typed_node(mention_id, KnowledgeGraphNodeType.MENTION)
        fragments = self.fragments_for_mention(mention_id)
        document_ids = []
        for fragment in fragments:
            for edge in self._incoming.get(fragment.node_id, ()):
                if edge.edge_type == KnowledgeGraphEdgeType.DOCUMENT_TO_FRAGMENT:
                    document_ids.append(edge.source_node_id)
        documents = tuple(self._nodes_by_id[node_id] for node_id in self._deduplicate_ids(document_ids))
        return MentionDocumentContext(mention=mention, documents=documents, fragments=fragments)

    def fragments_for_mention(self, mention_id: EntityId) -> tuple[KnowledgeGraphNode, ...]:
        self._require_typed_node(mention_id, KnowledgeGraphNodeType.MENTION)
        fragments = [self._nodes_by_id[edge.source_node_id] for edge in self._incoming.get(mention_id, ()) if edge.edge_type == KnowledgeGraphEdgeType.FRAGMENT_TO_MENTION]
        return self._sort_and_deduplicate_nodes(fragments)

    def candidates_for_mention(self, mention_id: EntityId) -> tuple[KnowledgeGraphNode, ...]:
        self._require_typed_node(mention_id, KnowledgeGraphNodeType.MENTION)
        candidates = [self._nodes_by_id[edge.target_node_id] for edge in self._outgoing.get(mention_id, ()) if edge.edge_type == KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE]
        return self._sort_and_deduplicate_nodes(candidates)

    def equivalence_decisions_for_mention(self, mention_id: EntityId) -> tuple[KnowledgeGraphNode, ...]:
        self._require_typed_node(mention_id, KnowledgeGraphNodeType.MENTION)
        decisions = [self._nodes_by_id[edge.target_node_id] for edge in self._outgoing.get(mention_id, ()) if edge.edge_type == KnowledgeGraphEdgeType.MENTION_TO_EQUIVALENCE_DECISION]
        return self._sort_and_deduplicate_nodes(decisions)

    def approved_concept_for_mention(self, mention_id: EntityId) -> KnowledgeGraphNode | None:
        approved_concepts = []
        for decision in self.equivalence_decisions_for_mention(mention_id):
            if self._node_attribute(decision, "status") != EquivalenceDecisionStatus.APPROVED.value:
                continue
            concept_edges = [edge for edge in self._outgoing.get(decision.node_id, ()) if edge.edge_type == KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT]
            approved_concepts.extend(self._nodes_by_id[edge.target_node_id] for edge in concept_edges)
        unique_concepts = self._sort_and_deduplicate_nodes(approved_concepts)
        return unique_concepts[0] if len(unique_concepts) == 1 else None

    def mentions_for_concept(self, concept_id: EntityId) -> tuple[KnowledgeGraphNode, ...]:
        self._require_typed_node(concept_id, KnowledgeGraphNodeType.CONCEPT)
        mentions: list[KnowledgeGraphNode] = []
        for edge in self._incoming.get(concept_id, ()):
            if edge.edge_type == KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE:
                mentions.append(self._nodes_by_id[edge.source_node_id])
            elif edge.edge_type == KnowledgeGraphEdgeType.EQUIVALENCE_DECISION_TO_CONCEPT:
                for incoming in self._incoming.get(edge.source_node_id, ()):
                    if incoming.edge_type == KnowledgeGraphEdgeType.MENTION_TO_EQUIVALENCE_DECISION:
                        mentions.append(self._nodes_by_id[incoming.source_node_id])
        return self._sort_and_deduplicate_nodes(mentions)

    def mentions_without_candidates(self) -> tuple[KnowledgeGraphNode, ...]:
        mentions = self.list_nodes_by_type(KnowledgeGraphNodeType.MENTION)
        candidate_sources = {edge.source_node_id for edge in self.list_edges_by_type(KnowledgeGraphEdgeType.MENTION_TO_CANDIDATE)}
        return tuple(node for node in mentions if node.node_id not in candidate_sources)

    def decisions_by_status(self, status: EquivalenceDecisionStatus) -> tuple[KnowledgeGraphNode, ...]:
        decisions = self.list_nodes_by_type(KnowledgeGraphNodeType.EQUIVALENCE_DECISION)
        return tuple(node for node in decisions if self._node_attribute(node, "status") == status.value)

    def traceability_for_mention(self, mention_id: EntityId, *, max_depth: int | None = None) -> KnowledgeGraphTraversal:
        root = self._require_typed_node(mention_id, KnowledgeGraphNodeType.MENTION)
        return self._trace(root, max_depth=max_depth)

    def traceability_for_concept(self, concept_id: EntityId, *, max_depth: int | None = None) -> KnowledgeGraphTraversal:
        root = self._require_typed_node(concept_id, KnowledgeGraphNodeType.CONCEPT)
        return self._trace(root, max_depth=max_depth)

    def report(self) -> KnowledgeGraphQueryReport:
        return KnowledgeGraphQueryReport(
            graph_node_count=len(self._nodes_by_id),
            graph_edge_count=len(self._edges_by_id),
            node_counts_by_type=dict(Counter(node.node_type.value for node in self._nodes_by_id.values())),
            edge_counts_by_type=dict(Counter(edge.edge_type.value for edge in self._edges_by_id.values())),
        )

    def _build_indexes(self) -> None:
        nodes_by_id: dict[EntityId, KnowledgeGraphNode] = {}
        nodes_by_type: dict[KnowledgeGraphNodeType, list[KnowledgeGraphNode]] = {}
        for node in self.graph.nodes:
            existing = nodes_by_id.get(node.node_id)
            if existing is None:
                nodes_by_id[node.node_id] = node
            elif existing != node:
                raise ValueError("Knowledge graph contains conflicting nodes for the same node_id")
            nodes_by_type.setdefault(node.node_type, []).append(node)

        edges_by_id: dict[EntityId, KnowledgeGraphEdge] = {}
        edges_by_type: dict[KnowledgeGraphEdgeType, list[KnowledgeGraphEdge]] = {}
        outgoing: dict[EntityId, list[KnowledgeGraphEdge]] = {}
        incoming: dict[EntityId, list[KnowledgeGraphEdge]] = {}
        for edge in self.graph.edges:
            existing = edges_by_id.get(edge.edge_id)
            if existing is None:
                edges_by_id[edge.edge_id] = edge
            elif existing != edge:
                raise ValueError("Knowledge graph contains conflicting edges for the same edge_id")
            if edge.source_node_id not in nodes_by_id or edge.target_node_id not in nodes_by_id:
                raise ValueError("Knowledge graph contains an edge with invalid node references")
            edges_by_type.setdefault(edge.edge_type, []).append(edge)
            outgoing.setdefault(edge.source_node_id, []).append(edge)
            incoming.setdefault(edge.target_node_id, []).append(edge)

        object.__setattr__(self, "_nodes_by_id", nodes_by_id)
        object.__setattr__(self, "_nodes_by_type", {key: tuple(sorted(values, key=self._node_sort_key)) for key, values in nodes_by_type.items()})
        object.__setattr__(self, "_edges_by_id", edges_by_id)
        object.__setattr__(self, "_edges_by_type", {key: tuple(sorted(values, key=self._edge_sort_key)) for key, values in edges_by_type.items()})
        object.__setattr__(self, "_outgoing", {key: tuple(sorted(values, key=self._edge_sort_key)) for key, values in outgoing.items()})
        object.__setattr__(self, "_incoming", {key: tuple(sorted(values, key=self._edge_sort_key)) for key, values in incoming.items()})

    def _trace(self, root: KnowledgeGraphNode, *, max_depth: int | None = None) -> KnowledgeGraphTraversal:
        depth_limit = self.max_traversal_depth if max_depth is None else max_depth
        if depth_limit < 0:
            raise ValueError("max_depth must be >= 0")
        visited_nodes = {root.node_id}
        visited_edges: dict[EntityId, KnowledgeGraphEdge] = {}
        queue: deque[tuple[EntityId, int]] = deque([(root.node_id, 0)])

        while queue:
            node_id, depth = queue.popleft()
            if depth >= depth_limit:
                continue
            adjacent_edges = list(self._outgoing.get(node_id, ())) + list(self._incoming.get(node_id, ()))
            for edge in sorted(adjacent_edges, key=self._edge_sort_key):
                visited_edges.setdefault(edge.edge_id, edge)
                neighbor_id = edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id
                if neighbor_id in visited_nodes:
                    continue
                visited_nodes.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))

        nodes = tuple(sorted((self._nodes_by_id[node_id] for node_id in visited_nodes), key=self._node_sort_key))
        edges = tuple(sorted(visited_edges.values(), key=self._edge_sort_key))
        return KnowledgeGraphTraversal(root=root, nodes=nodes, edges=edges, max_depth=depth_limit)

    def _require_node(self, node_id: EntityId) -> KnowledgeGraphNode:
        node = self.get_node(node_id)
        if node is None:
            raise ValueError(f"Knowledge graph node not found: {node_id}")
        return node

    def _require_typed_node(self, node_id: EntityId, node_type: KnowledgeGraphNodeType) -> KnowledgeGraphNode:
        node = self._require_node(node_id)
        if node.node_type != node_type:
            raise ValueError(f"Knowledge graph node {node_id} is not of type {node_type.value}")
        return node

    def _deduplicated_nodes_by_edge_order(self, edges: tuple[KnowledgeGraphEdge, ...], *, target: bool) -> tuple[KnowledgeGraphNode, ...]:
        node_ids = []
        for edge in edges:
            node_ids.append(edge.target_node_id if target else edge.source_node_id)
        return tuple(self._nodes_by_id[node_id] for node_id in self._deduplicate_ids(node_ids))

    def _sort_and_deduplicate_nodes(self, nodes: list[KnowledgeGraphNode]) -> tuple[KnowledgeGraphNode, ...]:
        unique: dict[EntityId, KnowledgeGraphNode] = {}
        for node in sorted(nodes, key=self._node_sort_key):
            existing = unique.get(node.node_id)
            if existing is None:
                unique[node.node_id] = node
            elif existing != node:
                raise ValueError("Knowledge graph query encountered conflicting nodes for the same node_id")
        return tuple(unique.values())

    def _deduplicate_ids(self, node_ids: list[EntityId]) -> tuple[EntityId, ...]:
        unique: dict[str, EntityId] = {}
        for node_id in sorted(node_ids, key=str):
            unique.setdefault(str(node_id), node_id)
        return tuple(unique.values())

    def _node_sort_key(self, node: KnowledgeGraphNode) -> tuple[str, str, str]:
        return (node.node_type.value, str(node.external_id), str(node.node_id))

    def _edge_sort_key(self, edge: KnowledgeGraphEdge) -> tuple[str, str, str, str]:
        return (edge.edge_type.value, str(edge.source_node_id), str(edge.target_node_id), str(edge.edge_id))

    def _node_attribute(self, node: KnowledgeGraphNode, name: str) -> object | None:
        for key, value in node.attributes:
            if key == name:
                return value
        return None
