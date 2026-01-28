from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import ExecutionPolicyState, Order, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "tf-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="tf-user",
            password_hash=hash_password("tf-password"),
            role="TRADER",
            display_name="TF User",
        )
        session.add(user)
        session.commit()


def _set_policy(overrides: Dict[str, Any]) -> None:
    defaults = client.get("/api/risk-policy/defaults").json()
    merged = {**defaults, **overrides}
    # Tests use TradingView-created orders which default to MIS; allow MIS so we
    # can exercise trade-frequency/loss-control enforcement without being
    # blocked by unrelated execution-safety defaults.
    exec_safety = dict(merged.get("execution_safety") or {})
    exec_safety["allow_mis"] = True
    exec_safety["allow_cnc"] = True
    merged["execution_safety"] = exec_safety
    resp = client.put("/api/risk-policy", json=merged)
    assert resp.status_code == 200


def _create_waiting_order(*, side: str, price: float, strategy_name: str) -> int:
    payload = {
        "secret": "tf-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "tf-user",
        "strategy_name": strategy_name,
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "15",
        "trade_details": {"order_action": side, "quantity": 1, "price": price},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    return response.json()["order_id"]


class _DummyResult:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id


class _AlwaysSuccessClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._n = 0

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        self._n += 1
        return _DummyResult(order_id=f"OK{self._n}")


def _patch_zerodha(monkeypatch: Any) -> _AlwaysSuccessClient:
    from app.api import orders as orders_api

    fake = _AlwaysSuccessClient()

    def _fake_get_client(db: Any, settings: Any) -> _AlwaysSuccessClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)
    return fake


