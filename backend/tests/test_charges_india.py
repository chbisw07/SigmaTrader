from __future__ import annotations

from app.services.charges_india import estimate_india_equity_charges


def test_charges_cnc_sell_includes_dp_when_enabled() -> None:
    est_on = estimate_india_equity_charges(
        broker="zerodha",
        product="CNC",
        side="SELL",
        exchange="NSE",
        turnover=100_000.0,
        include_dp=True,
    )
    est_off = estimate_india_equity_charges(
        broker="zerodha",
        product="CNC",
        side="SELL",
        exchange="NSE",
        turnover=100_000.0,
        include_dp=False,
    )

    assert est_on.dp > 0
    assert est_off.dp == 0.0
    assert est_on.total >= est_off.total


def test_charges_mis_has_no_dp_and_sell_only_stt() -> None:
    buy = estimate_india_equity_charges(
        broker="zerodha",
        product="MIS",
        side="BUY",
        exchange="NSE",
        turnover=50_000.0,
        include_dp=True,
    )
    sell = estimate_india_equity_charges(
        broker="zerodha",
        product="MIS",
        side="SELL",
        exchange="NSE",
        turnover=50_000.0,
        include_dp=True,
    )

    assert buy.dp == 0.0
    assert sell.dp == 0.0
    assert buy.stt == 0.0
    assert sell.stt > 0
