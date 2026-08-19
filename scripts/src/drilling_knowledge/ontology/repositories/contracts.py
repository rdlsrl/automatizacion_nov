"""Repository contracts for explicit ontology relations."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.ontology.domain import OntologyRelation, OntologyRelationStatus, OntologyRelationType


class OntologyRelationRepository(Protocol):
    def get_latest(self, source_concept_id: EntityId, target_concept_id: EntityId, relation_type: OntologyRelationType) -> OntologyRelation | None:
        ...

    def get_active(self, source_concept_id: EntityId, target_concept_id: EntityId, relation_type: OntologyRelationType) -> OntologyRelation | None:
        ...

    def list_history(self, source_concept_id: EntityId, target_concept_id: EntityId, relation_type: OntologyRelationType) -> tuple[OntologyRelation, ...]:
        ...

    def list_all(self) -> tuple[OntologyRelation, ...]:
        ...

    def list_by_status(self, status: OntologyRelationStatus) -> tuple[OntologyRelation, ...]:
        ...

    def append(self, relation: OntologyRelation) -> "OntologyRelationRepository":
        ...
