from __future__ import annotations

import os
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Candle

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_candles(symbol: str, *, days: int = 80) -> None:
    start = datetime(2026, 1, 1)
    with SessionLocal() as db:
        for i in range(days):
            ts = start + timedelta(days=i)
            close = 100.0 + (i * 0.1)  # very low volatility, mild uptrend
            db.add(
                Candle(
                    symbol=symbol,
                    exchange="NSE",
                    timeframe="1d",
                    ts=ts,
                    open=close - 0.05,
                    high=close + 0.10,
                    low=close - 0.10,
                    close=close,
                    volume=1000.0,
                )
            )
        db.commit()


def test_market_context_overlay_classifies_trend_and_volatility() -> None:
    _seed_candles("INFY", days=80)

    resp = client.get("/api/ai/market-context?account_id=default&symbols=INFY&exchange=NSE&timeframe=1d")
    assert resp.status_code == 200
    data = resp.json()
    overlay = data["overlay"]
    assert overlay["exchange"] == "NSE"
    assert overlay["timeframe"] == "1d"
    assert len(overlay["items"]) == 1
    item = overlay["items"][0]
    assert item["symbol"] == "INFY"
    assert item["trend_regime"] in {"up", "range", "unknown"}
    # With an increasing close series, we should be in an uptrend once SMA windows are met.
    assert item["trend_regime"] == "up"
    assert item["volatility_regime"] in {"low", "normal", "high", "unknown"}


def test_sizing_suggest_is_deterministic_with_explicit_equity() -> None:
    resp = client.post(
        "/api/ai/sizing/suggest",
        json={
            "account_id": "default",
            "symbol": "INFY",
            "exchange": "NSE",
            "product": "CNC",
            "entry_price": 100.0,
            "stop_price": 90.0,
            "risk_budget_pct": 0.5,
            "equity_value": 100000.0,
        },
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["suggested_qty"] == 50
    assert abs(float(out["risk_amount"]) - 500.0) < 1e-9
    assert abs(float(out["risk_per_share"]) - 10.0) < 1e-9
