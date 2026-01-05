from __future__ import annotations

import json
import os
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault("ST_CRYPTO_KEY", "test-deployments-runtime-safety-secret")

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import (
    Position,
    StrategyDeployment,
    StrategyDeploymentJob,
    StrategyDeploymentState,
    User,
)

client = TestClient(app)


def setup_function(_fn) -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_user(db) -> User:
    user = User(
        username=f"safe-user-{uuid4().hex}",
        password_hash=hash_password("password"),
        role="TRADER",
        display_name="Safety User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(username: str) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password"},
    )
    assert resp.status_code == 200


def test_create_rejects_invalid_short_configs() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        username = user.username

    _login(username)
    base = {
        "name": f"dep-{uuid4().hex}",
        "description": None,
        "kind": "STRATEGY",
        "enabled": False,
        "universe": {
            "target_kind": "SYMBOL",
            "symbols": [{"exchange": "NSE", "symbol": "INFY"}],
        },
        "config": {
            "timeframe": "1m",
            "entry_dsl": "PRICE(1d) > 0",
            "exit_dsl": "PRICE(1d) > 0",
            "broker_name": "zerodha",
            "execution_target": "PAPER",
        },
    }

    bad = json.loads(json.dumps(base))
    bad["config"].update({"product": "CNC", "direction": "SHORT"})
    resp = client.post("/api/deployments/", json=bad)
    assert resp.status_code == 400

    bad2 = json.loads(json.dumps(base))
    bad2["config"].update({"product": "MIS", "direction": "SHORT"})
    resp = client.post("/api/deployments/", json=bad2)
    assert resp.status_code == 400
    assert "acknowledge_short_risk" in str(resp.json().get("detail", ""))

    ok = json.loads(json.dumps(base))
    ok["name"] = f"dep-{uuid4().hex}"
    ok["config"].update(
        {"product": "MIS", "direction": "SHORT", "acknowledge_short_risk": True}
    )
    resp = client.post("/api/deployments/", json=ok)
    assert resp.status_code == 201


def test_start_pauses_on_direction_mismatch_live() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"live-mismatch-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="LIVE",
            enabled=False,
            broker_name="zerodha",
            product="MIS",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="INFY",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "INFY"}],
                    },
                    "config": {
                        "timeframe": "1m",
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) > 0",
                        "product": "MIS",
                        "direction": "LONG",
                        "broker_name": "zerodha",
                        "execution_target": "LIVE",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="STOPPED"))
        db.add(
            Position(
                broker_name="zerodha",
                symbol="INFY",
                exchange="NSE",
                product="MIS",
                qty=-5,
                avg_price=100.0,
                pnl=0.0,
            )
        )
        db.commit()
        dep_id = dep.id
        username = user.username

    _login(username)
    resp = client.post(f"/api/deployments/{dep_id}/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["status"] == "PAUSED"
    assert body["state"]["runtime_state"] == "PAUSED_DIRECTION_MISMATCH"
    assert body["state"]["exposure"]
    assert body["state"]["exposure"]["symbols"][0]["broker_side"] == "SHORT"


def test_resolve_direction_mismatch_adopt_exit_only_imports_position() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"live-mismatch2-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="LIVE",
            enabled=True,
            broker_name="zerodha",
            product="MIS",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="INFY",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "INFY"}],
                    },
                    "config": {
                        "timeframe": "1m",
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) > 0",
                        "product": "MIS",
                        "direction": "LONG",
                        "broker_name": "zerodha",
                        "execution_target": "LIVE",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="PAUSED"))
        db.add(
            Position(
                broker_name="zerodha",
                symbol="INFY",
                exchange="NSE",
                product="MIS",
                qty=-2,
                avg_price=110.0,
                pnl=0.0,
            )
        )
        db.commit()
        dep_id = dep.id
        username = user.username

    _login(username)
    resp = client.post(
        f"/api/deployments/{dep_id}/direction-mismatch/resolve",
        json={"action": "ADOPT_EXIT_ONLY"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["status"] == "RUNNING"

    with SessionLocal() as db:
        st = db.query(StrategyDeploymentState).filter_by(deployment_id=dep_id).one()
        s = json.loads(st.state_json or "{}")
        assert s.get("exit_only") is True
        pos = (s.get("positions") or {}).get("NSE:INFY") or {}
        assert int(pos.get("qty") or 0) > 0
        assert str(pos.get("side") or "").upper() == "SHORT"


def test_resolve_direction_mismatch_flatten_enqueues_force_flatten_job() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"live-mismatch3-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="LIVE",
            enabled=True,
            broker_name="zerodha",
            product="MIS",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="INFY",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "INFY"}],
                    },
                    "config": {
                        "timeframe": "1m",
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) > 0",
                        "product": "MIS",
                        "direction": "LONG",
                        "broker_name": "zerodha",
                        "execution_target": "LIVE",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="PAUSED"))
        db.add(
            Position(
                broker_name="zerodha",
                symbol="INFY",
                exchange="NSE",
                product="MIS",
                qty=-1,
                avg_price=110.0,
                pnl=0.0,
            )
        )
        db.commit()
        dep_id = dep.id
        username = user.username

    _login(username)
    resp = client.post(
        f"/api/deployments/{dep_id}/direction-mismatch/resolve",
        json={"action": "FLATTEN_THEN_CONTINUE"},
    )
    assert resp.status_code == 200

    with SessionLocal() as db:
        job = (
            db.query(StrategyDeploymentJob)
            .filter(StrategyDeploymentJob.deployment_id == dep_id)
            .order_by(StrategyDeploymentJob.id.desc())
            .first()
        )
        assert job is not None
        payload = json.loads(job.payload_json or "{}")
        assert str(payload.get("window") or "").upper() == "FORCE_FLATTEN"


def test_enter_on_start_enqueues_bar_closed_job(monkeypatch) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"enter-on-start-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=False,
            broker_name="zerodha",
            product="CNC",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="INFY",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "INFY"}],
                    },
                    "config": {
                        "timeframe": "1m",
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) > 0",
                        "product": "CNC",
                        "direction": "LONG",
                        "broker_name": "zerodha",
                        "execution_target": "PAPER",
                        "enter_immediately_on_start": True,
                        "acknowledge_enter_immediately_risk": True,
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="STOPPED"))
        db.commit()
        dep_id = dep.id
        username = user.username

    from app.api import deployments as deployments_api

    monkeypatch.setattr(
        deployments_api,
        "now_ist_naive",
        lambda *_args, **_kwargs: datetime(2026, 1, 2, 10, 0, 0),
    )

    _login(username)
    resp = client.post(f"/api/deployments/{dep_id}/start")
    assert resp.status_code == 200

    with SessionLocal() as db:
        jobs = (
            db.query(StrategyDeploymentJob)
            .filter(StrategyDeploymentJob.deployment_id == dep_id)
            .all()
        )
        assert any("ENTER_ON_START" in str(j.dedupe_key or "") for j in jobs)
