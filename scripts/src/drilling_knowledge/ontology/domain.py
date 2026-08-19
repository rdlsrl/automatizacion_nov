"""Deterministic ontology relations over existing catalog concepts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class OntologyRelationType(StrEnum):
    IS_A = "IS_A"
    MEASURES = "MEASURES"
    BELONGS_TO_SUBSYSTEM = "BELONGS_TO_SUBSYSTEM"
    PRODUCED_BY_SENSOR = "PRODUCED_BY_SENSOR"
    USES_UNIT = "USES_UNIT"
    UNIT_COMPATIBLE_WITH_QUANTITY = "UNIT_COMPATIBLE_WITH_QUANTITY"
    ALIAS_OF = "ALIAS_OF"
    RELATED_TO = "RELATED_TO"


class OntologyRelationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True, slots=True)
class OntologyConceptReference:
    concept_id: EntityId
    catalog_code: str
    catalog_entity_type: str
    canonical_name: str

    def __post_init__(self) -> None:
        catalog_code = self.catalog_code.strip()
        catalog_entity_type = self.catalog_entity_type.strip()
        canonical_name = self.canonical_name.strip()
        if not catalog_code:
            raise ValueError("OntologyConceptReference.catalog_code cannot be empty")
        if not catalog_entity_type:
            raise ValueError("OntologyConceptReference.catalog_entity_type cannot be empty")
        if not canonical_name:
            raise ValueError("OntologyConceptReference.canonical_name cannot be empty")
        object.__setattr__(self, "catalog_code", catalog_code)
        object.__setattr__(self, "catalog_entity_type", catalog_entity_type)
        object.__setattr__(self, "canonical_name", canonical_name)


@dataclass(frozen=True, slots=True)
class OntologyRelation:
    relation_id: EntityId
    source_concept: OntologyConceptReference
    target_concept: OntologyConceptReference
    relation_type: OntologyRelationType
    status: OntologyRelationStatus
    evidence: str
    rationale: str
    source_trace: ExtractionSourceTrace
    created_by: str
    created_at: datetime
    revision: int

    @property
    def source_concept_id(self) -> EntityId:
        return self.source_concept.concept_id

    @property
    def target_concept_id(self) -> EntityId:
        return self.target_concept.concept_id

    def __post_init__(self) -> None:
        evidence = self.evidence.strip()
        rationale = self.rationale.strip()
        created_by = self.created_by.strip()
        if not evidence:
            raise ValueError("OntologyRelation.evidence cannot be empty")
        if not rationale:
            raise ValueError("OntologyRelation.rationale cannot be empty")
        if not created_by:
            raise ValueError("OntologyRelation.created_by cannot be empty")
        if self.revision < 1:
            raise ValueError("OntologyRelation.revision must be >= 1")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "created_by", created_by)
