from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.config_files import load_zerodha_symbol_map
from app.models import User
from app.pydantic_compat import model_to_json
from app.schemas.webhook import TradingViewWebhookPayload


@dataclass
class NormalizedAlert:
    user_id: int
    broker_name: str
    strategy_name: str
    symbol_display: str
    broker_symbol: str
    broker_exchange: str
    side: str
    qty: float
    price: Optional[float]
    order_type: str
    product: str
    timeframe: Optional[str]
    bar_time: Optional[datetime]
    reason: Optional[str]
    raw_payload: str


def normalize_tradingview_payload_for_zerodha(
    payload: TradingViewWebhookPayload,
    user: User,
) -> NormalizedAlert:
    """Map a TradingView webhook payload into the normalized alert schema.

    This adapter is Zerodha-focused for now and assumes that TradingView and
    Zerodha share compatible NSE/BSE symbols. It derives:
    - symbol_display from payload.symbol (e.g. ``NSE:INFY``),
    - broker_exchange and broker_symbol from either the ``NSE:INFY`` prefix or
      the explicit ``exchange``/``symbol`` fields.
    """

    # Side and quantity come directly from trade_details; order_action is
    # already normalized to BUY/SELL by the schema validator.
    side = payload.trade_details.order_action
    qty_raw = payload.trade_details.quantity
    qty = float(qty_raw) if qty_raw is not None else 0.0

    price = payload.trade_details.price
    product = (payload.trade_details.product or "MIS").upper()

    # Derive order_type:
    # - When a price is provided in the TradingView payload we treat this as
    #   a LIMIT order to avoid accidentally sending market orders at
    #   unfavourable prices.
    # - When price is omitted we default to MARKET.
    order_type = "LIMIT" if price is not None else "MARKET"

    symbol_display = payload.symbol
    broker_exchange = payload.exchange or "NSE"
    broker_symbol = symbol_display

    if ":" in symbol_display:
        ex, ts = symbol_display.split(":", 1)
        broker_exchange = ex or broker_exchange
        broker_symbol = ts or broker_symbol

    # Apply optional config-based symbol mapping for Zerodha so that we can
    # correct any differences between TradingView and broker symbols.
    symbol_map = load_zerodha_symbol_map()
    exch_key = broker_exchange.upper()
    sym_key = broker_symbol.upper()
    mapped = symbol_map.get(exch_key, {}).get(sym_key)
    if mapped:
        broker_symbol = mapped

    timeframe = payload.interval
    bar_time = payload.bar_time

    # Prefer a human-friendly reason/comment when available.
    reason = payload.trade_details.comment or payload.trade_details.alert_message

    return NormalizedAlert(
        user_id=user.id,
        broker_name="zerodha",
        strategy_name=(payload.strategy_id or payload.strategy_name),
        symbol_display=symbol_display,
        broker_symbol=broker_symbol,
        broker_exchange=broker_exchange,
        side=side,
        qty=qty,
        price=price,
        order_type=order_type,
        product=product,
        timeframe=timeframe,
        bar_time=bar_time,
        reason=reason,
        raw_payload=model_to_json(payload),
    )


__all__ = ["NormalizedAlert", "normalize_tradingview_payload_for_zerodha"]
