from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionReviewState, AssertionStatus, EvidenceAssertion
from drilling_knowledge.assertions.consolidation.domain import ConsolidatedFact, FactLifecycle
from drilling_knowledge.catalog import EngineeringUnit, PhysicalQuantity, Variable, VariableClassification
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph import GraphProjector, GraphProjectionPlan

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class GraphProjectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="graph-projection-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="graph-projection")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.assertion = fact_run.assertions[0]
        self.fact = fact_run.facts[0]
        self.variable = Variable(
            entity_id=self.fact.subject_id,
            code=CatalogCode("variable.pressure"),
            names=LocalizedName("Standpipe Pressure", "Presion Standpipe"),
            description="Pressure variable.",
            scope=CatalogScope(),
            physical_quantity_code=CatalogCode("quantity.pressure"),
            canonical_unit_code=CatalogCode("unit.psi"),
            classification_codes=(CatalogCode("classification.process"),),
            subsystem_codes=(),
        )
        self.quantity = PhysicalQuantity(
            entity_id=EntityId.from_seed("graph.catalog.quantity", "pressure"),
            code=CatalogCode("quantity.pressure"),
            names=LocalizedName("Pressure"),
            description="Pressure quantity.",
            scope=CatalogScope(),
            quantity_family="pressure",
            dimension_code="pressure",
            canonical_unit_code=CatalogCode("unit.psi"),
        )
        self.unit = EngineeringUnit(
            entity_id=self.assertion.object_id or EntityId.from_seed("graph.catalog.unit", "psi"),
            code=CatalogCode("unit.psi"),
            names=LocalizedName("PSI"),
            description="Pressure unit.",
            scope=CatalogScope(),
            symbol="psi",
            dimension_code="pressure",
        )
        self.classification = VariableClassification(
            entity_id=EntityId.from_seed("graph.catalog.classification", "process"),
            code=CatalogCode("classification.process"),
            names=LocalizedName("Process"),
            description="Process variable.",
            scope=CatalogScope(),
            axis="kind",
        )
        self.projector = GraphProjector.create()

    def test_valid_projection_covers_catalog_assertion_fact_and_relationships(self) -> None:
        plan = self._project()

        labels = {node.label for node in plan.nodes}
        relationship_types = {relationship.relationship_type for relationship in plan.relationships}
        assertion_node = next(node for node in plan.nodes if node.label == "EvidenceAssertion")
        fact_node = next(node for node in plan.nodes if node.label == "ConsolidatedFact")
        self.assertIn("Variable", labels)
        self.assertIn("EvidenceAssertion", labels)
        self.assertIn("ConsolidatedFact", labels)
        self.assertIn("Fragment", labels)
        self.assertIn("HAS_CLASSIFICATION", relationship_types)
        self.assertIn("EVIDENCED_IN", relationship_types)
        self.assertEqual(dict(assertion_node.properties)["predicate_projection_status"], "predicate_not_projectable")
        self.assertEqual(dict(fact_node.properties)["predicate_projection_status"], "predicate_not_projectable")

    def test_duplicate_active_fact_lineages_are_rejected(self) -> None:
        plan = self._project()
        base_fact_node = next(node for node in plan.nodes if node.label == "ConsolidatedFact")
        duplicate_fact_node = replace(
            base_fact_node,
            graph_node_id=EntityId.from_seed("graph.unit.duplicate.node", "active-lineage"),
            source_entity_id=EntityId.from_seed("graph.unit.duplicate.source", "active-lineage"),
            properties=tuple(("id", str(EntityId.from_seed("graph.unit.duplicate.source", "active-lineage"))) if key == "id" else (key, value) for key, value in base_fact_node.properties),
        )

        with self.assertRaises(ValueError):
            GraphProjectionPlan(
                projection_id=plan.projection_id,
                nodes=plan.nodes + (duplicate_fact_node,),
                relationships=plan.relationships,
                metrics=replace(plan.metrics, projected_nodes=plan.metrics.projected_nodes + 1, active_fact_nodes=plan.metrics.active_fact_nodes + 1),
            )

    def test_order_is_deterministic(self) -> None:
        first = self._project()
        second = self._project()

        self.assertEqual(first, second)
        self.assertEqual(first.projection_id, second.projection_id)

    def test_reversed_input_order_produces_same_plan(self) -> None:
        first = self._project()
        second = self.projector.project(
            catalog_entities=(self.classification, self.unit, self.quantity, self.variable),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )

        self.assertEqual(first, second)

    def test_duplicate_nodes_are_rejected(self) -> None:
        plan = self._project()
        with self.assertRaises(ValueError):
            GraphProjectionPlan(
                projection_id=plan.projection_id,
                nodes=(plan.nodes[0], plan.nodes[0]),
                relationships=(),
                metrics=replace(plan.metrics, projected_nodes=2, projected_relationships=0),
            )

    def test_duplicate_relationships_are_rejected(self) -> None:
        plan = self._project()
        with self.assertRaises(ValueError):
            GraphProjectionPlan(
                projection_id=plan.projection_id,
                nodes=plan.nodes,
                relationships=(plan.relationships[0], plan.relationships[0]),
                metrics=replace(plan.metrics, projected_relationships=2),
            )

    def test_invalid_references_are_rejected(self) -> None:
        bad_fact = replace(self.fact, object_id=EntityId.from_seed("graph.catalog.missing", "object"), object_table="variables")

        with self.assertRaises(ValueError):
            self.projector.project(
                catalog_entities=(self.variable, self.quantity, self.unit, self.classification),
                assertions=(self.assertion,),
                facts=(bad_fact,),
            )

    def test_serialization_is_stable(self) -> None:
        plan = self._project()

        self.assertEqual(
            json.dumps(plan.as_serializable(), sort_keys=True),
            json.dumps(self._project().as_serializable(), sort_keys=True),
        )

    def test_idempotence_preserves_identical_projection(self) -> None:
        first = self._project()
        second = self._project()

        self.assertEqual(first.as_serializable(), second.as_serializable())

    def test_inmutability_is_enforced(self) -> None:
        plan = self._project()

        with self.assertRaises(FrozenInstanceError):
            plan.nodes = ()

    def test_active_state_updates_for_version_changes(self) -> None:
        superseded = replace(
            self.fact,
            fact_id=EntityId.from_seed("graph.fact", "superseded"),
            lifecycle=FactLifecycle.SUPERSEDED,
            active_revision=False,
            version=2,
            supersedes_fact_id=self.fact.fact_id,
            updated_at=datetime.now(UTC),
        )
        plan = self.projector.project(
            catalog_entities=(self.variable, self.quantity, self.unit, self.classification),
            assertions=(self.assertion,),
            facts=(self.fact, superseded),
        )

        fact_nodes = {node.source_entity_id: node for node in plan.nodes if node.label == "ConsolidatedFact"}
        self.assertTrue(fact_nodes[self.fact.fact_id].active)
        self.assertFalse(fact_nodes[superseded.fact_id].active)

    def _project(self):
        return self.projector.project(
            catalog_entities=(self.variable, self.quantity, self.unit, self.classification),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )