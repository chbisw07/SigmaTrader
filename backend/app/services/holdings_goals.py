from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
from sqlalchemy.orm import Session

from app.models import HoldingGoal, HoldingGoalImportPreset, HoldingGoalReview
from app.pydantic_compat import PYDANTIC_V2
from app.schemas.holdings import (
    GoalLabel,
    GoalReviewAction,
    HoldingGoalImportRequest,
    HoldingGoalImportResult,
    HoldingGoalImportError,
    HoldingGoalImportPresetCreate,
    HoldingGoalReviewActionRequest,
    HoldingGoalUpsert,
)
from app.holdings_exit.symbols import normalize_holding_symbol_exchange

LABEL_DEFAULT_REVIEW_DAYS: dict[GoalLabel, int] = {
    "CORE": 180,
    "TRADE": 30,
    "THEME": 90,
    "HEDGE": 120,
    "INCOME": 180,
    "PARKING": 60,
}


def normalize_symbol_exchange(symbol: str, exchange: str | None) -> tuple[str, str]:
    # Backward-compatible alias used by Holding Goals (and a few other modules).
    return normalize_holding_symbol_exchange(symbol, exchange)


def _default_review_date(label: GoalLabel) -> date:
    days = LABEL_DEFAULT_REVIEW_DAYS.get(label, 90)
    today = datetime.now(UTC).date()
    return today + timedelta(days=days)


def _get_goal(
    db: Session,
    *,
    user_id: int,
    broker_name: str | None,
    symbol: str,
    exchange: str | None,
) -> HoldingGoal:
    broker = (broker_name or "zerodha").strip().lower()
    sym, exch = normalize_symbol_exchange(symbol, exchange)
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
        raise ValueError("Holding goal not found.")
    return goal


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


def apply_review_action(
    db: Session,
    *,
    user_id: int,
    payload: HoldingGoalReviewActionRequest,
) -> tuple[HoldingGoal, HoldingGoalReview]:
    goal = _get_goal(
        db,
        user_id=user_id,
        broker_name=payload.broker_name,
        symbol=payload.symbol,
        exchange=payload.exchange,
    )
    previous_date = goal.review_date
    action: GoalReviewAction = payload.action
    today = datetime.now(UTC).date()

    if action in {"EXTEND", "SNOOZE"}:
        if payload.days is None:
            raise ValueError("Days is required for this action.")
        base = previous_date
        if action == "SNOOZE":
            base = max(previous_date, today)
        new_date = base + timedelta(days=payload.days)
    elif action == "REVIEWED":
        new_date = _default_review_date(goal.label)
    else:
        raise ValueError("Unsupported review action.")

    goal.review_date = new_date
    db.add(goal)

    review = HoldingGoalReview(
        goal_id=goal.id,
        user_id=user_id,
        broker_name=goal.broker_name,
        symbol=goal.symbol,
        exchange=goal.exchange,
        action=action,
        previous_review_date=previous_date,
        new_review_date=new_date,
        note=payload.note,
    )
    db.add(review)
    db.commit()
    db.refresh(goal)
    db.refresh(review)
    return goal, review


def list_reviews(
    db: Session,
    *,
    user_id: int,
    broker_name: str | None,
    symbol: str,
    exchange: str | None,
    limit: int = 50,
) -> list[HoldingGoalReview]:
    goal = _get_goal(
        db,
        user_id=user_id,
        broker_name=broker_name,
        symbol=symbol,
        exchange=exchange,
    )
    return (
        db.query(HoldingGoalReview)
        .filter(
            HoldingGoalReview.user_id == user_id,
            HoldingGoalReview.goal_id == goal.id,
        )
        .order_by(HoldingGoalReview.created_at.desc())
        .limit(limit)
        .all()
    )


def list_presets(db: Session, *, user_id: int) -> list[HoldingGoalImportPreset]:
    return (
        db.query(HoldingGoalImportPreset)
        .filter(HoldingGoalImportPreset.user_id == user_id)
        .order_by(HoldingGoalImportPreset.name.asc())
        .all()
    )


