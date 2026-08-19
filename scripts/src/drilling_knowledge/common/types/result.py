"""A small result container for explicit success/failure flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Result(Generic[T, E]):
    """Explicit result object that avoids exceptions in expected control paths."""

    value: T | None = None
    error: E | None = None

    @classmethod
    def ok(cls, value: T) -> "Result[T, E]":
        return cls(value=value, error=None)

    @classmethod
    def fail(cls, error: E) -> "Result[T, E]":
        return cls(value=None, error=error)

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def unwrap(self) -> T:
        if self.error is not None:
            raise RuntimeError(f"Cannot unwrap error result: {self.error}")
        return self.value  # type: ignore[return-value]

    def unwrap_error(self) -> E:
        if self.error is None:
            raise RuntimeError("Cannot unwrap_error from a successful result")
        return self.error
