from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import floor
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AnalyticsTrade, DrawdownThreshold, Order, RiskProfile, User
from app.schemas.risk_policy import OrderSourceBucket, ProductOverrides, ProductType, RiskPolicy
from app.services.risk_engine_v2_flag_store import get_risk_engine_v2_enabled
from app.services.risk_policy_enforcement import is_group_enforced
from app.services.risk_policy_store import get_risk_policy

DrawdownState = Literal["NORMAL", "CAUTION", "DEFENSE", "HARD_STOP"]
RiskCategory = Literal["LC", "MC", "SC", "ETF"]
RiskProduct = Literal["CNC", "MIS"]

IST_OFFSET = timedelta(hours=5, minutes=30)


def _as_of_date_ist(now_utc: datetime) -> date:
    return (now_utc + IST_OFFSET).date()


def _day_bounds_ist(now_utc: datetime) -> tuple[datetime, datetime]:
    d = _as_of_date_ist(now_utc)
    start_ist = datetime(d.year, d.month, d.day, tzinfo=UTC) - IST_OFFSET
    end_ist = start_ist + timedelta(days=1)
    return start_ist, end_ist


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


def select_risk_profile(db: Session, *, product: RiskProduct) -> RiskProfile | None:
    prod = (product or "").strip().upper()
    row = (
        db.query(RiskProfile)
        .filter(
            RiskProfile.enabled.is_(True),
            RiskProfile.is_default.is_(True),
            RiskProfile.product == prod,
        )
        .one_or_none()
    )
    if row is not None:
        return row
    return (
        db.query(RiskProfile)
        .filter(RiskProfile.enabled.is_(True), RiskProfile.product == prod)
        .order_by(RiskProfile.id)
        .first()
    )


def resolve_drawdown_config(
    db: Session,
    *,
    product: RiskProduct,
    category: RiskCategory,
) -> DrawdownConfig | None:
    prod = (product or "").strip().upper()
    cat = (category or "").strip().upper()
    row = (
        db.query(DrawdownThreshold)
        .filter(
            DrawdownThreshold.user_id.is_(None),
            DrawdownThreshold.product == prod,
            DrawdownThreshold.category == cat,
        )
        .one_or_none()
    )
    if row is None:
        return None
    return DrawdownConfig(
        caution_pct=float(row.caution_pct or 0.0),
        defense_pct=float(row.defense_pct or 0.0),
        hard_stop_pct=float(row.hard_stop_pct or 0.0),
    )


def compute_portfolio_pnl_state(
    db: Session,
    *,
    user_id: int | None,
    baseline_equity: float,
    now_utc: datetime,
) -> PortfolioPnlState:
    base = float(baseline_equity or 0.0)
    if base <= 0:
        return PortfolioPnlState(
            baseline_equity=base,
            equity=base,
            peak_equity=base,
            drawdown_pct=0.0,
            pnl_today=0.0,
            consecutive_losses=0,
        )

    query = db.query(AnalyticsTrade).join(Order, AnalyticsTrade.entry_order_id == Order.id)
    if user_id is not None:
        query = query.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
    trades = query.order_by(AnalyticsTrade.closed_at.asc()).all()

    start_day, end_day = _day_bounds_ist(now_utc)
    pnl_today = 0.0
    cumulative = 0.0
    peak_cum = 0.0

    for t in trades:
        pnl = float(t.pnl or 0.0)
        cumulative += pnl
        if cumulative > peak_cum:
            peak_cum = cumulative
        if t.closed_at >= start_day and t.closed_at < end_day:
            pnl_today += pnl

    streak = 0
    for t in reversed(trades):
        pnl = float(t.pnl or 0.0)
        if pnl < 0:
            streak += 1
        else:
            break

    equity = base + cumulative
    peak_equity = max(base, base + peak_cum)
    dd = 0.0
    if peak_equity > 0:
        dd = ((peak_equity - equity) / peak_equity) * 100.0
        if dd < 0:
            dd = 0.0

    return PortfolioPnlState(
        baseline_equity=base,
        equity=equity,
        peak_equity=peak_equity,
        drawdown_pct=dd,
        pnl_today=pnl_today,
        consecutive_losses=streak,
    )