def create_preset(
    db: Session, *, user_id: int, payload: HoldingGoalImportPresetCreate
) -> HoldingGoalImportPreset:
    existing = (
        db.query(HoldingGoalImportPreset)
        .filter(
            HoldingGoalImportPreset.user_id == user_id,
            HoldingGoalImportPreset.name == payload.name,
        )
        .one_or_none()
    )
    if existing is not None:
        raise ValueError("Preset name already exists.")

    mapping = payload.mapping.model_dump() if PYDANTIC_V2 else payload.mapping.dict()
    preset = HoldingGoalImportPreset(
        user_id=user_id,
        name=payload.name,
        mapping_json=json.dumps(mapping),
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


def delete_preset(db: Session, *, user_id: int, preset_id: int) -> bool:
    preset = (
        db.query(HoldingGoalImportPreset)
        .filter(
            HoldingGoalImportPreset.user_id == user_id,
            HoldingGoalImportPreset.id == preset_id,
        )
        .one_or_none()
    )
    if preset is None:
        return False
    db.delete(preset)
    db.commit()
    return True


def _parse_review_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        pass
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            continue
    return None


def _build_holdings_symbol_set(symbols: list[str] | None) -> set[str]:
    if not symbols:
        return set()
    result: set[str] = set()
    for raw in symbols:
        sym, exch = normalize_symbol_exchange(raw, None)
        if sym:
            result.add(f"{exch}:{sym}")
            result.add(sym)
    return result


def import_goals(
    db: Session,
    *,
    user_id: int,
    payload: HoldingGoalImportRequest,
) -> HoldingGoalImportResult:
    mapping = payload.mapping
    holdings_set = _build_holdings_symbol_set(payload.holdings_symbols)
    broker_name = (payload.broker_name or "zerodha").strip().lower()

    errors: list[HoldingGoalImportError] = []
    matched = 0
    created = 0
    updated = 0
    skipped = 0

    allowed_labels = set(LABEL_DEFAULT_REVIEW_DAYS.keys())

    for idx, row in enumerate(payload.rows or []):
        raw_symbol = row.get(mapping.symbol_column, "") if mapping.symbol_column else ""
        symbol, exchange = normalize_symbol_exchange(
            raw_symbol, row.get(mapping.exchange_column)
        )
        if not symbol:
            skipped += 1
            errors.append(
                HoldingGoalImportError(
                    row_index=idx + 1, symbol=None, reason="missing_symbol"
                )
            )
            continue

        if (
            holdings_set
            and f"{exchange}:{symbol}" not in holdings_set
            and symbol not in holdings_set
        ):
            skipped += 1
            errors.append(
                HoldingGoalImportError(
                    row_index=idx + 1,
                    symbol=f"{exchange}:{symbol}",
                    reason="not_in_holdings",
                )
            )
            continue

        raw_label = (
            row.get(mapping.label_column, "") if mapping.label_column else ""
        ).strip().upper()
        if raw_label and raw_label not in allowed_labels:
            skipped += 1
            errors.append(
                HoldingGoalImportError(
                    row_index=idx + 1,
                    symbol=f"{exchange}:{symbol}",
                    reason=f"invalid_label:{raw_label}",
                )
            )
            continue

        label = raw_label or (mapping.label_default or "CORE")

        review_date = _parse_review_date(
            row.get(mapping.review_date_column) if mapping.review_date_column else None
        )
        if review_date is None and mapping.review_date_default_days:
            review_date = (
                datetime.now(UTC).date()
                + timedelta(days=int(mapping.review_date_default_days))
            )
        if review_date is None:
            review_date = _default_review_date(label)

        target_value = None
        if mapping.target_value_column:
            raw_target = (row.get(mapping.target_value_column) or "").strip()
            if raw_target:
                try:
                    target_value = float(raw_target)
                except Exception:
                    skipped += 1
                    errors.append(
                        HoldingGoalImportError(
                            row_index=idx + 1,
                            symbol=f"{exchange}:{symbol}",
                            reason="invalid_target_value",
                        )
                    )
                    continue

        if target_value is not None and mapping.target_type is None:
            skipped += 1
            errors.append(
                HoldingGoalImportError(
                    row_index=idx + 1,
                    symbol=f"{exchange}:{symbol}",
                    reason="missing_target_type",
                )
            )
            continue

        note = row.get(mapping.note_column) if mapping.note_column else None
        note = note.strip() if isinstance(note, str) else None

        existing = (
            db.query(HoldingGoal)
            .filter(
                HoldingGoal.user_id == user_id,
                HoldingGoal.broker_name == broker_name,
                HoldingGoal.symbol == symbol,
                HoldingGoal.exchange == exchange,
            )
            .one_or_none()
        )

        if existing is None:
            goal = HoldingGoal(
                user_id=user_id,
                broker_name=broker_name,
                symbol=symbol,
                exchange=exchange,
                label=label,
                review_date=review_date,
                target_type=mapping.target_type,
                target_value=target_value,
                note=note,
            )
            db.add(goal)
            created += 1
        else:
            existing.label = label
            existing.review_date = review_date
            existing.target_type = mapping.target_type
            existing.target_value = target_value
            existing.note = note
            db.add(existing)
            updated += 1

        matched += 1

    if created or updated:
        db.commit()

    return HoldingGoalImportResult(
        matched=matched,
        updated=updated,
        created=created,
        skipped=skipped,
        errors=errors,
    )


__all__ = [
    "LABEL_DEFAULT_REVIEW_DAYS",
    "list_goals",
    "upsert_goal",
    "delete_goal",
    "normalize_symbol_exchange",
    "apply_review_action",
    "list_reviews",
    "list_presets",
    "create_preset",
    "delete_preset",
    "import_goals",
]
