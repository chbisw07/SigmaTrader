from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.auth import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    Candle,
    Group,
    GroupMember,
    Order,
    StrategyDeployment,
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
        username=f"deploy-runner-user-{uuid4().hex}",
        password_hash=hash_password("password"),
        role="TRADER",
        display_name="Deploy Runner User",
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
    open_px: float,
    close_px: float,
) -> None:
    db.add(
        Candle(
            exchange=exchange,
            symbol=symbol,
            timeframe="1m",
            ts=ts_ist,
            open=open_px,
            high=max(open_px, close_px),
            low=min(open_px, close_px),
            close=close_px,
            volume=1000.0,
        )
    )


def test_paper_runner_entry_exit_idempotent() -> None:
    exit_job_id: int
    with SessionLocal() as db:
        user = _seed_user(db)
        exchange = "NSE"
        symbol = "TCS"

        # 1m bars starting at 10:00 IST.
        t0 = datetime(2026, 1, 2, 10, 0)
        closes = [100.0, 100.0, 101.0, 102.0, 99.0, 99.0]
        prev_close = closes[0]
        for i, close_px in enumerate(closes):
            ts = t0 + timedelta(minutes=i)
            open_px = prev_close if i > 0 else close_px
            _add_1m_candle(
                db,
                exchange=exchange,
                symbol=symbol,
                ts_ist=ts,
                open_px=open_px,
                close_px=close_px,
            )
            prev_close = close_px
        db.commit()

        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-runner-{uuid4().hex}",
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
                        "entry_dsl": "PRICE(1d) > SMA(3,1d)",
                        "exit_dsl": "PRICE(1d) < SMA(3,1d)",
                        "initial_cash": 10000.0,
                        "position_size_pct": 100.0,
                        "execution_target": "PAPER",
                        "product": "CNC",
                        "direction": "LONG",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="RUNNING"))
        db.commit()

        # Entry evaluated at bar_end 10:03 (uses 10:02 close); fill at open of 10:03.
        entry_bar_end_ist = datetime(2026, 1, 2, 10, 3)
        entry_job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="BAR_CLOSED",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:1m:{exchange}:{symbol}:{entry_bar_end_ist.isoformat()}",
            scheduled_for=ist_naive_to_utc(entry_bar_end_ist),
            run_after=datetime(2026, 1, 2, 4, 34, tzinfo=UTC),
            payload_json=json.dumps(
                {
                    "kind": "BAR_CLOSED",
                    "deployment_id": dep.id,
                    "timeframe": "1m",
                    "exchange": exchange,
                    "symbol": symbol,
                    "bar_end_ist": entry_bar_end_ist.isoformat(),
                }
            ),
        )
        db.add(entry_job)

        # Exit evaluated at bar_end 10:05 (uses 10:04 close); fill at open of 10:05.
        exit_bar_end_ist = datetime(2026, 1, 2, 10, 5)
        exit_job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="BAR_CLOSED",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:1m:{exchange}:{symbol}:{exit_bar_end_ist.isoformat()}",
            scheduled_for=ist_naive_to_utc(exit_bar_end_ist),
            run_after=datetime(2026, 1, 2, 4, 36, tzinfo=UTC),
            payload_json=json.dumps(
                {
                    "kind": "BAR_CLOSED",
                    "deployment_id": dep.id,
                    "timeframe": "1m",
                    "exchange": exchange,
                    "symbol": symbol,
                    "bar_end_ist": exit_bar_end_ist.isoformat(),
                }
            ),
        )
        db.add(exit_job)
        db.commit()
        exit_job_id = int(exit_job.id)

    # Execute jobs using worker logic (claims + per-deployment lock).
    with SessionLocal() as db:
        did = execute_job_once(
            db, worker_id="runner-test", now=datetime(2026, 1, 2, 4, 35, tzinfo=UTC)
        )
        assert did is True
        did = execute_job_once(
            db, worker_id="runner-test", now=datetime(2026, 1, 2, 4, 37, tzinfo=UTC)
        )
        assert did is True

        orders = (
            db.query(Order)
            .filter(Order.deployment_id.isnot(None))
            .order_by(Order.id)
            .all()
        )
        assert len(orders) == 2
        assert orders[0].side == "BUY"
        assert orders[0].execution_target == "PAPER"
        assert orders[0].simulated is True
        assert orders[0].status == "EXECUTED"
        assert orders[1].side == "SELL"

        # Re-run exit job to simulate retry: should not create a duplicate order.
        exit_job = db.get(StrategyDeploymentJob, exit_job_id)
        assert exit_job is not None
        exit_job.status = "PENDING"
        exit_job.locked_at = None
        exit_job.locked_by = None
        db.add(exit_job)
        db.commit()

        did = execute_job_once(
            db, worker_id="runner-test", now=datetime(2026, 1, 2, 4, 38, tzinfo=UTC)
        )
        assert did is True
        orders2 = db.query(Order).filter(Order.deployment_id.isnot(None)).all()
        assert len(orders2) == 2


