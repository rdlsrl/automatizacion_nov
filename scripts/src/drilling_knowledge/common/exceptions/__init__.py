"""Domain-specific exception hierarchy."""

from .base import (
    ConfigurationError,
    ConflictError,
    DuplicateCanonicalCodeError,
    InvariantViolationError,
    NotFoundError,
    PlatformError,
    ValidationError,
)

__all__ = [
    "ConfigurationError",
    "ConflictError",
    "DuplicateCanonicalCodeError",
    "InvariantViolationError",
    "NotFoundError",
    "PlatformError",
    "ValidationError",
]
