from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, Strategy, User
from app.services.risk_unified_store import upsert_unified_risk_global

client = TestClient(app)


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "no-trade-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="no-trade-user",
                password_hash=hash_password("no-trade-password"),
                role="TRADER",
                display_name="No Trade User",
            )
        )
        session.add(
            Strategy(
                name="no-trade-auto",
                description="test",
                owner_id=None,
                scope="GLOBAL",
                execution_mode="AUTO",
                execution_target="LIVE",
                enabled=True,
                available_for_alert=True,
            )
        )
        session.commit()


def _create_waiting_order(*, side: str = "BUY") -> int:
    # Use strategy-driven mode (default fallback) so we can set execution_mode=AUTO
    # without requiring TradingView webhook config rows.
    payload: Dict[str, Any] = {
        "secret": "no-trade-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "no-trade-user",
        "strategy_name": "no-trade-auto",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": side, "quantity": 1, "price": 1500.0},
    }
    resp = client.post("/webhook/tradingview", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    return int(data["order_id"])


def test_auto_dispatch_is_deferred_during_no_trade_window(monkeypatch: Any) -> None:
    # Create a rule window that includes "now" in IST.
    now_utc = datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = now_utc
    start = now_ist - timedelta(minutes=1)
    end = now_ist + timedelta(minutes=1)
    rules = f"{_hhmm(start)}-{_hhmm(end)} PAUSE_AUTO CNC_BUY"

    with SessionLocal() as session:
        # Ensure this webhook is routed via strategy mode with AUTO execution.
        existing = (
            session.query(Strategy).filter(Strategy.name == "no-trade-auto").one_or_none()
        )
        if existing is None:
            session.add(
                Strategy(
                    name="no-trade-auto",
                    description="test",
                    owner_id=None,
                    scope="GLOBAL",
                    execution_mode="AUTO",
                    execution_target="LIVE",
                    enabled=True,
                    available_for_alert=True,
                )
            )
        upsert_unified_risk_global(
            session,
            enabled=False,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
            no_trade_rules=rules,
        )
        session.commit()

    from app.api import orders as orders_api

    def _fail_get_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Broker client must not be created during AUTO pause window.")

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fail_get_client)

    order_id = _create_waiting_order(side="BUY")

    resp = client.post(f"/api/orders/{order_id}/execute?auto_dispatch=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "WAITING"
    assert data["mode"] == "MANUAL"
    assert "paused" in (data.get("error_message") or "").lower()
    assert data.get("armed_at") is not None

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "WAITING"
        assert order.mode == "MANUAL"
        assert "paused" in (order.error_message or "").lower()
        assert order.armed_at is not None


def test_no_trade_auto_resume_worker_is_disabled(monkeypatch: Any) -> None:
    # Create a short-lived window that includes "now" and ensure we do NOT
    # automatically resume execution after it ends.
    now_utc = datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = now_utc
    start = now_ist - timedelta(minutes=1)
    end = now_ist + timedelta(minutes=1)
    rules = f"{_hhmm(start)}-{_hhmm(end)} PAUSE_AUTO CNC_BUY"

    with SessionLocal() as session:
        upsert_unified_risk_global(
            session,
            enabled=False,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
            no_trade_rules=rules,
        )

    from app.api import orders as orders_api

    # Ensure the initial AUTO execution is paused (no broker client creation).
    def _fail_get_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Broker client must not be created during AUTO pause window.")

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fail_get_client)

    order_id = _create_waiting_order(side="BUY")

    # Make the order eligible for what used to be an auto-resume worker.
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        order.armed_at = now_utc - timedelta(seconds=1)
        session.add(order)
        session.commit()

    # Advance "now" used by execution to after the window end.
    later_utc = now_utc + timedelta(minutes=2)
    monkeypatch.setattr(orders_api, "_now_utc", lambda: later_utc)

    from app.services import no_trade_deferred_dispatch as nt_worker

    processed = nt_worker.process_no_trade_deferred_dispatch_once()
    assert processed == 0

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "WAITING"
        assert order.mode == "MANUAL"


def test_auto_mode_is_deferred_without_auto_dispatch_flag(monkeypatch: Any) -> None:
    now_utc = datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = now_utc
    start = now_ist - timedelta(minutes=1)
    end = now_ist + timedelta(minutes=1)
    rules = f"{_hhmm(start)}-{_hhmm(end)} PAUSE_AUTO CNC_BUY"

    with SessionLocal() as session:
        upsert_unified_risk_global(
            session,
            enabled=False,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
            no_trade_rules=rules,
        )
        user = session.query(User).filter(User.username == "no-trade-user").one()
        order = Order(
            user_id=user.id,
            broker_name="zerodha",
            alert_id=None,
            strategy_id=None,
            portfolio_group_id=None,
            symbol="NSE:INFY",
            exchange="NSE",
            side="BUY",
            qty=1.0,
            price=None,
            trigger_price=None,
            trigger_percent=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            synthetic_gtt=False,
            status="WAITING",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            error_message=None,
            risk_spec_json=None,
            is_exit=False,
            created_at=now_utc,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        order_id = int(order.id)

    from app.api import orders as orders_api

    def _fail_get_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Broker client must not be created during AUTO pause window.")

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fail_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "WAITING"
    assert data["mode"] == "MANUAL"
    assert "paused" in (data.get("error_message") or "").lower()
    assert data.get("armed_at") is not None


def test_auto_exit_is_deferred_during_no_trade_window(monkeypatch: Any) -> None:
    now_utc = datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = now_utc
    start = now_ist - timedelta(minutes=1)
    end = now_ist + timedelta(minutes=1)
    rules = f"{_hhmm(start)}-{_hhmm(end)} PAUSE_AUTO CNC_SELL"

    with SessionLocal() as session:
        upsert_unified_risk_global(
            session,
            enabled=False,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
            no_trade_rules=rules,
        )
        user = session.query(User).filter(User.username == "no-trade-user").one()
        order = Order(
            user_id=user.id,
            broker_name="zerodha",
            alert_id=None,
            strategy_id=None,
            portfolio_group_id=None,
            symbol="NSE:INFY",
            exchange="NSE",
            side="SELL",
            qty=1.0,
            price=None,
            trigger_price=None,
            trigger_percent=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            synthetic_gtt=False,
            status="WAITING",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            error_message=None,
            risk_spec_json=None,
            is_exit=True,
            created_at=now_utc,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        order_id = int(order.id)

    from app.api import orders as orders_api

    def _fail_get_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Broker client must not be created during AUTO pause window.")

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fail_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "WAITING"
    assert data["mode"] == "MANUAL"
    assert "paused" in (data.get("error_message") or "").lower()
    assert data.get("armed_at") is not None
