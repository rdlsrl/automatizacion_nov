"""Repositories for the initial IDKB backbone."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from drilling_knowledge.catalog.repositories.memory import InMemoryEntityRepository
from drilling_knowledge.idkb.domain import (
    ArticleTemplate,
    CanonicalIdentifierDefinition,
    KnowledgeDomain,
    KnowledgePackManifest,
    MaturityLevel,
)


class IdkbRepository(Protocol):
    @property
    def domains(self) -> InMemoryEntityRepository[KnowledgeDomain]:
        ...

    @property
    def identifier_definitions(self) -> InMemoryEntityRepository[CanonicalIdentifierDefinition]:
        ...

    @property
    def article_templates(self) -> InMemoryEntityRepository[ArticleTemplate]:
        ...

    @property
    def maturity_levels(self) -> InMemoryEntityRepository[MaturityLevel]:
        ...

    @property
    def knowledge_packs(self) -> InMemoryEntityRepository[KnowledgePackManifest]:
        ...


@dataclass(slots=True)
class InMemoryIdkbRepository:
    domains: InMemoryEntityRepository[KnowledgeDomain] = field(default_factory=lambda: InMemoryEntityRepository(()))
    identifier_definitions: InMemoryEntityRepository[CanonicalIdentifierDefinition] = field(
        default_factory=lambda: InMemoryEntityRepository(())
    )
    article_templates: InMemoryEntityRepository[ArticleTemplate] = field(
        default_factory=lambda: InMemoryEntityRepository(())
    )
    maturity_levels: InMemoryEntityRepository[MaturityLevel] = field(default_factory=lambda: InMemoryEntityRepository(()))
    knowledge_packs: InMemoryEntityRepository[KnowledgePackManifest] = field(
        default_factory=lambda: InMemoryEntityRepository(())
    )

    @classmethod
    def empty(cls) -> "InMemoryIdkbRepository":
        return cls()