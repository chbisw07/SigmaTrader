from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import floor
from typing import Any, Literal, Optional, cast

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertDecisionLog,
    AnalyticsTrade,
    DrawdownThreshold,
    EquitySnapshot,
    Order,
    Position,
    RiskProfile,
    SymbolRiskCategory,
    User,
)
from app.services.risk_compiler import (
    apply_drawdown_throttle_v2 as _apply_drawdown_throttle_v2,
    compute_portfolio_pnl_state as _compute_portfolio_pnl_state,
    drawdown_state as _drawdown_state,
    resolve_drawdown_config as _resolve_drawdown_config,
)
from app.services.risk_policy import _normalized_symbol_exchange  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

DrawdownState = Literal["NORMAL", "CAUTION", "DEFENSE", "HARD_STOP"]

IST_OFFSET = timedelta(hours=5, minutes=30)


def _as_of_date_ist(now_utc: datetime) -> date:
    return (now_utc + IST_OFFSET).date()


def _day_bounds_ist(now_utc: datetime) -> tuple[datetime, datetime]:
    d = _as_of_date_ist(now_utc)
    start_ist = datetime(d.year, d.month, d.day, tzinfo=UTC) - IST_OFFSET
    end_ist = start_ist + timedelta(days=1)
    return start_ist, end_ist


def _parse_hhmm(raw: str | None) -> time | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        hh = int(parts[0])
        mm = int(parts[1])
    except ValueError:
        return None
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return time(hour=hh, minute=mm)


def _now_time_ist(now_utc: datetime) -> time:
    return (now_utc + IST_OFFSET).time()


def _safe_json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


@dataclass(frozen=True)
class PortfolioPnlState:
    baseline_equity: float
    equity: float
    peak_equity: float
    drawdown_pct: float
    pnl_today: float
    consecutive_losses: int


@dataclass(frozen=True)
class DrawdownConfig:
    caution_pct: float
    defense_pct: float
    hard_stop_pct: float


@dataclass(frozen=True)
class RiskDecisionV2:
    blocked: bool
    reasons: list[str]
    resolved_product: str | None
    risk_profile_id: int | None
    risk_category: str | None
    drawdown_state: DrawdownState | None
    drawdown_pct: float | None
    final_qty: float | None
    final_order_type: str | None
    final_price: float | None


def pick_risk_profile(
    db: Session,
    *,
    product_hint: str | None,
) -> RiskProfile | None:
    hint = (product_hint or "").strip().upper()
    product = "MIS" if hint == "MIS" else "CNC" if hint == "CNC" else None
    if product is None:
        # No hint: prefer any enabled default profile (CNC first).
        for p in ("CNC", "MIS"):
            row = (
                db.query(RiskProfile)
                .filter(RiskProfile.enabled.is_(True), RiskProfile.is_default.is_(True), RiskProfile.product == p)
                .one_or_none()
            )
            if row is not None:
                return row
        return (
            db.query(RiskProfile).filter(RiskProfile.enabled.is_(True)).order_by(RiskProfile.product, RiskProfile.id).first()
        )

    row = (
        db.query(RiskProfile)
        .filter(
            RiskProfile.enabled.is_(True),
            RiskProfile.is_default.is_(True),
            RiskProfile.product == product,
        )
        .one_or_none()
    )
    if row is not None:
        return row
    return (
        db.query(RiskProfile)
        .filter(RiskProfile.enabled.is_(True), RiskProfile.product == product)
        .order_by(RiskProfile.id)
        .first()
    )


