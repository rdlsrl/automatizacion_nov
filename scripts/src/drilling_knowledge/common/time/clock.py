"""Time abstractions for deterministic services and tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class Clock(Protocol):
    """Protocol for services that supply timestamps."""

    def now(self) -> datetime:
        ...


@dataclass(frozen=True, slots=True)
class UtcClock:
    """Production clock using wall-clock UTC time."""

    def now(self) -> datetime:
        return utc_now()


@dataclass(slots=True)
class FrozenClock:
    """Mutable deterministic clock for tests and replay flows."""

    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance_seconds(self, seconds: int) -> datetime:
        self.current = self.current.fromtimestamp(self.current.timestamp() + seconds, UTC)
        return self.current
