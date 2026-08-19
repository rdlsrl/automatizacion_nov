"""Repository contracts for ontology proposal runs."""

from drilling_knowledge.catalog.services.ontology_proposals.repositories.contracts import OntologyProposalRunRepository
from drilling_knowledge.catalog.services.ontology_proposals.repositories.memory import InMemoryOntologyProposalRunRepository

__all__ = ["InMemoryOntologyProposalRunRepository", "OntologyProposalRunRepository"]