def test_max_trades_per_symbol_per_day_blocks_third(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 2,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 3,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    strategy_name = f"tf-max-{uuid4().hex}"
    ids = [
        _create_waiting_order(side="BUY", price=3500.0, strategy_name=strategy_name),
        _create_waiting_order(side="BUY", price=3501.0, strategy_name=strategy_name),
        _create_waiting_order(side="BUY", price=3502.0, strategy_name=strategy_name),
    ]

    for oid in ids[:2]:
        resp = client.post(f"/api/orders/{oid}/execute")
        assert resp.status_code == 200
        assert resp.json()["status"] == "SENT"

    resp3 = client.post(f"/api/orders/{ids[2]}/execute")
    assert resp3.status_code == 400
    detail = resp3.json().get("detail") or {}
    assert detail.get("reason_code") == "RISK_POLICY_TRADE_FREQ_MAX_TRADES"


def test_min_bars_between_trades_blocks_within_window(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 100,
                "min_bars_between_trades": 2,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 3,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    t0 = datetime(2026, 1, 20, 3, 45, tzinfo=UTC)  # 09:15 IST
    t1 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)  # 09:30 IST (1 bar)
    t2 = datetime(2026, 1, 20, 4, 15, tzinfo=UTC)  # 09:45 IST (2 bars)

    seq = {"i": 0, "times": [t0, t1, t2]}

    def _fake_now() -> datetime:
        idx = min(seq["i"], len(seq["times"]) - 1)
        out = seq["times"][idx]
        seq["i"] += 1
        return out

    monkeypatch.setattr(orders_api, "_now_utc", _fake_now)

    strategy_name = f"tf-bars-{uuid4().hex}"
    o1 = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    o2 = _create_waiting_order(side="BUY", price=101.0, strategy_name=strategy_name)
    o3 = _create_waiting_order(side="BUY", price=102.0, strategy_name=strategy_name)

    r1 = client.post(f"/api/orders/{o1}/execute")
    assert r1.status_code == 200

    r2 = client.post(f"/api/orders/{o2}/execute")
    assert r2.status_code == 400
    assert (r2.json().get("detail") or {}).get("reason_code") == (
        "RISK_POLICY_TRADE_FREQ_MIN_BARS"
    )

    r3 = client.post(f"/api/orders/{o3}/execute")
    assert r3.status_code == 200


def test_cooldown_after_loss_blocks_reentry(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 100,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 2,
            },
            "loss_controls": {
                "max_consecutive_losses": 99,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    # BUY then SELL lower (loss) then attempt BUY within 2 bars.
    t0 = datetime(2026, 1, 20, 3, 45, tzinfo=UTC)  # 09:15 IST
    t1 = datetime(2026, 1, 20, 4, 15, tzinfo=UTC)  # 09:45 IST (2 bars later)
    t2 = datetime(2026, 1, 20, 4, 30, tzinfo=UTC)  # 10:00 IST (1 bar after loss close)
    t3 = datetime(2026, 1, 20, 4, 45, tzinfo=UTC)  # 10:15 IST (2 bars after loss close)

    seq = {"i": 0, "times": [t0, t1, t2, t3]}

    def _fake_now() -> datetime:
        idx = min(seq["i"], len(seq["times"]) - 1)
        out = seq["times"][idx]
        seq["i"] += 1
        return out

    monkeypatch.setattr(orders_api, "_now_utc", _fake_now)

    strategy_name = f"tf-cool-{uuid4().hex}"
    buy = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    sell = _create_waiting_order(side="SELL", price=90.0, strategy_name=strategy_name)
    re1 = _create_waiting_order(side="BUY", price=95.0, strategy_name=strategy_name)
    re2 = _create_waiting_order(side="BUY", price=96.0, strategy_name=strategy_name)

    assert client.post(f"/api/orders/{buy}/execute").status_code == 200
    assert client.post(f"/api/orders/{sell}/execute").status_code == 200

    r_block = client.post(f"/api/orders/{re1}/execute")
    assert r_block.status_code == 400
    assert (r_block.json().get("detail") or {}).get("reason_code") == (
        "RISK_POLICY_TRADE_FREQ_COOLDOWN_LOSS"
    )

    r_ok = client.post(f"/api/orders/{re2}/execute")
    assert r_ok.status_code == 200


def test_pause_after_loss_streak_eod_blocks_then_unblocks_next_day(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 100,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 1,
                "pause_after_loss_streak": True,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    # Same day: loss triggers pause; next order blocked. Next day: allowed.
    t0 = datetime(2026, 1, 20, 3, 45, tzinfo=UTC)  # 09:15 IST
    t1 = datetime(2026, 1, 20, 4, 15, tzinfo=UTC)  # 09:45 IST
    t2 = datetime(2026, 1, 20, 4, 30, tzinfo=UTC)  # 10:00 IST (still paused)
    t3 = datetime(2026, 1, 21, 3, 45, tzinfo=UTC)  # next day 09:15 IST

    seq = {"i": 0, "times": [t0, t1, t2, t3]}

    def _fake_now() -> datetime:
        idx = min(seq["i"], len(seq["times"]) - 1)
        out = seq["times"][idx]
        seq["i"] += 1
        return out

    monkeypatch.setattr(orders_api, "_now_utc", _fake_now)

    strategy_name = f"tf-pause-{uuid4().hex}"
    buy = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    sell = _create_waiting_order(side="SELL", price=90.0, strategy_name=strategy_name)
    blocked = _create_waiting_order(
        side="BUY", price=95.0, strategy_name=strategy_name
    )
    next_day = _create_waiting_order(
        side="BUY", price=96.0, strategy_name=strategy_name
    )

    assert client.post(f"/api/orders/{buy}/execute").status_code == 200
    assert client.post(f"/api/orders/{sell}/execute").status_code == 200

    r_block = client.post(f"/api/orders/{blocked}/execute")
    assert r_block.status_code == 400
    assert (r_block.json().get("detail") or {}).get("reason_code") in {
        "RISK_POLICY_PAUSED",
        "RISK_POLICY_LOSS_STREAK_PAUSE",
    }

    r_ok = client.post(f"/api/orders/{next_day}/execute")
    assert r_ok.status_code == 200


def test_block_reason_is_persisted_on_order_row(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 1,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 3,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    strategy_name = f"tf-persist-{uuid4().hex}"
    o1 = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    o2 = _create_waiting_order(side="BUY", price=101.0, strategy_name=strategy_name)
    assert client.post(f"/api/orders/{o1}/execute").status_code == 200
    r2 = client.post(f"/api/orders/{o2}/execute")
    assert r2.status_code == 400

    with SessionLocal() as session:
        order2 = session.get(Order, o2)
        assert order2 is not None
        assert order2.status == "REJECTED_RISK"
        assert "RISK_POLICY_TRADE_FREQ_MAX_TRADES" in (order2.error_message or "")


def test_concurrent_execution_waits_instead_of_permanently_rejecting(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 100,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 99,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    t0 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)
    times = [
        t0,
        t0 + timedelta(seconds=0.1),
        t0 + timedelta(seconds=0.2),
        t0 + timedelta(seconds=0.6),
        t0 + timedelta(seconds=1.1),
        t0 + timedelta(seconds=1.2),
        t0 + timedelta(seconds=1.3),
    ]

    def _fake_now() -> datetime:
        return times.pop(0) if times else (t0 + timedelta(seconds=2))

    monkeypatch.setattr(orders_api, "_now_utc", _fake_now)
    monkeypatch.setattr(orders_api.time, "sleep", lambda _s: None)

    strategy_name = f"tf-concurrent-{uuid4().hex}"
    inflight_order_id = _create_waiting_order(
        side="BUY", price=100.0, strategy_name=strategy_name
    )
    waiting_order_id = _create_waiting_order(
        side="BUY", price=101.0, strategy_name=strategy_name
    )

    with SessionLocal() as session:
        inflight_order = session.get(Order, inflight_order_id)
        assert inflight_order is not None
        key = orders_api.scope_key_for_order(inflight_order)
        state = orders_api.get_or_create_execution_state(
            session,
            key=key,
            now_utc=t0,
            interval_minutes=15,
            lock=True,
        )
        state.inflight_order_id = int(inflight_order_id)
        state.inflight_started_at = t0
        state.inflight_expires_at = t0 + timedelta(seconds=1)
        session.add(state)
        session.commit()

    # Should wait briefly for inflight marker to clear (instead of rejecting as REJECTED_RISK).
    resp = client.post(f"/api/orders/{waiting_order_id}/execute")
    assert resp.status_code == 200

    with SessionLocal() as session:
        order2 = session.get(Order, waiting_order_id)
        assert order2 is not None
        assert order2.status != "REJECTED_RISK"
        assert "RISK_POLICY_CONCURRENT_EXECUTION" not in (order2.error_message or "")


def test_entry_only_counting_and_structural_exit_never_blocked(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 1,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 1,
                "pause_after_loss_streak": True,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    t0 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)

    def _fake_now() -> datetime:
        return t0

    monkeypatch.setattr(orders_api, "_now_utc", _fake_now)

    strategy_name = f"tf-exit-{uuid4().hex}"
    buy = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    sell_exit = _create_waiting_order(
        side="SELL", price=90.0, strategy_name=strategy_name
    )
    buy2 = _create_waiting_order(side="BUY", price=101.0, strategy_name=strategy_name)

    assert client.post(f"/api/orders/{buy}/execute").status_code == 200

    # Force a pause on the scope key and ensure the exposure-reducing SELL is
    # still allowed.
    with SessionLocal() as session:
        order_buy = session.get(Order, buy)
        assert order_buy is not None
        key = orders_api.scope_key_for_order(order_buy)
        expected_ref = str(key.strategy_ref)
        state = orders_api.get_or_create_execution_state(
            session,
            key=key,
            now_utc=t0,
            interval_minutes=15,
            lock=True,
        )
        state.paused_until = t0 + timedelta(hours=1)
        state.paused_reason = "Paused by test."
        session.add(state)
        session.commit()

    assert client.post(f"/api/orders/{sell_exit}/execute").status_code == 200

    # Remove pause so the next block reason is purely trade-frequency.
    with SessionLocal() as session:
        state = (
            session.query(ExecutionPolicyState)
            .filter(ExecutionPolicyState.strategy_ref == expected_ref)
            .one()
        )
        state.paused_until = None
        state.paused_reason = None
        session.add(state)
        session.commit()

    # Second entry should be blocked by max-trades-per-day, proving exits don't
    # consume trades_today.
    r2 = client.post(f"/api/orders/{buy2}/execute")
    assert r2.status_code == 400
    assert (r2.json().get("detail") or {}).get("reason_code") == (
        "RISK_POLICY_TRADE_FREQ_MAX_TRADES"
    )

    with SessionLocal() as session:
        # trades_today must still be 1 (entry-only counting).
        state = (
            session.query(ExecutionPolicyState)
            .filter(ExecutionPolicyState.strategy_ref == expected_ref)
            .one()
        )
        assert state.trades_today == 1


def test_interval_default_fallback_is_persisted_with_source(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 100,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 99,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    t0 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)
    monkeypatch.setattr(orders_api, "_now_utc", lambda: t0)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "tf-user").one()
        user_id = int(user.id)
        order = Order(
            user_id=user_id,
            broker_name="zerodha",
            alert_id=None,
            strategy_id=None,
            portfolio_group_id=None,
            deployment_id=None,
            deployment_action_id=None,
            symbol="NSE:TCS",
            exchange="NSE",
            side="BUY",
            qty=1.0,
            price=100.0,
            order_type="LIMIT",
            product="MIS",
            gtt=False,
            synthetic_gtt=False,
            status="WAITING",
            mode="MANUAL",
            execution_target="LIVE",
            simulated=False,
            error_message=None,
        )
        session.add(order)
        session.commit()
        oid = int(order.id)

    resp = client.post(f"/api/orders/{oid}/execute")
    assert resp.status_code == 200

    with SessionLocal() as session:
        state = (
            session.query(ExecutionPolicyState)
            .filter(
                ExecutionPolicyState.user_id == user_id,
                ExecutionPolicyState.strategy_ref == "manual",
                ExecutionPolicyState.symbol == "NSE:TCS",
                ExecutionPolicyState.product == "MIS",
            )
            .one()
        )
        assert int(state.interval_minutes) == 5
        assert state.interval_source == "default_fallback"
        assert bool(state.default_interval_logged) is True


def test_concurrent_executions_do_not_race_past_max_trades(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 1,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 99,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api
    import threading

    t0 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)
    monkeypatch.setattr(orders_api, "_now_utc", lambda: t0)

    strategy_name = f"tf-conc-{uuid4().hex}"
    o1 = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    o2 = _create_waiting_order(side="BUY", price=101.0, strategy_name=strategy_name)

    barrier = threading.Barrier(2)
    results: List[str] = []

    def _run(order_id: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                out = orders_api.execute_order_internal(
                    order_id, db=session, settings=get_settings()
                )
                results.append(str(getattr(out, "status", "")))
            except HTTPException as exc:
                if isinstance(exc.detail, dict):
                    results.append(str(exc.detail.get("reason_code") or "blocked"))
                else:
                    results.append("blocked")

    t1 = threading.Thread(target=_run, args=(o1,))
    t2 = threading.Thread(target=_run, args=(o2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert results.count("SENT") == 1
    assert len(results) == 2
    assert any(r != "SENT" for r in results)


def test_trade_frequency_group_toggle_off_disables_trade_frequency_blocks(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "enforcement": {"trade_frequency": False},
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 1,
                "min_bars_between_trades": 100,
                "cooldown_after_loss_bars": 100,
            },
            "loss_controls": {
                "max_consecutive_losses": 99,
                "pause_after_loss_streak": False,
                "pause_duration": "EOD",
            },
        }
    )

    strategy_name = f"tf-off-{uuid4().hex}"
    o1 = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    o2 = _create_waiting_order(side="BUY", price=101.0, strategy_name=strategy_name)
    o3 = _create_waiting_order(side="BUY", price=102.0, strategy_name=strategy_name)

    assert client.post(f"/api/orders/{o1}/execute").status_code == 200
    assert client.post(f"/api/orders/{o2}/execute").status_code == 200
    assert client.post(f"/api/orders/{o3}/execute").status_code == 200


def test_loss_controls_group_toggle_off_disables_pause(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "enforcement": {"loss_controls": False},
            "trade_frequency": {
                "max_trades_per_symbol_per_day": 100,
                "min_bars_between_trades": 0,
                "cooldown_after_loss_bars": 0,
            },
            "loss_controls": {
                "max_consecutive_losses": 1,
                "pause_after_loss_streak": True,
                "pause_duration": "EOD",
            },
        }
    )

    from app.api import orders as orders_api

    t0 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)
    monkeypatch.setattr(orders_api, "_now_utc", lambda: t0)

    strategy_name = f"lc-off-{uuid4().hex}"
    buy = _create_waiting_order(side="BUY", price=100.0, strategy_name=strategy_name)
    sell = _create_waiting_order(side="SELL", price=90.0, strategy_name=strategy_name)
    reentry = _create_waiting_order(
        side="BUY", price=101.0, strategy_name=strategy_name
    )

    assert client.post(f"/api/orders/{buy}/execute").status_code == 200
    assert client.post(f"/api/orders/{sell}/execute").status_code == 200

    # Loss controls group is disabled, so pause-after-streak must not block.
    r = client.post(f"/api/orders/{reentry}/execute")
    assert r.status_code == 200
