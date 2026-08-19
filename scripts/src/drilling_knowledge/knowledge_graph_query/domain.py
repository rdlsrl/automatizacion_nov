"""Read-only query result types for deterministic knowledge graph access."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.knowledge_graph.domain import KnowledgeGraphEdge, KnowledgeGraphNode


@dataclass(frozen=True, slots=True)
class KnowledgeGraphTraversal:
    root: KnowledgeGraphNode
    nodes: tuple[KnowledgeGraphNode, ...] = ()
    edges: tuple[KnowledgeGraphEdge, ...] = ()
    max_depth: int = 0


@dataclass(frozen=True, slots=True)
class MentionDocumentContext:
    mention: KnowledgeGraphNode
    documents: tuple[KnowledgeGraphNode, ...] = ()
    fragments: tuple[KnowledgeGraphNode, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeGraphQueryReport:
    graph_node_count: int = 0
    graph_edge_count: int = 0
    node_counts_by_type: dict[str, int] = field(default_factory=dict)
    edge_counts_by_type: dict[str, int] = field(default_factory=dict)
