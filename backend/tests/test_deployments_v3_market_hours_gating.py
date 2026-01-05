from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ST_CRYPTO_KEY", "test-market-hours-v3-secret")

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import (
    MarketCalendar,
    StrategyDeployment,
    StrategyDeploymentJob,
    StrategyDeploymentState,
    User,
)
from app.services.deployment_scheduler import enqueue_due_jobs_once, ist_naive_to_utc

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_user(db) -> User:
    user = User(
        username=f"mh-user-{uuid4().hex}",
        password_hash=hash_password("password"),
        role="TRADER",
        display_name="Market Hours User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_scheduler_does_not_enqueue_outside_market_hours() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"mh-dep-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="CNC",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="TCS",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "TCS"}],
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

        now_utc = ist_naive_to_utc(datetime(2026, 1, 2, 20, 0, 0))
        from app.core.config import get_settings

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


def test_scheduler_respects_closed_session_day() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        db.query(MarketCalendar).delete()
        db.add(
            MarketCalendar(
                date=date(2026, 1, 2),
                exchange="NSE",
                session_type="CLOSED",
                open_time=None,
                close_time=None,
                notes="Holiday",
            )
        )
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"mh-dep-holiday-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="CNC",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="TCS",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "TCS"}],
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

        now_utc = ist_naive_to_utc(datetime(2026, 1, 2, 10, 0, 0))
        from app.core.config import get_settings

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


def test_daily_jobs_use_session_derived_proxy_close() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        db.query(MarketCalendar).delete()
        db.add(
            MarketCalendar(
                date=date(2026, 1, 2),
                exchange="NSE",
                session_type="HALF_DAY",
                open_time=time(9, 15),
                close_time=time(13, 0),
                notes="Half day",
            )
        )
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"mh-dep-daily-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="MIS",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="INFY",
            timeframe="1d",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "INFY"}],
                    },
                    "config": {
                        "timeframe": "1d",
                        "daily_via_intraday": {"enabled": True, "base_timeframe": "5m"},
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) > 0",
                        "product": "MIS",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="RUNNING"))
        db.commit()

        now_utc = ist_naive_to_utc(datetime(2026, 1, 2, 12, 58, 0))
        from app.core.config import get_settings

        res = enqueue_due_jobs_once(
            db,
            get_settings(),
            now_utc=now_utc,
            tolerance_seconds=5,
            max_backfill=10,
            prefetch_candles=False,
        )
        db.commit()
        assert res.jobs_created >= 1

        jobs = (
            db.query(StrategyDeploymentJob)
            .filter(StrategyDeploymentJob.deployment_id == dep.id)
            .all()
        )
        kinds = {
            (j.kind, json.loads(j.payload_json or "{}").get("window")) for j in jobs
        }
        # Proxy close is close_time - 5 minutes = 12:55.
        assert ("DAILY_PROXY_CLOSED", None) in kinds
        assert ("WINDOW", "BUY_CLOSE") in kinds
        assert ("WINDOW", "MIS_FLATTEN") in kinds


def test_run_now_blocked_when_market_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    with SessionLocal() as db:
        user = _seed_user(db)
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"mh-dep-run-now-{uuid4().hex}",
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

    from app.api import deployments as deployments_api

    monkeypatch.setattr(
        deployments_api,
        "now_ist_naive",
        lambda *_args, **_kwargs: datetime(2026, 1, 2, 20, 0, 0),
    )

    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password"},
    )
    assert login.status_code == 200

    resp = client.post(f"/api/deployments/{dep_id}/run-now")
    assert resp.status_code == 400
    assert "Market is closed" in resp.json().get("detail", "")
