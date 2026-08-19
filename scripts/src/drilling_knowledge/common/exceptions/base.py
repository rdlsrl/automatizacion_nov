"""Base exception types for the platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlatformError(Exception):
    """Base error carrying a stable code and structured context."""

    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        if not self.context:
            return f"{self.code}: {self.message}"
        return f"{self.code}: {self.message} | context={self.context}"


class ValidationError(PlatformError):
    """Raised when input or domain validation fails."""


class ConfigurationError(PlatformError):
    """Raised when required configuration is missing or invalid."""


class NotFoundError(PlatformError):
    """Raised when a requested entity is not found."""


class ConflictError(PlatformError):
    """Raised when mutually incompatible states are detected."""


class DuplicateCanonicalCodeError(ConflictError):
    """Raised when two canonical records collide on the same effective identity."""


class InvariantViolationError(PlatformError):
    """Raised when a core domain invariant is violated."""
