from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Alert, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "test-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Create a dedicated user that webhook alerts can be routed to.
    with SessionLocal() as session:
        user = User(
            username="webhook-user",
            password_hash=hash_password("webhook-password"),
            role="TRADER",
            display_name="Webhook User",
        )
        session.add(user)
        session.commit()


def test_webhook_rejects_invalid_secret() -> None:
    payload = {
        "secret": "wrong-secret",
        "platform": "TRADINGVIEW",
        "strategy_name": "webhook-test-strategy",
        "symbol": "NSE:RELIANCE",
        "exchange": "NSE",
        "interval": "15",
        "trade_details": {"order_action": "BUY", "quantity": 1},
    }

    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 401


def test_webhook_persists_alert_with_valid_secret() -> None:
    unique_strategy = f"webhook-test-strategy-{uuid4().hex}"
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "SELL", "quantity": 2, "price": 1500.0},
    }

    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    alert_id = data["alert_id"]
    order_id = data["order_id"]

    with SessionLocal() as session:
        alert = session.get(Alert, alert_id)
        assert alert is not None
        assert alert.symbol == "NSE:INFY"
        assert alert.action == "SELL"
        assert alert.qty == 2
        assert alert.price == 1500.0

        from app.models import Order

        order = session.get(Order, order_id)
        assert order is not None
        assert order.alert_id == alert_id
        assert order.symbol == alert.symbol
        assert order.side == alert.action
        assert order.qty == alert.qty
        assert order.status == "WAITING"
        assert order.mode == "MANUAL"


def test_webhook_auto_strategy_routes_to_auto_and_executes(monkeypatch: Any) -> None:
    unique_strategy = f"webhook-auto-strategy-{uuid4().hex}"

    # Create an AUTO strategy for this name.
    from app.models import Order, Strategy  # type: ignore

    with SessionLocal() as session:
        strategy = Strategy(
            name=unique_strategy,
            description="Auto strategy",
            execution_mode="AUTO",
            enabled=True,
        )
        session.add(strategy)
        session.commit()

    # Monkeypatch Zerodha client factory so no real broker calls are made.
    from app.api import orders as orders_api

    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def place_order(self, **params: Any) -> Any:
            self.calls.append(params)

            class _R:
                order_id = "AUTO123"

            return _R()

    fake_client = _FakeClient()

    def _fake_get_client(db: Any, settings: Any) -> _FakeClient:
        return fake_client

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 3500.0},
    }

    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    alert_id = data["alert_id"]
    order_id = data["order_id"]

    # Order should be AUTO mode and already executed (SENT) with a broker id.
    with SessionLocal() as session:
        alert = session.get(Alert, alert_id)
        assert alert is not None
        assert alert.strategy_id is not None

        order = session.get(Order, order_id)
        assert order is not None
        assert order.mode == "AUTO"
        assert order.status == "SENT"
        assert order.zerodha_order_id == "AUTO123"

    assert len(fake_client.calls) == 1
