from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.db.session import get_db
from app.models import Alert, Strategy, User
from app.schemas.tv_alerts import TvAlertRead

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("", response_model=List[TvAlertRead])
def list_tv_alerts(
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    received_from: str | None = Query(default=None),
    received_to: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> List[dict[str, Any]]:
    def _parse_iso_dt(raw: str | None) -> datetime | None:
        s = (raw or "").strip()
        if not s:
            return None
        try:
            s2 = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s2)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid received_from/received_to; expected ISO datetime.",
            ) from exc

    dt_from = _parse_iso_dt(received_from)
    dt_to = _parse_iso_dt(received_to)
    if dt_from is not None and dt_to is not None:
        if dt_to < dt_from:
            raise HTTPException(status_code=400, detail="received_to must be >= received_from.")
        if (dt_to - dt_from) > timedelta(days=15):
            raise HTTPException(status_code=400, detail="Date range too large; max allowed is 15 days.")

    query = (
        db.query(Alert, Strategy.name.label("strategy_name"))
        .outerjoin(Strategy, Alert.strategy_id == Strategy.id)
        .filter(Alert.source == "TRADINGVIEW")
    )
    if user is not None:
        query = query.filter((Alert.user_id == user.id) | (Alert.user_id.is_(None)))
    if dt_from is not None:
        query = query.filter(Alert.received_at >= dt_from)
    if dt_to is not None:
        query = query.filter(Alert.received_at <= dt_to)

    rows: list[tuple[Alert, Optional[str]]] = (
        query.order_by(Alert.received_at.desc()).limit(limit).all()
    )

    return [
        {
            "id": alert.id,
            "user_id": alert.user_id,
            "strategy_id": alert.strategy_id,
            "strategy_name": strategy_name,
            "symbol": alert.symbol,
            "exchange": alert.exchange,
            "interval": alert.interval,
            "action": alert.action,
            "qty": alert.qty,
            "price": alert.price,
            "platform": alert.platform,
            "source": alert.source,
            "reason": alert.reason,
            "received_at": alert.received_at,
            "bar_time": alert.bar_time,
            "raw_payload": alert.raw_payload,
        }
        for alert, strategy_name in rows
    ]


__all__ = ["router"]
