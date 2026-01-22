from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Group, GroupMember
from app.services.market_data import MarketDataError
from app.services.market_quotes import get_bulk_quotes


def freeze_basket_prices(
    db: Session,
    settings: Settings,
    *,
    group: Group,
    members: list[GroupMember],
    frozen_at: datetime,
) -> None:
    if group.kind != "MODEL_PORTFOLIO":
        raise ValueError("freeze_basket_prices requires group.kind=MODEL_PORTFOLIO")
    if not members:
        raise ValueError("freeze_basket_prices requires non-empty members")

    keys: list[tuple[str, str]] = []
    for m in members:
        exch = (m.exchange or "NSE").strip().upper() or "NSE"
        sym = (m.symbol or "").strip().upper()
        if not sym:
            continue
        keys.append((exch, sym))

    quotes = get_bulk_quotes(db, settings, keys)
    missing: list[str] = []
    for exch, sym in keys:
        q = quotes.get((exch, sym)) or {}
        ltp = float(q.get("last_price") or 0.0)
        if ltp <= 0:
            missing.append(f"{exch}:{sym}")

    if missing:
        raise MarketDataError(
            "Missing quotes for: "
            + ", ".join(missing[:25])
            + ("…" if len(missing) > 25 else "")
        )

    group.frozen_at = frozen_at
    db.add(group)

    for m in members:
        exch = (m.exchange or "NSE").strip().upper() or "NSE"
        sym = (m.symbol or "").strip().upper()
        q = quotes.get((exch, sym)) or {}
        ltp = float(q.get("last_price") or 0.0)
        if ltp <= 0:
            continue
        m.frozen_price = ltp
        db.add(m)


__all__ = ["freeze_basket_prices"]
