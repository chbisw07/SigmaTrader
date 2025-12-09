from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app  # noqa: F401  # ensure routes are imported
from app.models import Candle, Position
from app.services.alert_expression import (
    ComparisonNode,
    IndicatorOperand,
    IndicatorSpec,
    NumberOperand,
    evaluate_expression_for_symbol,
)
from app.services.alert_expression_dsl import parse_expression

UTC = timezone.utc


def setup_module() -> None:  # type: ignore[override]
    # Ensure settings are initialised and DB schema is ready.
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Avoid hitting external market data/Kite during tests by stubbing out
    # history backfill. The indicator engine will operate solely on the
    # candles we seed below.
    from app.services import market_data as md

    def _noop_fetch(*_args, **_kwargs) -> None:  # pragma: no cover - trivial stub
        return

    md._fetch_and_store_history = _noop_fetch  # type: ignore[attr-defined]

    # Seed some simple daily candles for a synthetic symbol.
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as session:
        prices = [
            100.0,
            102.0,
            104.0,
            103.0,
            106.0,  # last close
        ]
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
        # Seed a simple CNC position for field-based tests.
        pos = Position(
            symbol="TEST",
            product="CNC",
            qty=10.0,
            avg_price=100.0,
            pnl=0.0,
        )
        session.add(pos)
        session.commit()


def test_evaluate_simple_price_gt_constant() -> None:
    spec = IndicatorSpec(kind="PRICE", timeframe="1d", params={})
    expr = ComparisonNode(
        left=IndicatorOperand(spec),
        operator="GT",
        right=NumberOperand(105.0),
    )

    settings = get_settings()
    with SessionLocal() as session:
        matched, samples = evaluate_expression_for_symbol(
            session,
            settings,
            symbol="TEST",
            exchange="NSE",
            expr=expr,
        )

    assert matched
    # Sanity-check that we actually computed the indicator.
    assert samples


def test_evaluate_price_cross_above_level() -> None:
    spec = IndicatorSpec(kind="PRICE", timeframe="1d", params={})
    expr = ComparisonNode(
        left=IndicatorOperand(spec),
        operator="CROSS_ABOVE",
        right=NumberOperand(104.0),
    )

    settings = get_settings()
    with SessionLocal() as session:
        matched, _ = evaluate_expression_for_symbol(
            session,
            settings,
            symbol="TEST",
            exchange="NSE",
            expr=expr,
        )

    assert matched


def test_dsl_parses_and_evaluates_complex_expression() -> None:
    # Expression uses DSL syntax and is parsed into an AST which is then
    # evaluated. For the seeded price path, PRICE(1d) moved from 103 to 106,
    # so it has recently crossed above 104.
    dsl = "(PRICE(1d) > 100) AND PRICE(1d) CROSS_ABOVE 104"
    expr = parse_expression(dsl)

    settings = get_settings()
    with SessionLocal() as session:
        matched, _ = evaluate_expression_for_symbol(
            session,
            settings,
            symbol="TEST",
            exchange="NSE",
            expr=expr,
        )

    assert matched


def test_dsl_can_use_fields_and_indicators() -> None:
    # With qty=10, avg_price=100 and last close=106, INVESTED=1000 and
    # PNL_PCT ~= 6%, so the field-based subexpression should match.
    dsl = "INVESTED > 500 AND PNL_PCT > 5"
    expr = parse_expression(dsl)

    settings = get_settings()
    with SessionLocal() as session:
        matched, _ = evaluate_expression_for_symbol(
            session,
            settings,
            symbol="TEST",
            exchange="NSE",
            expr=expr,
        )

    assert matched
