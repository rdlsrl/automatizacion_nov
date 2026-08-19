"""Ontology repository implementations and contracts."""

from drilling_knowledge.ontology.repositories.contracts import OntologyRelationRepository
from drilling_knowledge.ontology.repositories.memory import InMemoryOntologyRelationRepository

__all__ = ["InMemoryOntologyRelationRepository", "OntologyRelationRepository"]
