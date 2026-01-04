from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ST_CRYPTO_KEY", "test-deployments-observability-secret")

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import StrategyDeploymentAction, StrategyDeploymentJob, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="deploy-ob-user",
                password_hash=hash_password("password"),
                role="TRADER",
                display_name="Deploy Observability User",
            )
        )
        session.commit()


def _login() -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": "deploy-ob-user", "password": "password"},
    )
    assert resp.status_code == 200


def _create_strategy_deployment(*, timeframe: str = "1m") -> int:
    name = f"obs-dep-{uuid4().hex}"
    daily = {"enabled": True, "base_timeframe": "5m"} if timeframe == "1d" else None
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
                "timeframe": timeframe,
                "daily_via_intraday": daily,
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
    return int(resp.json()["id"])


def test_deployment_actions_and_jobs_metrics_endpoints() -> None:
    _login()
    dep_id = _create_strategy_deployment(timeframe="1m")

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "deploy-ob-user").one()
        db.add(
            StrategyDeploymentAction(
                deployment_id=dep_id,
                kind="EVALUATION",
                payload_json=json.dumps(
                    {"note": "test action", "dsl": {"entry": "PRICE(1d) > 0"}},
                    ensure_ascii=False,
                ),
            )
        )
        ts = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
        db.add_all(
            [
                StrategyDeploymentJob(
                    deployment_id=dep_id,
                    owner_id=user.id,
                    kind="BAR_CLOSED",
                    status="PENDING",
                    dedupe_key=f"DEP:{dep_id}:BAR_CLOSED:TEST:PENDING",
                    scheduled_for=ts,
                    run_after=ts,
                    payload_json=json.dumps({"kind": "BAR_CLOSED"}, ensure_ascii=False),
                ),
                StrategyDeploymentJob(
                    deployment_id=dep_id,
                    owner_id=user.id,
                    kind="BAR_CLOSED",
                    status="FAILED",
                    dedupe_key=f"DEP:{dep_id}:BAR_CLOSED:TEST:FAILED",
                    scheduled_for=ts,
                    run_after=ts,
                    payload_json=json.dumps({"kind": "BAR_CLOSED"}, ensure_ascii=False),
                ),
            ]
        )
        db.commit()

    resp = client.get(f"/api/deployments/{dep_id}/actions?limit=10")
    assert resp.status_code == 200
    items = resp.json()
    assert items and items[0]["deployment_id"] == dep_id
    assert items[0]["payload"].get("note") == "test action"

    resp = client.get(f"/api/deployments/{dep_id}/jobs/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_counts"].get("PENDING", 0) >= 1
    assert body["job_counts"].get("FAILED", 0) >= 1
    assert body["oldest_pending_scheduled_for"]


def test_run_now_enqueues_job_for_intraday(monkeypatch: pytest.MonkeyPatch) -> None:
    _login()
    dep_id = _create_strategy_deployment(timeframe="1m")

    from app.api import deployments as deployments_api

    monkeypatch.setattr(
        deployments_api,
        "now_ist_naive",
        lambda *_args, **_kwargs: datetime(2026, 1, 2, 10, 5, 10),
    )

    resp = client.post(f"/api/deployments/{dep_id}/run-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("enqueued") is True
    assert body.get("scheduled_for")

    resp = client.get(f"/api/deployments/{dep_id}/jobs/metrics")
    assert resp.status_code == 200
    assert resp.json()["job_counts"].get("PENDING", 0) >= 1


def test_run_now_enqueues_job_for_daily_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _login()
    dep_id = _create_strategy_deployment(timeframe="1d")

    from app.api import deployments as deployments_api

    monkeypatch.setattr(
        deployments_api,
        "now_ist_naive",
        lambda *_args, **_kwargs: datetime(2026, 1, 2, 15, 26, 0),
    )

    resp = client.post(f"/api/deployments/{dep_id}/run-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("enqueued") is True
    assert body.get("scheduled_for")
