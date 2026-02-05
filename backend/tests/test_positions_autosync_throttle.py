from __future__ import annotations

from datetime import UTC, datetime, timedelta


class _DummyThread:
    def __init__(self, *, target, name: str, daemon: bool):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True


def test_positions_autosync_is_throttled(monkeypatch) -> None:
    from app.services import positions_autosync

    positions_autosync._reset_autosync_state_for_tests()
    monkeypatch.setattr(positions_autosync, "Thread", _DummyThread)

    # Unknown broker does nothing.
    scheduled = positions_autosync.schedule_positions_autosync(
        settings=object(),  # not used when broker != zerodha
        broker_name="angelone",
        user_id=1,
        reason="test",
    )
    assert scheduled is False

    # First schedule succeeds and marks pending.
    scheduled = positions_autosync.schedule_positions_autosync(
        settings=object(),  # thread won't run due to dummy Thread
        broker_name="zerodha",
        user_id=1,
        reason="test",
        delay_seconds=9999.0,
        min_interval_seconds=60.0,
    )
    assert scheduled is True

    # Second schedule is rejected while pending.
    scheduled = positions_autosync.schedule_positions_autosync(
        settings=object(),
        broker_name="zerodha",
        user_id=1,
        reason="test",
        delay_seconds=9999.0,
        min_interval_seconds=60.0,
    )
    assert scheduled is False

    # Simulate completion and enforce min-interval.
    key = ("zerodha", 1)
    positions_autosync._state[key] = {
        "pending": False,
        "last_done_at": datetime.now(UTC),
    }
    scheduled = positions_autosync.schedule_positions_autosync(
        settings=object(),
        broker_name="zerodha",
        user_id=1,
        reason="test",
        delay_seconds=9999.0,
        min_interval_seconds=60.0,
    )
    assert scheduled is False

    # Past min-interval should allow scheduling again.
    positions_autosync._state[key] = {
        "pending": False,
        "last_done_at": datetime.now(UTC) - timedelta(seconds=120),
    }
    scheduled = positions_autosync.schedule_positions_autosync(
        settings=object(),
        broker_name="zerodha",
        user_id=1,
        reason="test",
        delay_seconds=9999.0,
        min_interval_seconds=60.0,
    )
    assert scheduled is True

