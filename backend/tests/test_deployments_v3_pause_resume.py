from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault("ST_CRYPTO_KEY", "test-deployments-pause-resume-secret")

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import (
    Order,
    StrategyDeployment,
    StrategyDeploymentJob,
    StrategyDeploymentState,
    User,
)
from app.services.deployment_scheduler import ist_naive_to_utc
from app.services.deployment_worker import execute_job_once

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def setup_function(_fn) -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_user(db) -> User:
    user = User(
        username=f"pause-user-{uuid4().hex}",
        password_hash=hash_password("password"),
        role="TRADER",
        display_name="Pause User",
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


def test_pause_resume_endpoints_persist_timestamps_and_reason() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        other = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"pause-dep-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
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
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="RUNNING"))
        db.commit()
        dep_id = dep.id
        username = user.username
        other_username = other.username

    _login(username)
    resp = client.post(
        f"/api/deployments/{dep_id}/pause",
        json={"reason": "maintenance"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["status"] == "PAUSED"
    assert body["state"]["paused_at"]
    assert body["state"]["pause_reason"] == "maintenance"

    # run-now is blocked when paused (regardless of market hours gating).
    resp = client.post(f"/api/deployments/{dep_id}/run-now")
    assert resp.status_code == 400
    assert "paused" in str(resp.json().get("detail", "")).lower()

    resp = client.post(f"/api/deployments/{dep_id}/resume")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["status"] == "RUNNING"
    assert body["state"]["resumed_at"]

    # Non-owner cannot pause.
    _login(other_username)
    resp = client.post(f"/api/deployments/{dep_id}/pause", json={"reason": "nope"})
    assert resp.status_code == 404


def test_scheduler_does_not_enqueue_bar_closed_when_paused() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"pause-dep-scheduler-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
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
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="PAUSED"))
        db.commit()

        from app.core.config import get_settings
        from app.services.deployment_scheduler import enqueue_due_jobs_once

        now_utc = ist_naive_to_utc(datetime(2026, 1, 2, 10, 0, 0))
        res = enqueue_due_jobs_once(
            db,
            get_settings(),
            now_utc=now_utc,
            tolerance_seconds=5,
            max_backfill=10,
            prefetch_candles=False,
        )
        db.commit()
        assert res.jobs_created == 0

        jobs = (
            db.query(StrategyDeploymentJob)
            .filter(StrategyDeploymentJob.deployment_id == dep.id)
            .all()
        )
        assert jobs == []


def test_worker_skips_bar_close_when_paused_but_allows_mis_flatten() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"pause-dep2-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
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
                        "execution_target": "PAPER",
                        "direction": "LONG",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        state = StrategyDeploymentState(deployment_id=dep.id, status="PAUSED")

        # Create a broker-side protection order (should remain untouched by pause).
        stop_order = Order(
            user_id=user.id,
            strategy_id=None,
            alert_id=None,
            portfolio_group_id=None,
            deployment_id=dep.id,
            deployment_action_id=None,
            client_order_id=f"dep:{dep.id}:DISASTER_STOP:TEST",
            symbol="INFY",
            exchange="NSE",
            side="SELL",
            qty=1.0,
            price=95.0,
            order_type="LIMIT",
            trigger_price=95.0,
            product="MIS",
            status="WAITING",
            mode="AUTO",
            execution_target="PAPER",
            broker_name="zerodha",
            gtt=True,
            synthetic_gtt=True,
            trigger_operator="<=",
            simulated=True,
        )
        db.add(stop_order)
        db.flush()

        state.state_json = json.dumps(
            {
                "version": 1,
                "cash": 10000.0,
                "positions": {
                    "NSE:INFY": {
                        "qty": 1,
                        "side": "LONG",
                        "entry_price": 100.0,
                        "entry_ts": "2026-01-02T10:00:00Z",
                        "disaster_stop_order_id": stop_order.id,
                    }
                },
            }
        )
        db.add(state)
        db.commit()

        ts = datetime(2026, 1, 2, 9, 50, tzinfo=UTC)
        bar_job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="BAR_CLOSED",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:TEST:{ts.isoformat()}",
            scheduled_for=ts,
            run_after=ts,
            payload_json=json.dumps(
                {"kind": "BAR_CLOSED", "bar_end_utc": ts.isoformat()}
            ),
        )
        db.add(bar_job)
        db.commit()

        did = execute_job_once(db, worker_id="pause-worker", now=ts)
        assert did is True
        db.refresh(bar_job)
        assert bar_job.status == "DONE"
        db.refresh(stop_order)
        assert stop_order.status == "WAITING"

        # MIS flatten should still execute even if paused.
        flatten_ist = datetime(2026, 1, 2, 15, 25)
        flatten_utc = ist_naive_to_utc(flatten_ist)
        win_job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="WINDOW",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:WINDOW:MIS_FLATTEN:{flatten_utc.isoformat()}",
            scheduled_for=flatten_utc,
            run_after=flatten_utc,
            payload_json=json.dumps(
                {
                    "kind": "WINDOW",
                    "window": "MIS_FLATTEN",
                    "window_utc": flatten_utc.isoformat(),
                }
            ),
        )
        db.add(win_job)
        db.commit()

        did = execute_job_once(db, worker_id="pause-worker", now=flatten_utc)
        assert did is True
        db.refresh(win_job)
        assert win_job.status == "DONE"

        db.refresh(state)
        s = json.loads(state.state_json or "{}")
        assert int(s.get("positions", {}).get("NSE:INFY", {}).get("qty") or 0) == 0
