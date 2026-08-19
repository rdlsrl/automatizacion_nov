from __future__ import annotations

from datetime import UTC, datetime

from drilling_knowledge.common.time import FrozenClock, UtcClock


def test_utc_clock_returns_timezone_aware_timestamp() -> None:
    current = UtcClock().now()

    assert current.tzinfo == UTC


def test_frozen_clock_is_deterministic_and_advanceable() -> None:
    frozen = FrozenClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    assert frozen.now() == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert frozen.advance_seconds(30) == datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