def test_portfolio_ranking_picks_top_symbol() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        exchange = "NSE"
        sym_a = "AAA"
        sym_b = "BBB"

        t0 = datetime(2026, 1, 2, 10, 0)
        closes_a = [100.0, 105.0, 110.0]
        closes_b = [100.0, 101.0, 101.5]
        for i in range(3):
            ts = t0 + timedelta(minutes=i)
            _add_1m_candle(
                db,
                exchange=exchange,
                symbol=sym_a,
                ts_ist=ts,
                open_px=closes_a[i],
                close_px=closes_a[i],
            )
            _add_1m_candle(
                db,
                exchange=exchange,
                symbol=sym_b,
                ts_ist=ts,
                open_px=closes_b[i],
                close_px=closes_b[i],
            )
        db.commit()

        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-pf-{uuid4().hex}",
            kind="PORTFOLIO_STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="CNC",
            target_kind="GROUP",
            group_id=None,
            timeframe="1m",
            config_json=json.dumps(
                {
                    "kind": "PORTFOLIO_STRATEGY",
                    "universe": {
                        "target_kind": "GROUP",
                        "group_id": None,
                    },
                    "config": {
                        "timeframe": "1m",
                        "entry_dsl": "PRICE(1d) > 0",
                        "exit_dsl": "PRICE(1d) > 999999",
                        "initial_cash": 10000.0,
                        "max_open_positions": 1,
                        "allocation_mode": "RANKING",
                        "ranking_window": 2,
                        "sizing_mode": "FIXED_CASH",
                        "fixed_cash_per_trade": 5000.0,
                        "execution_target": "PAPER",
                        "product": "CNC",
                        "direction": "LONG",
                    },
                }
            ),
        )
        group = Group(owner_id=user.id, name=f"grp-{uuid4().hex}", kind="WATCHLIST")
        db.add(group)
        db.flush()
        db.add_all(
            [
                GroupMember(group_id=group.id, exchange=exchange, symbol=sym_a),
                GroupMember(group_id=group.id, exchange=exchange, symbol=sym_b),
            ]
        )
        db.flush()
        dep.group_id = group.id
        # Mirror group_id into the stored universe snapshot.
        dep_payload = json.loads(dep.config_json)
        dep_payload["universe"]["group_id"] = group.id
        dep.config_json = json.dumps(dep_payload)
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="RUNNING"))

        bar_end_ist = datetime(2026, 1, 2, 10, 3)
        job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="BAR_CLOSED",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:1m:{exchange}:{sym_a}:{bar_end_ist.isoformat()}",
            scheduled_for=ist_naive_to_utc(bar_end_ist),
            run_after=datetime(2026, 1, 2, 4, 40, tzinfo=UTC),
            payload_json=json.dumps(
                {
                    "kind": "BAR_CLOSED",
                    "deployment_id": dep.id,
                    "timeframe": "1m",
                    "bar_end_ist": bar_end_ist.isoformat(),
                }
            ),
        )
        db.add(job)
        db.commit()

    with SessionLocal() as db:
        did = execute_job_once(
            db,
            worker_id="runner-test",
            now=datetime(2026, 1, 2, 4, 41, tzinfo=UTC),
        )
        assert did is True
        orders = (
            db.query(Order)
            .filter(Order.deployment_id.isnot(None))
            .filter(Order.symbol.in_([sym_a, sym_b]))
            .all()
        )
        assert len(orders) == 1
        assert orders[0].symbol == sym_a


