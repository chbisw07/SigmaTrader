from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Group, GroupMember, Order, User


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _safe_name(db: Session, *, owner_id: int | None, base: str) -> str:
    base2 = (base or "").strip() or "Portfolio"
    candidate = base2
    suffix = 1
    while True:
        exists = (
            db.query(Group.id)
            .filter(
                Group.owner_id == owner_id,
                func.lower(Group.name) == candidate.lower(),
            )
            .first()
            is not None
        )
        if not exists:
            return candidate
        suffix += 1
        candidate = f"{base2} ({suffix})"


def create_portfolio_from_basket(
    db: Session,
    *,
    user: User,
    basket: Group,
    members: list[GroupMember],
    orders_spec: list[tuple[str, str, int]],
    broker_name: str,
    product: str,
    order_type: str,
    execution_target: str,
) -> tuple[Group, list[GroupMember], list[Order]]:
    if basket.kind != "MODEL_PORTFOLIO":
        raise ValueError("basket must be MODEL_PORTFOLIO")
    if not members:
        raise ValueError("basket must be non-empty")
    if basket.frozen_at is None:
        raise ValueError("basket must be frozen before buy")
    if any((m.frozen_price or 0.0) <= 0 for m in members):
        raise ValueError("basket has missing frozen prices")

    now = _now_utc()
    owner_id = user.id
    portfolio_name = _safe_name(
        db,
        owner_id=owner_id,
        base=f"{basket.name} Portfolio {now.strftime('%Y-%m-%d %H:%M')}",
    )

    portfolio = Group(
        owner_id=owner_id,
        name=portfolio_name,
        kind="PORTFOLIO",
        description=f"Created from basket {basket.id}.",
        funds=None,
        allocation_mode=None,
        frozen_at=basket.frozen_at,
        origin_basket_id=basket.id,
        bought_at=now,
    )
    db.add(portfolio)
    db.flush()

    copied_members: list[GroupMember] = []
    by_key: dict[tuple[str, str], GroupMember] = {}
    for m in members:
        exch = (m.exchange or "NSE").strip().upper() or "NSE"
        sym = (m.symbol or "").strip().upper()
        target_weight = m.target_weight
        if basket.funds and basket.funds > 0:
            mode = (basket.allocation_mode or "").strip().upper()
            if mode == "AMOUNT" and m.allocation_amount is not None:
                try:
                    amt = float(m.allocation_amount)
                except Exception:
                    amt = 0.0
                if amt > 0:
                    target_weight = amt / float(basket.funds)
            elif (
                mode == "QTY"
                and m.allocation_qty is not None
                and m.frozen_price is not None
            ):
                try:
                    qty = float(m.allocation_qty)
                    px = float(m.frozen_price)
                except Exception:
                    qty = 0.0
                    px = 0.0
                if qty > 0 and px > 0:
                    target_weight = (qty * px) / float(basket.funds)
        gm = GroupMember(
            group_id=portfolio.id,
            symbol=sym,
            exchange=exch,
            target_weight=target_weight,
            notes=None,
            reference_qty=0,
            reference_price=None,
            frozen_price=m.frozen_price,
            weight_locked=False,
            allocation_amount=m.allocation_amount,
            allocation_qty=m.allocation_qty,
        )
        db.add(gm)
        copied_members.append(gm)
        by_key[(exch, sym)] = gm

    created_orders: list[Order] = []
    for exch, sym, qty in orders_spec:
        key = ((exch or "NSE").strip().upper() or "NSE", (sym or "").strip().upper())
        if key not in by_key:
            raise ValueError(f"Order symbol not in basket: {key[0]}:{key[1]}")
        if qty <= 0:
            continue
        o = Order(
            user_id=user.id,
            portfolio_group_id=portfolio.id,
            broker_name=(broker_name or "zerodha").strip().lower() or "zerodha",
            symbol=key[1],
            exchange=key[0],
            side="BUY",
            qty=float(qty),
            price=None,
            trigger_price=None,
            trigger_percent=None,
            order_type=(order_type or "MARKET").strip().upper() or "MARKET",
            product=(product or "CNC").strip().upper() or "CNC",
            gtt=False,
            synthetic_gtt=False,
            status="WAITING",
            mode="MANUAL",
            execution_target=(execution_target or "LIVE").strip().upper() or "LIVE",
            risk_spec_json=None,
            is_exit=False,
        )
        db.add(o)
        created_orders.append(o)

    db.flush()
    return portfolio, copied_members, created_orders


__all__ = ["create_portfolio_from_basket"]
