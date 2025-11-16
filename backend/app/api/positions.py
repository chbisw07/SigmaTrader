from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.config_files import load_kite_config
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import get_db
from app.models import BrokerConnection, Position
from app.schemas.positions import HoldingRead, PositionRead
from app.services.positions_sync import sync_positions_from_zerodha

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _get_zerodha_client_for_positions(
    db: Session,
    settings: Settings,
) -> ZerodhaClient:
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha is not connected.",
        )

    kite_cfg = load_kite_config()

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=kite_cfg.kite_connect.api_key)
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
) -> List[HoldingRead]:
    """Return live holdings from Zerodha.

    For now holdings are not cached in DB; they are fetched on-demand
    from Zerodha and projected into a simple schema that includes
    quantity, average_price, last_price, and derived P&L when possible.
    """

    client = _get_zerodha_client_for_positions(db, settings)
    raw = client.list_holdings()
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

        holdings.append(
            HoldingRead(
                symbol=symbol,
                quantity=qty_f,
                average_price=avg_f,
                last_price=last_f,
                pnl=pnl,
            )
        )

    return holdings


__all__ = ["router"]
