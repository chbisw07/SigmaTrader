from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.core.config import Settings
from app.core.crypto import decrypt_token
from app.models import Order, Strategy
from app.models.broker import BrokerConnection  # type: ignore[attr-defined]
from app.services.system_events import record_system_event


@dataclass
class PaperFillResult:
    filled_orders: int


def _get_price_client(db: Session, settings: Settings) -> ZerodhaClient:
    """Return a ZerodhaClient for price data (LTP) only.

    We reuse the most recent Zerodha BrokerConnection; since prices are
    global per market, it is safe to use any connected account for LTP.
    """

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise RuntimeError("Zerodha is not connected; cannot run paper fills.")

    api_key = settings.zerodha_api_key
    if not api_key:
        raise RuntimeError("Zerodha API key (ST_ZERODHA_API_KEY) not configured.")

    from kiteconnect import KiteConnect  # type: ignore[import]

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return ZerodhaClient(kite)


def submit_paper_order(
    db: Session,
    settings: Settings,
    order: Order,
    *,
    correlation_id: Optional[str] = None,
) -> Order:
    """Mark an order as a paper trade and put it into SENT state.

    Actual fills are performed by `poll_paper_orders`.
    """

    order.simulated = True
    if order.status != "WAITING":
        return order
    order.status = "SENT"
    order.error_message = None
    db.add(order)
    db.commit()
    db.refresh(order)

    record_system_event(
        db,
        level="INFO",
        category="paper",
        message="Paper order submitted",
        correlation_id=correlation_id,
        details={
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
        },
    )
    return order


def poll_paper_orders(db: Session, settings: Settings) -> PaperFillResult:
    """Check simulated orders and mark them EXECUTED when prices cross limits.

    This v1 engine uses simple LTP-based rules:
    - MARKET: execute at current LTP.
    - LIMIT:
      - BUY: execute when LTP <= limit price.
      - SELL: execute when LTP >= limit price.

    More advanced behaviour (SL/SL-M, partial fills, etc.) can be added later.
    """

    try:
        client = _get_price_client(db, settings)
    except Exception:
        return PaperFillResult(filled_orders=0)

    open_orders: List[Order] = (
        db.query(Order)
        .join(Strategy, Strategy.id == Order.strategy_id)
        .filter(
            Order.simulated.is_(True),
            Order.status.in_(["SENT", "OPEN"]),
            Strategy.execution_target == "PAPER",
        )
        .order_by(Order.created_at)
        .all()
    )

    filled = 0

    for order in open_orders:
        symbol = order.symbol
        exchange = order.exchange or "NSE"
        if ":" in symbol:
            ex, ts = symbol.split(":", 1)
            if ex:
                exchange = ex
            symbol = ts

        try:
            ltp = client.get_ltp(exchange=exchange, tradingsymbol=symbol)
        except Exception:
            continue

        should_fill = False
        exec_price: Optional[float] = None

        if order.order_type == "MARKET":
            should_fill = True
            exec_price = ltp
        elif order.order_type == "LIMIT" and order.price is not None:
            if order.side.upper() == "BUY" and ltp <= order.price:
                should_fill = True
                exec_price = order.price
            elif order.side.upper() == "SELL" and ltp >= order.price:
                should_fill = True
                exec_price = order.price

        if not should_fill:
            continue

        order.status = "EXECUTED"
        if exec_price is not None:
            order.price = exec_price
        db.add(order)
        filled += 1

        record_system_event(
            db,
            level="INFO",
            category="paper",
            message="Paper order executed",
            correlation_id=None,
            details={
                "order_id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "price": order.price,
                "ltp": ltp,
            },
        )

    if filled:
        db.commit()

    return PaperFillResult(filled_orders=filled)


__all__ = ["PaperFillResult", "submit_paper_order", "poll_paper_orders"]
