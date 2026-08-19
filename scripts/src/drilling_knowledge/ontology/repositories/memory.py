"""In-memory append-only repository for explicit ontology relations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.ontology.domain import OntologyRelation, OntologyRelationStatus, OntologyRelationType
from drilling_knowledge.ontology.repositories.contracts import OntologyRelationRepository


@dataclass(slots=True)
class InMemoryOntologyRelationRepository(OntologyRelationRepository):
    relations: tuple[OntologyRelation, ...] | Iterable[OntologyRelation] = ()
    _history_by_key: dict[tuple[EntityId, EntityId, OntologyRelationType], tuple[OntologyRelation, ...]] = field(
        init=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized = tuple(sorted(tuple(self.relations), key=self._sort_key))
        history_by_key: dict[tuple[EntityId, EntityId, OntologyRelationType], list[OntologyRelation]] = defaultdict(list)
        seen_ids: set[EntityId] = set()
        seen_revisions: dict[tuple[EntityId, EntityId, OntologyRelationType], set[int]] = defaultdict(set)

        for relation in normalized:
            if relation.relation_id in seen_ids:
                raise ValueError("Duplicate ontology relation_id detected")
            seen_ids.add(relation.relation_id)
            key = (relation.source_concept_id, relation.target_concept_id, relation.relation_type)
            if relation.revision in seen_revisions[key]:
                raise ValueError("Contradictory ontology relations detected for the same relation revision")
            seen_revisions[key].add(relation.revision)
            history_by_key[key].append(relation)

        for key, history in history_by_key.items():
            expected_revisions = tuple(range(1, len(history) + 1))
            actual_revisions = tuple(relation.revision for relation in history)
            if actual_revisions != expected_revisions:
                raise ValueError(
                    f"Ontology relation history must be contiguous for key {key}: expected {expected_revisions}, got {actual_revisions}"
                )

        object.__setattr__(self, "relations", normalized)
        object.__setattr__(self, "_history_by_key", {key: tuple(history) for key, history in history_by_key.items()})

    @classmethod
    def empty(cls) -> "InMemoryOntologyRelationRepository":
        return cls(())

    def get_latest(self, source_concept_id: EntityId, target_concept_id: EntityId, relation_type: OntologyRelationType) -> OntologyRelation | None:
        history = self.list_history(source_concept_id, target_concept_id, relation_type)
        return history[-1] if history else None

    def get_active(self, source_concept_id: EntityId, target_concept_id: EntityId, relation_type: OntologyRelationType) -> OntologyRelation | None:
        latest = self.get_latest(source_concept_id, target_concept_id, relation_type)
        return latest if latest is not None and latest.status == OntologyRelationStatus.ACTIVE else None

    def list_history(self, source_concept_id: EntityId, target_concept_id: EntityId, relation_type: OntologyRelationType) -> tuple[OntologyRelation, ...]:
        return self._history_by_key.get((source_concept_id, target_concept_id, relation_type), ())

    def list_all(self) -> tuple[OntologyRelation, ...]:
        return self.relations

    def list_by_status(self, status: OntologyRelationStatus) -> tuple[OntologyRelation, ...]:
        return tuple(relation for relation in self.relations if relation.status == status)

    def append(self, relation: OntologyRelation) -> "InMemoryOntologyRelationRepository":
        return InMemoryOntologyRelationRepository(self.relations + (relation,))

    @staticmethod
    def _sort_key(relation: OntologyRelation) -> tuple[str, str, str, int, str, str]:
        return (
            str(relation.source_concept_id),
            str(relation.target_concept_id),
            relation.relation_type.value,
            relation.revision,
            relation.created_at.isoformat(),
            str(relation.relation_id),
        )
