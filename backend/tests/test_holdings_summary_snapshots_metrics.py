from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Candle
from app.models import User
from app.schemas.positions import HoldingRead
from app.services.holdings_summary_snapshots import (
    compute_holdings_summary_metrics,
    default_snapshot_as_of_date,
    upsert_holdings_summary_snapshot,
)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-holdings-summary-snapshots"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_daily_candles(
    *,
    db,
    symbol: str,
    exchange: str,
    start: datetime,
    days: int,
    base_close: float,
    step: float,
) -> None:
    for i in range(days):
        ts = start + timedelta(days=i)
        close = base_close + step * i
        db.add(
            Candle(
                symbol=symbol,
                exchange=exchange,
                timeframe="1d",
                ts=ts,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=0.0,
            )
        )
    db.commit()


def test_compute_metrics_and_upsert_snapshot() -> None:
    settings = get_settings()

    now = (datetime.now(UTC) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)
    start = now - timedelta(days=270)

    with SessionLocal() as db:
        db.add(User(id=1, username="test", password_hash="x", role="ADMIN"))
        db.commit()

        # Seed enough daily candles to compute 1Y CAGR and alpha/beta.
        _seed_daily_candles(
            db=db,
            symbol="ABC",
            exchange="NSE",
            start=start,
            days=260,
            base_close=90.0,
            step=0.1,
        )
        _seed_daily_candles(
            db=db,
            symbol="NIFTYBEES",
            exchange="NSE",
            start=start,
            days=260,
            base_close=100.0,
            step=0.05,
        )

        holding = HoldingRead(
            symbol="ABC",
            exchange="NSE",
            quantity=10,
            average_price=100.0,
            last_price=120.0,
            pnl=200.0,
            total_pnl_percent=20.0,
            today_pnl_percent=1.0,
        )

        metrics = compute_holdings_summary_metrics(
            holdings=[holding],
            funds_available=500.0,
            settings=settings,
            db=db,
            allow_fetch_market_data=False,
        )

        assert metrics.holdings_count == 1
        assert metrics.invested == pytest.approx(1000.0)
        assert metrics.equity_value == pytest.approx(1200.0)
        assert metrics.account_value == pytest.approx(1700.0)
        assert metrics.total_pnl_pct == pytest.approx(20.0)
        assert metrics.today_pnl_pct is not None

        # With seeded candles, these should be computed (best-effort).
        assert metrics.cagr_1y_pct is not None
        assert metrics.alpha_annual_pct is not None
        assert metrics.beta is not None

        as_of = date.today()
        row1 = upsert_holdings_summary_snapshot(
            db,
            user_id=1,
            broker_name="zerodha",
            as_of_date=as_of,
            metrics=metrics,
        )

        # Upsert should update in-place and keep the same date unique key.
        metrics2 = compute_holdings_summary_metrics(
            holdings=[holding],
            funds_available=600.0,
            settings=settings,
            db=db,
            allow_fetch_market_data=False,
        )
        row2 = upsert_holdings_summary_snapshot(
            db,
            user_id=1,
            broker_name="zerodha",
            as_of_date=as_of,
            metrics=metrics2,
        )

        assert int(row1.id) == int(row2.id)
        assert row2.funds_available == pytest.approx(600.0)


def test_default_snapshot_as_of_date_before_0900_ist_uses_previous_trading_day() -> None:
    # 2026-02-11 08:30 IST
    now_utc = datetime(2026, 2, 11, 3, 0, 0, tzinfo=UTC)
    assert default_snapshot_as_of_date(now_utc) == date(2026, 2, 10)


def test_default_snapshot_as_of_date_after_0900_ist_uses_today() -> None:
    # 2026-02-11 09:30 IST
    now_utc = datetime(2026, 2, 11, 4, 0, 0, tzinfo=UTC)
    assert default_snapshot_as_of_date(now_utc) == date(2026, 2, 11)


def test_default_snapshot_as_of_date_monday_skips_weekend_gap() -> None:
    # 2026-02-09 (Mon) 08:00 IST should finalize 2026-02-06 (Fri).
    now_utc = datetime(2026, 2, 9, 2, 30, 0, tzinfo=UTC)
    assert default_snapshot_as_of_date(now_utc) == date(2026, 2, 6)
