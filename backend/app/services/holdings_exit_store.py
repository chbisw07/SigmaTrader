from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.holdings_exit.constants import HOLDING_EXIT_EVENT_TYPES
from app.models import HoldingExitEvent, HoldingExitSubscription


def utc_now() -> datetime:
    return datetime.now(UTC)


def write_holding_exit_event(
    db: Session,
    *,
    subscription_id: int,
    event_type: str,
    details: dict[str, Any] | None = None,
    price_snapshot: dict[str, Any] | None = None,
) -> HoldingExitEvent:
    et = str(event_type or "").strip().upper()
    if et not in set(HOLDING_EXIT_EVENT_TYPES):
        et = "SUB_ERROR"

    details_json = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
    px_json = (
        json.dumps(price_snapshot or {}, ensure_ascii=False, separators=(",", ":"))
        if price_snapshot is not None
        else None
    )
    ev = HoldingExitEvent(
        subscription_id=int(subscription_id),
        event_type=et,
        event_ts=utc_now(),
        details_json=details_json,
        price_snapshot_json=px_json,
        created_at=utc_now(),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def ensure_subscription_owned(
    sub: HoldingExitSubscription, *, user_id: int | None
) -> None:
    """Raise ValueError if current user isn't allowed to access this subscription.

    We allow:
    - user_id is None (admin basic / single-user mode)
    - subscription.user_id is None (legacy/single-user mode rows)
    - subscription.user_id matches the current user
    """

    if user_id is None:
        return
    if sub.user_id is None:
        return
    if int(sub.user_id) != int(user_id):
        raise ValueError("Not found.")


__all__ = [
    "ensure_subscription_owned",
    "utc_now",
    "write_holding_exit_event",
]

