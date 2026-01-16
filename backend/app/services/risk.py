from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Order, Position, RiskSettings


@dataclass
class RiskResult:
    """Outcome of applying risk settings to an order."""

    blocked: bool
    clamped: bool
    reason: Optional[str]
    original_qty: float
    final_qty: float


def _describe_scope(settings: RiskSettings) -> str:
    if settings.scope == "GLOBAL":
        return "GLOBAL"
    if settings.scope == "STRATEGY" and settings.strategy_id is not None:
        return f"STRATEGY({settings.strategy_id})"
    return settings.scope


def _normalized_symbol_exchange(order: Order) -> tuple[str, str]:
    symbol_raw = (order.symbol or "").strip()
    exchange = (getattr(order, "exchange", None) or "NSE").strip().upper() or "NSE"
    symbol = symbol_raw
    if ":" in symbol_raw:
        ex, sym = symbol_raw.split(":", 1)
        if ex.strip():
            exchange = ex.strip().upper()
        symbol = sym
    return symbol.strip().upper(), exchange


def _position_qty_for_order(db: Session, order: Order) -> float:
    broker = (getattr(order, "broker_name", None) or "zerodha").strip().lower()
    product = (getattr(order, "product", None) or "MIS").strip().upper()
    symbol, exchange = _normalized_symbol_exchange(order)
    pos = (
        db.query(Position)
        .filter(
            Position.broker_name == broker,
            Position.symbol == symbol,
            Position.exchange == exchange,
            Position.product == product,
        )
        .one_or_none()
    )
    return float(pos.qty) if pos is not None else 0.0


def _would_open_or_increase_short(db: Session, order: Order) -> bool:
    """Return True if this order would create/increase a short position.

    This is best-effort and relies on the cached `positions` table.
    """

    side = (order.side or "").strip().upper()
    if side != "SELL":
        return False

    product = (getattr(order, "product", None) or "MIS").strip().upper()
    # CNC short selling isn't supported by the broker, so do not block SELL
    # here. Oversell/no-holdings will be rejected by the broker anyway.
    if product == "CNC":
        return False

    qty = float(order.qty or 0.0)
    if qty <= 0:
        return False

    pos_qty = _position_qty_for_order(db, order)
    # SELL reduces long qty; if we'd go negative, that's a short sell.
    return (pos_qty - qty) < 0.0


def evaluate_order_risk(db: Session, order: Order) -> RiskResult:
    """Evaluate basic risk rules for an order.

    This uses the v1 RiskSettings fields:
    - max_quantity_per_order
    - max_order_value
    - allow_short_selling

    The daily loss limit is deliberately not enforced yet; it will be wired
    in when we start tracking realized PnL in later sprints.
    """

    original_qty = float(order.qty or 0.0)
    current_qty = original_qty
    reasons: List[str] = []

    # Managed exit orders should not be blocked/clamped by the entry risk rules.
    if bool(getattr(order, "is_exit", False)):
        return RiskResult(
            blocked=False,
            clamped=False,
            reason=None,
            original_qty=original_qty,
            final_qty=original_qty,
        )

    # No risk rows defined → accept as-is.
    settings_rows: List[RiskSettings] = list(
        db.query(RiskSettings).order_by(RiskSettings.scope, RiskSettings.id).all()
    )
    if not settings_rows:
        return RiskResult(
            blocked=False,
            clamped=False,
            reason=None,
            original_qty=original_qty,
            final_qty=original_qty,
        )

    # Prefer GLOBAL rows only. Strategy-scoped rows exist in the DB schema for
    # legacy/experimental use, but the current product surface configures risk
    # globally (including TradingView webhook orders).
    global_settings: List[RiskSettings] = [
        rs for rs in settings_rows if rs.scope == "GLOBAL"
    ]
    ordered_settings: List[RiskSettings] = []
    ordered_settings.extend(global_settings)

    # Helper to emit a blocked result.
    def _blocked(reason: str) -> RiskResult:
        reasons.append(reason)
        return RiskResult(
            blocked=True,
            clamped=False,
            reason="; ".join(reasons),
            original_qty=original_qty,
            final_qty=original_qty,
        )

    for rs in ordered_settings:
        scope_desc = _describe_scope(rs)

        # If short selling is disabled, block only orders that would open or
        # increase a short position (not normal SELL exits).
        if rs.allow_short_selling is False and _would_open_or_increase_short(db, order):
            return _blocked(f"Short selling is disabled in {scope_desc} risk settings.")

        # max_quantity_per_order
        if rs.max_quantity_per_order is not None and current_qty:
            max_qty = float(rs.max_quantity_per_order)
            if abs(current_qty) > max_qty:
                if rs.clamp_mode == "CLAMP":
                    new_qty = max_qty if current_qty > 0 else -max_qty
                    reasons.append(
                        f"Quantity clamped from {current_qty} to {new_qty} due to "
                        f"max_quantity_per_order={max_qty} in {scope_desc}."
                    )
                    current_qty = new_qty
                else:
                    msg = (
                        f"Quantity {current_qty} exceeds "
                        f"max_quantity_per_order={max_qty} in {scope_desc}."
                    )
                    return _blocked(msg)

        # max_order_value
        if rs.max_order_value is not None and order.price is not None and current_qty:
            limit_value = float(rs.max_order_value)
            value = abs(current_qty * float(order.price))
            if value > limit_value:
                if rs.clamp_mode == "CLAMP":
                    # Compute the maximum allowable quantity for this price and
                    # clamp to an integer number of units (Zerodha does not
                    # allow fractional quantities).
                    max_abs_qty = limit_value / float(order.price)
                    # Respect the current quantity but do not exceed the
                    # allowed maximum.
                    candidate = min(abs(current_qty), max_abs_qty)
                    new_abs_qty = floor(candidate)
                    if new_abs_qty < 1:
                        msg = (
                            "Order value "
                            f"{value:.2f} exceeds max_order_value={limit_value:.2f} "
                            f"in {scope_desc} and cannot be clamped "
                            "to at least 1 whole unit."
                        )
                        return _blocked(msg)
                    new_qty = new_abs_qty if current_qty > 0 else -new_abs_qty
                    reasons.append(
                        f"Quantity clamped from {current_qty} to {new_qty} due to "
                        f"max_order_value={limit_value:.2f} in {scope_desc}."
                    )
                    current_qty = new_qty
                else:
                    msg = (
                        "Order value "
                        f"{value:.2f} exceeds max_order_value={limit_value:.2f} "
                        f"in {scope_desc}."
                    )
                    return _blocked(msg)

        # max_daily_loss is intentionally not enforced yet; will be implemented
        # once realized PnL is tracked (S07+).

    clamped = current_qty != original_qty
    reason: Optional[str]
    if reasons:
        reason = "; ".join(reasons)
    else:
        reason = None

    return RiskResult(
        blocked=False,
        clamped=clamped,
        reason=reason,
        original_qty=original_qty,
        final_qty=current_qty,
    )


__all__ = ["RiskResult", "evaluate_order_risk"]
