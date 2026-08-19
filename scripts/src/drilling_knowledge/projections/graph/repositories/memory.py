"""In-memory append-only repository for graph projection plans."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.graph.domain import GraphProjectionPlan
from drilling_knowledge.projections.graph.repositories.contracts import GraphProjectionPlanRepository


@dataclass(frozen=True, slots=True)
class InMemoryGraphProjectionPlanRepository(GraphProjectionPlanRepository):
    plans: tuple[GraphProjectionPlan, ...] = ()
    _plans_by_id: dict[EntityId, GraphProjectionPlan] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        plans_by_id: dict[EntityId, GraphProjectionPlan] = {}
        for plan in self.plans:
            self._validate_plan(plan)
            existing = plans_by_id.get(plan.projection_id)
            if existing is not None and existing != plan:
                raise ConflictError(
                    code="duplicate_graph_projection_plan",
                    message="A different graph projection plan already exists for the same projection id",
                    context={"projection_id": str(plan.projection_id)},
                )
            plans_by_id[plan.projection_id] = plan
        object.__setattr__(self, "_plans_by_id", plans_by_id)

    def get_plan(self, projection_id: EntityId) -> GraphProjectionPlan | None:
        return self._plans_by_id.get(projection_id)

    def list_plans(self) -> tuple[GraphProjectionPlan, ...]:
        return self.plans

    def append_plan(self, plan: GraphProjectionPlan) -> "InMemoryGraphProjectionPlanRepository":
        self._validate_plan(plan)
        existing = self._plans_by_id.get(plan.projection_id)
        if existing is not None:
            if existing != plan:
                raise ConflictError(
                    code="duplicate_graph_projection_plan",
                    message="A different graph projection plan already exists for the same projection id",
                    context={"projection_id": str(plan.projection_id)},
                )
            return self
        return InMemoryGraphProjectionPlanRepository(self.plans + (plan,))

    @staticmethod
    def _validate_plan(plan: GraphProjectionPlan) -> None:
        if not isinstance(plan, GraphProjectionPlan):
            raise ValueError("GraphProjectionPlanRepository can only store GraphProjectionPlan values")
        GraphProjectionPlan._active_fact_lineages(plan.nodes)