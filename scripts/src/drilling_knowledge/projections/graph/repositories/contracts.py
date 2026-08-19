"""Repository contracts for graph projection plans."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph.domain import GraphProjectionPlan


class GraphProjectionPlanRepository(Protocol):
    def get_plan(self, projection_id: EntityId) -> GraphProjectionPlan | None:
        ...

    def list_plans(self) -> tuple[GraphProjectionPlan, ...]:
        ...

    def append_plan(self, plan: GraphProjectionPlan) -> "GraphProjectionPlanRepository":
        ...