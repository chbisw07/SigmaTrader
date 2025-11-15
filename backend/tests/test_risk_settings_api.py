from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Strategy

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_create_global_and_per_strategy_risk_settings() -> None:
    with SessionLocal() as session:
        strategy = Strategy(
            name=f"api-risk-strategy-{uuid4().hex}", execution_mode="MANUAL"
        )
        session.add(strategy)
        session.commit()
        session.refresh(strategy)
        strategy_id = strategy.id

    response_global = client.post(
        "/api/risk-settings/",
        json={
            "scope": "GLOBAL",
            "strategy_id": None,
            "max_order_value": 100000.0,
            "allow_short_selling": True,
            "clamp_mode": "CLAMP",
        },
    )
    assert response_global.status_code == 201
    global_payload = response_global.json()
    assert global_payload["scope"] == "GLOBAL"
    assert global_payload["strategy_id"] is None

    response_strategy = client.post(
        "/api/risk-settings/",
        json={
            "scope": "STRATEGY",
            "strategy_id": strategy_id,
            "max_order_value": 50000.0,
            "allow_short_selling": False,
            "clamp_mode": "REJECT",
        },
    )
    assert response_strategy.status_code == 201
    per_strategy_payload = response_strategy.json()
    assert per_strategy_payload["scope"] == "STRATEGY"
    assert per_strategy_payload["strategy_id"] == strategy_id

    list_response = client.get(
        "/api/risk-settings/", params={"scope": "STRATEGY", "strategy_id": strategy_id}
    )
    assert list_response.status_code == 200
    items = list_response.json()
    assert any(item["id"] == per_strategy_payload["id"] for item in items)
