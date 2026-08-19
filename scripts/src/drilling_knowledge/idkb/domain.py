"""Domain entities for the initial IDKB backbone."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.catalog.domain import KnowledgeEntity
from drilling_knowledge.catalog.domain.value_objects import CatalogCode


@dataclass(frozen=True, slots=True)
class KnowledgeDomain(KnowledgeEntity):
    parent_code: CatalogCode | None = None
    volume_code: str = ""

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        volume_code = self.volume_code.strip().lower()
        if not volume_code:
            raise ValueError("KnowledgeDomain.volume_code cannot be empty")
        object.__setattr__(self, "volume_code", volume_code)


@dataclass(frozen=True, slots=True)
class CanonicalIdentifierDefinition(KnowledgeEntity):
    namespace: str = ""
    target_kind: str = ""
    pattern: str = ""

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        namespace = self.namespace.strip().lower()
        target_kind = self.target_kind.strip().lower()
        pattern = self.pattern.strip()
        if not namespace:
            raise ValueError("CanonicalIdentifierDefinition.namespace cannot be empty")
        if not target_kind:
            raise ValueError("CanonicalIdentifierDefinition.target_kind cannot be empty")
        if not pattern:
            raise ValueError("CanonicalIdentifierDefinition.pattern cannot be empty")
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "target_kind", target_kind)
        object.__setattr__(self, "pattern", pattern)


@dataclass(frozen=True, slots=True)
class ArticleTemplate(KnowledgeEntity):
    target_kind: str = ""
    required_sections: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        target_kind = self.target_kind.strip().lower()
        sections = tuple(section.strip().lower() for section in self.required_sections if section.strip())
        if not target_kind:
            raise ValueError("ArticleTemplate.target_kind cannot be empty")
        if not sections:
            raise ValueError("ArticleTemplate.required_sections cannot be empty")
        object.__setattr__(self, "target_kind", target_kind)
        object.__setattr__(self, "required_sections", sections)


@dataclass(frozen=True, slots=True)
class MaturityLevel(KnowledgeEntity):
    ordinal: int = 0

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        if self.ordinal < 0:
            raise ValueError("MaturityLevel.ordinal cannot be negative")


@dataclass(frozen=True, slots=True)
class KnowledgePackManifest(KnowledgeEntity):
    pack_version: str = "1.0.0"
    domain_codes: tuple[CatalogCode, ...] = ()
    article_template_code: CatalogCode = field(default_factory=lambda: CatalogCode("undefined.template"))
    maturity_level_code: CatalogCode = field(default_factory=lambda: CatalogCode("m0"))

    def __post_init__(self) -> None:
        KnowledgeEntity.__post_init__(self)
        pack_version = self.pack_version.strip()
        if not pack_version:
            raise ValueError("KnowledgePackManifest.pack_version cannot be empty")
        if not self.domain_codes:
            raise ValueError("KnowledgePackManifest.domain_codes cannot be empty")
        object.__setattr__(self, "pack_version", pack_version)