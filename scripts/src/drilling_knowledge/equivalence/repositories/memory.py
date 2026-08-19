"""In-memory append-only repository for explicit equivalence decisions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence.domain import EquivalenceDecision
from drilling_knowledge.equivalence.repositories.contracts import EquivalenceDecisionRepository


@dataclass(slots=True)
class InMemoryEquivalenceDecisionRepository(EquivalenceDecisionRepository):
    decisions: tuple[EquivalenceDecision, ...] | Iterable[EquivalenceDecision] = ()
    _history_by_pair: dict[tuple[EntityId, EntityId], tuple[EquivalenceDecision, ...]] = field(
        init=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized = tuple(sorted(tuple(self.decisions), key=self._sort_key))
        history_by_pair: dict[tuple[EntityId, EntityId], list[EquivalenceDecision]] = defaultdict(list)
        seen_ids: set[EntityId] = set()
        seen_revisions: dict[tuple[EntityId, EntityId], set[int]] = defaultdict(set)

        for decision in normalized:
            if decision.decision_id in seen_ids:
                raise ValueError("Duplicate equivalence decision_id detected")
            seen_ids.add(decision.decision_id)
            pair = (decision.mention_id, decision.catalog_entity_id)
            if decision.revision in seen_revisions[pair]:
                raise ValueError("Contradictory active equivalence decisions detected for the same mention-concept revision")
            seen_revisions[pair].add(decision.revision)
            history_by_pair[pair].append(decision)

        for pair, history in history_by_pair.items():
            expected_revisions = tuple(range(1, len(history) + 1))
            actual_revisions = tuple(decision.revision for decision in history)
            if actual_revisions != expected_revisions:
                raise ValueError(
                    f"Equivalence decision history must be contiguous for pair {pair}: expected {expected_revisions}, got {actual_revisions}"
                )

        object.__setattr__(self, "decisions", normalized)
        object.__setattr__(
            self,
            "_history_by_pair",
            {pair: tuple(history) for pair, history in history_by_pair.items()},
        )

    @classmethod
    def empty(cls) -> "InMemoryEquivalenceDecisionRepository":
        return cls(())

    def get_active(self, mention_id: EntityId, catalog_entity_id: EntityId) -> EquivalenceDecision | None:
        history = self._history_by_pair.get((mention_id, catalog_entity_id), ())
        return history[-1] if history else None

    def list_history(self, mention_id: EntityId, catalog_entity_id: EntityId) -> tuple[EquivalenceDecision, ...]:
        return self._history_by_pair.get((mention_id, catalog_entity_id), ())

    def list_all(self) -> tuple[EquivalenceDecision, ...]:
        return self.decisions

    def append(self, decision: EquivalenceDecision) -> "InMemoryEquivalenceDecisionRepository":
        return InMemoryEquivalenceDecisionRepository(self.decisions + (decision,))

    @staticmethod
    def _sort_key(decision: EquivalenceDecision) -> tuple[str, str, int, str, str]:
        return (
            str(decision.mention_id),
            str(decision.catalog_entity_id),
            decision.revision,
            decision.decided_at.isoformat(),
            str(decision.decision_id),
        )
