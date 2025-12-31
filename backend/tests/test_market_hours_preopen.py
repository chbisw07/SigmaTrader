from __future__ import annotations

from datetime import datetime

from app.core.market_hours import is_preopen_now


def test_is_preopen_now_true_in_window() -> None:
    # Wednesday
    now = datetime(2025, 1, 15, 9, 5)
    assert is_preopen_now(now) is True


def test_is_preopen_now_false_outside_window() -> None:
    # Before
    now1 = datetime(2025, 1, 15, 8, 59)
    assert is_preopen_now(now1) is False
    # At market open (end-exclusive)
    now2 = datetime(2025, 1, 15, 9, 15)
    assert is_preopen_now(now2) is False
    # After
    now3 = datetime(2025, 1, 15, 10, 0)
    assert is_preopen_now(now3) is False


def test_is_preopen_now_false_on_weekend() -> None:
    # Saturday
    now = datetime(2025, 1, 18, 9, 5)
    assert is_preopen_now(now) is False
