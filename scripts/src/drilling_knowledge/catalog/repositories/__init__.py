"""Repository contracts and in-memory implementations for catalog reading."""

from .contracts import CatalogRepository, EntityRepository
from .memory import InMemoryCatalogRepository

__all__ = ["CatalogRepository", "EntityRepository", "InMemoryCatalogRepository"]
