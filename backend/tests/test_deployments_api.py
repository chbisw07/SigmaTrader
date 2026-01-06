from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault("ST_CRYPTO_KEY", "test-deployments-api-secret")

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add_all(
            [
                User(
                    username="dep-user-1",
                    password_hash=hash_password("password"),
                    role="TRADER",
                    display_name="Dep User 1",
                ),
                User(
                    username="dep-user-2",
                    password_hash=hash_password("password"),
                    role="TRADER",
                    display_name="Dep User 2",
                ),
            ]
        )
        session.commit()


def _login(username: str) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password"},
    )
    assert resp.status_code == 200


def test_deployment_crud_and_toggle() -> None:
    _login("dep-user-1")

    name = f"test-deployment-{uuid4().hex}"
    resp = client.post(
        "/api/deployments/",
        json={
            "name": name,
            "kind": "STRATEGY",
            "enabled": False,
            "universe": {
                "target_kind": "SYMBOL",
                "symbols": [{"exchange": "NSE", "symbol": "RELIANCE"}],
            },
            "config": {
                "timeframe": "1d",
                "daily_via_intraday": {"enabled": True, "base_timeframe": "5m"},
                "entry_dsl": "PRICE(1d) > 0",
                "exit_dsl": "PRICE(1d) > 0",
                "product": "CNC",
                "direction": "LONG",
                "broker_name": "zerodha",
                "execution_target": "PAPER",
                "position_size_pct": 100.0,
            },
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    dep_id = created["id"]
    assert created["name"] == name
    assert created["kind"] == "STRATEGY"
    assert created["enabled"] is False
    assert created["universe"]["target_kind"] == "SYMBOL"
    assert created["universe"]["symbols"][0]["symbol"] == "RELIANCE"
    assert created["state"]["status"] == "STOPPED"

    resp = client.get("/api/deployments/")
    assert resp.status_code == 200
    items = resp.json()
    assert any(d["id"] == dep_id for d in items)

    resp = client.post(f"/api/deployments/{dep_id}/start")
    assert resp.status_code == 200
    started = resp.json()
    assert started["enabled"] is True
    assert started["state"]["status"] == "RUNNING"

    new_name = f"{name}-updated"
    resp = client.put(
        f"/api/deployments/{dep_id}",
        json={
            "name": new_name,
            "enabled": False,
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == new_name
    assert updated["enabled"] is False
    assert updated["state"]["status"] == "STOPPED"

    resp = client.post(f"/api/deployments/{dep_id}/stop")
    assert resp.status_code == 200
    stopped = resp.json()
    assert stopped["enabled"] is False
    assert stopped["state"]["status"] == "STOPPED"

    resp = client.delete(f"/api/deployments/{dep_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/deployments/{dep_id}")
    assert resp.status_code == 404


def test_deployment_update_accepts_universe_dict() -> None:
    _login("dep-user-1")

    name = f"test-deployment-update-universe-{uuid4().hex}"
    resp = client.post(
        "/api/deployments/",
        json={
            "name": name,
            "kind": "STRATEGY",
            "enabled": True,
            "universe": {
                "target_kind": "SYMBOL",
                "symbols": [{"exchange": "NSE", "symbol": "RELIANCE"}],
            },
            "config": {
                "timeframe": "1d",
                "entry_dsl": "PRICE(1d) > 0",
                "exit_dsl": "PRICE(1d) > 0",
                "product": "CNC",
                "direction": "LONG",
                "broker_name": "zerodha",
                "execution_target": "PAPER",
                "position_size_pct": 100.0,
            },
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    dep_id = created["id"]

    resp = client.put(
        f"/api/deployments/{dep_id}",
        json={
            "enabled": False,
            "universe": created["universe"],
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["enabled"] is False
    assert updated["universe"]["target_kind"] == "SYMBOL"
    assert updated["universe"]["symbols"][0]["symbol"] == "RELIANCE"


def test_deployment_ownership_enforced() -> None:
    _login("dep-user-1")
    name = f"test-deployment-own-{uuid4().hex}"
    resp = client.post(
        "/api/deployments/",
        json={
            "name": name,
            "kind": "STRATEGY",
            "enabled": True,
            "universe": {
                "target_kind": "SYMBOL",
                "symbols": [{"exchange": "NSE", "symbol": "TCS"}],
            },
            "config": {
                "timeframe": "1d",
                "entry_dsl": "PRICE(1d) > 0",
                "exit_dsl": "PRICE(1d) > 0",
                "product": "CNC",
                "direction": "LONG",
                "broker_name": "zerodha",
                "execution_target": "PAPER",
            },
        },
    )
    assert resp.status_code == 201
    dep_id = resp.json()["id"]

    _login("dep-user-2")

    resp = client.get(f"/api/deployments/{dep_id}")
    assert resp.status_code == 404
    resp = client.put(f"/api/deployments/{dep_id}", json={"enabled": False})
    assert resp.status_code == 404
    resp = client.delete(f"/api/deployments/{dep_id}")
    assert resp.status_code == 404


def test_deployment_validation_errors() -> None:
    _login("dep-user-1")
    name = f"test-deployment-bad-{uuid4().hex}"

    resp = client.post(
        "/api/deployments/",
        json={
            "name": name,
            "kind": "STRATEGY",
            "enabled": False,
            "universe": {"target_kind": "SYMBOL", "symbols": []},
            "config": {
                "timeframe": "1d",
                "entry_dsl": "UNKNOWN_FUNC(1d) > 0",
                "exit_dsl": "PRICE(1d) > 0",
                "product": "CNC",
                "direction": "LONG",
                "broker_name": "zerodha",
                "execution_target": "PAPER",
            },
        },
    )
    assert resp.status_code == 400

    resp = client.post(
        "/api/deployments/",
        json={
            "name": f"{name}-group-mismatch",
            "kind": "STRATEGY",
            "universe": {"target_kind": "GROUP", "group_id": 1},
            "config": {
                "timeframe": "1d",
                "entry_dsl": "PRICE(1d) > 0",
                "exit_dsl": "PRICE(1d) > 0",
                "product": "CNC",
                "direction": "LONG",
                "broker_name": "zerodha",
                "execution_target": "PAPER",
            },
        },
    )
    assert resp.status_code == 400
