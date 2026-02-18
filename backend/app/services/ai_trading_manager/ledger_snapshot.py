from __future__ import annotations

from datetime import UTC, datetime
from typing import List

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Order, Position
from app.models.ai_trading_manager import AiTmExpectedPosition
from app.schemas.ai_trading_manager import LedgerOrder, LedgerPosition, LedgerSnapshot


def build_ledger_snapshot(db: Session, *, account_id: str = "default") -> LedgerSnapshot:
    now = datetime.now(UTC)

    expected_positions: List[LedgerPosition] = []
    expected_rows = (
        db.execute(
            select(AiTmExpectedPosition)
            .where(AiTmExpectedPosition.account_id == account_id)
            .order_by(AiTmExpectedPosition.symbol)
        )
        .scalars()
        .all()
    )
    if expected_rows:
        for p in expected_rows:
            expected_positions.append(
                LedgerPosition(
                    symbol=p.symbol,
                    product=p.product,
                    expected_qty=float(p.expected_qty),
                    avg_price=float(p.avg_price) if p.avg_price is not None else None,
                )
            )
    else:
        # Phase 0 fallback: use the existing positions table as a best-effort
        # "expected ledger" snapshot until expected ledger is populated.
        positions = db.execute(select(Position).order_by(Position.symbol)).scalars().all()
        for p in positions:
            expected_positions.append(
                LedgerPosition(
                    symbol=p.symbol,
                    product=p.product,
                    expected_qty=float(p.qty),
                    avg_price=float(p.avg_price) if p.avg_price is not None else None,
                )
            )

    orders = db.execute(select(Order).order_by(desc(Order.created_at)).limit(500)).scalars().all()
    expected_orders: List[LedgerOrder] = []
    for o in orders:
        expected_orders.append(
            LedgerOrder(
                order_id=str(o.id),
                symbol=o.symbol,
                side=o.side,
                product=o.product,
                qty=float(o.qty),
                order_type=o.order_type,
                status=o.status,
                broker_order_id=o.broker_order_id,
            )
        )

    return LedgerSnapshot(
        as_of_ts=now,
        account_id=account_id,
        expected_positions=expected_positions,
        expected_orders=expected_orders,
        watchers=[],
    )
