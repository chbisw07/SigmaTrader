from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Alert

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "test-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


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
    alert_id = data["id"]

    with SessionLocal() as session:
        alert = session.get(Alert, alert_id)
        assert alert is not None
        assert alert.symbol == "NSE:INFY"
        assert alert.action == "SELL"
        assert alert.qty == 2
        assert alert.price == 1500.0
