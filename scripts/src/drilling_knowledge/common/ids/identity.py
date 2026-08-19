"""Strongly typed identifiers used across the platform."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5


@dataclass(frozen=True, slots=True)
class Identifier:
    """Base immutable identifier wrapper.

    Subclasses provide semantic clarity without changing runtime behavior.
    """

    value: UUID

    @classmethod
    def new(cls) -> "Identifier":
        return cls(uuid4())

    @classmethod
    def from_string(cls, raw: str) -> "Identifier":
        return cls(UUID(raw.strip()))

    @classmethod
    def from_seed(cls, namespace: str, seed: str) -> "Identifier":
        return cls(uuid5(NAMESPACE_URL, f"{namespace}:{seed.strip()}"))

    def as_uuid(self) -> UUID:
        return self.value

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class EntityId(Identifier):
    """Identifier for persistent semantic entities."""


@dataclass(frozen=True, slots=True)
class RunId(Identifier):
    """Identifier for workflow and pipeline runs."""


@dataclass(frozen=True, slots=True)
class CorrelationId(Identifier):
    """Identifier used to correlate logs and cross-cutting operations."""
