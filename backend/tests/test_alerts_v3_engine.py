from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import AlertDefinition, Candle, Position, User
from app.services.alerts_v3_compiler import compile_alert_definition
from app.services.alerts_v3_dsl import parse_v3_expression
from app.services.alerts_v3_expression import EventNode, eval_condition

UTC = timezone.utc

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-alerts-v3-secret"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Avoid hitting external market data/Kite during tests by stubbing out
    # history backfill. The evaluator will operate solely on seeded candles.
    from app.services import market_data as md

    def _noop_fetch(*_args, **_kwargs) -> None:  # pragma: no cover
        return

    md._fetch_and_store_history = _noop_fetch  # type: ignore[attr-defined]

    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as session:
        # Seed a user for ORM FK references used by AlertDefinition.
        user = User(
            username="seed-user",
            password_hash="dummy",
            role="ADMIN",
            display_name="Seed User",
        )
        session.add(user)
        session.flush()

        prices = [100.0, 102.0, 104.0, 103.0, 106.0]  # last close = 106
        for i, close in enumerate(prices):
            ts = now - timedelta(days=len(prices) - 1 - i)
            c = Candle(
                symbol="TEST",
                exchange="NSE",
                timeframe="1d",
                ts=ts,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000.0,
            )
            session.add(c)

        # Seed a second symbol with a simple trend + range so ADX/MACD have
        # enough non-degenerate bars to produce values.
        trend = [100.0 + float(i) for i in range(12)]  # 12 bars
        for i, close in enumerate(trend):
            ts = now - timedelta(days=len(trend) - 1 - i)
            c = Candle(
                symbol="TREND",
                exchange="NSE",
                timeframe="1d",
                ts=ts,
                open=close - 0.25,
                high=close + 0.75,
                low=close - 0.75,
                close=close,
                volume=1000.0,
            )
            session.add(c)
        pos = Position(
            symbol="TEST",
            product="CNC",
            qty=10.0,
            avg_price=100.0,
            pnl=0.0,
        )
        session.add(pos)
        session.commit()


def _register_and_login(username: str) -> None:
    resp_register = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "display_name": username},
    )
    assert resp_register.status_code == 201

    resp_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    assert resp_login.status_code == 200
    client.cookies.clear()
    client.cookies.update(resp_login.cookies)


def test_v3_dsl_parses_event_ops() -> None:
    expr = parse_v3_expression('PRICE("1d") CROSSING_ABOVE 104')
    assert isinstance(expr, EventNode)
    assert expr.op == "CROSSES_ABOVE"


def test_v3_eval_condition_matches_simple_expression() -> None:
    settings = get_settings()
    expr = parse_v3_expression('PRICE("1d") > 100 AND PRICE("1d") CROSSES_ABOVE 104')
    with SessionLocal() as session:
        matched, _snapshot, _bar_time = eval_condition(
            expr,
            db=session,
            settings=settings,
            symbol="TEST",
            exchange="NSE",
            custom_indicators={},
        )
    assert matched


def test_v3_compiler_inlines_variables_and_autopicks_cadence() -> None:
    with SessionLocal() as session:
        alert = AlertDefinition(
            user_id=1,
            name="t",
            target_kind="SYMBOL",
            target_ref="TEST",
            exchange="NSE",
            evaluation_cadence="",
            variables_json='[{"name":"SMA3","dsl":"SMA(close, 3, \\"1d\\")"}]',
            condition_dsl='PRICE("1d") > SMA3',
            trigger_mode="ONCE_PER_BAR",
            only_market_hours=False,
            enabled=True,
        )
        session.add(alert)
        session.flush()

        compiled = compile_alert_definition(
            session, alert=alert, user_id=1, custom_indicators={}
        )
        # variable SMA3 should have been inlined; no IdentNode("SMA3") remains.
        raw = alert.condition_ast_json or ""
        assert raw
        assert "SMA3" not in raw
        assert alert.evaluation_cadence == "1d"

        # Sanity check: compiled expression matches on seeded candles.
        settings = get_settings()
        matched, _snapshot, _bar_time = eval_condition(
            compiled,
            db=session,
            settings=settings,
            symbol="TEST",
            exchange="NSE",
            custom_indicators={},
        )
        assert matched


def test_v3_eval_supports_adx_and_macd_builtins() -> None:
    settings = get_settings()
    # Use short lengths so the seeded 12 daily bars are sufficient to produce
    # stable values without hitting missing-data paths.
    expr = parse_v3_expression(
        'ADX(3, "1d") > 10 AND MACD(close, 3, 6, 2, "1d") > -100000 '
        'AND MACD_SIGNAL(close, 3, 6, 2, "1d") > -100000 '
        'AND MACD_HIST(close, 3, 6, 2, "1d") > -100000'
    )
    with SessionLocal() as session:
        matched, _snapshot, _bar_time = eval_condition(
            expr,
            db=session,
            settings=settings,
            symbol="TREND",
            exchange="NSE",
            custom_indicators={},
        )
    assert matched


def test_alerts_v3_api_create_and_list() -> None:
    _register_and_login("alerts-v3-api-user")

    resp = client.post(
        "/api/alerts-v3/",
        json={
            "name": "pnl",
            "target_kind": "SYMBOL",
            "target_ref": "TEST",
            "exchange": "NSE",
            "evaluation_cadence": "",
            "variables": [
                {"name": "P", "dsl": 'PRICE("1d")'},
            ],
            "condition_dsl": "P > 100",
            "trigger_mode": "ONCE_PER_BAR",
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    created = resp.json()
    assert created["name"] == "pnl"
    assert created["evaluation_cadence"] == "1d"

    resp = client.get("/api/alerts-v3/")
    assert resp.status_code == 200
    items = resp.json()
    assert any(a["id"] == created["id"] for a in items)


def test_alerts_v3_api_test_endpoint() -> None:
    _register_and_login("alerts-v3-test-user")

    resp = client.post(
        "/api/alerts-v3/test?limit=10",
        json={
            "target_kind": "SYMBOL",
            "target_ref": "TEST",
            "exchange": "NSE",
            "evaluation_cadence": "",
            "variables": [],
            "condition_dsl": 'PRICE("1d") > 100',
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluation_cadence"] == "1d"
    assert len(data["results"]) == 1
    row = data["results"][0]
    assert row["symbol"] == "TEST"
    assert row["exchange"] == "NSE"
    assert row["matched"] is True
    assert row["bar_time"] is not None
    assert row["snapshot"]["LHS"] == 106.0
    assert row["snapshot"]["RHS"] == 100.0
