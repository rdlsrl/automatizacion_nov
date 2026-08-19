"""Repository contracts for explicit equivalence decisions."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence.domain import EquivalenceDecision


class EquivalenceDecisionRepository(Protocol):
    def get_active(self, mention_id: EntityId, catalog_entity_id: EntityId) -> EquivalenceDecision | None:
        ...

    def list_history(self, mention_id: EntityId, catalog_entity_id: EntityId) -> tuple[EquivalenceDecision, ...]:
        ...

    def list_all(self) -> tuple[EquivalenceDecision, ...]:
        ...

    def append(self, decision: EquivalenceDecision) -> "EquivalenceDecisionRepository":
        ...
