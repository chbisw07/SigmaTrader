from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    StrategyDeployment,
    StrategyDeploymentBarCursor,
    StrategyDeploymentJob,
    StrategyDeploymentState,
    User,
)
from app.services.deployment_jobs import (
    acquire_deployment_lock,
    claim_next_job,
    enqueue_job,
    requeue_stale_running_jobs,
)
from app.services.deployment_scheduler import (
    enqueue_due_jobs_once,
    ist_naive_to_utc,
    latest_closed_bar_end_ist,
    now_ist_naive,
)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="deploy-job-user",
                password_hash=hash_password("password"),
                role="TRADER",
                display_name="Deploy Job User",
            )
        )
        session.commit()


def test_job_dedupe_and_claim_semantics() -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "deploy-job-user").one()
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="CNC",
            target_kind="SYMBOL",
            exchange="NSE",
            symbol="RELIANCE",
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": "NSE", "symbol": "RELIANCE"}],
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

        ts = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
        job = enqueue_job(
            db,
            deployment_id=dep.id,
            owner_id=user.id,
            kind="WINDOW",
            dedupe_key=f"DEP:{dep.id}:WINDOW:SELL_OPEN:2026-01-02",
            scheduled_for=ts,
            payload={"kind": "WINDOW", "window": "SELL_OPEN"},
        )
        assert job is not None
        dup = enqueue_job(
            db,
            deployment_id=dep.id,
            owner_id=user.id,
            kind="WINDOW",
            dedupe_key=f"DEP:{dep.id}:WINDOW:SELL_OPEN:2026-01-02",
            scheduled_for=ts,
            payload={"kind": "WINDOW", "window": "SELL_OPEN"},
        )
        assert dup is None
        db.commit()

    with SessionLocal() as db1:
        claim = claim_next_job(db1, worker_id="w1", now=ts)
        assert claim is not None
        assert claim.job.status == "RUNNING"
        db1.commit()

    with SessionLocal() as db2:
        claim2 = claim_next_job(db2, worker_id="w2", now=ts)
        assert claim2 is None


def test_requeue_stale_running_jobs() -> None:
    with SessionLocal() as db:
        job = (
            db.query(StrategyDeploymentJob)
            .order_by(StrategyDeploymentJob.id.desc())
            .first()
        )
        assert job is not None
        job.status = "RUNNING"
        job.locked_at = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
        db.add(job)
        db.commit()

        updated = requeue_stale_running_jobs(
            db,
            now=datetime(2026, 1, 2, 9, 2, tzinfo=UTC),
            running_ttl_seconds=30,
        )
        assert updated >= 1
        db.commit()
        db.refresh(job)
        assert job.status == "PENDING"
        assert job.locked_at is None


def test_deployment_lock_ttl() -> None:
    with SessionLocal() as db:
        dep = db.query(StrategyDeployment).first()
        assert dep is not None

        now = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
        ok = acquire_deployment_lock(
            db,
            deployment_id=dep.id,
            worker_id="w1",
            now=now,
            ttl_seconds=10,
        )
        assert ok is True
        db.commit()

        ok2 = acquire_deployment_lock(
            db,
            deployment_id=dep.id,
            worker_id="w2",
            now=now,
            ttl_seconds=10,
        )
        assert ok2 is False
        db.commit()

        ok3 = acquire_deployment_lock(
            db,
            deployment_id=dep.id,
            worker_id="w2",
            now=now.replace(second=11),
            ttl_seconds=10,
        )
        assert ok3 is True


def test_bar_boundary_and_backfill_enqueues_jobs() -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "deploy-job-user").one()
        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-bars-{uuid4().hex}",
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

        last_ist = datetime(2026, 1, 2, 10, 0)  # IST naive
        cursor = StrategyDeploymentBarCursor(
            deployment_id=dep.id,
            exchange="NSE",
            symbol="TCS",
            timeframe="1m",
            last_emitted_bar_end_ts=ist_naive_to_utc(last_ist),
        )
        db.add(cursor)
        db.commit()

        now_utc = ist_naive_to_utc(datetime(2026, 1, 2, 10, 5, 10))
        now_ist = now_ist_naive(now_utc)
        latest_end = latest_closed_bar_end_ist(
            now_ist=now_ist,
            timeframe="1m",
            tolerance_seconds=5,
        )
        assert latest_end == datetime(2026, 1, 2, 10, 5)

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
        assert res.jobs_created >= 5

        db.refresh(cursor)
        assert cursor.last_emitted_bar_end_ts == ist_naive_to_utc(
            datetime(2026, 1, 2, 10, 5)
        )
