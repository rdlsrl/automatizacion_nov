from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.assertions.consolidation.domain import FactLifecycle
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph import GraphProjector, InMemoryGraphProjectionPlanRepository

from tests.contract.projections.test_graph_projection_contracts import GraphProjectionContractTests


class GraphProjectionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = GraphProjectionContractTests()
        fixture.setUp()
        self.assertion = fixture.assertion
        self.fact = fixture.fact
        self.variable = fixture.variable
        self.quantity = fixture.quantity
        self.unit = fixture.unit
        self.classification = fixture.classification
        self.projector = GraphProjector.create()

    def test_catalog_assertions_facts_project_persist_and_recover(self) -> None:
        plan = self._project(self.assertion, self.fact)
        repository = InMemoryGraphProjectionPlanRepository().append_plan(plan)

        recovered = repository.get_plan(plan.projection_id)
        self.assertEqual(recovered, plan)
        self.assertEqual(repository.list_plans(), (plan,))
        self.assertEqual(dict(next(node for node in plan.nodes if node.label == "ConsolidatedFact").properties)["predicate_projection_status"], "predicate_not_projectable")

    def test_repository_revalidates_duplicate_active_fact_lineages(self) -> None:
        plan = self._project(self.assertion, self.fact)
        base_fact_node = next(node for node in plan.nodes if node.label == "ConsolidatedFact")
        duplicate_fact_node = replace(
            base_fact_node,
            graph_node_id=EntityId.from_seed("graph.integration.duplicate.node", "active-lineage"),
            source_entity_id=EntityId.from_seed("graph.integration.duplicate.source", "active-lineage"),
            properties=tuple(("id", str(EntityId.from_seed("graph.integration.duplicate.source", "active-lineage"))) if key == "id" else (key, value) for key, value in base_fact_node.properties),
        )

        invalid_plan = object.__new__(type(plan))
        object.__setattr__(invalid_plan, "projection_id", plan.projection_id)
        object.__setattr__(invalid_plan, "nodes", plan.nodes + (duplicate_fact_node,))
        object.__setattr__(invalid_plan, "relationships", plan.relationships)
        object.__setattr__(invalid_plan, "metrics", replace(plan.metrics, projected_nodes=plan.metrics.projected_nodes + 1, active_fact_nodes=plan.metrics.active_fact_nodes + 1))

        with self.assertRaises(ValueError):
            InMemoryGraphProjectionPlanRepository().append_plan(invalid_plan)

    def test_versioned_facts_keep_single_active_revision_per_lineage(self) -> None:
        superseded_fact = replace(
            self.fact,
            fact_id=EntityId.from_seed("graph.integration.fact", "superseded"),
            lifecycle=FactLifecycle.SUPERSEDED,
            active_revision=False,
            version=2,
            supersedes_fact_id=self.fact.fact_id,
            updated_at=datetime.now(UTC),
        )

        plan = self._project(self.assertion, superseded_fact, self.fact)
        repository = InMemoryGraphProjectionPlanRepository().append_plan(plan)
        recovered = repository.get_plan(plan.projection_id)

        self.assertEqual(recovered, plan)
        self.assertEqual(plan.metrics.active_fact_nodes, 1)
        self.assertEqual(json.dumps(plan.as_serializable(), sort_keys=True), json.dumps(recovered.as_serializable(), sort_keys=True))

    def _project(self, assertion, *facts):
        return self.projector.project(
            catalog_entities=(self.variable, self.quantity, self.unit, self.classification),
            assertions=(assertion,),
            facts=facts,
        )