"""Deterministic graph projector over catalog entities, assertions, and facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields, is_dataclass
import json

from drilling_knowledge.assertions import EvidenceAssertion
from drilling_knowledge.assertions.consolidation import ConsolidatedFact, FactLifecycle
from drilling_knowledge.catalog import KnowledgeEntity, Variable
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph.domain import (
    GraphNode,
    GraphProjectionMetrics,
    GraphProjectionPlan,
    GraphProjectionRelationship,
)


_CATALOG_LABELS = {
    "EngineeringUnit",
    "EquipmentClass",
    "InstrumentClass",
    "LocationClass",
    "MeasurementPrinciple",
    "OriginClass",
    "PhysicalQuantity",
    "ProcessClass",
    "SensorClass",
    "SubsystemClass",
    "SystemClass",
    "Variable",
    "VariableClassification",
}

_PREDICATE_TO_RELATIONSHIP_TYPE = {
    "origin_publisher_association": "PUBLISHED_BY",
    "origin_publisher_compatibility": "PUBLISHED_BY",
    "measurement_chain_link": "HAS_MEASUREMENT_CHAIN",
    "measurement_chain_stage": "HAS_MEASUREMENT_CHAIN",
    "measurement_chain_compatibility": "HAS_MEASUREMENT_CHAIN",
}


class GraphProjector:
    @classmethod
    def create(cls) -> "GraphProjector":
        return cls()

    def project(
        self,
        *,
        catalog_entities: Iterable[KnowledgeEntity],
        assertions: Iterable[EvidenceAssertion],
        facts: Iterable[ConsolidatedFact],
    ) -> GraphProjectionPlan:
        catalog_entities = tuple(
            sorted(
                tuple(catalog_entities),
                key=lambda entity: json.dumps(self._catalog_signature(entity), sort_keys=True, separators=(",", ":")),
            )
        )
        assertions = tuple(
            sorted(
                tuple(assertions),
                key=lambda assertion: json.dumps(self._assertion_signature(assertion), sort_keys=True, separators=(",", ":")),
            )
        )
        facts = tuple(
            sorted(
                tuple(facts),
                key=lambda fact: json.dumps(self._fact_signature(fact), sort_keys=True, separators=(",", ":")),
            )
        )
        serializable_signature = json.dumps(
            {
                "catalog_entities": [self._catalog_signature(entity) for entity in catalog_entities],
                "assertions": [self._assertion_signature(assertion) for assertion in assertions],
                "facts": [self._fact_signature(fact) for fact in facts],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        projection_id = EntityId.from_seed("graph.projection.plan", serializable_signature)

        nodes = [self._catalog_node(entity) for entity in catalog_entities]
        code_to_node_id = {str(entity.code): node.graph_node_id for entity, node in zip(catalog_entities, nodes, strict=False)}

        for assertion in assertions:
            nodes.append(self._assertion_node(assertion))
            nodes.extend(self._fragment_nodes(assertion))
        for fact in facts:
            nodes.append(self._fact_node(fact))

        node_ids_by_source = {node.source_entity_id: node.graph_node_id for node in nodes}
        relationships: list[GraphProjectionRelationship] = []

        for entity in catalog_entities:
            relationships.extend(self._catalog_relationships(entity, node_ids_by_source, code_to_node_id))
        for assertion in assertions:
            relationships.extend(self._assertion_relationships(assertion, node_ids_by_source))
        for fact in facts:
            relationships.extend(self._fact_relationships(fact, node_ids_by_source))

        metrics = GraphProjectionMetrics(
            projected_catalog_entities=len(catalog_entities),
            projected_assertions=len(assertions),
            projected_facts=len(facts),
            projected_nodes=len(nodes),
            projected_relationships=len(relationships),
            active_fact_nodes=sum(1 for fact in facts if fact.lifecycle == FactLifecycle.ACTIVE and fact.active_revision),
        )
        return GraphProjectionPlan(
            projection_id=projection_id,
            nodes=tuple(nodes),
            relationships=tuple(relationships),
            metrics=metrics,
        )

    @staticmethod
    def _catalog_signature(entity: KnowledgeEntity) -> dict[str, object]:
        return {
            "entity_id": str(entity.entity_id),
            "label": entity.__class__.__name__,
            "code": str(entity.code),
            "scope": entity.scope.label(),
            "semantic_version": entity.version.semantic_version,
            "record_status": entity.version.status,
        }

    @staticmethod
    def _assertion_signature(assertion: EvidenceAssertion) -> dict[str, object]:
        return {
            "assertion_id": str(assertion.assertion_id),
            "predicate_code": assertion.predicate_code,
            "subject_id": str(assertion.subject_id),
            "object_id": None if assertion.object_id is None else str(assertion.object_id),
            "status": assertion.status.value,
            "review_state": assertion.review_state.value,
            "evidence_link_ids": [str(link_id) for link_id in sorted(assertion.evidence_link_ids, key=str)],
        }

    @staticmethod
    def _fact_signature(fact: ConsolidatedFact) -> dict[str, object]:
        return {
            "fact_id": str(fact.fact_id),
            "predicate_code": fact.predicate_code,
            "subject_id": str(fact.subject_id),
            "object_id": None if fact.object_id is None else str(fact.object_id),
            "lifecycle": fact.lifecycle.value,
            "active_revision": fact.active_revision,
            "version": fact.version,
            "support_link_ids": [str(link_id) for link_id in sorted(fact.support_link_ids, key=str)],
        }

    def _catalog_node(self, entity: KnowledgeEntity) -> GraphNode:
        label = entity.__class__.__name__
        if label not in _CATALOG_LABELS:
            raise ValueError("GraphProjector only supports official catalog entity labels")
        return GraphNode(
            graph_node_id=EntityId.from_seed("graph.projection.node", f"catalog:{label}:{entity.entity_id}"),
            source_entity_id=entity.entity_id,
            label=label,
            active=entity.version.status == "active",
            properties=self._catalog_properties(entity),
        )

    @staticmethod
    def _catalog_properties(entity: KnowledgeEntity) -> tuple[tuple[str, str], ...]:
        properties = [
            ("id", str(entity.entity_id)),
            ("code", str(entity.code)),
            ("name", entity.canonical_name),
            ("name_es", entity.names.spanish or ""),
            ("record_status", entity.version.status),
            ("semantic_version", str(entity.version.semantic_version)),
            ("valid_from", entity.version.valid_from.isoformat() if entity.version.valid_from else ""),
            ("valid_to", entity.version.valid_to.isoformat() if entity.version.valid_to else ""),
            ("created_at", ""),
            ("updated_at", ""),
            ("scope", entity.scope.label()),
        ]
        if isinstance(entity, Variable):
            properties.append(("evidence_requirement_level", entity.evidence_requirement_level))
            properties.append(("ambiguity_level", entity.ambiguity_level))
        return tuple(properties)

    @staticmethod
    def _assertion_node(assertion: EvidenceAssertion) -> GraphNode:
        relationship_type = GraphProjector._relationship_type_for_predicate(assertion.predicate_code)
        return GraphNode(
            graph_node_id=EntityId.from_seed("graph.projection.node", f"assertion:{assertion.assertion_id}"),
            source_entity_id=assertion.assertion_id,
            label="EvidenceAssertion",
            active=assertion.status not in {assertion.status.REJECTED, assertion.status.INVALIDATED, assertion.status.SUPERSEDED},
            properties=(
                ("id", str(assertion.assertion_id)),
                ("predicate_code", assertion.predicate_code),
                ("subject_id", str(assertion.subject_id)),
                ("object_id", "" if assertion.object_id is None else str(assertion.object_id)),
                ("status", assertion.status.value),
                ("review_state", assertion.review_state.value),
                ("predicate_projection_status", "projectable" if relationship_type is not None else "predicate_not_projectable"),
                ("projected_relationship_type", "" if relationship_type is None else relationship_type),
                ("score", f"{assertion.score:.6f}"),
            ),
        )

    @staticmethod
    def _fact_node(fact: ConsolidatedFact) -> GraphNode:
        relationship_type = GraphProjector._relationship_type_for_predicate(fact.predicate_code)
        return GraphNode(
            graph_node_id=EntityId.from_seed("graph.projection.node", f"fact:{fact.fact_id}"),
            source_entity_id=fact.fact_id,
            label="ConsolidatedFact",
            active=fact.lifecycle == FactLifecycle.ACTIVE and fact.active_revision,
            properties=(
                ("id", str(fact.fact_id)),
                ("claim_key", fact.claim_key),
                ("predicate_code", fact.predicate_code),
                ("value_key", fact.value_key),
                ("subject_id", str(fact.subject_id)),
                ("object_id", "" if fact.object_id is None else str(fact.object_id)),
                ("record_status", fact.lifecycle.value),
                ("semantic_version", str(fact.version)),
                ("created_at", fact.created_at.isoformat()),
                ("updated_at", fact.updated_at.isoformat()),
                ("scope", fact.scope),
                ("predicate_projection_status", "projectable" if relationship_type is not None else "predicate_not_projectable"),
                ("projected_relationship_type", "" if relationship_type is None else relationship_type),
            ),
        )

    def _catalog_relationships(
        self,
        entity: KnowledgeEntity,
        node_ids_by_source: dict[EntityId, EntityId],
        code_to_node_id: dict[str, EntityId],
    ) -> tuple[GraphProjectionRelationship, ...]:
        relationships: list[GraphProjectionRelationship] = []
        if isinstance(entity, Variable):
            for classification_code in sorted(entity.classification_codes, key=str):
                target = code_to_node_id.get(str(classification_code))
                if target is not None:
                    relationships.append(
                        self._relationship(
                            source_entity_id=entity.entity_id,
                            relationship_type="HAS_CLASSIFICATION",
                            start_node_id=node_ids_by_source[entity.entity_id],
                            end_node_id=target,
                        )
                    )
            for origin_code in sorted(entity.origin_codes, key=str):
                target = code_to_node_id.get(str(origin_code))
                if target is not None:
                    relationships.append(
                        self._relationship(
                            source_entity_id=entity.entity_id,
                            relationship_type="HAS_ORIGIN",
                            start_node_id=node_ids_by_source[entity.entity_id],
                            end_node_id=target,
                        )
                    )
            for subsystem_code in sorted(entity.subsystem_codes, key=str):
                target = code_to_node_id.get(str(subsystem_code))
                if target is not None:
                    relationships.append(
                        self._relationship(
                            source_entity_id=entity.entity_id,
                            relationship_type="BELONGS_TO_SUBSYSTEM",
                            start_node_id=node_ids_by_source[entity.entity_id],
                            end_node_id=target,
                        )
                    )
        return tuple(relationships)

    @staticmethod
    def _fragment_nodes(assertion: EvidenceAssertion) -> tuple[GraphNode, ...]:
        return tuple(
            GraphNode(
                graph_node_id=EntityId.from_seed("graph.projection.node", f"fragment:{evidence_link_id}"),
                source_entity_id=evidence_link_id,
                label="Fragment",
                active=True,
                properties=(("id", str(evidence_link_id)),),
            )
            for evidence_link_id in sorted(assertion.evidence_link_ids, key=str)
        )

    def _assertion_relationships(
        self,
        assertion: EvidenceAssertion,
        node_ids_by_source: dict[EntityId, EntityId],
    ) -> tuple[GraphProjectionRelationship, ...]:
        start_node_id = node_ids_by_source.get(assertion.subject_id)
        if start_node_id is None:
            raise ValueError("GraphProjector assertions cannot reference missing catalog entity nodes")
        if assertion.object_id is not None and assertion.object_id not in node_ids_by_source:
            raise ValueError("GraphProjector assertions cannot reference missing catalog entity nodes")
        relationship_type = self._relationship_type_for_predicate(assertion.predicate_code)
        relationships: list[GraphProjectionRelationship] = []
        if assertion.object_id is not None and relationship_type is not None:
            end_node_id = node_ids_by_source.get(assertion.object_id)
            if end_node_id is None:
                raise ValueError("GraphProjector assertions cannot reference missing catalog entity nodes")
            relationships.append(
                self._relationship(
                    source_entity_id=assertion.assertion_id,
                    relationship_type=relationship_type,
                    start_node_id=start_node_id,
                    end_node_id=end_node_id,
                    properties=(("evidence_assertion_id", str(assertion.assertion_id)), ("record_status", assertion.status.value)),
                    active=assertion.status not in {assertion.status.REJECTED, assertion.status.INVALIDATED, assertion.status.SUPERSEDED},
                )
            )
        assertion_node_id = node_ids_by_source[assertion.assertion_id]
        for evidence_link_id in sorted(assertion.evidence_link_ids, key=str):
            fragment_node_id = EntityId.from_seed("graph.projection.node", f"fragment:{evidence_link_id}")
            relationships.append(
                self._relationship(
                    source_entity_id=assertion.assertion_id,
                    relationship_type="EVIDENCED_IN",
                    start_node_id=assertion_node_id,
                    end_node_id=fragment_node_id,
                    properties=(("evidence_link_id", str(evidence_link_id)),),
                )
            )
        return tuple(relationships)

    def _fact_relationships(
        self,
        fact: ConsolidatedFact,
        node_ids_by_source: dict[EntityId, EntityId],
    ) -> tuple[GraphProjectionRelationship, ...]:
        relationships: list[GraphProjectionRelationship] = []
        start_node_id = node_ids_by_source.get(fact.subject_id)
        if start_node_id is None:
            raise ValueError("GraphProjector facts cannot reference missing catalog entity nodes")
        if fact.object_id is not None and fact.object_id not in node_ids_by_source:
            raise ValueError("GraphProjector facts cannot reference missing catalog entity nodes")
        relationship_type = self._relationship_type_for_predicate(fact.predicate_code)
        if fact.object_id is not None and relationship_type is not None:
            end_node_id = node_ids_by_source.get(fact.object_id)
            if end_node_id is None:
                raise ValueError("GraphProjector facts cannot reference missing catalog entity nodes")
            relationships.append(
                self._relationship(
                    source_entity_id=fact.fact_id,
                    relationship_type=relationship_type,
                    start_node_id=start_node_id,
                    end_node_id=end_node_id,
                    properties=(("consolidated_fact_id", str(fact.fact_id)), ("record_status", fact.lifecycle.value)),
                    active=fact.lifecycle == FactLifecycle.ACTIVE and fact.active_revision,
                )
            )
        if fact.supersedes_fact_id is not None:
            start_node_id = node_ids_by_source[fact.fact_id]
            end_node_id = node_ids_by_source.get(fact.supersedes_fact_id)
            if end_node_id is None:
                raise ValueError("GraphProjector facts cannot reference missing superseded fact nodes")
            relationships.append(
                self._relationship(
                    source_entity_id=fact.fact_id,
                    relationship_type="SUPERSEDES",
                    start_node_id=start_node_id,
                    end_node_id=end_node_id,
                )
            )
        return tuple(relationships)

    @staticmethod
    def _relationship(
        *,
        source_entity_id: EntityId,
        relationship_type: str,
        start_node_id: EntityId,
        end_node_id: EntityId,
        properties: tuple[tuple[str, str], ...] = (),
        active: bool = True,
    ) -> GraphProjectionRelationship:
        relationship_signature = json.dumps(
            {
                "source_entity_id": str(source_entity_id),
                "relationship_type": relationship_type.upper(),
                "start_node_id": str(start_node_id),
                "end_node_id": str(end_node_id),
                "properties": list(properties),
                "active": active,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return GraphProjectionRelationship(
            relationship_id=EntityId.from_seed("graph.projection.relationship", relationship_signature),
            relationship_type=relationship_type.upper(),
            start_node_id=start_node_id,
            end_node_id=end_node_id,
            source_entity_id=source_entity_id,
            properties=properties,
            active=active,
        )

    @staticmethod
    def _relationship_type_for_predicate(predicate_code: str) -> str | None:
        normalized = predicate_code.strip().lower()
        if not normalized:
            return None
        if normalized in _PREDICATE_TO_RELATIONSHIP_TYPE:
            return _PREDICATE_TO_RELATIONSHIP_TYPE[normalized]
        candidate = normalized.upper()
        if candidate in {
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
        }:
            return candidate
        return None