"""Explicit ontology relations package."""

from drilling_knowledge.ontology.domain import (
    OntologyConceptReference,
    OntologyRelation,
    OntologyRelationStatus,
    OntologyRelationType,
)
from drilling_knowledge.ontology.repositories.contracts import OntologyRelationRepository
from drilling_knowledge.ontology.repositories.memory import InMemoryOntologyRelationRepository
from drilling_knowledge.ontology.service import OntologyService

__all__ = [
    "InMemoryOntologyRelationRepository",
    "OntologyConceptReference",
    "OntologyRelation",
    "OntologyRelationRepository",
    "OntologyRelationStatus",
    "OntologyRelationType",
    "OntologyService",
]
