from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Alert, Order, Strategy, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-webhook-crypto-key"
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "test-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Create dedicated users that webhook alerts can be routed to.
    with SessionLocal() as session:
        for username in ("webhook-user", "webhook-auto-user", "webhook-manual-user"):
            user = User(
                username=username,
                password_hash=hash_password(f"{username}-password"),
                role="TRADER",
                display_name=username.replace("-", " ").title(),
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


def test_webhook_accepts_header_secret_without_body_secret() -> None:
    unique_strategy = f"webhook-test-strategy-header-{uuid4().hex}"
    payload = {
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "SELL", "quantity": 1, "price": 1500.0},
    }

    response = client.post(
        "/webhook/tradingview",
        json=payload,
        headers={"X-SIGMATRADER-SECRET": "test-secret"},
    )
    assert response.status_code == 201


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
        user = session.query(User).filter(User.username == "webhook-user").one()
        alert = session.get(Alert, alert_id)
        assert alert is not None
        assert alert.user_id == user.id
        assert alert.symbol == "NSE:INFY"
        assert alert.action == "SELL"
        assert alert.qty == 2
        assert alert.price == 1500.0

        order = session.get(Order, order_id)
        assert order is not None
        assert order.user_id == user.id
        assert order.alert_id == alert_id
        assert order.symbol == alert.symbol
        assert order.side == alert.action
        assert order.qty == alert.qty
        assert order.status == "WAITING"
        assert order.mode == "MANUAL"


def test_webhook_root_accepts_tradingview_payload() -> None:
    unique_strategy = f"webhook-test-strategy-root-{uuid4().hex}"
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:BSE",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 320.29},
    }

    response = client.post("/webhook", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"

    with SessionLocal() as session:
        order = session.get(Order, data["order_id"])
        assert order is not None
        assert order.price == 320.3


def test_webhook_accepts_flat_payload_fields() -> None:
    unique_strategy = f"webhook-test-strategy-flat-{uuid4().hex}"
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        # flat (no trade_details object)
        "order_action": "BUY",
        "quantity": 2,
        "price": 320.29,
        "product": "CNC",
    }

    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"

    with SessionLocal() as session:
        alert = session.get(Alert, data["alert_id"])
        assert alert is not None
        assert alert.symbol == "NSE:INFY"

        order = session.get(Order, data["order_id"])
        assert order is not None
        assert order.qty == 2
        assert order.price == 320.3


def test_webhook_accepts_tradingview_text_plain_json_body() -> None:
    unique_strategy = f"webhook-test-strategy-text-{uuid4().hex}"
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 1500.0},
    }

    response = client.post(
        "/webhook/tradingview",
        data=json.dumps(payload),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"


def test_webhook_root_accepts_tradingview_text_plain_json_body() -> None:
    unique_strategy = f"webhook-test-strategy-root-text-{uuid4().hex}"
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:BSE",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 320.29},
    }

    response = client.post(
        "/webhook",
        data=json.dumps(payload),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"


def test_webhook_accepts_price_with_thousands_separator() -> None:
    unique_strategy = f"webhook-test-strategy-commas-{uuid4().hex}"
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:BSE",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": "1", "price": "2,673.10"},
    }

    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"


def test_webhook_accepts_text_plain_body_with_unquoted_thousands_number() -> None:
    unique_strategy = f"webhook-test-strategy-raw-commas-{uuid4().hex}"
    # This is not valid JSON until the server strips thousands separators.
    body = (
        "{"
        f'"secret":"test-secret","platform":"TRADINGVIEW","st_user_id":"webhook-user","strategy_name":"{unique_strategy}",'
        '"symbol":"NSE:BSE","exchange":"NSE","interval":"5",'
        '"trade_details":{"order_action":"BUY","quantity":1,"price":2,673.10,"product":"CNC"}'
        "}"
    )

    response = client.post(
        "/webhook/tradingview",
        data=body,
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"


def test_webhook_auto_strategy_routes_to_auto_and_executes(monkeypatch: Any) -> None:
    unique_strategy = f"webhook-auto-strategy-{uuid4().hex}"

    # Create an AUTO strategy for this name.
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
        "st_user_id": "webhook-auto-user",
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

    # Order should be AUTO mode and already executed (SENT) for the user.
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "webhook-auto-user").one()
        alert = session.get(Alert, alert_id)
        assert alert is not None
        assert alert.user_id == user.id
        assert alert.strategy_id is not None

        order = session.get(Order, order_id)
        assert order is not None
        assert order.user_id == user.id
        assert order.mode == "AUTO"
        assert order.status == "SENT"
        assert order.zerodha_order_id == "AUTO123"

    assert len(fake_client.calls) == 1


def test_tradingview_secret_can_be_overridden_via_settings_api() -> None:
    # First confirm the env-backed secret is visible.
    response = client.get("/api/webhook-settings/tradingview-secret")
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "test-secret"

    # Override with a DB-stored secret.
    response = client.put(
        "/api/webhook-settings/tradingview-secret",
        json={"value": "db-secret"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "db-secret"
    assert data["source"] == "db"

    # Old secret should now be rejected.
    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-user",
        "strategy_name": f"webhook-test-strategy-db-{uuid4().hex}",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 401

    # DB secret should be accepted.
    payload["secret"] = "db-secret"
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201

    # Restore to env-backed secret for other tests in this module.
    response = client.put(
        "/api/webhook-settings/tradingview-secret",
        json={"value": ""},
    )
    assert response.status_code == 200


def test_webhook_manual_strategy_creates_waiting_order_for_user() -> None:
    """MANUAL strategies should create per-user WAITING orders without execution."""

    unique_strategy = f"webhook-manual-strategy-{uuid4().hex}"

    with SessionLocal() as session:
        strategy = Strategy(
            name=unique_strategy,
            description="Manual strategy",
            execution_mode="MANUAL",
            enabled=True,
        )
        session.add(strategy)
        session.commit()

    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-manual-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "15",
        "trade_details": {"order_action": "BUY", "quantity": 3, "price": 3500.0},
    }

    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    alert_id = data["alert_id"]
    order_id = data["order_id"]

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "webhook-manual-user").one()
        alert = session.get(Alert, alert_id)
        assert alert is not None
        assert alert.user_id == user.id

        order = session.get(Order, order_id)
        assert order is not None
        assert order.user_id == user.id
        assert order.mode == "MANUAL"
        assert order.status == "WAITING"


def test_webhook_auto_strategy_rejected_when_broker_not_connected() -> None:
    """AUTO alerts should fail clearly when Zerodha is not connected."""

    unique_strategy = f"webhook-auto-noconn-{uuid4().hex}"

    with SessionLocal() as session:
        strategy = Strategy(
            name=unique_strategy,
            description="Auto strategy without connection",
            execution_mode="AUTO",
            enabled=True,
        )
        session.add(strategy)
        session.commit()

    payload = {
        "secret": "test-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "webhook-auto-user",
        "strategy_name": unique_strategy,
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 3500.0},
    }

    # No BrokerConnection is created in this test, so the AUTO execution
    # path should fail with a clear error.
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert "Zerodha is not connected" in body.get("detail", "")

    # The order should exist and be marked as FAILED with a helpful message.
    with SessionLocal() as session:
        orders = session.query(Order).order_by(Order.id.desc()).all()
        assert orders, "Expected at least one order to be created"
        order = orders[0]
        assert order.mode == "AUTO"
        assert order.status == "FAILED"
        assert "Zerodha is not connected for AUTO mode." in (order.error_message or "")