def drawdown_state(
    dd_pct: float,
    cfg: DrawdownConfig,
) -> DrawdownState:
    dd = float(dd_pct or 0.0)
    if float(cfg.hard_stop_pct or 0.0) > 0 and dd >= float(cfg.hard_stop_pct):
        return "HARD_STOP"
    if float(cfg.defense_pct or 0.0) > 0 and dd >= float(cfg.defense_pct):
        return "DEFENSE"
    if float(cfg.caution_pct or 0.0) > 0 and dd >= float(cfg.caution_pct):
        return "CAUTION"
    return "NORMAL"


@dataclass(frozen=True)
class V2ThrottleResult:
    throttle_multiplier: float
    effective_capital_per_trade: float
    effective_max_positions: int
    allow_new_entries: bool
    reasons: list[str]


def apply_drawdown_throttle_v2(
    *,
    profile: RiskProfile,
    state: DrawdownState,
    category: RiskCategory,
) -> V2ThrottleResult:
    reasons: list[str] = []
    cap = float(profile.capital_per_trade or 0.0)
    max_pos = int(profile.max_positions or 0)
    multiplier = 1.0

    if state == "CAUTION":
        multiplier = 0.7
        cap = cap * multiplier
        max_pos = max(1, int(floor(max_pos * multiplier))) if max_pos > 0 else 0
        reasons.append("Drawdown CAUTION: throttling capital_per_trade and max_positions.")
        return V2ThrottleResult(
            throttle_multiplier=multiplier,
            effective_capital_per_trade=cap,
            effective_max_positions=max_pos,
            allow_new_entries=True,
            reasons=reasons,
        )

    if state == "DEFENSE":
        cat = (category or "").strip().upper()
        allow = cat in {"ETF", "LC"}
        if not allow:
            reasons.append("Drawdown DEFENSE: new entries restricted to ETF/LC symbols.")
        return V2ThrottleResult(
            throttle_multiplier=multiplier,
            effective_capital_per_trade=cap,
            effective_max_positions=max_pos,
            allow_new_entries=allow,
            reasons=reasons,
        )

    if state == "HARD_STOP":
        reasons.append("Drawdown HARD_STOP: new entries blocked.")
        return V2ThrottleResult(
            throttle_multiplier=multiplier,
            effective_capital_per_trade=cap,
            effective_max_positions=max_pos,
            allow_new_entries=False,
            reasons=reasons,
        )

    return V2ThrottleResult(
        throttle_multiplier=multiplier,
        effective_capital_per_trade=cap,
        effective_max_positions=max_pos,
        allow_new_entries=True,
        reasons=reasons,
    )


def _normalize_product(product: RiskProduct) -> ProductType:
    p = (product or "").strip().upper()
    return cast(ProductType, "MIS" if p == "MIS" else "CNC")


