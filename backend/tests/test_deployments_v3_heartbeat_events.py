from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    Candle,
    StrategyDeployment,
    StrategyDeploymentEventLog,
    StrategyDeploymentJob,
    StrategyDeploymentState,
    User,
)
from app.services.deployment_scheduler import ist_naive_to_utc
from app.services.deployment_worker import execute_job_once


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_user(db) -> User:
    user = User(
        username=f"deploy-v3-user-{uuid4().hex}",
        password_hash=hash_password("password"),
        role="TRADER",
        display_name="Deploy V3 User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_1m_candle(
    db,
    *,
    exchange: str,
    symbol: str,
    ts_ist: datetime,
    close_px: float,
) -> None:
    db.add(
        Candle(
            exchange=exchange,
            symbol=symbol,
            timeframe="1m",
            ts=ts_ist,
            open=close_px,
            high=close_px,
            low=close_px,
            close=close_px,
            volume=1000.0,
        )
    )


def test_v3_heartbeat_fields_and_event_journal_written() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        exchange = "NSE"
        symbol = "INFY"
        t0 = datetime(2026, 1, 2, 10, 0)
        for i in range(3):
            _add_1m_candle(
                db,
                exchange=exchange,
                symbol=symbol,
                ts_ist=t0 + timedelta(minutes=i),
                close_px=100.0 + i,
            )
        db.commit()

        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-v3-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="CNC",
            target_kind="SYMBOL",
            exchange=exchange,
            symbol=symbol,
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "STRATEGY",
                    "universe": {
                        "target_kind": "SYMBOL",
                        "symbols": [{"exchange": exchange, "symbol": symbol}],
                    },
                    "config": {
                        "timeframe": "1m",
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) < 0",
                        "initial_cash": 10000.0,
                        "position_size_pct": 100.0,
                        "execution_target": "PAPER",
                        "product": "CNC",
                        "direction": "LONG",
                    },
                },
                ensure_ascii=False,
            ),
        )
        db.add(dep)
        db.flush()
        dep.state = StrategyDeploymentState(deployment_id=dep.id, status="RUNNING")
        db.add(dep.state)
        db.flush()

        bar_end_ist = t0 + timedelta(minutes=2)
        scheduled_for = ist_naive_to_utc(bar_end_ist)
        job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="BAR_CLOSED",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:{scheduled_for.isoformat()}",
            scheduled_for=scheduled_for,
            run_after=scheduled_for,
            payload_json=json.dumps(
                {
                    "kind": "BAR_CLOSED",
                    "deployment_id": dep.id,
                    "timeframe": "1m",
                    "bar_end_ist": bar_end_ist.isoformat(),
                    "bar_end_utc": scheduled_for.isoformat(),
                },
                ensure_ascii=False,
            ),
        )
        db.add(job)
        db.commit()

        did = execute_job_once(db, worker_id="test-worker", now=datetime.now(UTC))
        assert did is True

        state = db.query(StrategyDeploymentState).filter_by(deployment_id=dep.id).one()
        assert state.last_eval_at is not None
        assert state.last_eval_bar_end_ts == scheduled_for
        assert state.runtime_state in {"FLAT", "IN_POSITION", "WARMING_UP", "PAUSED"}
        assert state.last_decision is not None
        assert state.last_decision_reason
        assert state.next_eval_at is not None

        logs = (
            db.query(StrategyDeploymentEventLog)
            .filter(StrategyDeploymentEventLog.deployment_id == dep.id)
            .all()
        )
        kinds = {log.kind for log in logs}
        assert "EVAL_STARTED" in kinds
        assert "EVAL_FINISHED" in kinds
        assert "BAR_CLOSED_RECEIVED" in kinds
        # Entry should have happened (PRICE > 0).
        assert "ENTRY" in kinds
