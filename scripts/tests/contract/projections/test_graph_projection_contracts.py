from __future__ import annotations

from dataclasses import replace
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.catalog import EngineeringUnit, PhysicalQuantity, Variable, VariableClassification
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph.domain import GraphProjectionPlan
from drilling_knowledge.projections.graph import (
    GraphProjector,
    InMemoryGraphProjectionPlanRepository,
)

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class GraphProjectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="graph-projection-contract-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="graph-projection-contract")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        self.assertion = fact_run.assertions[0]
        self.fact = fact_run.facts[0]
        self.variable = Variable(
            entity_id=self.fact.subject_id,
            code=CatalogCode("variable.pressure"),
            names=LocalizedName("Standpipe Pressure"),
            description="Pressure variable.",
            scope=CatalogScope(),
            physical_quantity_code=CatalogCode("quantity.pressure"),
            canonical_unit_code=CatalogCode("unit.psi"),
            classification_codes=(CatalogCode("classification.process"),),
            subsystem_codes=(),
        )
        self.quantity = PhysicalQuantity(
            entity_id=EntityId.from_seed("graph.contract.quantity", "pressure"),
            code=CatalogCode("quantity.pressure"),
            names=LocalizedName("Pressure"),
            description="Pressure quantity.",
            scope=CatalogScope(),
            quantity_family="pressure",
            dimension_code="pressure",
            canonical_unit_code=CatalogCode("unit.psi"),
        )
        self.unit = EngineeringUnit(
            entity_id=self.assertion.object_id or EntityId.from_seed("graph.contract.unit", "psi"),
            code=CatalogCode("unit.psi"),
            names=LocalizedName("PSI"),
            description="Pressure unit.",
            scope=CatalogScope(),
            symbol="psi",
            dimension_code="pressure",
        )
        self.classification = VariableClassification(
            entity_id=EntityId.from_seed("graph.contract.classification", "process"),
            code=CatalogCode("classification.process"),
            names=LocalizedName("Process"),
            description="Process variable.",
            scope=CatalogScope(),
            axis="kind",
        )
        self.projector = GraphProjector.create()

    def test_public_contract_and_recovery(self) -> None:
        plan = self._plan()
        repository = InMemoryGraphProjectionPlanRepository().append_plan(plan)

        self.assertEqual(repository.get_plan(plan.projection_id), plan)
        self.assertEqual(repository.list_plans(), (plan,))

    def test_append_only_idempotence(self) -> None:
        plan = self._plan()
        repository = InMemoryGraphProjectionPlanRepository().append_plan(plan)

        self.assertIs(repository.append_plan(plan), repository)

    def test_conflicting_projection_id_is_rejected(self) -> None:
        plan = self._plan()
        variable_node = next(node for node in plan.nodes if node.label == "Variable")
        mutated_node = replace(variable_node, active=not variable_node.active)
        conflicting = replace(
            plan,
            nodes=tuple(mutated_node if node.source_entity_id == variable_node.source_entity_id else node for node in plan.nodes),
        )

        with self.assertRaises(ConflictError):
            InMemoryGraphProjectionPlanRepository((plan, conflicting))

    def test_determinism_is_stable_for_recovery(self) -> None:
        plan = self._plan()
        recovered = InMemoryGraphProjectionPlanRepository((plan,)).get_plan(plan.projection_id)

        self.assertEqual(json.dumps(plan.as_serializable(), sort_keys=True), json.dumps(recovered.as_serializable(), sort_keys=True))

    def test_reversed_input_order_produces_same_persisted_plan(self) -> None:
        first = self._plan()
        second = self.projector.project(
            catalog_entities=(self.classification, self.unit, self.quantity, self.variable),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )

        self.assertEqual(first, second)

    def test_repository_rejects_invalid_active_lineage_even_for_prebuilt_plan(self) -> None:
        plan = self._plan()
        base_fact_node = next(node for node in plan.nodes if node.label == "ConsolidatedFact")
        duplicate_fact_node = replace(
            base_fact_node,
            graph_node_id=EntityId.from_seed("graph.contract.duplicate.node", "active-lineage"),
            source_entity_id=EntityId.from_seed("graph.contract.duplicate.source", "active-lineage"),
            properties=tuple(("id", str(EntityId.from_seed("graph.contract.duplicate.source", "active-lineage"))) if key == "id" else (key, value) for key, value in base_fact_node.properties),
        )
        invalid_plan = object.__new__(GraphProjectionPlan)
        object.__setattr__(invalid_plan, "projection_id", plan.projection_id)
        object.__setattr__(invalid_plan, "nodes", plan.nodes + (duplicate_fact_node,))
        object.__setattr__(invalid_plan, "relationships", plan.relationships)
        object.__setattr__(invalid_plan, "metrics", replace(plan.metrics, projected_nodes=plan.metrics.projected_nodes + 1, active_fact_nodes=plan.metrics.active_fact_nodes + 1))

        with self.assertRaises(ValueError):
            InMemoryGraphProjectionPlanRepository().append_plan(invalid_plan)

    def _plan(self):
        return self.projector.project(
            catalog_entities=(self.variable, self.quantity, self.unit, self.classification),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )