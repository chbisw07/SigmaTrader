from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.models import Position


def sync_positions_from_zerodha(db: Session, client: ZerodhaClient) -> int:
    """Fetch positions from Zerodha and cache them in the local positions table.

    For now we use the `net` section of the Zerodha positions payload and
    replace all existing rows in the `positions` table for the single-user
    SigmaTrader instance.
    """

    payload: Dict[str, object] = client.list_positions()
    net: List[Dict[str, object]] = []
    net_raw = payload.get("net")
    if isinstance(net_raw, list):
        net = [entry for entry in net_raw if isinstance(entry, dict)]

    # Clear existing positions for a simple cache refresh.
    db.query(Position).delete()

    updated = 0
    now = datetime.now(UTC)

    for entry in net:
        symbol = entry.get("tradingsymbol")
        product = entry.get("product")
        quantity = entry.get("quantity", 0)
        avg_price = entry.get("average_price", 0)
        pnl = entry.get("pnl", 0)

        if not isinstance(symbol, str) or not isinstance(product, str):
            continue

        try:
            qty_f = float(quantity)
            avg_price_f = float(avg_price)
            pnl_f = float(pnl)
        except (TypeError, ValueError):
            continue

        position = Position(
            symbol=symbol,
            product=product,
            qty=qty_f,
            avg_price=avg_price_f,
            pnl=pnl_f,
            last_updated=now,
        )
        db.add(position)
        updated += 1

    if updated:
        db.commit()

    return updated


__all__ = ["sync_positions_from_zerodha"]