def test_mis_flatten_window_exits() -> None:
    with SessionLocal() as db:
        user = _seed_user(db)
        exchange = "NSE"
        symbol = "MISX"
        t0 = datetime(2026, 1, 2, 15, 20)
        closes = [100.0, 101.0, 102.0]
        prev = closes[0]
        for i, c in enumerate(closes):
            ts = t0 + timedelta(minutes=i)
            _add_1m_candle(
                db,
                exchange=exchange,
                symbol=symbol,
                ts_ist=ts,
                open_px=prev if i > 0 else c,
                close_px=c,
            )
            prev = c
        db.commit()

        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-mis-{uuid4().hex}",
            kind="STRATEGY",
            execution_target="PAPER",
            enabled=True,
            broker_name="zerodha",
            product="MIS",
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
                        "exit_dsl": "PRICE(1d) > 999999",
                        "initial_cash": 10000.0,
                        "position_size_pct": 100.0,
                        "execution_target": "PAPER",
                        "product": "MIS",
                        "direction": "LONG",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="RUNNING"))

        # Enter on bar close 15:22 (fill at open 15:22).
        entry_end_ist = datetime(2026, 1, 2, 15, 22)
        db.add(
            StrategyDeploymentJob(
                deployment_id=dep.id,
                owner_id=user.id,
                kind="BAR_CLOSED",
                status="PENDING",
                dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:1m:{exchange}:{symbol}:{entry_end_ist.isoformat()}",
                scheduled_for=ist_naive_to_utc(entry_end_ist),
                run_after=datetime(2026, 1, 2, 9, 51, tzinfo=UTC),
                payload_json=json.dumps(
                    {
                        "kind": "BAR_CLOSED",
                        "deployment_id": dep.id,
                        "timeframe": "1m",
                        "exchange": exchange,
                        "symbol": symbol,
                        "bar_end_ist": entry_end_ist.isoformat(),
                    }
                ),
            )
        )
        # Flatten window at 15:25.
        flatten_ist = datetime(2026, 1, 2, 15, 25)
        db.add(
            StrategyDeploymentJob(
                deployment_id=dep.id,
                owner_id=user.id,
                kind="WINDOW",
                status="PENDING",
                dedupe_key=f"DEP:{dep.id}:WINDOW:MIS_FLATTEN:{flatten_ist.date().isoformat()}",
                scheduled_for=ist_naive_to_utc(flatten_ist),
                run_after=datetime(2026, 1, 2, 9, 52, tzinfo=UTC),
                payload_json=json.dumps(
                    {
                        "kind": "WINDOW",
                        "deployment_id": dep.id,
                        "window": "MIS_FLATTEN",
                        "window_ist": flatten_ist.isoformat(),
                    }
                ),
            )
        )
        db.commit()

    with SessionLocal() as db:
        did = execute_job_once(
            db,
            worker_id="runner-test",
            now=datetime(2026, 1, 2, 9, 51, tzinfo=UTC),
        )
        assert did is True
        did = execute_job_once(
            db,
            worker_id="runner-test",
            now=datetime(2026, 1, 2, 9, 52, tzinfo=UTC),
        )
        assert did is True
        orders = (
            db.query(Order)
            .filter(Order.deployment_id.isnot(None))
            .filter(Order.symbol == symbol)
            .order_by(Order.id)
            .all()
        )
        assert len(orders) == 2
        assert orders[0].side == "BUY"
        assert orders[1].side == "SELL"


