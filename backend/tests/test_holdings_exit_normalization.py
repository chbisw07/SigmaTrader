from __future__ import annotations

from app.holdings_exit.symbols import normalize_holding_symbol_exchange


def test_normalize_holding_symbol_exchange_defaults_exchange() -> None:
    sym, exch = normalize_holding_symbol_exchange("INFY", None)
    assert sym == "INFY"
    assert exch == "NSE"


def test_normalize_holding_symbol_exchange_parses_exchange_prefix() -> None:
    sym, exch = normalize_holding_symbol_exchange("bse: tcs ", None)
    assert sym == "TCS"
    assert exch == "BSE"

