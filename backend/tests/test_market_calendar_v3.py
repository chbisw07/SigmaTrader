from __future__ import annotations

import os
import tempfile
from datetime import date

from fastapi.testclient import TestClient

from app.core import market_hours
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import MarketCalendar

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_market_calendar_import_and_resolve() -> None:
    csv_text = (
        "date,exchange,session_type,open_time,close_time,notes\n"
        "2026-01-26,NSE,CLOSED,,,\n"
        "2026-01-14,NSE,HALF_DAY,09:15,13:00,Test half day\n"
    )
    resp = client.post(
        "/api/market-calendar/import?exchange=NSE",
        content=csv_text,
        headers={"Content-Type": "text/csv"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] >= 2

    resp = client.get("/api/market-calendar/resolve?exchange=NSE&day=2026-01-26")
    assert resp.status_code == 200
    sess = resp.json()
    assert sess["session_type"] == "CLOSED"
    assert sess["open_time"] is None

    resp = client.get("/api/market-calendar/resolve?exchange=NSE&day=2026-01-14")
    assert resp.status_code == 200
    sess = resp.json()
    assert sess["session_type"] == "HALF_DAY"
    assert sess["open_time"] == "09:15"
    assert sess["close_time"] == "13:00"
    # Derived from close_time - 5 minutes.
    assert sess["proxy_close_time"] == "12:55"
    assert sess["preferred_buy_window"][0] == "12:55"
    assert sess["preferred_buy_window"][1] == "13:00"


def test_market_calendar_import_validation_errors() -> None:
    csv_text = (
        "date,exchange,session_type,open_time,close_time,notes\n"
        "2026-01-26,NSE,BOGUS,,,\n"
    )
    resp = client.post(
        "/api/market-calendar/import?exchange=NSE",
        content=csv_text,
        headers={"Content-Type": "text/csv"},
    )
    assert resp.status_code == 400


def test_market_calendar_weekends_and_json_holiday_fallback() -> None:
    with SessionLocal() as db:
        # Ensure no DB row exists for this weekday.
        db.query(MarketCalendar).delete()
        db.commit()

        # Weekend is closed even without calendar rows.
        sess = market_hours.resolve_market_session(
            db,
            day=date(2026, 1, 3),  # Saturday
            exchange="NSE",
        )
        assert sess.session_type == "CLOSED"

    with tempfile.TemporaryDirectory() as td:
        os.environ["ST_CONFIG_DIR"] = td
        market_hours._load_indian_holidays.cache_clear()
        with open(os.path.join(td, "indian_holidays.json"), "w", encoding="utf-8") as f:
            f.write('["2026-01-02"]')

        with SessionLocal() as db:
            sess = market_hours.resolve_market_session(
                db,
                day=date(2026, 1, 2),  # Friday, but holiday via JSON
                exchange="NSE",
            )
            assert sess.session_type == "CLOSED"

    os.environ.pop("ST_CONFIG_DIR", None)
    market_hours._load_indian_holidays.cache_clear()
