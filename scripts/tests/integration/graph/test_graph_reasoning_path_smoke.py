from __future__ import annotations

import unittest

from drilling_knowledge.assertions.domain import AssertionStatus
from drilling_knowledge.projections.graph import GraphProjector
from drilling_knowledge.reasoning import ExplanationAssembler, ReasoningAppliedRule, ReasoningQuestionType, ReasoningQueryPlanner, ReasoningRequest, StructuredAnswerStatement

from tests.unit.assertions.test_fact_consolidation import FactConsolidatorTests


class GraphReasoningPathSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        helpers = FactConsolidatorTests()
        helpers.setUp()
        accepted = helpers._assertion("4 mA = 0 psi", version_seed="graph-v1", status=AssertionStatus.ACCEPTED)
        assertion_run = helpers._assertion_run((accepted,), run_seed="graph")
        conflict_run = helpers.conflict_resolver.resolve(assertion_run)
        self.fact_run = helpers.consolidator.consolidate(assertion_run, conflict_run)
        catalog_entities = helpers.catalog.variables.list_all()
        catalog_ids = {entity.entity_id for entity in catalog_entities}
        projectable_assertions = tuple(
            assertion
            for assertion in self.fact_run.assertions
            if assertion.subject_id in catalog_ids and (assertion.object_id is None or assertion.object_id in catalog_ids)
        )
        self.projectable_facts = tuple(
            fact
            for fact in self.fact_run.facts
            if fact.subject_id in catalog_ids and (fact.object_id is None or fact.object_id in catalog_ids)
        )
        self.graph = GraphProjector.create().project(catalog_entities=catalog_entities, assertions=projectable_assertions, facts=self.projectable_facts)
        self.plan = ReasoningQueryPlanner.create().build_plan(
            ReasoningRequest(
                target_entity_id=self.fact_run.facts[0].subject_id,
                question_type=ReasoningQuestionType.LINEAGE_JUSTIFICATION,
                context_scope=self.fact_run.facts[0].scope,
                requested_confidence_threshold=0.5,
            )
        )

    def test_graph_answers_match_consolidated_facts(self) -> None:
        response = ExplanationAssembler.create().assemble(
            self.plan,
            answer_statement=StructuredAnswerStatement(
                statement_text="Lineage remains backed by consolidated evidence.",
                answer_kind="lineage",
                target_entity_id=self.fact_run.facts[0].subject_id,
            ),
            supporting_facts=self.fact_run.facts,
            supporting_assertions=self.fact_run.assertions,
            supporting_fragments=self.fact_run.evidence_links,
            applied_rules=(ReasoningAppliedRule(rule_code="B059", rule_summary="Graph path validation", rule_priority=1),),
            confidence=1.0,
        )

        graph_fact_nodes = {node.source_entity_id for node in self.graph.nodes if node.label == "ConsolidatedFact"}
        self.assertEqual(graph_fact_nodes, {fact.fact_id for fact in self.projectable_facts})
        self.assertEqual({fact.fact_id for fact in response.supporting_facts}, {fact.fact_id for fact in self.fact_run.facts})
        self.assertGreaterEqual(self.graph.metrics.projected_nodes, len(self.projectable_facts))