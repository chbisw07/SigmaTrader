from __future__ import annotations

import os

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.schemas.positions import HoldingRead
from app.services.alerts_v3_dsl import parse_v3_expression
from app.services.alerts_v3_expression import eval_condition


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-alerts-v3-holdings-metrics"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Avoid hitting external market data during tests.
    from app.services import market_data as md

    def _noop_fetch(*_args, **_kwargs) -> None:  # pragma: no cover
        return

    md._fetch_and_store_history = _noop_fetch  # type: ignore[attr-defined]


def test_today_pnl_pct_uses_holdings_snapshot() -> None:
    settings = get_settings()
    expr = parse_v3_expression("TODAY_PNL_PCT > 1.6")

    holding = HoldingRead(
        symbol="BSE",
        exchange="NSE",
        quantity=37,
        average_price=1449.62,
        last_price=2661.0,
        pnl=44821.0,
        total_pnl_percent=83.57,
        today_pnl_percent=2.11,
    )

    with SessionLocal() as session:
        matched, snapshot, _bar_time = eval_condition(
            expr,
            db=session,
            settings=settings,
            symbol="BSE",
            exchange="NSE",
            holding=holding,
            custom_indicators={},
        )

    assert matched
    assert snapshot["LHS"] == 2.11
    assert snapshot["RHS"] == 1.6