def test_disaster_stop_created_and_cancelled() -> None:
    exit_job_id: int
    with SessionLocal() as db:
        user = _seed_user(db)
        exchange = "NSE"
        symbol = "DSTP"

        t0 = datetime(2026, 1, 2, 10, 0)
        closes = [100.0, 100.0, 101.0, 102.0, 99.0, 99.0]
        prev_close = closes[0]
        for i, close_px in enumerate(closes):
            ts = t0 + timedelta(minutes=i)
            open_px = prev_close if i > 0 else close_px
            _add_1m_candle(
                db,
                exchange=exchange,
                symbol=symbol,
                ts_ist=ts,
                open_px=open_px,
                close_px=close_px,
            )
            prev_close = close_px
        db.commit()

        dep = StrategyDeployment(
            owner_id=user.id,
            name=f"dep-dstop-{uuid4().hex}",
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
                        "entry_dsl": "PRICE(1d) > SMA(3,1d)",
                        "exit_dsl": "PRICE(1d) < SMA(3,1d)",
                        "initial_cash": 10000.0,
                        "position_size_pct": 100.0,
                        "stop_loss_pct": 1.0,
                        "execution_target": "PAPER",
                        "product": "CNC",
                        "direction": "LONG",
                    },
                }
            ),
        )
        db.add(dep)
        db.flush()
        db.add(StrategyDeploymentState(deployment_id=dep.id, status="RUNNING"))
        db.commit()

        entry_end_ist = datetime(2026, 1, 2, 10, 3)
        exit_end_ist = datetime(2026, 1, 2, 10, 5)
        db.add(
            StrategyDeploymentJob(
                deployment_id=dep.id,
                owner_id=user.id,
                kind="BAR_CLOSED",
                status="PENDING",
                dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:1m:{exchange}:{symbol}:{entry_end_ist.isoformat()}",
                scheduled_for=ist_naive_to_utc(entry_end_ist),
                run_after=datetime(2026, 1, 2, 4, 50, tzinfo=UTC),
                payload_json=json.dumps(
                    {
                        "kind": "BAR_CLOSED",
                        "deployment_id": dep.id,
                        "timeframe": "1m",
                        "exchange": exchange,
                        "symbol": symbol,
                        "bar_end_ist": entry_end_ist.isoformat(),
                    }
                ),
            )
        )
        exit_job = StrategyDeploymentJob(
            deployment_id=dep.id,
            owner_id=user.id,
            kind="BAR_CLOSED",
            status="PENDING",
            dedupe_key=f"DEP:{dep.id}:BAR_CLOSED:1m:{exchange}:{symbol}:{exit_end_ist.isoformat()}",
            scheduled_for=ist_naive_to_utc(exit_end_ist),
            run_after=datetime(2026, 1, 2, 4, 51, tzinfo=UTC),
            payload_json=json.dumps(
                {
                    "kind": "BAR_CLOSED",
                    "deployment_id": dep.id,
                    "timeframe": "1m",
                    "exchange": exchange,
                    "symbol": symbol,
                    "bar_end_ist": exit_end_ist.isoformat(),
                }
            ),
        )
        db.add(exit_job)
        db.commit()
        exit_job_id = int(exit_job.id)

    with SessionLocal() as db:
        did = execute_job_once(
            db,
            worker_id="runner-test",
            now=datetime(2026, 1, 2, 4, 50, tzinfo=UTC),
        )
        assert did is True

        orders = (
            db.query(Order)
            .filter(Order.deployment_id.isnot(None))
            .filter(Order.symbol == symbol)
            .order_by(Order.id)
            .all()
        )
        # Entry + disaster stop.
        assert len(orders) == 2
        assert orders[0].side == "BUY"
        assert orders[1].status == "WAITING"
        assert orders[1].gtt is True

        did = execute_job_once(
            db,
            worker_id="runner-test",
            now=datetime(2026, 1, 2, 4, 51, tzinfo=UTC),
        )
        assert did is True

        orders2 = (
            db.query(Order)
            .filter(Order.deployment_id.isnot(None))
            .filter(Order.symbol == symbol)
            .order_by(Order.id)
            .all()
        )
        # Entry + disaster stop + exit.
        assert len(orders2) == 3
        assert orders2[-1].side == "SELL"
        # Disaster stop should be cancelled by the runner.
        cancelled = [o for o in orders2 if o.gtt and o.status == "CANCELLED"]
        assert cancelled
        assert db.get(StrategyDeploymentJob, exit_job_id) is not None