def resolve_symbol_category(
    db: Session,
    *,
    user_id: int | None,
    broker_name: str,
    symbol: str,
    exchange: str,
) -> str | None:
    sym = symbol.strip().upper()
    ex = exchange.strip().upper() or "NSE"
    broker = (broker_name or "zerodha").strip().lower() or "zerodha"
    # Allow broker/exchange wildcards ("*") so categories can be treated as
    # broker-independent in the UI while still supporting per-broker overrides.
    candidates = (
        db.query(SymbolRiskCategory)
        .filter(
            SymbolRiskCategory.user_id == user_id,
            SymbolRiskCategory.symbol == sym,
            SymbolRiskCategory.broker_name.in_([broker, "*"]),
            SymbolRiskCategory.exchange.in_([ex, "*"]),
        )
        # Prefer the most recently updated mapping (lets "global" overrides win
        # without needing to delete older broker/exchange-specific rows).
        .order_by(SymbolRiskCategory.updated_at.desc())
        .all()
    )
    if not candidates:
        return None
    return candidates[0].risk_category


def resolve_drawdown_config(
    db: Session,
    *,
    product: str,
    category: str,
) -> DrawdownConfig | None:
    # Delegate to shared compiler logic so UI summaries match runtime behavior.
    return cast(
        DrawdownConfig | None,
        _resolve_drawdown_config(
            db,
            product=(str(product or "").strip().upper() or "CNC"),  # type: ignore[arg-type]
            category=(str(category or "").strip().upper() or "LC"),  # type: ignore[arg-type]
        ),
    )


def compute_portfolio_pnl_state(
    db: Session,
    *,
    user_id: int | None,
    baseline_equity: float,
    now_utc: datetime,
) -> PortfolioPnlState:
    return cast(
        PortfolioPnlState,
        _compute_portfolio_pnl_state(
            db,
            user_id=user_id,
            baseline_equity=baseline_equity,
            now_utc=now_utc,
        ),
    )


def drawdown_state(dd_pct: float, cfg: DrawdownConfig) -> DrawdownState:
    return cast(DrawdownState, _drawdown_state(dd_pct, cfg))


def _is_structural_exit(db: Session, order: Order) -> bool:
    if bool(getattr(order, "is_exit", False)):
        return True
    try:
        qty = float(order.qty or 0.0)
        if qty <= 0:
            return False
        side = (order.side or "").strip().upper()
        if side not in {"BUY", "SELL"}:
            return False
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
        pos_qty = float(pos.qty) if pos is not None else 0.0
        delta = qty if side == "BUY" else -qty
        return abs(pos_qty + delta) < abs(pos_qty)
    except Exception:
        return False


def _price_for_sizing(order: Order) -> float | None:
    if order.price is None:
        return None
    p = float(order.price or 0.0)
    return p if p > 0 else None


def _interval_minutes(raw: str | None) -> int | None:
    s = str(raw or "").strip().lower()
    if not s:
        return None
    try:
        if s.endswith("m"):
            return int(s[:-1])
        if s.endswith("h"):
            return int(s[:-1]) * 60
        if s.endswith("d"):
            return int(s[:-1]) * 1440
        if s.isdigit():
            return int(s)
    except Exception:
        return None
    return None


def _apply_drawdown_throttle(
    profile: RiskProfile,
    state: DrawdownState,
    category: str,
) -> tuple[float, int, list[str]]:
    out = _apply_drawdown_throttle_v2(
        profile=profile,
        state=state,
        category=(category or "LC").strip().upper(),  # type: ignore[arg-type]
    )
    return float(out.effective_capital_per_trade), int(out.effective_max_positions), list(out.reasons)


