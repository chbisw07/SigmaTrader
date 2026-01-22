from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from sqlalchemy.orm import Session

from app.models import HoldingGoal
from app.schemas.holdings import GoalLabel, HoldingGoalUpsert

LABEL_DEFAULT_REVIEW_DAYS: dict[GoalLabel, int] = {
    "CORE": 180,
    "TRADE": 30,
    "THEME": 90,
    "HEDGE": 120,
    "INCOME": 180,
    "PARKING": 60,
}


def normalize_symbol_exchange(
    symbol: str, exchange: str | None
) -> tuple[str, str]:
    raw_symbol = (symbol or "").strip().upper()
    raw_exchange = (exchange or "").strip().upper() if exchange else ""
    if ":" in raw_symbol:
        prefix, rest = raw_symbol.split(":", 1)
        if prefix in {"NSE", "BSE"} and rest.strip():
            raw_exchange = prefix
            raw_symbol = rest.strip().upper()
    if not raw_exchange:
        raw_exchange = "NSE"
    return raw_symbol, raw_exchange


def _default_review_date(label: GoalLabel) -> date:
    days = LABEL_DEFAULT_REVIEW_DAYS.get(label, 90)
    today = datetime.now(UTC).date()
    return today + timedelta(days=days)


def list_goals(
    db: Session,
    *,
    user_id: int,
    broker_name: str | None = None,
) -> list[HoldingGoal]:
    query = db.query(HoldingGoal).filter(HoldingGoal.user_id == user_id)
    if broker_name:
        query = query.filter(HoldingGoal.broker_name == broker_name)
    return query.order_by(HoldingGoal.symbol.asc()).all()


def upsert_goal(
    db: Session,
    *,
    user_id: int,
    payload: HoldingGoalUpsert,
) -> HoldingGoal:
    symbol, exchange = normalize_symbol_exchange(payload.symbol, payload.exchange)
    if not symbol:
        raise ValueError("Symbol is required.")

    broker_name = (payload.broker_name or "zerodha").strip().lower()
    label = payload.label

    review_date = payload.review_date or _default_review_date(label)

    if payload.target_type and payload.target_value is None:
        raise ValueError("Target value is required when target type is set.")
    if payload.target_value is not None and not payload.target_type:
        raise ValueError("Target type is required when target value is set.")

    goal = (
        db.query(HoldingGoal)
        .filter(
            HoldingGoal.user_id == user_id,
            HoldingGoal.broker_name == broker_name,
            HoldingGoal.symbol == symbol,
            HoldingGoal.exchange == exchange,
        )
        .one_or_none()
    )

    if goal is None:
        goal = HoldingGoal(
            user_id=user_id,
            broker_name=broker_name,
            symbol=symbol,
            exchange=exchange,
            label=label,
            review_date=review_date,
            target_type=payload.target_type,
            target_value=payload.target_value,
            note=payload.note,
        )
        db.add(goal)
    else:
        goal.label = label
        goal.review_date = review_date
        goal.target_type = payload.target_type
        goal.target_value = payload.target_value
        goal.note = payload.note
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(
    db: Session,
    *,
    user_id: int,
    symbol: str,
    exchange: str | None,
    broker_name: str | None = None,
) -> bool:
    sym, exch = normalize_symbol_exchange(symbol, exchange)
    broker = (broker_name or "zerodha").strip().lower()
    if not sym:
        raise ValueError("Symbol is required.")

    goal = (
        db.query(HoldingGoal)
        .filter(
            HoldingGoal.user_id == user_id,
            HoldingGoal.broker_name == broker,
            HoldingGoal.symbol == sym,
            HoldingGoal.exchange == exch,
        )
        .one_or_none()
    )
    if goal is None:
        return False
    db.delete(goal)
    db.commit()
    return True


__all__ = [
    "LABEL_DEFAULT_REVIEW_DAYS",
    "list_goals",
    "upsert_goal",
    "delete_goal",
    "normalize_symbol_exchange",
]
