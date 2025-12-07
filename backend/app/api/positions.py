from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.clients import ZerodhaClient
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import get_db
from app.models import BrokerConnection, Order, Position, User
from app.schemas.positions import HoldingRead, PositionRead
from app.services.broker_secrets import get_broker_secret
from app.services.positions_sync import sync_positions_from_zerodha

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _get_zerodha_client_for_positions(
    db: Session,
    settings: Settings,
) -> ZerodhaClient:
    """Return a Zerodha client for positions sync.

    When multiple connections exist for Zerodha, we prefer the most
    recently updated one so that the last-connected account is used.
    """

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=conn.user_id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    return ZerodhaClient(kite)


@router.post("/sync", response_model=dict)
def sync_positions(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Synchronize positions from Zerodha into the local DB cache."""

    client = _get_zerodha_client_for_positions(db, settings)
    updated = sync_positions_from_zerodha(db, client)
    return {"updated": updated}


@router.get("/", response_model=List[PositionRead])
def list_positions(db: Session = Depends(get_db)) -> List[Position]:
    """Return cached positions from the local DB."""

    return (
        db.query(Position)
        .order_by(Position.symbol, Position.product)  # type: ignore[arg-type]
        .all()
    )


@router.get("/holdings", response_model=List[HoldingRead])
def list_holdings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> List[HoldingRead]:
    """Return live holdings from Zerodha for the current user.

    For now holdings are not cached in DB; they are fetched on-demand
    from Zerodha and projected into a simple schema that includes
    quantity, average_price, last_price, and derived P&L when possible.
    """

    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user.id,
        )
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=user.id,
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha API key is not configured. "
            "Please configure it in the broker settings.",
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    client = ZerodhaClient(kite)

    raw = client.list_holdings()

    # Pre-compute the last executed BUY order date per symbol for this user so
    # that the holdings response can surface a "last purchase date" column.
    buy_orders: List[Order] = (
        db.query(Order)
        .filter(
            Order.user_id == user.id,
            Order.side == "BUY",
            Order.status.in_(["EXECUTED", "PARTIALLY_EXECUTED"]),
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    last_buy_by_symbol: dict[str, datetime] = {}
    for o in buy_orders:
        symbol = o.symbol
        if symbol not in last_buy_by_symbol:
            last_buy_by_symbol[symbol] = o.created_at

    holdings: List[HoldingRead] = []

    for entry in raw:
        symbol = entry.get("tradingsymbol")
        qty = entry.get("quantity", 0)
        avg = entry.get("average_price", 0)
        last = entry.get("last_price")

        if not isinstance(symbol, str):
            continue

        try:
            qty_f = float(qty)
            avg_f = float(avg)
            last_f = float(last) if last is not None else None
        except (TypeError, ValueError):
            continue

        pnl = None
        if last_f is not None:
            pnl = (last_f - avg_f) * qty_f

        last_purchase_date = last_buy_by_symbol.get(symbol)

        holdings.append(
            HoldingRead(
                symbol=symbol,
                quantity=qty_f,
                average_price=avg_f,
                last_price=last_f,
                pnl=pnl,
                last_purchase_date=last_purchase_date,
            )
        )

    return holdings


__all__ = ["router"]
