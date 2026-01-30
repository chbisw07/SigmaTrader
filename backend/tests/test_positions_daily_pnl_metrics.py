from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import PositionSnapshot

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "positions-daily-pnl-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_daily_positions_realised_pnl_is_only_for_closed_positions(
    monkeypatch: Any,
) -> None:
    _ = monkeypatch  # keep signature consistent with other tests
    as_of = date(2026, 1, 29)

    with SessionLocal() as session:
        session.add(
            PositionSnapshot(
                broker_name="zerodha",
                as_of_date=as_of,
                captured_at=datetime(2026, 1, 29, 9, 28, 0, tzinfo=UTC),
                symbol="AMBER",
                exchange="NSE",
                product="CNC",
                qty=3.0,
                avg_price=5539.0,
                pnl=0.0,
                last_price=5614.0,
                close_price=5500.0,
                buy_qty=3.0,
                buy_avg_price=5539.0,
                sell_qty=0.0,
                sell_avg_price=None,
                day_buy_qty=3.0,
                day_buy_avg_price=5539.0,
                day_sell_qty=0.0,
                day_sell_avg_price=None,
                holding_qty=3.0,
            )
        )
        session.add(
            PositionSnapshot(
                broker_name="zerodha",
                as_of_date=as_of,
                captured_at=datetime(2026, 1, 29, 9, 28, 0, tzinfo=UTC),
                symbol="ASTRAMICRO",
                exchange="NSE",
                product="CNC",
                qty=-31.0,
                avg_price=969.35,
                pnl=0.0,
                last_price=971.55,
                close_price=970.0,
                buy_qty=31.0,
                buy_avg_price=957.90,
                sell_qty=62.0,
                sell_avg_price=969.35,
                day_buy_qty=0.0,
                day_buy_avg_price=None,
                day_sell_qty=31.0,
                day_sell_avg_price=969.35,
                holding_qty=0.0,
            )
        )
        session.add(
            PositionSnapshot(
                broker_name="zerodha",
                as_of_date=as_of,
                captured_at=datetime(2026, 1, 29, 9, 28, 0, tzinfo=UTC),
                symbol="BSE",
                exchange="NSE",
                product="MIS",
                qty=0.0,
                avg_price=0.0,
                pnl=236.0,
                last_price=2761.2,
                close_price=2750.0,
                buy_qty=20.0,
                buy_avg_price=2747.0,
                sell_qty=20.0,
                sell_avg_price=2770.6,
                day_buy_qty=0.0,
                day_buy_avg_price=None,
                day_sell_qty=0.0,
                day_sell_avg_price=None,
                holding_qty=0.0,
            )
        )
        session.commit()

    resp = client.get(
        "/api/positions/daily",
        params={
            "broker_name": "zerodha",
            "start_date": "2026-01-29",
            "end_date": "2026-01-29",
            "include_zero": "true",
        },
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3

    amber = next(r for r in rows if r["symbol"] == "AMBER")
    assert amber["order_type"] == "BUY"
    assert amber["pnl_value"] is None
    assert amber["pnl_pct"] is None

    astramicro = next(r for r in rows if r["symbol"] == "ASTRAMICRO")
    expected_pnl = (969.35 - 957.90) * 31.0
    expected_pct = (expected_pnl / (957.90 * 31.0)) * 100.0
    assert abs(astramicro["pnl_value"] - expected_pnl) < 1e-6
    assert abs(astramicro["pnl_pct"] - expected_pct) < 1e-6

    bse = next(r for r in rows if r["symbol"] == "BSE")
    assert bse["order_type"] == "FLAT"
    expected_pnl = (2770.6 - 2747.0) * 20.0
    expected_pct = (expected_pnl / (2747.0 * 20.0)) * 100.0
    assert abs(bse["pnl_value"] - expected_pnl) < 1e-6
    assert abs(bse["pnl_pct"] - expected_pct) < 1e-6
