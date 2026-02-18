from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.ai_trading_manager import AiTmExpectedPosition
from app.schemas.ai_trading_manager import BrokerSnapshot


def resync_expected_positions(
    db: Session,
    *,
    account_id: str,
    broker_snapshot: BrokerSnapshot,
) -> int:
    """Rebuild expected positions from broker truth snapshot (read-only w.r.t broker)."""

    db.execute(delete(AiTmExpectedPosition).where(AiTmExpectedPosition.account_id == account_id))
    now = datetime.now(UTC)
    rows = []
    for p in broker_snapshot.positions:
        rows.append(
            AiTmExpectedPosition(
                account_id=account_id,
                symbol=str(p.symbol).upper(),
                product=str(p.product).upper(),
                expected_qty=float(p.qty),
                avg_price=float(p.avg_price) if p.avg_price is not None else None,
                updated_at=now,
            )
        )
    if rows:
        db.add_all(rows)
    db.commit()
    return len(rows)
