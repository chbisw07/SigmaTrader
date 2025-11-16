from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import AnalyticsTrade, Order, Strategy
from app.services.analytics import compute_strategy_analytics, rebuild_trades


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "analytics-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_executed_orders() -> int:
    with SessionLocal() as session:
        strategy = Strategy(
            name="analytics-strategy",
            description="Analytics test strategy",
            execution_mode="AUTO",
            enabled=True,
        )
        session.add(strategy)
        session.commit()
        session.refresh(strategy)

        now = datetime.now(UTC)

        # Long trade: BUY 100 @ 100 then SELL 100 @ 110 -> +1000
        buy1 = Order(
            strategy_id=strategy.id,
            symbol="NSE:INFY",
            exchange="NSE",
            side="BUY",
            qty=100,
            price=100.0,
            order_type="LIMIT",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            simulated=False,
            created_at=now,
            updated_at=now,
        )
        sell1 = Order(
            strategy_id=strategy.id,
            symbol="NSE:INFY",
            exchange="NSE",
            side="SELL",
            qty=100,
            price=110.0,
            order_type="LIMIT",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            simulated=False,
            created_at=now + timedelta(minutes=5),
            updated_at=now + timedelta(minutes=5),
        )

        # Losing trade: BUY 50 @ 200 then SELL 50 @ 180 -> -1000
        buy2 = Order(
            strategy_id=strategy.id,
            symbol="NSE:TCS",
            exchange="NSE",
            side="BUY",
            qty=50,
            price=200.0,
            order_type="LIMIT",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            simulated=False,
            created_at=now + timedelta(minutes=10),
            updated_at=now + timedelta(minutes=10),
        )
        sell2 = Order(
            strategy_id=strategy.id,
            symbol="NSE:TCS",
            exchange="NSE",
            side="SELL",
            qty=50,
            price=180.0,
            order_type="LIMIT",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            simulated=False,
            created_at=now + timedelta(minutes=20),
            updated_at=now + timedelta(minutes=20),
        )

        session.add_all([buy1, sell1, buy2, sell2])
        session.commit()

        return strategy.id


def test_rebuild_trades_and_compute_analytics() -> None:
    strategy_id = _seed_executed_orders()

    with SessionLocal() as session:
        created = rebuild_trades(session, strategy_id=strategy_id)
        assert created == 2

    with SessionLocal() as session:
        trades = session.query(AnalyticsTrade).all()
        assert len(trades) == 2

        summary = compute_strategy_analytics(session, strategy_id=strategy_id)

    # One winning (+1000) and one losing (-1000) trade.
    assert summary.trades == 2
    assert summary.total_pnl == 0.0
    assert summary.win_rate == 0.5
    assert summary.avg_win == 1000.0
    assert summary.avg_loss == -1000.0
    # Max drawdown should be non-negative.
    assert summary.max_drawdown >= 0.0
