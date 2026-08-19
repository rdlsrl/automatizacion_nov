"""Deterministic knowledge graph domain built from extraction, resolution, and equivalence outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class KnowledgeGraphNodeType(StrEnum):
    DOCUMENT = "DOCUMENT"
    FRAGMENT = "FRAGMENT"
    MENTION = "MENTION"
    CONCEPT = "CONCEPT"
    EQUIVALENCE_DECISION = "EQUIVALENCE_DECISION"


class KnowledgeGraphEdgeType(StrEnum):
    DOCUMENT_TO_FRAGMENT = "DOCUMENT_TO_FRAGMENT"
    FRAGMENT_TO_MENTION = "FRAGMENT_TO_MENTION"
    MENTION_TO_CANDIDATE = "MENTION_TO_CANDIDATE"
    MENTION_TO_EQUIVALENCE_DECISION = "MENTION_TO_EQUIVALENCE_DECISION"
    EQUIVALENCE_DECISION_TO_CONCEPT = "EQUIVALENCE_DECISION_TO_CONCEPT"


@dataclass(frozen=True, slots=True)
class KnowledgeGraphNode:
    node_id: EntityId
    node_type: KnowledgeGraphNodeType
    external_id: EntityId
    source_traces: tuple[ExtractionSourceTrace, ...] = ()
    attributes: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeGraphEdge:
    edge_id: EntityId
    edge_type: KnowledgeGraphEdgeType
    source_node_id: EntityId
    target_node_id: EntityId
    source_traces: tuple[ExtractionSourceTrace, ...] = ()
    attributes: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeGraphMetrics:
    node_counts_by_type: dict[str, int] = field(default_factory=dict)
    relation_counts_by_type: dict[str, int] = field(default_factory=dict)
    documents_processed: int = 0
    mentions_without_candidates: int = 0
    approved_decisions: int = 0
    rejected_decisions: int = 0
    pending_decisions: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeGraph:
    nodes: tuple[KnowledgeGraphNode, ...] = ()
    edges: tuple[KnowledgeGraphEdge, ...] = ()
    metrics: KnowledgeGraphMetrics = field(default_factory=KnowledgeGraphMetrics)
