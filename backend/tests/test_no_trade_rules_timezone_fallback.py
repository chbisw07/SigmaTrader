from __future__ import annotations

from datetime import UTC, datetime, time as dt_time
from typing import Any


def _break_zoneinfo(monkeypatch: Any) -> None:
    import zoneinfo

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise Exception("zoneinfo unavailable")

    monkeypatch.setattr(zoneinfo, "ZoneInfo", _boom)


def test_resolve_no_trade_action_uses_ist_offset_when_zoneinfo_missing(
    monkeypatch: Any,
) -> None:
    _break_zoneinfo(monkeypatch)

    from app.services.no_trade_rules import resolve_no_trade_action

    # 03:47 UTC == 09:17 IST
    now_utc = datetime(2026, 2, 27, 3, 47, tzinfo=UTC)
    rules = "09:15-09:20 PAUSE_AUTO CNC_BUY"

    match = resolve_no_trade_action(
        rules_text=rules,
        now_utc=now_utc,
        product="CNC",
        side="BUY",
    )
    assert match is not None
    assert match.action == "PAUSE_AUTO"

    after_utc = datetime(2026, 2, 27, 3, 51, tzinfo=UTC)  # 09:21 IST
    assert (
        resolve_no_trade_action(
            rules_text=rules,
            now_utc=after_utc,
            product="CNC",
            side="BUY",
        )
        is None
    )


def test_compute_defer_until_utc_uses_ist_offset_when_zoneinfo_missing(
    monkeypatch: Any,
) -> None:
    _break_zoneinfo(monkeypatch)

    from app.services.no_trade_rules import compute_no_trade_defer_until_utc

    # 03:47 UTC == 09:17 IST; defer until 09:20 IST == 03:50 UTC
    now_utc = datetime(2026, 2, 27, 3, 47, tzinfo=UTC)
    defer_until = compute_no_trade_defer_until_utc(
        now_utc=now_utc,
        start=dt_time(9, 15),
        end=dt_time(9, 20),
    )
    assert defer_until == datetime(2026, 2, 27, 3, 50, tzinfo=UTC)
