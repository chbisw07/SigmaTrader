from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import IndicatorRule
from app.services.indicator_alerts import _iter_rule_symbols

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-indicator-alerts-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _register_and_login(username: str) -> None:
    resp_register = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "display_name": username},
    )
    assert resp_register.status_code == 201

    resp_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    assert resp_login.status_code == 200
    client.cookies.clear()
    client.cookies.update(resp_login.cookies)


def test_group_target_rule_iterates_group_members() -> None:
    _register_and_login("alert-group-user")

    resp_group = client.post(
        "/api/groups/",
        json={"name": "test-group", "kind": "WATCHLIST", "description": "test"},
    )
    assert resp_group.status_code == 200
    group_id = resp_group.json()["id"]

    resp_members = client.post(
        f"/api/groups/{group_id}/members/bulk",
        json=[
            {"symbol": "AAA", "exchange": "NSE"},
            {"symbol": "BBB", "exchange": "BSE"},
        ],
    )
    assert resp_members.status_code == 200

    resp_rule = client.post(
        "/api/indicator-alerts/",
        json={
            "target_type": "GROUP",
            "target_id": str(group_id),
            "timeframe": "1d",
            "logic": "AND",
            "conditions": [
                {
                    "indicator": "PRICE",
                    "operator": "GT",
                    "threshold_1": 0,
                    "params": {},
                }
            ],
            "dsl_expression": "TODAY_PNL_PCT > 5",
            "trigger_mode": "ONCE",
            "action_type": "ALERT_ONLY",
            "action_params": {},
            "enabled": True,
        },
    )
    assert resp_rule.status_code == 201
    created = resp_rule.json()
    assert created["target_type"] == "GROUP"
    assert created["target_id"] == str(group_id)

    with SessionLocal() as session:
        rule = session.query(IndicatorRule).first()
        assert rule is not None
        pairs = list(_iter_rule_symbols(session, get_settings(), rule))
        assert ("AAA", "NSE") in pairs
        assert ("BBB", "BSE") in pairs
