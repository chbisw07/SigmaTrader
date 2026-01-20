from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import floor

from sqlalchemy.orm import Session

from app.models import Order, Position, PositionSnapshot
from app.schemas.risk_policy import (
    OrderSourceBucket,
    ProductOverrides,
    ProductType,
    RiskPolicy,
)
from app.services.market_data import load_series


@dataclass
class RiskPolicyDecision:
    blocked: bool
    clamped: bool
    reason: str | None
    original_qty: float
    final_qty: float
    effective_price: float | None
    source_bucket: OrderSourceBucket


def _bucket_for_order(order: Order) -> OrderSourceBucket:
    if order.alert is not None:
        src = (getattr(order.alert, "source", None) or "").strip().upper()
        if src == "TRADINGVIEW":
            return "TRADINGVIEW"
    return "SIGMATRADER"


def _normalize_product(product: str | None) -> ProductType:
    p = (product or "").strip().upper()
    return "MIS" if p == "MIS" else "CNC"


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
    side = (order.side or "").strip().upper()
    if side != "SELL":
        return False

    product = (getattr(order, "product", None) or "MIS").strip().upper()
    if product == "CNC":
        return False

    qty = float(order.qty or 0.0)
    if qty <= 0:
        return False

    pos_qty = _position_qty_for_order(db, order)
    return (pos_qty - qty) < 0.0


def _count_entries_today(
    db: Session,
    *,
    broker_name: str,
    symbol: str,
    exchange: str,
    product: str,
    side: str,
) -> int:
    start_day, end_day = _day_bounds_ist(datetime.now(UTC))
    try:
        count = (
            db.query(Order)
            .filter(
                Order.broker_name == broker_name,
                Order.symbol == symbol,
                Order.exchange == exchange,
                Order.product == product,
                Order.side == side,
                Order.is_exit.is_(False),
                Order.status.in_(["EXECUTED", "PARTIALLY_EXECUTED"]),
                Order.created_at >= start_day,
                Order.created_at < end_day,
            )
            .count()
        )
        return int(count or 0)
    except Exception:
        return 0


def _as_of_date_ist(now_utc: datetime):
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        return now_utc.date()


