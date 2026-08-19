"""Immutable graph projection contracts for Neo4j synchronization."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum

from drilling_knowledge.common.ids import EntityId, Identifier


_OFFICIAL_NODE_LABELS = frozenset(
    {
        "Variable",
        "VariableClassification",
        "OriginClass",
        "PhysicalQuantity",
        "EngineeringUnit",
        "MeasurementPrinciple",
        "SensorClass",
        "InstrumentClass",
        "SignalClass",
        "ChannelClass",
        "MeasurementChain",
        "SystemClass",
        "SubsystemClass",
        "EquipmentClass",
        "LocationClass",
        "ProcessClass",
        "OperationalContext",
        "Vendor",
        "Model",
        "Firmware",
        "SoftwareProduct",
        "SoftwareVersion",
        "Protocol",
        "Standard",
        "Document",
        "DocumentVersion",
        "Fragment",
        "EvidenceAssertion",
        "ConsolidatedFact",
        "ConflictSet",
        "RuleDefinition",
        "ControlLoopClass",
        "AlarmClass",
        "StatusClass",
    }
)

_OFFICIAL_RELATIONSHIP_TYPES = frozenset(
    {
        "PART_OF",
        "BELONGS_TO_SYSTEM",
        "BELONGS_TO_SUBSYSTEM",
        "MEASURES",
        "MEASURED_BY",
        "USES_SENSOR",
        "USES_INSTRUMENT",
        "USES_MEASUREMENT_PRINCIPLE",
        "USES_PROTOCOL",
        "ALLOWS_UNIT",
        "HAS_CLASSIFICATION",
        "HAS_ORIGIN",
        "HAS_MEASUREMENT_CHAIN",
        "HAS_ALIAS",
        "HAS_MNEMONIC",
        "HAS_TAG_PATTERN",
        "PUBLISHED_BY",
        "GENERATED_BY",
        "ACQUIRED_BY",
        "LOCATED_AT",
        "INSTALLED_ON",
        "PARTICIPATES_IN",
        "REPRESENTS_PROCESS",
        "CALCULATED_FROM",
        "DERIVED_FROM",
        "FILTERED_FROM",
        "AVERAGED_FROM",
        "NORMALIZED_FROM",
        "COMPENSATED_FROM",
        "INTEGRATED_FROM",
        "ACCUMULATED_FROM",
        "ESTIMATED_FROM",
        "DEPENDS_ON",
        "USED_BY",
        "CONSUMED_BY",
        "TRIGGERS",
        "VALIDATED_BY",
        "EQUIVALENT_TO",
        "CONFLICTS_WITH",
        "SUPERSEDES",
        "REPLACES",
        "CONFORMS_TO",
        "SUPPORTED_BY",
        "EVIDENCED_IN",
        "SUPPORTED_BY_ASSERTION",
        "GROUPED_IN_CONFLICT",
        "EXECUTED_RULE",
    }
)


def _require_entity_id(field_name: str, value: object) -> EntityId:
    if value is None:
        raise ValueError(f"{field_name} cannot be null")
    if not isinstance(value, EntityId):
        raise ValueError(f"{field_name} must be an EntityId")
    if value.as_uuid().int == 0:
        raise ValueError(f"{field_name} cannot be empty")
    return value


def _normalize_properties(field_name: str, values: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if values is None:
        raise ValueError(f"{field_name} cannot be null")
    normalized: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for key, value in tuple(values):
        property_key = key.strip()
        property_value = value.strip()
        if not property_key:
            raise ValueError(f"{field_name} cannot contain blank property keys")
        if property_key in seen_keys:
            raise ValueError(f"{field_name} cannot contain duplicate property keys")
        seen_keys.add(property_key)
        normalized.append((property_key, property_value))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _serialize_value(value: object) -> object:
    if isinstance(value, Identifier):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return value


@dataclass(frozen=True, slots=True)
class GraphNode:
    graph_node_id: EntityId
    source_entity_id: EntityId
    label: str
    properties: tuple[tuple[str, str], ...]
    active: bool

    def __post_init__(self) -> None:
        graph_node_id = _require_entity_id("GraphNode.graph_node_id", self.graph_node_id)
        source_entity_id = _require_entity_id("GraphNode.source_entity_id", self.source_entity_id)
        label = self.label.strip()
        if label not in _OFFICIAL_NODE_LABELS:
            raise ValueError("GraphNode.label must be one of the official Neo4j node labels")
        properties = _normalize_properties("GraphNode.properties", self.properties)
        object.__setattr__(self, "graph_node_id", graph_node_id)
        object.__setattr__(self, "source_entity_id", source_entity_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "properties", properties)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class GraphProjectionRelationship:
    relationship_id: EntityId
    relationship_type: str
    start_node_id: EntityId
    end_node_id: EntityId
    source_entity_id: EntityId
    properties: tuple[tuple[str, str], ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        relationship_id = _require_entity_id("GraphProjectionRelationship.relationship_id", self.relationship_id)
        start_node_id = _require_entity_id("GraphProjectionRelationship.start_node_id", self.start_node_id)
        end_node_id = _require_entity_id("GraphProjectionRelationship.end_node_id", self.end_node_id)
        source_entity_id = _require_entity_id("GraphProjectionRelationship.source_entity_id", self.source_entity_id)
        relationship_type = self.relationship_type.strip().upper()
        if relationship_type not in _OFFICIAL_RELATIONSHIP_TYPES:
            raise ValueError("GraphProjectionRelationship.relationship_type must be one of the official Neo4j relationship types")
        if start_node_id == end_node_id and relationship_type not in {"EQUIVALENT_TO", "SUPERSEDES"}:
            raise ValueError("GraphProjectionRelationship cannot self-reference unless explicitly allowed")
        properties = _normalize_properties("GraphProjectionRelationship.properties", self.properties)
        object.__setattr__(self, "relationship_id", relationship_id)
        object.__setattr__(self, "relationship_type", relationship_type)
        object.__setattr__(self, "start_node_id", start_node_id)
        object.__setattr__(self, "end_node_id", end_node_id)
        object.__setattr__(self, "source_entity_id", source_entity_id)
        object.__setattr__(self, "properties", properties)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class GraphProjectionMetrics:
    projected_catalog_entities: int
    projected_assertions: int
    projected_facts: int
    projected_nodes: int
    projected_relationships: int
    active_fact_nodes: int

    def __post_init__(self) -> None:
        for field_name in (
            "projected_catalog_entities",
            "projected_assertions",
            "projected_facts",
            "projected_nodes",
            "projected_relationships",
            "active_fact_nodes",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"GraphProjectionMetrics.{field_name} cannot be negative")
        if self.projected_nodes < 1:
            raise ValueError("GraphProjectionMetrics.projected_nodes must be >= 1")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class GraphProjectionPlan:
    projection_id: EntityId
    nodes: tuple[GraphNode, ...]
    relationships: tuple[GraphProjectionRelationship, ...]
    metrics: GraphProjectionMetrics

    def __post_init__(self) -> None:
        projection_id = _require_entity_id("GraphProjectionPlan.projection_id", self.projection_id)
        normalized_nodes = tuple(sorted(tuple(self.nodes), key=lambda node: (node.label, str(node.source_entity_id), str(node.graph_node_id))))
        normalized_relationships = tuple(
            sorted(
                tuple(self.relationships),
                key=lambda relationship: (
                    relationship.relationship_type,
                    str(relationship.start_node_id),
                    str(relationship.end_node_id),
                    str(relationship.relationship_id),
                ),
            )
        )
        if not normalized_nodes:
            raise ValueError("GraphProjectionPlan.nodes cannot be empty")
        for node in normalized_nodes:
            if not isinstance(node, GraphNode):
                raise ValueError("GraphProjectionPlan.nodes must contain only GraphNode values")
        for relationship in normalized_relationships:
            if not isinstance(relationship, GraphProjectionRelationship):
                raise ValueError("GraphProjectionPlan.relationships must contain only GraphProjectionRelationship values")
        if len({node.graph_node_id for node in normalized_nodes}) != len(normalized_nodes):
            raise ValueError("GraphProjectionPlan.nodes cannot contain duplicate node ids")
        if len({(node.label, node.source_entity_id) for node in normalized_nodes}) != len(normalized_nodes):
            raise ValueError("GraphProjectionPlan.nodes cannot contain duplicate label/source pairs")
        if len({relationship.relationship_id for relationship in normalized_relationships}) != len(normalized_relationships):
            raise ValueError("GraphProjectionPlan.relationships cannot contain duplicate relationship ids")
        if len({(relationship.relationship_type, relationship.start_node_id, relationship.end_node_id, relationship.source_entity_id) for relationship in normalized_relationships}) != len(normalized_relationships):
            raise ValueError("GraphProjectionPlan.relationships cannot contain duplicate relationship tuples")
        node_ids = {node.graph_node_id for node in normalized_nodes}
        for relationship in normalized_relationships:
            if relationship.start_node_id not in node_ids or relationship.end_node_id not in node_ids:
                raise ValueError("GraphProjectionPlan.relationships cannot reference missing nodes")
        metrics = self.metrics
        active_lineages = self._active_fact_lineages(normalized_nodes)
        if len(active_lineages) != sum(1 for node in normalized_nodes if node.label == "ConsolidatedFact" and node.active):
            raise ValueError("GraphProjectionPlan cannot contain multiple active fact revisions for the same lineage")
        if metrics.projected_nodes != len(normalized_nodes):
            raise ValueError("GraphProjectionPlan.metrics.projected_nodes must match nodes")
        if metrics.projected_relationships != len(normalized_relationships):
            raise ValueError("GraphProjectionPlan.metrics.projected_relationships must match relationships")
        if metrics.active_fact_nodes != len(active_lineages):
            raise ValueError("GraphProjectionPlan.metrics.active_fact_nodes must match active ConsolidatedFact nodes")
        object.__setattr__(self, "projection_id", projection_id)
        object.__setattr__(self, "nodes", normalized_nodes)
        object.__setattr__(self, "relationships", normalized_relationships)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)

    @staticmethod
    def _active_fact_lineages(nodes: tuple[GraphNode, ...]) -> set[tuple[str, str, str, str, str]]:
        active_lineages: set[tuple[str, str, str, str, str]] = set()
        for node in nodes:
            if node.label != "ConsolidatedFact" or not node.active:
                continue
            properties = dict(node.properties)
            lineage = (
                properties.get("claim_key", ""),
                properties.get("scope", ""),
                properties.get("subject_id", ""),
                properties.get("predicate_code", ""),
                properties.get("value_key", ""),
            )
            if lineage in active_lineages:
                raise ValueError("GraphProjectionPlan cannot contain multiple active fact revisions for the same lineage")
            active_lineages.add(lineage)
        return active_lineages