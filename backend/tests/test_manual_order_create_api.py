from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-manual-order-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Register + login once; cookies stay on the TestClient instance.
    resp_register = client.post(
        "/api/auth/register",
        json={"username": "trader", "password": "secret123", "display_name": "Trader"},
    )
    assert resp_register.status_code == 201

    resp_login = client.post(
        "/api/auth/login",
        json={"username": "trader", "password": "secret123"},
    )
    assert resp_login.status_code == 200
    client.cookies.clear()
    client.cookies.update(resp_login.cookies)


def test_create_manual_market_order_without_price() -> None:
    resp = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "MARKET",
            "product": "CNC",
            "gtt": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TCS"
    assert data["order_type"] == "MARKET"
    assert data["qty"] == 1
    assert data["status"] == "WAITING"
    assert data["mode"] == "MANUAL"
    assert data["execution_target"] == "LIVE"


def test_create_manual_order_accepts_risk_spec() -> None:
    resp = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "MARKET",
            "product": "CNC",
            "gtt": False,
            "risk_spec": {
                "stop_loss": {
                    "enabled": True,
                    "mode": "PCT",
                    "value": 2.0,
                    "atr_period": 14,
                    "atr_tf": "5m",
                },
                "trailing_stop": {
                    "enabled": True,
                    "mode": "PCT",
                    "value": 1.0,
                    "atr_period": 14,
                    "atr_tf": "5m",
                },
                "trailing_activation": {
                    "enabled": True,
                    "mode": "PCT",
                    "value": 3.0,
                    "atr_period": 14,
                    "atr_tf": "5m",
                },
                "exit_order_type": "MARKET",
            },
        },
    )
    assert resp.status_code == 200


def test_create_manual_limit_requires_positive_price() -> None:
    resp_missing = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "product": "CNC",
        },
    )
    assert resp_missing.status_code == 400
    assert "LIMIT" in resp_missing.json().get("detail", "")

    resp_zero = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 0,
            "product": "CNC",
        },
    )
    assert resp_zero.status_code == 400

    resp_ok = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 3500.0,
            "product": "CNC",
        },
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["order_type"] == "LIMIT"
    assert data["price"] == 3500.0


def test_create_manual_limit_rounds_price_to_tick() -> None:
    resp = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 320.29,
            "product": "CNC",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] == 320.3

    resp2 = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 320.26,
            "product": "CNC",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["price"] == 320.25


def test_create_manual_sl_requires_trigger_and_price() -> None:
    resp_missing_trigger = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "SL",
            "price": 3500.0,
            "product": "CNC",
        },
    )
    assert resp_missing_trigger.status_code == 400
    assert "Trigger price" in resp_missing_trigger.json().get("detail", "")

    resp_missing_price = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "SL",
            "trigger_price": 3490.0,
            "product": "CNC",
        },
    )
    assert resp_missing_price.status_code == 400
    assert "Price" in resp_missing_price.json().get("detail", "")

    resp_ok = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "SL",
            "price": 3500.0,
            "trigger_price": 3490.0,
            "product": "CNC",
        },
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["order_type"] == "SL"
    assert data["price"] == 3500.0
    assert data["trigger_price"] == 3490.0


def test_create_manual_sl_rounds_price_and_trigger_to_tick() -> None:
    resp = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "SL",
            "price": 320.29,
            "trigger_price": 319.99,
            "product": "CNC",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] == 320.3
    assert data["trigger_price"] == 320.0


def test_create_manual_slm_requires_trigger() -> None:
    resp_missing = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "SL-M",
            "product": "CNC",
        },
    )
    assert resp_missing.status_code == 400
    assert "Trigger price" in resp_missing.json().get("detail", "")

    resp_ok = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "SL-M",
            "trigger_price": 3490.0,
            "product": "CNC",
        },
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["order_type"] == "SL-M"
    assert data["trigger_price"] == 3490.0


def test_create_manual_gtt_requires_limit() -> None:
    resp_bad = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "MARKET",
            "gtt": True,
            "product": "CNC",
        },
    )
    assert resp_bad.status_code == 400
    assert "GTT" in resp_bad.json().get("detail", "")

    resp_ok = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 3500.0,
            "gtt": True,
            "product": "CNC",
        },
    )
    assert resp_ok.status_code == 200


def test_create_manual_gtt_defaults_trigger_to_rounded_price() -> None:
    resp = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 320.29,
            "gtt": True,
            "product": "CNC",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] == 320.3
    assert data["trigger_price"] == 320.3


def test_bulk_like_multiple_create_calls_allow_partial_success() -> None:
    payloads = [
        {
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "MARKET",
            "product": "CNC",
        },
        {
            "symbol": "INFY",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "price": 1500.0,
            "product": "CNC",
        },
    ]
    for p in payloads:
        resp = client.post("/api/orders/", json=p)
        assert resp.status_code == 200

    # One invalid payload should fail without affecting others.
    resp_invalid = client.post(
        "/api/orders/",
        json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 0,
            "order_type": "MARKET",
            "product": "CNC",
        },
    )
    assert resp_invalid.status_code == 400


def test_create_auto_paper_order_executes_immediately(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Avoid market-hours dependent failures in the paper engine routing.
    monkeypatch.setattr("app.api.orders.is_market_open_now", lambda: True)

    resp = client.post(
        "/api/orders/",
        json={
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "qty": 1,
            "order_type": "MARKET",
            "product": "CNC",
            "mode": "AUTO",
            "execution_target": "PAPER",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "AUTO"
    assert data["execution_target"] == "PAPER"
    assert data["simulated"] is True
    assert data["status"] == "SENT"
