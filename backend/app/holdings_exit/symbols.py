from __future__ import annotations


def normalize_holding_symbol_exchange(
    symbol: str, exchange: str | None
) -> tuple[str, str]:
    """Normalize holdings-scope symbols.

    Rules:
    - Strip whitespace, uppercase
    - Accept `NSE:INFY` / `BSE:INFY` in the symbol field (TradingView-style)
    - Default exchange to NSE when not provided

    This is intentionally conservative: it does *not* strip special characters
    because holdings symbols (broker-provided) are expected to already be clean.
    """

    raw_symbol = (symbol or "").strip().upper()
    raw_exchange = (exchange or "").strip().upper() if exchange else ""
    if ":" in raw_symbol:
        prefix, rest = raw_symbol.split(":", 1)
        prefix = prefix.strip().upper()
        rest = rest.strip().upper()
        if prefix in {"NSE", "BSE"} and rest:
            raw_exchange = prefix
            raw_symbol = rest
    if not raw_exchange:
        raw_exchange = "NSE"
    return raw_symbol, raw_exchange


__all__ = ["normalize_holding_symbol_exchange"]

