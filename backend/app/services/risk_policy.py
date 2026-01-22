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
from app.services.risk_policy_enforcement import is_group_enforced


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


def _is_structural_exit(db: Session, order: Order) -> bool:
    """Return True if the order reduces absolute open position quantity."""

    if bool(getattr(order, "is_exit", False)):
        return True
    try:
        qty = float(order.qty or 0.0)
        if qty <= 0:
            return False
        side = (order.side or "").strip().upper()
        if side not in {"BUY", "SELL"}:
            return False
        pos_qty = float(_position_qty_for_order(db, order))
        delta = qty if side == "BUY" else -qty
        return abs(pos_qty + delta) < abs(pos_qty)
    except Exception:
        return False


def _group_reason(group: str, msg: str) -> str:
    return f"{group}: {msg}"


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
    source_bucket = _bucket_for_order(order)
    if _is_structural_exit(db, order):
        original_qty = float(order.qty or 0.0)
        return RiskPolicyDecision(
            blocked=False,
            clamped=False,
            reason=None,
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=_resolve_price_for_checks(db, settings, order=order),
            source_bucket=source_bucket,
        )
    original_qty = float(order.qty or 0.0)
    current_qty = float(order.qty or 0.0)
    reasons: list[str] = []

    product = _normalize_product(order.product)

    em_on = is_group_enforced(policy, "emergency_controls")
    acct_on = is_group_enforced(policy, "account_level")
    exec_on = is_group_enforced(policy, "execution_safety")
    pos_on = is_group_enforced(policy, "position_sizing")
    per_on = is_group_enforced(policy, "per_trade")
    stop_on = is_group_enforced(policy, "stop_rules")
    ovr_on = is_group_enforced(policy, "overrides")

    if not any([em_on, acct_on, exec_on, pos_on, per_on, stop_on]):
        return RiskPolicyDecision(
            blocked=False,
            clamped=False,
            reason=None,
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=_resolve_price_for_checks(db, settings, order=order),
            source_bucket=source_bucket,
        )

    if em_on and policy.emergency_controls.panic_stop:
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=_group_reason("emergency_controls", "panic_stop is enabled."),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    equity_needed_by: list[str] = []
    if acct_on and policy.account_risk.max_daily_loss_abs is None and float(
        policy.account_risk.max_daily_loss_pct or 0.0
    ) > 0:
        equity_needed_by.append("account_level")
    if acct_on and float(policy.account_risk.max_exposure_pct or 0.0) > 0:
        equity_needed_by.append("account_level")
    if exec_on and float(policy.execution_safety.max_order_value_pct or 0.0) > 0:
        equity_needed_by.append("execution_safety")
    if per_on and (
        float(policy.trade_risk.max_risk_per_trade_pct or 0.0) > 0
        or float(policy.trade_risk.hard_max_risk_pct or 0.0) > 0
    ):
        equity_needed_by.append("per_trade")

    equity = float(policy.equity.manual_equity_inr or 0.0)
    if equity_needed_by and equity <= 0:
        groups = ", ".join(sorted(set(equity_needed_by)))
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=_group_reason(
                groups,
                "manual_equity_inr must be set (> 0) to enforce enabled groups.",
            ),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    if acct_on:
        # Account-level: daily loss guardrail (best-effort).
        max_daily_abs = policy.account_risk.max_daily_loss_abs
        if max_daily_abs is None:
            pct = float(policy.account_risk.max_daily_loss_pct or 0.0)
            if pct > 0 and equity > 0:
                max_daily_abs = equity * pct / 100.0
        if max_daily_abs is not None and float(max_daily_abs) > 0:
            broker_name = (
                (getattr(order, "broker_name", None) or "zerodha")
                .strip()
                .lower()
            )
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
                    total_pnl = sum(
                        float(getattr(s, "pnl", 0.0) or 0.0) for s in snaps
                    )
            except Exception:
                total_pnl = None
            if total_pnl is None:
                try:
                    pos_rows = (
                        db.query(Position)
                        .filter(Position.broker_name == broker_name)
                        .all()
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
                    reason=_group_reason(
                        "account_level",
                        (
                            f"max_daily_loss reached (pnl={total_pnl:.2f}, "
                            f"limit={float(max_daily_abs):.2f})."
                        ),
                    ),
                    original_qty=original_qty,
                    final_qty=original_qty,
                    effective_price=None,
                    source_bucket=source_bucket,
                )

    # Effective per-product overrides (source bucket + product).
    ovr: ProductOverrides = (
        policy.product_overrides(source=source_bucket, product=product)
        if ovr_on
        else ProductOverrides()
    )

    if exec_on:
        allow = ovr.allow if ovr_on else None
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
                reason=_group_reason(
                    "execution_safety",
                    f"{product} is disabled for {source_bucket} orders.",
                ),
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

    if (
        exec_on
        and (not policy.execution_safety.allow_short_selling)
        and _would_open_or_increase_short(db, order)
    ):
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=_group_reason("execution_safety", "Short selling is disabled."),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    price_needed_by: list[str] = []
    if acct_on and float(policy.account_risk.max_exposure_pct or 0.0) > 0:
        price_needed_by.append("account_level")
    if exec_on and (
        float(policy.execution_safety.max_order_value_pct or 0.0) > 0
        or (
            ovr_on
            and (
                ovr.max_order_value_abs is not None
                and float(ovr.max_order_value_abs) > 0
            )
        )
    ):
        price_needed_by.append("execution_safety")
    if pos_on and (
        float(policy.position_sizing.capital_per_trade or 0.0) > 0
        or (
            ovr_on
            and (
                ovr.capital_per_trade is not None
                and float(ovr.capital_per_trade) > 0
            )
        )
    ):
        price_needed_by.append("position_sizing")
    if per_on and stop_on and (
        float(policy.trade_risk.max_risk_per_trade_pct or 0.0) > 0
        or float(policy.trade_risk.hard_max_risk_pct or 0.0) > 0
        or bool(policy.trade_risk.stop_loss_mandatory)
    ):
        price_needed_by.append("per_trade")

    effective_price = _resolve_price_for_checks(db, settings, order=order)
    if price_needed_by and (effective_price is None or effective_price <= 0):
        groups = ", ".join(sorted(set(price_needed_by)))
        return RiskPolicyDecision(
            blocked=True,
            clamped=False,
            reason=_group_reason(
                groups,
                (
                    "Price is required for enabled risk checks (set a limit price "
                    "or hydrate candles)."
                ),
            ),
            original_qty=original_qty,
            final_qty=original_qty,
            effective_price=None,
            source_bucket=source_bucket,
        )

    open_positions: list[Position] = []
    if acct_on or pos_on:
        # Account-level: max open positions / concurrent symbols / exposure
        # (best-effort).
        try:
            positions = db.query(Position).filter(Position.qty != 0).all()
        except Exception:
            positions = []
        open_positions = [
            p for p in positions if float(getattr(p, "qty", 0.0) or 0.0) != 0.0
        ]

    if pos_on:
        # Position sizing: scale-in and pyramiding controls (best-effort).
        try:
            broker = (
                (getattr(order, "broker_name", None) or "zerodha")
                .strip()
                .lower()
            )
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
                            reason=_group_reason(
                                "position_sizing", "Scale-in is disabled."
                            ),
                            original_qty=original_qty,
                            final_qty=original_qty,
                            effective_price=effective_price,
                            source_bucket=source_bucket,
                        )

                    pyramiding = int(
                        getattr(policy.position_sizing, "pyramiding", 1) or 1
                    )
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
                            reason=_group_reason(
                                "position_sizing",
                                f"Pyramiding limit reached ({entries}/{pyramiding}).",
                            ),
                            original_qty=original_qty,
                            final_qty=original_qty,
                            effective_price=effective_price,
                            source_bucket=source_bucket,
                        )
        except Exception:
            pass
    if acct_on:
        if policy.account_risk.max_open_positions >= 0 and len(open_positions) >= int(
            policy.account_risk.max_open_positions
        ):
            return RiskPolicyDecision(
                blocked=True,
                clamped=False,
                reason=_group_reason(
                    "account_level",
                    (
                        "max_open_positions="
                        f"{policy.account_risk.max_open_positions} reached."
                    ),
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
                reason=_group_reason(
                    "account_level", f"max_concurrent_symbols={max_concurrent} reached."
                ),
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
                    if (effective_price or 0) > 0 and order.side.upper() == "BUY"
                    else 0.0
                )
                if exposure + inc > max_exposure:
                    return RiskPolicyDecision(
                        blocked=True,
                        clamped=False,
                        reason=_group_reason(
                            "account_level",
                            (
                                "max_exposure_pct="
                                f"{policy.account_risk.max_exposure_pct}% exceeded."
                            ),
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
    if exec_on:
        max_qty = ovr.max_quantity_per_order
        if max_qty is not None and max_qty > 0 and abs(current_qty) > float(max_qty):
            new_qty = float(floor(float(max_qty)))
            if new_qty < 1:
                return RiskPolicyDecision(
                    blocked=True,
                    clamped=False,
                    reason=_group_reason(
                        "execution_safety",
                        "max_quantity_per_order results in qty < 1; rejected.",
                    ),
                    original_qty=original_qty,
                    final_qty=original_qty,
                    effective_price=effective_price,
                    source_bucket=source_bucket,
                )
            reasons.append(
                _group_reason(
                    "execution_safety",
                    f"qty clamped to max_quantity_per_order={max_qty}.",
                )
            )
            current_qty = new_qty

    # 2) Max order value (absolute, percent, and fixed capital per trade).
    if (exec_on or pos_on) and (effective_price or 0) > 0:
        caps: list[tuple[float, str]] = []

        if (
            exec_on
            and ovr.max_order_value_abs is not None
            and float(ovr.max_order_value_abs) > 0
        ):
            caps.append((float(ovr.max_order_value_abs), "execution_safety"))

        if exec_on and equity > 0:
            max_value_pct = (
                equity * float(policy.execution_safety.max_order_value_pct) / 100.0
            )
            if max_value_pct > 0:
                caps.append((float(max_value_pct), "execution_safety"))

        if pos_on:
            cap_trade = (
                float(ovr.capital_per_trade)
                if ovr.capital_per_trade is not None
                else float(policy.position_sizing.capital_per_trade)
            )
            if cap_trade > 0:
                caps.append((float(cap_trade), "position_sizing"))

        if caps:
            max_value, max_group = min(caps, key=lambda x: x[0])
            value = float(current_qty) * float(effective_price)
            if value > float(max_value) and effective_price > 0:
                new_qty = floor(float(max_value) / float(effective_price))
                if new_qty < 1:
                    return RiskPolicyDecision(
                        blocked=True,
                        clamped=False,
                        reason=_group_reason(
                            max_group,
                            "Order value cap results in qty < 1; rejected.",
                        ),
                        original_qty=original_qty,
                        final_qty=original_qty,
                        effective_price=effective_price,
                        source_bucket=source_bucket,
                    )
                reasons.append(
                    _group_reason(
                        max_group,
                        f"qty clamped by order value cap ({float(max_value):.2f}).",
                    )
                )
                current_qty = float(new_qty)

    # 3) Per-trade risk cap based on stop distance.
    if per_on and stop_on and (effective_price or 0) > 0 and equity > 0:
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
            price=float(effective_price),
            policy=policy,
        )
        if stop_dist is None or stop_dist <= 0:
            if bool(policy.trade_risk.stop_loss_mandatory):
                return RiskPolicyDecision(
                    blocked=True,
                    clamped=False,
                    reason=_group_reason(
                        "per_trade",
                        "Stop distance unavailable; stop_loss_mandatory is enabled.",
                    ),
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
                        reason=_group_reason(
                            "per_trade",
                            "hard_max_risk cap results in qty < 1; rejected.",
                        ),
                        original_qty=original_qty,
                        final_qty=original_qty,
                        effective_price=effective_price,
                        source_bucket=source_bucket,
                    )
                reasons.append(
                    _group_reason(
                        "per_trade",
                        (
                            "qty clamped by hard_max_risk_pct="
                            f"{hard_risk_pct}% (stop={stop_src})."
                        ),
                    )
                )
                current_qty = float(allowed)
                risk_money = float(current_qty) * float(stop_dist)
            if max_risk_money > 0 and risk_money > max_risk_money:
                allowed = floor(float(max_risk_money) / float(stop_dist))
                if allowed < 1:
                    return RiskPolicyDecision(
                        blocked=True,
                        clamped=False,
                        reason=_group_reason(
                            "per_trade",
                            "max_risk_per_trade cap results in qty < 1; rejected.",
                        ),
                        original_qty=original_qty,
                        final_qty=original_qty,
                        effective_price=effective_price,
                        source_bucket=source_bucket,
                    )
                reasons.append(
                    _group_reason(
                        "per_trade",
                        (
                            "qty clamped by max_risk_per_trade_pct="
                            f"{max_risk_pct}% (stop={stop_src})."
                        ),
                    )
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