def evaluate_order_risk_v2(
    db: Session,
    *,
    user: User | None,
    order: Order,
    baseline_equity: float,
    now_utc: datetime,
    product_hint: str | None,
) -> RiskDecisionV2:
    reasons: list[str] = []
    is_exit = _is_structural_exit(db, order)

    # Never block structural exits; allow them to proceed even when risk
    # configuration is missing or incomplete.
    if is_exit:
        resolved_product = (getattr(order, "product", None) or "MIS").strip().upper()
        return RiskDecisionV2(
            blocked=False,
            reasons=["Structural exit: bypassing entry risk checks."],
            resolved_product=resolved_product,
            risk_profile_id=None,
            risk_category=None,
            drawdown_state=None,
            drawdown_pct=None,
            final_qty=float(getattr(order, "qty", 0.0) or 0.0) or None,
            final_order_type=(order.order_type or "MARKET").strip().upper(),
            final_price=_price_for_sizing(order),
        )

    profile = pick_risk_profile(db, product_hint=product_hint)
    if profile is None:
        return RiskDecisionV2(
            blocked=True,
            reasons=["Missing RiskProfile (create at least one enabled profile)."],
            resolved_product=None,
            risk_profile_id=None,
            risk_category=None,
            drawdown_state=None,
            drawdown_pct=None,
            final_qty=None,
            final_order_type=None,
            final_price=None,
        )

    resolved_product = (profile.product or "").strip().upper()

    # Order-type policy (optional): comma-separated allowlist (e.g. "MARKET,LIMIT,SL,SL-M").
    otp = str(getattr(profile, "order_type_policy", "") or "").strip()
    if otp:
        allowed = {t.strip().upper() for t in otp.replace(";", ",").split(",") if t.strip()}
        if not allowed:
            return RiskDecisionV2(
                blocked=True,
                reasons=["Invalid order_type_policy configuration (empty allowlist)."],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=None,
                drawdown_state=None,
                drawdown_pct=None,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )
        order_type = (order.order_type or "MARKET").strip().upper()
        if order_type not in allowed:
            return RiskDecisionV2(
                blocked=True,
                reasons=[f"Order type {order_type} blocked by order_type_policy ({sorted(allowed)})."],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=None,
                drawdown_state=None,
                drawdown_pct=None,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

    symbol, exchange = _normalized_symbol_exchange(order)
    category = resolve_symbol_category(
        db,
        user_id=(user.id if user is not None else None),
        broker_name=(getattr(order, "broker_name", None) or "zerodha"),
        symbol=symbol,
        exchange=exchange,
    )
    if not category:
        return RiskDecisionV2(
            blocked=True,
            reasons=[
                "Missing symbol risk category (set LC/MC/SC/ETF from Holdings/Universe)."
            ],
            resolved_product=resolved_product,
            risk_profile_id=profile.id,
            risk_category=None,
            drawdown_state=None,
            drawdown_pct=None,
            final_qty=None,
            final_order_type=None,
            final_price=None,
        )

    dd_cfg = resolve_drawdown_config(db, product=resolved_product, category=category)
    if dd_cfg is None:
        return RiskDecisionV2(
            blocked=True,
            reasons=[
                f"Missing drawdown thresholds for {resolved_product}+{category} (configure in Settings)."
            ],
            resolved_product=resolved_product,
            risk_profile_id=profile.id,
            risk_category=category,
            drawdown_state=None,
            drawdown_pct=None,
            final_qty=None,
            final_order_type=None,
            final_price=None,
        )

    pnl_state = compute_portfolio_pnl_state(
        db,
        user_id=(user.id if user is not None else None),
        baseline_equity=baseline_equity,
        now_utc=now_utc,
    )
    if pnl_state.baseline_equity <= 0:
        return RiskDecisionV2(
            blocked=True,
            reasons=["Missing/invalid baseline equity (set Manual equity in Risk Policy)."],
            resolved_product=resolved_product,
            risk_profile_id=profile.id,
            risk_category=category,
            drawdown_state=None,
            drawdown_pct=None,
            final_qty=None,
            final_order_type=None,
            final_price=None,
        )

    # Persist a daily equity snapshot (portfolio-level MVP).
    try:
        snap_date = _as_of_date_ist(now_utc)
        snap = (
            db.query(EquitySnapshot)
            .filter(
                EquitySnapshot.user_id == (user.id if user is not None else None),
                EquitySnapshot.as_of_date == snap_date,
            )
            .one_or_none()
        )
        if snap is None:
            snap = EquitySnapshot(
                user_id=(user.id if user is not None else None),
                as_of_date=snap_date,
                equity=float(pnl_state.equity),
                peak_equity=float(pnl_state.peak_equity),
                drawdown_pct=float(pnl_state.drawdown_pct),
            )
            db.add(snap)
        else:
            snap.equity = float(pnl_state.equity)
            snap.peak_equity = float(max(snap.peak_equity or 0.0, pnl_state.peak_equity))
            snap.drawdown_pct = float(pnl_state.drawdown_pct)
            db.add(snap)
        db.commit()
    except Exception:
        # Snapshotting should not break enforcement decisions.
        pass

    dd_state = drawdown_state(pnl_state.drawdown_pct, dd_cfg)

    cap_eff, max_pos_eff, dd_reasons = _apply_drawdown_throttle(profile, dd_state, category)
    reasons.extend(dd_reasons)

    # Drawdown gating applies to entries; exits are always allowed.
    if not is_exit:
        if dd_state == "HARD_STOP":
            return RiskDecisionV2(
                blocked=True,
                reasons=reasons,
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )
        if dd_state == "DEFENSE" and (category or "").strip().upper() not in {"ETF", "LC"}:
            return RiskDecisionV2(
                blocked=True,
                reasons=reasons,
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

    # Daily loss checks (entries only).
    if not is_exit and profile.daily_loss_pct and profile.daily_loss_pct > 0:
        daily_loss_pct = (abs(min(0.0, pnl_state.pnl_today)) / pnl_state.baseline_equity) * 100.0
        if profile.hard_daily_loss_pct and profile.hard_daily_loss_pct > 0 and daily_loss_pct >= float(profile.hard_daily_loss_pct):
            return RiskDecisionV2(
                blocked=True,
                reasons=[
                    *reasons,
                    f"Hard daily loss limit reached ({daily_loss_pct:.2f}% >= {float(profile.hard_daily_loss_pct):.2f}%).",
                ],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )
        if daily_loss_pct >= float(profile.daily_loss_pct):
            return RiskDecisionV2(
                blocked=True,
                reasons=[
                    *reasons,
                    f"Daily loss limit reached ({daily_loss_pct:.2f}% >= {float(profile.daily_loss_pct):.2f}%).",
                ],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

    # Loss streak checks (entries only).
    if not is_exit and profile.max_consecutive_losses and profile.max_consecutive_losses > 0:
        if pnl_state.consecutive_losses >= int(profile.max_consecutive_losses):
            return RiskDecisionV2(
                blocked=True,
                reasons=[
                    *reasons,
                    f"Max consecutive losses reached ({pnl_state.consecutive_losses} >= {int(profile.max_consecutive_losses)}).",
                ],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

    # Entry time cutoff (MIS-only, entries only).
    if not is_exit and resolved_product == "MIS":
        cutoff = _parse_hhmm(profile.entry_cutoff_time)
        if cutoff is not None and _now_time_ist(now_utc) >= cutoff:
            return RiskDecisionV2(
                blocked=True,
                reasons=[*reasons, f"MIS entry cutoff time reached ({profile.entry_cutoff_time})."],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

        squareoff = _parse_hhmm(profile.force_squareoff_time)
        if squareoff is not None and _now_time_ist(now_utc) >= squareoff:
            return RiskDecisionV2(
                blocked=True,
                reasons=[
                    *reasons,
                    f"MIS force square-off time reached ({profile.force_squareoff_time}).",
                ],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

        start_day, end_day = _day_bounds_ist(now_utc)
        broker = (getattr(order, "broker_name", None) or "zerodha").strip().lower()
        user_id = user.id if user is not None else None

        def _symbol_match_clause() -> Any:
            # Best-effort: support orders storing either "SBIN" or "NSE:SBIN" in symbol.
            alt = f"{exchange}:{symbol}"
            return or_(Order.symbol == symbol, Order.symbol == alt)

        if profile.max_trades_per_day and int(profile.max_trades_per_day) > 0:
            q = db.query(Order).filter(
                Order.created_at >= start_day,
                Order.created_at < end_day,
                Order.broker_name == broker,
                Order.product == resolved_product,
                Order.is_exit.is_(False),
                (Order.broker_order_id.isnot(None) | (Order.status == "SENT")),
            )
            if user_id is not None:
                q = q.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
            trades_today = q.count()
            if trades_today >= int(profile.max_trades_per_day):
                return RiskDecisionV2(
                    blocked=True,
                    reasons=[
                        *reasons,
                        f"Max trades/day reached ({trades_today} >= {int(profile.max_trades_per_day)}).",
                    ],
                    resolved_product=resolved_product,
                    risk_profile_id=profile.id,
                    risk_category=category,
                    drawdown_state=dd_state,
                    drawdown_pct=pnl_state.drawdown_pct,
                    final_qty=None,
                    final_order_type=None,
                    final_price=None,
                )

        if profile.max_trades_per_symbol_per_day and int(profile.max_trades_per_symbol_per_day) > 0:
            q = db.query(Order).filter(
                Order.created_at >= start_day,
                Order.created_at < end_day,
                Order.broker_name == broker,
                Order.product == resolved_product,
                Order.is_exit.is_(False),
                Order.exchange == exchange,
                _symbol_match_clause(),
                (Order.broker_order_id.isnot(None) | (Order.status == "SENT")),
            )
            if user_id is not None:
                q = q.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
            trades_sym = q.count()
            if trades_sym >= int(profile.max_trades_per_symbol_per_day):
                return RiskDecisionV2(
                    blocked=True,
                    reasons=[
                        *reasons,
                        f"Max trades/symbol/day reached ({trades_sym} >= {int(profile.max_trades_per_symbol_per_day)}).",
                    ],
                    resolved_product=resolved_product,
                    risk_profile_id=profile.id,
                    risk_category=category,
                    drawdown_state=dd_state,
                    drawdown_pct=pnl_state.drawdown_pct,
                    final_qty=None,
                    final_order_type=None,
                    final_price=None,
                )

        # Min bars between trades (same symbol/product).
        if profile.min_bars_between_trades and int(profile.min_bars_between_trades) > 0:
            if order.alert is None:
                return RiskDecisionV2(
                    blocked=True,
                    reasons=[*reasons, "Missing alert context for min_bars_between_trades."],
                    resolved_product=resolved_product,
                    risk_profile_id=profile.id,
                    risk_category=category,
                    drawdown_state=dd_state,
                    drawdown_pct=pnl_state.drawdown_pct,
                    final_qty=None,
                    final_order_type=None,
                    final_price=None,
                )
            interval_min = _interval_minutes(getattr(order.alert, "interval", None))
            if interval_min is None or interval_min <= 0:
                return RiskDecisionV2(
                    blocked=True,
                    reasons=[*reasons, "Unknown alert interval for min_bars_between_trades."],
                    resolved_product=resolved_product,
                    risk_profile_id=profile.id,
                    risk_category=category,
                    drawdown_state=dd_state,
                    drawdown_pct=pnl_state.drawdown_pct,
                    final_qty=None,
                    final_order_type=None,
                    final_price=None,
                )
            now_bar = getattr(order.alert, "bar_time", None) or getattr(order.alert, "received_at", None) or now_utc
            last_entry = (
                db.query(Order, Alert)
                .join(Alert, Order.alert_id == Alert.id)
                .filter(
                    Order.id != order.id,
                    Order.broker_name == broker,
                    Order.product == resolved_product,
                    Order.is_exit.is_(False),
                    Order.exchange == exchange,
                    _symbol_match_clause(),
                    (Order.broker_order_id.isnot(None) | (Order.status == "SENT")),
                )
                .order_by(Alert.bar_time.desc(), Alert.received_at.desc())
                .first()
            )
            if last_entry is not None:
                _o2, a2 = last_entry
                prev_t = getattr(a2, "bar_time", None) or getattr(a2, "received_at", None)
                if prev_t is not None:
                    mins = (now_bar - prev_t).total_seconds() / 60.0
                    required = float(interval_min) * float(int(profile.min_bars_between_trades))
                    if mins < required:
                        return RiskDecisionV2(
                            blocked=True,
                            reasons=[
                                *reasons,
                                f"Min bars between trades not satisfied ({mins:.1f}m < {required:.1f}m).",
                            ],
                            resolved_product=resolved_product,
                            risk_profile_id=profile.id,
                            risk_category=category,
                            drawdown_state=dd_state,
                            drawdown_pct=pnl_state.drawdown_pct,
                            final_qty=None,
                            final_order_type=None,
                            final_price=None,
                        )

        # Cooldown after loss (same symbol): approximate using last losing trade close time.
        if profile.cooldown_after_loss_bars and int(profile.cooldown_after_loss_bars) > 0 and order.alert is not None:
            interval_min = _interval_minutes(getattr(order.alert, "interval", None))
            if interval_min is not None and interval_min > 0:
                now_bar = getattr(order.alert, "bar_time", None) or getattr(order.alert, "received_at", None) or now_utc
                q = db.query(AnalyticsTrade).join(Order, AnalyticsTrade.entry_order_id == Order.id)
                q = q.filter(Order.product == resolved_product, Order.exchange == exchange, _symbol_match_clause())
                if user_id is not None:
                    q = q.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
                last_trade = q.order_by(AnalyticsTrade.closed_at.desc()).first()
                if last_trade is not None and float(last_trade.pnl or 0.0) < 0:
                    mins = (now_bar - last_trade.closed_at).total_seconds() / 60.0
                    required = float(interval_min) * float(int(profile.cooldown_after_loss_bars))
                    if mins < required:
                        return RiskDecisionV2(
                            blocked=True,
                            reasons=[
                                *reasons,
                                f"Cooldown after loss active ({mins:.1f}m < {required:.1f}m).",
                            ],
                            resolved_product=resolved_product,
                            risk_profile_id=profile.id,
                            risk_category=category,
                            drawdown_state=dd_state,
                            drawdown_pct=pnl_state.drawdown_pct,
                            final_qty=None,
                            final_order_type=None,
                            final_price=None,
                        )

    # Max positions per product (entries only).
    if not is_exit and max_pos_eff and max_pos_eff > 0:
        broker = (getattr(order, "broker_name", None) or "zerodha").strip().lower()
        open_positions = (
            db.query(Position)
            .filter(
                Position.broker_name == broker,
                Position.product == resolved_product,
                Position.qty != 0,
            )
            .count()
        )
        if int(open_positions) >= int(max_pos_eff):
            return RiskDecisionV2(
                blocked=True,
                reasons=[*reasons, f"Max positions reached for {resolved_product} ({open_positions} >= {max_pos_eff})."],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=None,
            )

    price = _price_for_sizing(order)
    if price is None:
        return RiskDecisionV2(
            blocked=True,
            reasons=[*reasons, "Missing order price for sizing (provide trigger_price/price in alert)."],
            resolved_product=resolved_product,
            risk_profile_id=profile.id,
            risk_category=category,
            drawdown_state=dd_state,
            drawdown_pct=pnl_state.drawdown_pct,
            final_qty=None,
            final_order_type=None,
            final_price=None,
        )

    # Quantity sizing (simple capital-based sizing).
    cap_budget = float(cap_eff or 0.0)
    if cap_budget <= 0:
        return RiskDecisionV2(
            blocked=True,
            reasons=[*reasons, "Invalid capital_per_trade (must be > 0)."],
            resolved_product=resolved_product,
            risk_profile_id=profile.id,
            risk_category=category,
            drawdown_state=dd_state,
            drawdown_pct=pnl_state.drawdown_pct,
            final_qty=None,
            final_order_type=None,
            final_price=price,
        )

    qty = floor(cap_budget / float(price))
    if qty <= 0:
        return RiskDecisionV2(
            blocked=True,
            reasons=[*reasons, f"Capital per trade too small for price ({cap_budget} < {price})."],
            resolved_product=resolved_product,
            risk_profile_id=profile.id,
            risk_category=category,
            drawdown_state=dd_state,
            drawdown_pct=pnl_state.drawdown_pct,
            final_qty=None,
            final_order_type=None,
            final_price=price,
        )

    # Max exposure cap (product-level, portfolio-based).
    if profile.max_exposure_pct and float(profile.max_exposure_pct) > 0:
        broker = (getattr(order, "broker_name", None) or "zerodha").strip().lower()
        existing_exposure = 0.0
        try:
            positions = (
                db.query(Position)
                .filter(
                    Position.broker_name == broker,
                    Position.product == resolved_product,
                    Position.qty != 0,
                )
                .all()
            )
            for p in positions:
                existing_exposure += abs(float(p.qty or 0.0)) * float(p.avg_price or 0.0)
        except Exception:
            existing_exposure = 0.0

        max_exposure = float(pnl_state.equity) * float(profile.max_exposure_pct) / 100.0
        order_value = float(qty) * float(price)
        if max_exposure > 0 and (existing_exposure + order_value) > max_exposure:
            return RiskDecisionV2(
                blocked=True,
                reasons=[
                    *reasons,
                    f"Max exposure exceeded ({existing_exposure + order_value:.2f} > {max_exposure:.2f}).",
                ],
                resolved_product=resolved_product,
                risk_profile_id=profile.id,
                risk_category=category,
                drawdown_state=dd_state,
                drawdown_pct=pnl_state.drawdown_pct,
                final_qty=None,
                final_order_type=None,
                final_price=price,
            )

    return RiskDecisionV2(
        blocked=False,
        reasons=reasons,
        resolved_product=resolved_product,
        risk_profile_id=profile.id,
        risk_category=category,
        drawdown_state=dd_state,
        drawdown_pct=pnl_state.drawdown_pct,
        final_qty=float(qty),
        final_order_type=(order.order_type or "MARKET").strip().upper(),
        final_price=price,
    )


def record_decision_log(
    db: Session,
    *,
    user_id: int | None,
    alert: Alert | None,
    order: Order | None,
    decision: RiskDecisionV2,
    product_hint: str | None,
) -> None:
    try:
        strategy_ref: str | None = None
        if alert is not None:
            try:
                raw = str(getattr(alert, "raw_payload", "") or "")
                if raw.strip().startswith("{"):
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        strategy_ref = (
                            str(data.get("strategy_id") or "").strip()
                            or str(data.get("strategy_name") or "").strip()
                            or None
                        )
            except Exception:
                strategy_ref = None
            if strategy_ref is None and getattr(alert, "strategy_id", None) is not None:
                strategy_ref = f"strategy_db_id:{getattr(alert, 'strategy_id')}"

        log = AlertDecisionLog(
            user_id=user_id,
            alert_id=(alert.id if alert is not None else None),
            order_id=(order.id if order is not None else None),
            source=("TRADINGVIEW" if (alert is not None and (alert.source or "").upper() == "TRADINGVIEW") else "ALERT"),
            strategy_ref=strategy_ref,
            symbol=(order.symbol if order is not None else (alert.symbol if alert is not None else None)),
            exchange=(order.exchange if order is not None else (alert.exchange if alert is not None else None)),
            side=(order.side if order is not None else (alert.action if alert is not None else None)),
            trigger_price=(float(order.price) if (order is not None and order.price is not None) else (float(alert.price) if (alert is not None and alert.price is not None) else None)),
            product_hint=(product_hint or None),
            resolved_product=(decision.resolved_product or None),
            risk_profile_id=decision.risk_profile_id,
            risk_category=decision.risk_category,
            drawdown_pct=decision.drawdown_pct,
            drawdown_state=decision.drawdown_state,
            decision=("BLOCKED" if decision.blocked else "PLACED"),
            reasons_json=json.dumps(decision.reasons, ensure_ascii=False, default=str),
            details_json=json.dumps(
                {
                    "final_qty": decision.final_qty,
                    "final_order_type": decision.final_order_type,
                    "final_price": decision.final_price,
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to record alert decision log: %s", exc)


__all__ = [
    "RiskDecisionV2",
    "compute_portfolio_pnl_state",
    "drawdown_state",
    "evaluate_order_risk_v2",
    "pick_risk_profile",
    "record_decision_log",
    "resolve_drawdown_config",
    "resolve_symbol_category",
]
