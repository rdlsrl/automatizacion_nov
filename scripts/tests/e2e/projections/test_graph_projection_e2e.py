from __future__ import annotations

import json
import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.catalog import EngineeringUnit, PhysicalQuantity, Variable, VariableClassification
from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph import GraphProjector, InMemoryGraphProjectionPlanRepository

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class GraphProjectionEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = FactConsolidatorTests()
        self.helpers.setUp()
        accepted = self.helpers._assertion("4 mA = 0 psi", version_seed="graph-e2e-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = self.helpers._assertion_run((accepted,), run_seed="graph-e2e")
        conflict_run = self.helpers.conflict_resolver.resolve(assertion_run)
        fact_run = self.helpers.consolidator.consolidate(assertion_run, conflict_run)
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
            entity_id=EntityId.from_seed("graph.e2e.quantity", "pressure"),
            code=CatalogCode("quantity.pressure"),
            names=LocalizedName("Pressure"),
            description="Pressure quantity.",
            scope=CatalogScope(),
            quantity_family="pressure",
            dimension_code="pressure",
            canonical_unit_code=CatalogCode("unit.psi"),
        )
        self.unit = EngineeringUnit(
            entity_id=self.assertion.object_id or EntityId.from_seed("graph.e2e.unit", "psi"),
            code=CatalogCode("unit.psi"),
            names=LocalizedName("PSI"),
            description="Pressure unit.",
            scope=CatalogScope(),
            symbol="psi",
            dimension_code="pressure",
        )
        self.classification = VariableClassification(
            entity_id=EntityId.from_seed("graph.e2e.classification", "process"),
            code=CatalogCode("classification.process"),
            names=LocalizedName("Process"),
            description="Process variable.",
            scope=CatalogScope(),
            axis="kind",
        )
        self.projector = GraphProjector.create()

    def test_catalog_assertions_facts_projection_persists_and_recovers_identically(self) -> None:
        first = self._project()
        repository = InMemoryGraphProjectionPlanRepository().append_plan(first)

        second = self._project()
        repository = repository.append_plan(second)
        recovered = repository.get_plan(first.projection_id)

        self.assertEqual(first.projection_id, second.projection_id)
        self.assertEqual(first.nodes, second.nodes)
        self.assertEqual(first.relationships, second.relationships)
        self.assertEqual(first, second)
        self.assertEqual(recovered, first)
        self.assertEqual(
            json.dumps(first.as_serializable(), sort_keys=True),
            json.dumps(recovered.as_serializable(), sort_keys=True),
        )

    def _project(self):
        return self.projector.project(
            catalog_entities=(self.variable, self.quantity, self.unit, self.classification),
            assertions=(self.assertion,),
            facts=(self.fact,),
        )