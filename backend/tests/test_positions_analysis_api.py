from __future__ import annotations

import os
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import AnalyticsTrade, BrokerConnection, Order, PositionSnapshot

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "positions-analysis-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(BrokerConnection(broker_name="zerodha", access_token_encrypted="x"))
        session.commit()


def test_positions_analysis_endpoint_smoke() -> None:
    with SessionLocal() as session:
        # Snapshots (turnover).
        session.add(
            PositionSnapshot(
                broker_name="zerodha",
                as_of_date=date(2026, 1, 10),
                captured_at=datetime(2026, 1, 10, 10, 0, tzinfo=UTC),
                symbol="INFY",
                exchange="NSE",
                product="CNC",
                qty=10.0,
                avg_price=100.0,
                pnl=50.0,
                day_buy_qty=10.0,
                day_buy_avg_price=100.0,
            )
        )
        session.add(
            PositionSnapshot(
                broker_name="zerodha",
                as_of_date=date(2026, 1, 11),
                captured_at=datetime(2026, 1, 11, 10, 0, tzinfo=UTC),
                symbol="INFY",
                exchange="NSE",
                product="CNC",
                qty=0.0,
                avg_price=0.0,
                pnl=0.0,
                day_sell_qty=10.0,
                day_sell_avg_price=110.0,
            )
        )

        # Orders + trade (closed trades analytics).
        buy = Order(
            symbol="INFY",
            exchange="NSE",
            side="BUY",
            qty=10.0,
            price=100.0,
            product="CNC",
            status="EXECUTED",
            mode="MANUAL",
            execution_target="LIVE",
            broker_name="zerodha",
            created_at=datetime(2026, 1, 10, 10, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 10, 10, 1, tzinfo=UTC),
        )
        sell = Order(
            symbol="INFY",
            exchange="NSE",
            side="SELL",
            qty=10.0,
            price=110.0,
            product="CNC",
            status="EXECUTED",
            mode="MANUAL",
            execution_target="LIVE",
            broker_name="zerodha",
            created_at=datetime(2026, 1, 11, 10, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 11, 10, 1, tzinfo=UTC),
        )
        session.add(buy)
        session.add(sell)
        session.flush()

        session.add(
            AnalyticsTrade(
                entry_order_id=buy.id,
                exit_order_id=sell.id,
                strategy_id=None,
                pnl=(110.0 - 100.0) * 10.0,
                r_multiple=None,
                opened_at=buy.created_at,
                closed_at=sell.created_at,
            )
        )
        session.commit()

    resp = client.get(
        "/api/positions/analysis",
        params={
            "broker_name": "zerodha",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "symbol": "INFY",
            "top_n": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["summary"]["broker_name"] == "zerodha"
    assert data["summary"]["trades_count"] == 1
    assert data["summary"]["turnover_total"] > 0

    months = {row["month"] for row in data["monthly"]}
    assert "2026-01" in months

    winners = data["winners"]
    assert winners
    assert winners[0]["symbol"] == "INFY"


def test_positions_analysis_falls_back_to_snapshots_when_no_analytics_trades() -> None:
    with SessionLocal() as session:
        # Ensure no analytics trades exist, but a flat (qty=0) snapshot has PnL.
        session.query(AnalyticsTrade).delete()
        session.commit()

        session.add(
            PositionSnapshot(
                broker_name="zerodha",
                as_of_date=date(2026, 2, 1),
                captured_at=datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
                symbol="TCS",
                exchange="NSE",
                product="MIS",
                qty=0.0,
                avg_price=0.0,
                pnl=250.0,
                day_buy_qty=10.0,
                day_buy_avg_price=100.0,
                day_sell_qty=10.0,
                day_sell_avg_price=125.0,
            )
        )
        session.commit()

    resp = client.get(
        "/api/positions/analysis",
        params={
            "broker_name": "zerodha",
            "start_date": "2026-02-01",
            "end_date": "2026-02-01",
            "symbol": "TCS",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["trades_count"] >= 1
    assert data["summary"]["trades_pnl"] != 0
    assert data["monthly"][0]["trades_pnl"] != 0
    assert data["winners"] or data["losers"]