def _day_bounds_ist(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for the current IST trading day."""

    try:
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        d = now_utc.astimezone(ist).date()
        start_ist = datetime(d.year, d.month, d.day, tzinfo=ist)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(UTC), end_ist.astimezone(UTC)
    except Exception:
        start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)


def _resolve_price_for_checks(
    db: Session,
    settings,
    *,
    order: Order,
) -> float | None:
    if order.price is not None and float(order.price) > 0:
        return float(order.price)

    # Best-effort fallback from DB candles (no network fetch).
    symbol = order.symbol
    exchange = order.exchange or "NSE"
    if ":" in symbol:
        ex, ts = symbol.split(":", 1)
        if ex:
            exchange = ex
        symbol = ts
    now = datetime.now(UTC)
    start = now - timedelta(days=30)
    end = now
    try:
        candles = load_series(
            db,
            settings,
            symbol=symbol,
            exchange=(exchange or "NSE").strip().upper(),
            timeframe="1d",
            start=start,
            end=end,
            allow_fetch=False,
        )
        if candles:
            last = candles[-1]
            close = float(last.get("close") or 0.0)
            if close > 0:
                return close
    except Exception:
        return None
    return None


def _atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
) -> float | None:
    if period <= 1:
        return None
    n = min(len(closes), len(highs), len(lows))
    if n < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(float(tr))
    if len(trs) < period:
        return None
    # Wilder ATR
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


def _stop_distance_for_order(
    db: Session,
    settings,
    *,
    order: Order,
    price: float,
    policy: RiskPolicy,
) -> tuple[float | None, str | None]:
    sr = policy.stop_rules
    tr = policy.trade_risk

    min_abs = float(price) * float(sr.min_stop_distance_pct) / 100.0
    max_abs = float(price) * float(sr.max_stop_distance_pct) / 100.0

    if tr.stop_reference == "FIXED_PCT":
        dist = float(price) * float(sr.fallback_stop_pct) / 100.0
        dist = max(min_abs, min(dist, max_abs))
        return float(dist), "fixed_pct"

    # ATR reference.
    symbol = order.symbol
    exchange = order.exchange or "NSE"
    if ":" in symbol:
        ex, ts = symbol.split(":", 1)
        if ex:
            exchange = ex
        symbol = ts
    now = datetime.now(UTC)
    start = now - timedelta(days=60)
    end = now
    try:
        candles = load_series(
            db,
            settings,
            symbol=symbol,
            exchange=(exchange or "NSE").strip().upper(),
            timeframe="1d",
            start=start,
            end=end,
            allow_fetch=False,
        )
    except Exception:
        candles = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for c in candles or []:
        try:
            h = float(c.get("high") or 0.0)
            lo = float(c.get("low") or 0.0)
            cl = float(c.get("close") or 0.0)
        except Exception:
            continue
        if h <= 0 or lo <= 0 or cl <= 0:
            continue
        highs.append(h)
        lows.append(lo)
        closes.append(cl)

    atr_val = _atr(highs, lows, closes, int(sr.atr_period))
    if atr_val is None or atr_val <= 0:
        if not tr.stop_loss_mandatory:
            return None, "atr_unavailable"
        # Fallback to configured fixed stop %.
        dist = float(price) * float(sr.fallback_stop_pct) / 100.0
        dist = max(min_abs, min(dist, max_abs))
        return float(dist), "fallback_fixed_pct"

    dist = float(atr_val) * float(sr.initial_stop_atr)
    dist = max(min_abs, min(dist, max_abs))
    return float(dist), "atr"


def evaluate_execution_risk_policy(
    db: Session,
    settings,
    *,
    order: Order,
    policy: RiskPolicy,
) -> RiskPolicyDecision:
    if bool(getattr(order, "is_exit", False)):
        original_qty = float(order.qty or 0.0)
        return RiskPolicyDecision(
            blocked=False,
            clamped=False,
            reason=None,
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=_resolve_price_for_checks(db, settings, order=order),
            source_bucket=_bucket_for_order(order),
        )
    original_qty = float(order.qty or 0.0)
    current_qty = float(order.qty or 0.0)
    reasons: list[str] = []

    source_bucket = _bucket_for_order(order)
    product = _normalize_product(order.product)

    if policy.emergency_controls.panic_stop:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason="panic_stop is enabled in risk policy.",
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    equity = float(policy.equity.manual_equity_inr or 0.0)
    if equity <= 0:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason="manual_equity_inr must be set (> 0) to enforce risk policy.",
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    # Account-level: daily loss guardrail (best-effort).
    max_daily_abs = policy.account_risk.max_daily_loss_abs
    if max_daily_abs is None:
        pct = float(policy.account_risk.max_daily_loss_pct or 0.0)
        if pct > 0:
            max_daily_abs = equity * pct / 100.0
    if max_daily_abs is not None and float(max_daily_abs) > 0:
        broker_name = (getattr(order, "broker_name", None) or "zerodha").strip().lower()
        today = _as_of_date_ist(datetime.now(UTC))
        total_pnl: float | None = None
        try:
            snaps = (
                db.query(PositionSnapshot)
                .filter(
                    PositionSnapshot.broker_name == broker_name,
                    PositionSnapshot.as_of_date == today,
                )
                .all()
            )
            if snaps:
                total_pnl = sum(float(getattr(s, "pnl", 0.0) or 0.0) for s in snaps)
        except Exception:
            total_pnl = None
        if total_pnl is None:
            try:
                pos_rows = (
                    db.query(Position).filter(Position.broker_name == broker_name).all()
                )
                if pos_rows:
                    total_pnl = sum(
                        float(getattr(p, "pnl", 0.0) or 0.0) for p in pos_rows
                    )
            except Exception:
                total_pnl = None
        if total_pnl is not None and float(total_pnl) <= -float(max_daily_abs):
            return RiskPolicyDecision(
                blocked=True,
                clamped=False,
                reason=(
                    f"max_daily_loss reached (pnl={total_pnl:.2f}, "
                    f"limit={float(max_daily_abs):.2f})."
                ),
                original_qty=original_qty,
                final_qty=original_qty,
                effective_price=None,
                source_bucket=source_bucket,
            )

    # Effective per-product overrides (source bucket + product).
    ovr: ProductOverrides = policy.product_overrides(
        source=source_bucket, product=product
    )
    allow = ovr.allow
    if allow is None:
        allow = (
            policy.execution_safety.allow_mis
            if product == "MIS"
            else policy.execution_safety.allow_cnc
        )
    if not allow:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=f"{product} is disabled for {source_bucket} orders by risk policy.",
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    if current_qty <= 0:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason="Order has invalid quantity.",
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    if not policy.execution_safety.allow_short_selling and _would_open_or_increase_short(
        db, order
    ):
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason="Short selling is disabled by risk policy.",
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    effective_price = _resolve_price_for_checks(db, settings, order=order)
    if effective_price is None or effective_price <= 0:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=(
                "Price is required for risk checks "
                "(set a limit price or hydrate candles)."
            ),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    # Account-level: max open positions / concurrent symbols / exposure (best-effort).
    try:
        positions = db.query(Position).filter(Position.qty != 0).all()
    except Exception:
        positions = []
    open_positions = [
        p for p in positions if float(getattr(p, "qty", 0.0) or 0.0) != 0.0
    ]

    # Position sizing: scale-in and pyramiding controls (best-effort).
    try:
        broker = (getattr(order, "broker_name", None) or "zerodha").strip().lower()
        sym, exch = _normalized_symbol_exchange(order)
        prod = (getattr(order, "product", None) or "MIS").strip().upper()
        side = (order.side or "").strip().upper()
        pos = next(
            (
                p
                for p in open_positions
                if (p.broker_name or "").strip().lower() == broker
                and (p.symbol or "").strip().upper() == sym
                and (p.exchange or "").strip().upper() == exch
                and (p.product or "").strip().upper() == prod
            ),
            None,
        )
        if pos is not None:
            pos_qty = float(getattr(pos, "qty", 0.0) or 0.0)
            is_scale_in = (side == "BUY" and pos_qty > 0) or (
                side == "SELL" and pos_qty < 0
            )
            if is_scale_in:
                if not bool(policy.position_sizing.allow_scale_in):
                    return RiskPolicyDecision(
                        blocked=True,
                        clamped=False,
                        reason="Scale-in is disabled by risk policy.",
                        original_qty=original_qty,
                        final_qty=original_qty,
                        effective_price=effective_price,
                        source_bucket=source_bucket,
                    )

                pyramiding = int(getattr(policy.position_sizing, "pyramiding", 1) or 1)
                if pyramiding < 1:
                    pyramiding = 1
                entries = _count_entries_today(
                    db,
                    broker_name=broker,
                    symbol=sym,
                    exchange=exch,
                    product=prod,
                    side=side,
                )
                if entries == 0:
                    entries = 1
                if entries >= pyramiding:
                    return RiskPolicyDecision(
                        blocked=True,
                        clamped=False,
                        reason=(
                            f"Pyramiding limit reached ({entries}/{pyramiding})."
                        ),
                        original_qty=original_qty,
                        final_qty=original_qty,
                        effective_price=effective_price,
                        source_bucket=source_bucket,
                    )
    except Exception:
        pass
    if policy.account_risk.max_open_positions >= 0 and len(open_positions) >= int(
        policy.account_risk.max_open_positions
    ):
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=(
                f"max_open_positions={policy.account_risk.max_open_positions} reached."
            ),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=effective_price,
            source_bucket=source_bucket,
        )
    symbols = {
        str(p.symbol).strip().upper()
        for p in open_positions
        if getattr(p, "symbol", None)
    }
    max_concurrent = int(policy.account_risk.max_concurrent_symbols)
    if max_concurrent >= 0 and len(symbols) >= max_concurrent:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=("max_concurrent_symbols=" f"{max_concurrent} reached."),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=effective_price,
            source_bucket=source_bucket,
        )
    try:
        exposure = 0.0
        for p in open_positions:
            exposure += abs(float(p.qty) * float(p.avg_price))
        max_exposure = equity * float(policy.account_risk.max_exposure_pct) / 100.0
        if max_exposure > 0:
            # Conservative: buys increase exposure; sells do not increase exposure.
            inc = (
                float(current_qty) * float(effective_price)
                if order.side.upper() == "BUY"
                else 0.0
            )
            if exposure + inc > max_exposure:
                return RiskPolicyDecision(
                    blocked=True,
                    clamped=False,
                    reason=(
                        "max_exposure_pct="
                        f"{policy.account_risk.max_exposure_pct}% exceeded."
                    ),
                    original_qty=original_qty,
                    final_qty=original_qty,
                    effective_price=effective_price,
                    source_bucket=source_bucket,
                )
    except Exception:
        pass

    # NOTE: Trade-frequency and loss-control enforcement is handled at the
    # execution choke-point using persisted execution state so it remains
    # restart-safe and scoped by (user, strategy/deployment, symbol, product).

    # 1) Max quantity per order.
    max_qty = ovr.max_quantity_per_order
    if max_qty is not None and max_qty > 0 and abs(current_qty) > float(max_qty):
        new_qty = float(floor(float(max_qty)))
        if new_qty < 1:
            return RiskPolicyDecision(
                blocked=True,
                clamped=False,
                reason="max_quantity_per_order results in qty < 1; rejected.",
                original_qty=original_qty,
                final_qty=original_qty,
                effective_price=effective_price,
                source_bucket=source_bucket,
            )
        reasons.append(f"qty clamped to max_quantity_per_order={max_qty}.")
        current_qty = new_qty

    # 2) Max order value (absolute, percent, and fixed capital per trade).
    max_value_abs = ovr.max_order_value_abs
    cap_trade = (
        ovr.capital_per_trade
        if ovr.capital_per_trade is not None
        else policy.position_sizing.capital_per_trade
    )
    if cap_trade and cap_trade > 0:
        max_value_abs = min(
            float(max_value_abs) if max_value_abs else float("inf"), float(cap_trade)
        )
    max_value_pct = equity * float(policy.execution_safety.max_order_value_pct) / 100.0
    max_value = min(
        max_value_abs if max_value_abs is not None else float("inf"),
        float(max_value_pct) if max_value_pct > 0 else float("inf"),
    )
    if max_value != float("inf"):
        value = float(current_qty) * float(effective_price)
        if value > max_value and effective_price > 0:
            new_qty = floor(float(max_value) / float(effective_price))
            if new_qty < 1:
                return RiskPolicyDecision(
                    blocked=True,
                    clamped=False,
                    reason="Order value cap results in qty < 1; rejected.",
                    original_qty=original_qty,
                    final_qty=original_qty,
                    effective_price=effective_price,
                    source_bucket=source_bucket,
                )
            reasons.append(f"qty clamped by order value cap ({max_value:.2f}).")
            current_qty = float(new_qty)

    # 3) Per-trade risk cap based on stop distance.
    max_risk_pct = (
        float(ovr.max_risk_per_trade_pct)
        if ovr.max_risk_per_trade_pct is not None
        else float(policy.trade_risk.max_risk_per_trade_pct)
    )
    hard_risk_pct = (
        float(ovr.hard_max_risk_pct)
        if ovr.hard_max_risk_pct is not None
        else float(policy.trade_risk.hard_max_risk_pct)
    )
    max_risk_money = equity * max_risk_pct / 100.0
    hard_risk_money = equity * hard_risk_pct / 100.0

    stop_dist, stop_src = _stop_distance_for_order(
        db,
        settings,
        order=order,
        price=effective_price,
        policy=policy,
    )
    if stop_dist is None or stop_dist <= 0:
        if policy.trade_risk.stop_loss_mandatory:
            return RiskPolicyDecision(
                blocked=True,
                clamped=False,
                reason="Stop distance unavailable; stop_loss_mandatory is enabled.",
                original_qty=original_qty,
                final_qty=original_qty,
                effective_price=effective_price,
                source_bucket=source_bucket,
            )
    else:
        risk_money = float(current_qty) * float(stop_dist)
        if hard_risk_money > 0 and risk_money > hard_risk_money:
            allowed = floor(float(hard_risk_money) / float(stop_dist))
            if allowed < 1:
                return RiskPolicyDecision(
                    blocked=True,
                    clamped=False,
                    reason="hard_max_risk cap results in qty < 1; rejected.",
                    original_qty=original_qty,
                    final_qty=original_qty,
                    effective_price=effective_price,
                    source_bucket=source_bucket,
                )
            reasons.append(
                f"qty clamped by hard_max_risk_pct={hard_risk_pct}% (stop={stop_src})."
            )
            current_qty = float(allowed)
            risk_money = float(current_qty) * float(stop_dist)
        if max_risk_money > 0 and risk_money > max_risk_money:
            allowed = floor(float(max_risk_money) / float(stop_dist))
            if allowed < 1:
                return RiskPolicyDecision(
                    blocked=True,
                    clamped=False,
                    reason="max_risk_per_trade cap results in qty < 1; rejected.",
                    original_qty=original_qty,
                    final_qty=original_qty,
                    effective_price=effective_price,
                    source_bucket=source_bucket,
                )
            reasons.append(
                f"qty clamped by max_risk_per_trade_pct={max_risk_pct}% "
                f"(stop={stop_src})."
            )
            current_qty = float(allowed)

    # Align with broker execution behavior: quantities are submitted as integers.
    current_qty = float(floor(float(current_qty)))
    if current_qty < 1:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason="Final qty < 1 after integer rounding; rejected.",
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=effective_price,
            source_bucket=source_bucket,
        )

    clamped = float(current_qty) != float(original_qty)
    reason = "; ".join(reasons) if reasons else None
    return RiskPolicyDecision(
        blocked=False,
        clamped=clamped,
        reason=reason,
        original_qty=original_qty,
        final_qty=float(current_qty),
        effective_price=float(effective_price),
        source_bucket=source_bucket,
    )


__all__ = ["RiskPolicyDecision", "evaluate_execution_risk_policy"]
