from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.core.time_utils import ist_naive_to_utc, to_utc, to_utc_or_none


def test_ist_naive_to_utc_converts_offset() -> None:
    dt_ist_naive = datetime(2026, 1, 16, 10, 0, 0)
    out = ist_naive_to_utc(dt_ist_naive)
    assert out.tzinfo is UTC
    assert out == datetime(2026, 1, 16, 4, 30, 0, tzinfo=UTC)


def test_to_utc_treats_naive_as_ist_by_default() -> None:
    dt_ist_naive = datetime(2026, 1, 16, 10, 0, 0)
    out = to_utc(dt_ist_naive)
    assert out == datetime(2026, 1, 16, 4, 30, 0, tzinfo=UTC)


def test_to_utc_converts_tz_aware() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    dt_aware_ist = datetime(2026, 1, 16, 10, 0, 0, tzinfo=ist)
    out = to_utc(dt_aware_ist)
    assert out == datetime(2026, 1, 16, 4, 30, 0, tzinfo=UTC)


def test_to_utc_or_none_handles_none() -> None:
    assert to_utc_or_none(None) is None