def compile_risk_policy(
    db: Session,
    settings: Settings,
    *,
    user: User | None,
    product: RiskProduct,
    category: RiskCategory,
    scenario: DrawdownState | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    now_utc = datetime.now(UTC)
    policy, policy_source = get_risk_policy(db, settings)

    manual_equity = float(getattr(getattr(policy, "equity", None), "manual_equity_inr", 0.0) or 0.0)
    user_id = user.id if user is not None else None
    pnl_state = compute_portfolio_pnl_state(
        db,
        user_id=user_id,
        baseline_equity=manual_equity,
        now_utc=now_utc,
    )

    prod_norm = cast(RiskProduct, (product or "").strip().upper() or "CNC")
    cat_norm = cast(RiskCategory, (category or "").strip().upper() or "LC")

    v2_profile = select_risk_profile(db, product=prod_norm)
    dd_cfg = resolve_drawdown_config(db, product=prod_norm, category=cat_norm)

    overrides: list[dict[str, Any]] = []
    provenance: dict[str, dict[str, Any]] = {}
    blocking_reasons: list[str] = []

    computed_state: DrawdownState | None = None
    if dd_cfg is not None:
        computed_state = drawdown_state(pnl_state.drawdown_pct, dd_cfg)
        provenance["risk_engine_v2.drawdown_state"] = {"source": "computed", "detail": "computed from drawdown_pct + thresholds"}
    effective_state = scenario or computed_state
    if scenario is not None and computed_state is not None and scenario != computed_state:
        overrides.append(
            {
                "field": "risk_engine_v2.drawdown_state",
                "from_value": computed_state,
                "to_value": scenario,
                "reason": "Scenario override",
                "source": "STATE_OVERRIDE",
            }
        )
        provenance["risk_engine_v2.drawdown_state"] = {"source": "state_override", "detail": "forced by ?scenario="}

    if v2_profile is None:
        blocking_reasons.append("Missing RiskProfile (create at least one enabled profile for the selected product).")
        provenance["risk_engine_v2.profile"] = {"source": "unknown", "detail": "missing"}
    else:
        provenance["risk_engine_v2.profile"] = {"source": "profile", "detail": f"{v2_profile.name} (id={v2_profile.id})"}

    if dd_cfg is None:
        blocking_reasons.append(
            f"Missing drawdown thresholds for {prod_norm}+{cat_norm} (configure in Settings)."
        )
        provenance["risk_engine_v2.thresholds"] = {"source": "unknown", "detail": "missing"}
    else:
        provenance["risk_engine_v2.thresholds"] = {"source": "drawdown_settings", "detail": f"{prod_norm}+{cat_norm}"}

    throttle = None
    allow_new_entries_v2 = True
    if v2_profile is not None:
        state_for_throttle: DrawdownState = effective_state or "NORMAL"
        throttle = apply_drawdown_throttle_v2(profile=v2_profile, state=state_for_throttle, category=cat_norm)
        if throttle.reasons:
            for r in throttle.reasons:
                overrides.append(
                    {
                        "field": "risk_engine_v2.drawdown_throttle",
                        "from_value": None,
                        "to_value": r,
                        "reason": r,
                        "source": "DD_THROTTLE",
                    }
                )
        allow_new_entries_v2 = bool(throttle.allow_new_entries)
        if not allow_new_entries_v2 and state_for_throttle in {"DEFENSE", "HARD_STOP"}:
            blocking_reasons.append("Drawdown state blocks new entries for the selected product/category.")
    else:
        allow_new_entries_v2 = False

    # Risk policy compilation (for both sources).
    ovr_on = is_group_enforced(policy, "overrides")
    exec_on = is_group_enforced(policy, "execution_safety")
    prod_type = _normalize_product(prod_norm)

    def _policy_effective(source: OrderSourceBucket) -> dict[str, Any]:
        ovr: ProductOverrides = policy.product_overrides(source=source, product=prod_type) if ovr_on else ProductOverrides()

        allow = ovr.allow if (ovr_on and ovr.allow is not None) else None
        if allow is None:
            allow = policy.execution_safety.allow_mis if prod_type == "MIS" else policy.execution_safety.allow_cnc

        if exec_on:
            provenance[f"risk_policy.{source}.{prod_type}.allow_product"] = {"source": "risk_policy", "detail": "execution_safety + overrides"}
        else:
            provenance[f"risk_policy.{source}.{prod_type}.allow_product"] = {"source": "risk_policy", "detail": "execution_safety group disabled"}

        base_cap = float(policy.position_sizing.capital_per_trade or 0.0)
        cap = float(ovr.capital_per_trade) if (ovr_on and ovr.capital_per_trade is not None) else base_cap
        if ovr_on and ovr.capital_per_trade is not None and float(ovr.capital_per_trade) != base_cap:
            overrides.append(
                {
                    "field": f"risk_policy.{source}.{prod_type}.capital_per_trade",
                    "from_value": base_cap,
                    "to_value": cap,
                    "reason": "Product override capital_per_trade",
                    "source": "RISK_POLICY_OVERRIDE",
                }
            )
        provenance[f"risk_policy.{source}.{prod_type}.capital_per_trade"] = {"source": "risk_policy", "detail": "position_sizing + overrides"}

        base_risk = float(policy.trade_risk.max_risk_per_trade_pct or 0.0)
        risk_pct = float(ovr.max_risk_per_trade_pct) if (ovr_on and ovr.max_risk_per_trade_pct is not None) else base_risk
        if ovr_on and ovr.max_risk_per_trade_pct is not None and float(ovr.max_risk_per_trade_pct) != base_risk:
            overrides.append(
                {
                    "field": f"risk_policy.{source}.{prod_type}.max_risk_per_trade_pct",
                    "from_value": base_risk,
                    "to_value": risk_pct,
                    "reason": "Product override max_risk_per_trade_pct",
                    "source": "RISK_POLICY_OVERRIDE",
                }
            )
        provenance[f"risk_policy.{source}.{prod_type}.max_risk_per_trade_pct"] = {"source": "risk_policy", "detail": "trade_risk + overrides"}

        base_hard = float(policy.trade_risk.hard_max_risk_pct or 0.0)
        hard_pct = float(ovr.hard_max_risk_pct) if (ovr_on and ovr.hard_max_risk_pct is not None) else base_hard
        if ovr_on and ovr.hard_max_risk_pct is not None and float(ovr.hard_max_risk_pct) != base_hard:
            overrides.append(
                {
                    "field": f"risk_policy.{source}.{prod_type}.hard_max_risk_pct",
                    "from_value": base_hard,
                    "to_value": hard_pct,
                    "reason": "Product override hard_max_risk_pct",
                    "source": "RISK_POLICY_OVERRIDE",
                }
            )
        provenance[f"risk_policy.{source}.{prod_type}.hard_max_risk_pct"] = {"source": "risk_policy", "detail": "trade_risk + overrides"}

        max_order_pct = float(policy.execution_safety.max_order_value_pct or 0.0)
        max_order_abs_from_pct = (manual_equity * max_order_pct / 100.0) if (manual_equity > 0 and max_order_pct > 0) else None

        max_order_abs_override = (
            float(ovr.max_order_value_abs) if (ovr_on and ovr.max_order_value_abs is not None) else None
        )
        max_qty_override = (
            float(ovr.max_quantity_per_order) if (ovr_on and ovr.max_quantity_per_order is not None) else None
        )

        return {
            "allow_product": bool(allow),
            "allow_short_selling": bool(policy.execution_safety.allow_short_selling),
            "manual_equity_inr": manual_equity,
            "max_daily_loss_pct": float(policy.account_risk.max_daily_loss_pct or 0.0),
            "max_daily_loss_abs": (
                float(policy.account_risk.max_daily_loss_abs)
                if policy.account_risk.max_daily_loss_abs is not None
                else (manual_equity * float(policy.account_risk.max_daily_loss_pct or 0.0) / 100.0 if manual_equity > 0 else None)
            ),
            "max_exposure_pct": float(policy.account_risk.max_exposure_pct or 0.0),
            "max_open_positions": int(policy.account_risk.max_open_positions or 0),
            "max_concurrent_symbols": int(policy.account_risk.max_concurrent_symbols or 0),
            "max_order_value_pct": max_order_pct,
            "max_order_value_abs_from_pct": max_order_abs_from_pct,
            "max_order_value_abs_override": max_order_abs_override,
            "max_quantity_per_order": max_qty_override,
            "max_risk_per_trade_pct": risk_pct,
            "hard_max_risk_pct": hard_pct,
            "stop_loss_mandatory": bool(policy.trade_risk.stop_loss_mandatory),
            "capital_per_trade": cap,
            "allow_scale_in": bool(policy.position_sizing.allow_scale_in),
            "pyramiding": int(policy.position_sizing.pyramiding or 1),
            "stop_reference": str(policy.trade_risk.stop_reference),
            "atr_period": int(policy.stop_rules.atr_period or 14),
            "atr_mult_initial_stop": float(policy.stop_rules.initial_stop_atr or 0.0),
            "fallback_stop_pct": float(policy.stop_rules.fallback_stop_pct or 0.0),
            "min_stop_distance_pct": float(policy.stop_rules.min_stop_distance_pct or 0.0),
            "max_stop_distance_pct": float(policy.stop_rules.max_stop_distance_pct or 0.0),
            "trailing_stop_enabled": bool(policy.stop_rules.trailing_stop_enabled),
            "trail_activation_atr": float(policy.stop_rules.trail_activation_atr or 0.0),
            "trail_activation_pct": float(policy.stop_rules.trail_activation_pct or 0.0),
            "max_trades_per_symbol_per_day": int(policy.trade_frequency.max_trades_per_symbol_per_day or 0),
            "min_bars_between_trades": int(policy.trade_frequency.min_bars_between_trades or 0),
            "cooldown_after_loss_bars": int(policy.trade_frequency.cooldown_after_loss_bars or 0),
            "max_consecutive_losses": int(policy.loss_controls.max_consecutive_losses or 0),
            "pause_after_loss_streak": bool(policy.loss_controls.pause_after_loss_streak),
            "pause_duration": str(policy.loss_controls.pause_duration or ""),
        }

    policy_by_source = {
        "TRADINGVIEW": _policy_effective("TRADINGVIEW"),
        "SIGMATRADER": _policy_effective("SIGMATRADER"),
    }

    risk_engine_v2_enabled, _v2_src = get_risk_engine_v2_enabled(db, settings)
    allow_new_entries = True
    if risk_engine_v2_enabled and blocking_reasons:
        allow_new_entries = False
    if risk_engine_v2_enabled and not allow_new_entries_v2:
        allow_new_entries = False

    result = {
        "context": {
            "product": prod_norm,
            "category": cat_norm,
            "scenario": scenario,
            "symbol": symbol,
            "strategy_id": strategy_id,
        },
        "inputs": {
            "compiled_at": now_utc,
            "risk_policy_source": policy_source,
            "risk_policy_enabled": bool(getattr(policy, "enabled", False)),
            "risk_engine_v2_enabled": risk_engine_v2_enabled,
            "manual_equity_inr": manual_equity,
            "drawdown_pct": pnl_state.drawdown_pct,
        },
        "effective": {
            "allow_new_entries": bool(allow_new_entries),
            "blocking_reasons": blocking_reasons,
            "risk_policy_by_source": policy_by_source,
            "risk_engine_v2": {
                "drawdown_pct": pnl_state.drawdown_pct,
                "drawdown_state": effective_state,
                "allow_new_entries": bool(allow_new_entries_v2),
                "throttle_multiplier": float(getattr(throttle, "throttle_multiplier", 1.0) if throttle else 1.0),
                "profile": (
                    {
                        "id": int(v2_profile.id),
                        "name": str(v2_profile.name),
                        "product": str(v2_profile.product).upper(),
                        "enabled": bool(v2_profile.enabled),
                        "is_default": bool(v2_profile.is_default),
                    }
                    if v2_profile is not None
                    else None
                ),
                "thresholds": (
                    {
                        "caution_pct": float(dd_cfg.caution_pct),
                        "defense_pct": float(dd_cfg.defense_pct),
                        "hard_stop_pct": float(dd_cfg.hard_stop_pct),
                    }
                    if dd_cfg is not None
                    else None
                ),
                "capital_per_trade": (
                    float(throttle.effective_capital_per_trade) if throttle is not None else (float(v2_profile.capital_per_trade) if v2_profile is not None else None)
                ),
                "max_positions": (
                    int(throttle.effective_max_positions) if throttle is not None else (int(v2_profile.max_positions) if v2_profile is not None else None)
                ),
                "max_exposure_pct": (float(v2_profile.max_exposure_pct) if v2_profile is not None else None),
                "risk_per_trade_pct": (float(v2_profile.risk_per_trade_pct) if v2_profile is not None else None),
                "hard_risk_pct": (float(v2_profile.hard_risk_pct) if v2_profile is not None else None),
                "daily_loss_pct": (float(v2_profile.daily_loss_pct) if v2_profile is not None else None),
                "hard_daily_loss_pct": (float(v2_profile.hard_daily_loss_pct) if v2_profile is not None else None),
                "max_consecutive_losses": (int(v2_profile.max_consecutive_losses) if v2_profile is not None else None),
                "entry_cutoff_time": (v2_profile.entry_cutoff_time if v2_profile is not None else None),
                "force_squareoff_time": (v2_profile.force_squareoff_time if v2_profile is not None else None),
                "max_trades_per_day": (v2_profile.max_trades_per_day if v2_profile is not None else None),
                "max_trades_per_symbol_per_day": (v2_profile.max_trades_per_symbol_per_day if v2_profile is not None else None),
                "min_bars_between_trades": (v2_profile.min_bars_between_trades if v2_profile is not None else None),
                "cooldown_after_loss_bars": (v2_profile.cooldown_after_loss_bars if v2_profile is not None else None),
                "slippage_guard_bps": (v2_profile.slippage_guard_bps if v2_profile is not None else None),
                "gap_guard_pct": (v2_profile.gap_guard_pct if v2_profile is not None else None),
            },
        },
        "overrides": overrides,
        "provenance": provenance,
    }

    return result


__all__ = [
    "DrawdownConfig",
    "DrawdownState",
    "PortfolioPnlState",
    "RiskCategory",
    "RiskProduct",
    "V2ThrottleResult",
    "apply_drawdown_throttle_v2",
    "compile_risk_policy",
    "compute_portfolio_pnl_state",
    "drawdown_state",
    "resolve_drawdown_config",
    "select_risk_profile",
]
