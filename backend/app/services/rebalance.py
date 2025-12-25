from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.positions import list_holdings
from app.core.config import Settings
from app.models import Candle, Group, GroupMember, User
from app.pydantic_compat import model_to_dict
from app.schemas.rebalance import (
    RebalancePreviewRequest,
    RebalancePreviewResult,
    RebalancePreviewSummary,
    RebalanceTrade,
)
from app.services.rebalance_risk import derive_risk_parity_targets
from app.services.rebalance_rotation import derive_rotation_targets


def _json_dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _broker_list(broker_name: str) -> list[str]:
    b = (broker_name or "").strip().lower()
    if b == "both":
        return ["zerodha", "angelone"]
    if b in {"zerodha", "angelone"}:
        return [b]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported broker: {broker_name}",
    )


def _get_group_or_404(db: Session, group_id: int) -> Group:
    g = db.get(Group, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return g


def _ensure_group_access(group: Group, user: User) -> None:
    if group.owner_id is not None and group.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _norm_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _norm_exchange(exchange: Optional[str]) -> str:
    return (exchange or "NSE").strip().upper()


def _load_latest_close_prices(
    db: Session,
    pairs: Iterable[Tuple[str, str]],
) -> Dict[Tuple[str, str], float]:
    out: Dict[Tuple[str, str], float] = {}
    for symbol, exchange in pairs:
        row: Candle | None = (
            db.query(Candle)
            .filter(
                Candle.symbol == symbol,
                Candle.exchange == exchange,
                Candle.timeframe == "1d",
            )
            .order_by(Candle.ts.desc())
            .first()
        )
        if row is not None and row.close and row.close > 0:
            out[(symbol, exchange)] = float(row.close)
    return out


@dataclass(frozen=True)
class _MemberInfo:
    symbol: str
    exchange: str
    target_weight_raw: Optional[float]


def _normalize_target_weights(
    members: List[_MemberInfo],
) -> Dict[Tuple[str, str], float]:
    if not members:
        return {}

    specified: list[float] = []
    unspecified: list[int] = []
    for idx, m in enumerate(members):
        w = m.target_weight_raw
        if w is None:
            unspecified.append(idx)
        else:
            wv = float(w)
            specified.append(max(0.0, wv))

    if all(m.target_weight_raw is None for m in members):
        eq = 1.0 / len(members)
        return {(m.symbol, m.exchange): eq for m in members}

    specified_sum = sum(max(0.0, float(m.target_weight_raw or 0.0)) for m in members)
    weights: list[float] = []
    if specified_sum <= 0:
        eq = 1.0 / len(members)
        weights = [eq for _ in members]
    elif specified_sum >= 1.0:
        # Normalise down to 1.0, ignore unspecified.
        for m in members:
            w = max(0.0, float(m.target_weight_raw or 0.0))
            weights.append(w / specified_sum if specified_sum else 0.0)
    else:
        # Distribute leftover across unspecified weights.
        leftover = 1.0 - specified_sum
        per_unspecified = leftover / len(unspecified) if unspecified else 0.0
        for m in members:
            if m.target_weight_raw is None:
                weights.append(per_unspecified)
            else:
                weights.append(max(0.0, float(m.target_weight_raw)))
        # Normalise to exactly 1.0 to avoid rounding drift.
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]

    out: Dict[Tuple[str, str], float] = {}
    for m, w in zip(members, weights, strict=False):
        out[(m.symbol, m.exchange)] = float(w)
    return out


def preview_rebalance(
    db: Session,
    settings: Settings,
    *,
    user: User,
    req: RebalancePreviewRequest,
) -> List[RebalancePreviewResult]:
    brokers = _broker_list(req.broker_name)
    out: List[RebalancePreviewResult] = []
    if req.target_kind == "HOLDINGS":
        for broker in brokers:
            holdings = list_holdings(
                broker_name=broker,
                db=db,
                settings=settings,
                user=user,
            )
            member_infos = [
                _MemberInfo(
                    symbol=_norm_symbol(getattr(h, "symbol", "") or ""),
                    exchange=_norm_exchange(getattr(h, "exchange", None)),
                    target_weight_raw=None,
                )
                for h in holdings
                if _norm_symbol(getattr(h, "symbol", "") or "")
            ]
            if not member_infos:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No holdings found for this broker.",
                )
            target_weights = _normalize_target_weights(member_infos)
            result = _preview_rebalance_single_broker(
                db,
                settings,
                user=user,
                group_id=0,
                broker_name=broker,
                member_infos=member_infos,
                target_weights=target_weights,
                req=req,
            )
            result.target_kind = "HOLDINGS"
            result.group_id = None
            out.append(result)
        return out

    group_id = int(req.group_id or 0)
    group = _get_group_or_404(db, group_id)
    _ensure_group_access(group, user)

    members: List[GroupMember] = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id)
        .order_by(GroupMember.created_at.asc())
        .all()
    )
    if not members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group has no members.",
        )

    base_member_infos = [
        _MemberInfo(
            symbol=_norm_symbol(m.symbol),
            exchange=_norm_exchange(m.exchange),
            target_weight_raw=(
                None if group.kind == "HOLDINGS_VIEW" else m.target_weight
            ),
        )
        for m in members
        if _norm_symbol(m.symbol)
    ]
    if not base_member_infos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group has no valid symbols.",
        )

    member_infos = base_member_infos
    target_weights = _normalize_target_weights(member_infos)
    derived_targets: Optional[List[Dict[str, object]]] = None
    extra_reason_by_symbol: Dict[str, Dict[str, object]] = {}
    rotation_warnings: List[str] = []
    risk_warnings: List[str] = []

    if str(req.rebalance_method).upper() == "SIGNAL_ROTATION":
        if req.rotation is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rotation config is required for SIGNAL_ROTATION.",
            )
        rotation = derive_rotation_targets(
            db,
            settings,
            user=user,
            rebalance_group=group,
            cfg=req.rotation,
        )
        rotation_warnings = list(rotation.warnings or [])
        derived_targets = [
            {
                "symbol": t.symbol,
                "exchange": t.exchange,
                "rank": t.rank,
                "score": t.score,
                "target_weight": t.target_weight,
            }
            for t in rotation.targets
        ]

        # Build new member set: existing group members + any missing top-N symbols.
        existing_pairs = {(m.symbol, m.exchange) for m in base_member_infos}
        additions = [
            _MemberInfo(
                symbol=t.symbol, exchange=t.exchange, target_weight_raw=t.target_weight
            )
            for t in rotation.targets
            if (t.symbol, t.exchange) not in existing_pairs
        ]
        # Overwrite weights for base members; optionally rotate out non-top-N.
        member_infos = []
        selected_pairs = set(rotation.weight_by_pair.keys())
        for m in base_member_infos:
            key = (m.symbol, m.exchange)
            if key in selected_pairs:
                member_infos.append(
                    _MemberInfo(
                        symbol=m.symbol,
                        exchange=m.exchange,
                        target_weight_raw=float(rotation.weight_by_pair.get(key, 0.0)),
                    )
                )
                extra_reason_by_symbol[m.symbol] = rotation.meta_by_symbol.get(
                    m.symbol, {}
                )
            else:
                tw = (
                    0.0 if bool(req.rotation.sell_not_in_top_n) else m.target_weight_raw
                )
                member_infos.append(
                    _MemberInfo(
                        symbol=m.symbol,
                        exchange=m.exchange,
                        target_weight_raw=tw,
                    )
                )
                extra_reason_by_symbol[m.symbol] = {
                    "rotation": {
                        "included": False,
                        "reason": (
                            "not_in_top_n"
                            if bool(req.rotation.sell_not_in_top_n)
                            else "not_in_top_n_kept"
                        ),
                        "strategy": {
                            "signal_strategy_version_id": int(
                                req.rotation.signal_strategy_version_id
                            ),
                            "signal_output": str(req.rotation.signal_output),
                        },
                    }
                }

        for a in additions:
            member_infos.append(a)
            extra_reason_by_symbol[a.symbol] = rotation.meta_by_symbol.get(a.symbol, {})

        target_weights = _normalize_target_weights(member_infos)

    if str(req.rebalance_method).upper() == "RISK_PARITY":
        if req.risk is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="risk config is required for RISK_PARITY.",
            )

        member_pairs = [(m.symbol, m.exchange) for m in base_member_infos]
        risk = derive_risk_parity_targets(
            db,
            user=user,
            group=group,
            members=member_pairs,
            cfg=req.risk,
        )
        derived_targets = risk.derived_targets
        risk_warnings = list(risk.warnings or [])

        member_infos = [
            _MemberInfo(
                symbol=m.symbol,
                exchange=m.exchange,
                target_weight_raw=float(
                    risk.weight_by_pair.get((m.symbol, m.exchange), 0.0)
                ),
            )
            for m in base_member_infos
        ]

        risk_meta_by_symbol = {
            str(d.get("symbol") or ""): d for d in (risk.derived_targets or [])
        }
        for m in base_member_infos:
            meta = risk_meta_by_symbol.get(m.symbol)
            if meta:
                extra_reason_by_symbol[m.symbol] = {"risk_parity": meta}

        target_weights = _normalize_target_weights(member_infos)

    for broker in brokers:
        result = _preview_rebalance_single_broker(
            db,
            settings,
            user=user,
            group_id=group.id,
            broker_name=broker,
            member_infos=member_infos,
            target_weights=target_weights,
            req=req,
            derived_targets=derived_targets,
            extra_reason_by_symbol=extra_reason_by_symbol,
            extra_warnings=[*rotation_warnings, *risk_warnings],
        )
        result.target_kind = "GROUP"
        result.group_id = group.id
        out.append(result)
    return out


def _preview_rebalance_single_broker(
    db: Session,
    settings: Settings,
    *,
    user: User,
    group_id: int,
    broker_name: str,
    member_infos: List[_MemberInfo],
    target_weights: Dict[Tuple[str, str], float],
    req: RebalancePreviewRequest,
    derived_targets: Optional[List[Dict[str, object]]] = None,
    extra_reason_by_symbol: Optional[Dict[str, Dict[str, object]]] = None,
    extra_warnings: Optional[List[str]] = None,
) -> RebalancePreviewResult:
    warnings: list[str] = list(extra_warnings or [])
    extra_reason_by_symbol = extra_reason_by_symbol or {}

    holdings = list_holdings(
        broker_name=broker_name,
        db=db,
        settings=settings,
        user=user,
    )
    holdings_by_symbol: dict[str, object] = {}
    for h in holdings:
        sym = _norm_symbol(getattr(h, "symbol", "") or "")
        if not sym:
            continue
        holdings_by_symbol[sym] = h

    missing_prices: list[Tuple[str, str]] = []
    price_by_symbol: dict[str, float] = {}
    qty_by_symbol: dict[str, float] = {}
    for m in member_infos:
        h = holdings_by_symbol.get(m.symbol)
        qty = float(getattr(h, "quantity", 0.0) or 0.0) if h is not None else 0.0
        last = getattr(h, "last_price", None) if h is not None else None
        price = float(last) if last is not None else None
        if price is None or price <= 0:
            missing_prices.append((m.symbol, m.exchange))
        else:
            price_by_symbol[m.symbol] = price
        qty_by_symbol[m.symbol] = qty

    if missing_prices:
        close_map = _load_latest_close_prices(db, missing_prices)
        for sym, exch in missing_prices:
            price = close_map.get((sym, exch))
            if price is not None and price > 0:
                price_by_symbol[sym] = float(price)
            else:
                warnings.append(
                    f"Missing price for {sym} ({exch}); skipping trades for this symbol"
                )

    current_value_by_symbol: dict[str, float] = {}
    for m in member_infos:
        price = price_by_symbol.get(m.symbol)
        qty = qty_by_symbol.get(m.symbol, 0.0)
        if price is None or price <= 0:
            current_value_by_symbol[m.symbol] = 0.0
        else:
            current_value_by_symbol[m.symbol] = float(qty) * float(price)

    portfolio_value = sum(current_value_by_symbol.values())
    if portfolio_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portfolio value is zero; cannot rebalance.",
        )

    abs_band = float(req.drift_band_abs_pct or 0.0)
    rel_band = float(req.drift_band_rel_pct or 0.0)

    candidates: list[dict] = []
    max_abs_drift_before = 0.0
    for m in member_infos:
        target_w = float(target_weights.get((m.symbol, m.exchange), 0.0) or 0.0)
        current_val = float(current_value_by_symbol.get(m.symbol, 0.0) or 0.0)
        live_w = current_val / portfolio_value if portfolio_value else 0.0
        drift = live_w - target_w
        max_abs_drift_before = max(max_abs_drift_before, abs(drift))

        threshold = max(abs_band, rel_band * target_w)
        if abs(drift) < threshold:
            continue

        price = price_by_symbol.get(m.symbol)
        if price is None or price <= 0:
            continue

        desired_val = target_w * portfolio_value
        delta_val = desired_val - current_val
        if delta_val == 0:
            continue

        side = "BUY" if delta_val > 0 else "SELL"
        candidates.append(
            {
                "symbol": m.symbol,
                "exchange": m.exchange,
                "side": side,
                "price": float(price),
                "target_weight": target_w,
                "live_weight": live_w,
                "drift": drift,
                "current_value": current_val,
                "desired_value": desired_val,
                "delta_value": delta_val,
                "threshold": threshold,
            }
        )

    if not candidates:
        summary = RebalancePreviewSummary(
            portfolio_value=float(portfolio_value),
            budget=0.0,
            scale=0.0,
            total_buy_value=0.0,
            total_sell_value=0.0,
            turnover_pct=0.0,
            budget_used=0.0,
            budget_used_pct=0.0,
            max_abs_drift_before=float(max_abs_drift_before),
            max_abs_drift_after=float(max_abs_drift_before),
            trades_count=0,
        )
        return RebalancePreviewResult(
            group_id=group_id,
            broker_name=broker_name,  # type: ignore[assignment]
            trades=[],
            summary=summary,
            warnings=warnings,
        )

    budget_amount = (
        float(req.budget_amount)
        if req.budget_amount is not None and req.budget_amount >= 0
        else None
    )
    if budget_amount is None:
        budget_pct = float(req.budget_pct or 0.0)
        budget_amount = max(0.0, budget_pct * portfolio_value)

    total_buy = sum(max(0.0, float(c["delta_value"])) for c in candidates)
    total_sell = sum(max(0.0, -float(c["delta_value"])) for c in candidates)
    denom = max(total_buy, total_sell)
    scale = (
        min(1.0, (budget_amount / denom)) if denom > 0 and budget_amount > 0 else 0.0
    )

    trades: list[RebalanceTrade] = []
    for c in candidates:
        price = float(c["price"])
        delta_val = float(c["delta_value"])
        scaled_val = delta_val * scale
        qty = int(abs(scaled_val) / price) if price > 0 else 0
        if qty <= 0:
            continue

        if c["side"] == "SELL":
            held_qty = float(qty_by_symbol.get(c["symbol"], 0.0) or 0.0)
            qty = min(qty, int(held_qty))
            if qty <= 0:
                continue

        notional = float(qty) * price
        if notional < float(req.min_trade_value or 0.0):
            continue

        trades.append(
            RebalanceTrade(
                symbol=c["symbol"],
                exchange=c["exchange"],
                side=c["side"],
                qty=qty,
                estimated_price=price,
                estimated_notional=notional,
                target_weight=float(c["target_weight"]),
                live_weight=float(c["live_weight"]),
                drift=float(c["drift"]),
                current_value=float(c["current_value"]),
                desired_value=float(c["desired_value"]),
                delta_value=delta_val,
                scale=float(scale),
                reason={
                    "threshold": float(c["threshold"]),
                    "abs_band": abs_band,
                    "rel_band": rel_band,
                    "budget": float(budget_amount),
                    **(extra_reason_by_symbol.get(str(c["symbol"]) or "", {})),
                },
            )
        )

    trades.sort(key=lambda t: t.estimated_notional, reverse=True)
    if req.max_trades is not None and req.max_trades >= 0:
        trades = trades[: int(req.max_trades)]

    total_buy_value = sum(t.estimated_notional for t in trades if t.side == "BUY")
    total_sell_value = sum(t.estimated_notional for t in trades if t.side == "SELL")
    turnover_pct = (
        ((total_buy_value + total_sell_value) / portfolio_value) * 100.0
        if portfolio_value
        else 0.0
    )
    budget_used = max(total_buy_value, total_sell_value)
    budget_used_pct = (
        (budget_used / portfolio_value) * 100.0 if portfolio_value else 0.0
    )

    # Approximate post-trade drift by applying notional deltas against the same
    # portfolio value (cash ignored in v1).
    post_value_by_symbol = dict(current_value_by_symbol)
    for t in trades:
        cur = float(post_value_by_symbol.get(t.symbol, 0.0) or 0.0)
        if t.side == "BUY":
            post_value_by_symbol[t.symbol] = cur + float(t.estimated_notional)
        else:
            post_value_by_symbol[t.symbol] = max(0.0, cur - float(t.estimated_notional))

    post_total = sum(post_value_by_symbol.values()) or portfolio_value
    max_abs_drift_after = 0.0
    for m in member_infos:
        target_w = float(target_weights.get((m.symbol, m.exchange), 0.0) or 0.0)
        post_val = float(post_value_by_symbol.get(m.symbol, 0.0) or 0.0)
        post_w = post_val / post_total if post_total else 0.0
        max_abs_drift_after = max(max_abs_drift_after, abs(post_w - target_w))

    summary = RebalancePreviewSummary(
        portfolio_value=float(portfolio_value),
        budget=float(budget_amount),
        scale=float(scale),
        total_buy_value=float(total_buy_value),
        total_sell_value=float(total_sell_value),
        turnover_pct=float(turnover_pct),
        budget_used=float(budget_used),
        budget_used_pct=float(budget_used_pct),
        max_abs_drift_before=float(max_abs_drift_before),
        max_abs_drift_after=float(max_abs_drift_after),
        trades_count=len(trades),
    )

    return RebalancePreviewResult(
        group_id=group_id,
        broker_name=broker_name,  # type: ignore[assignment]
        trades=trades,
        summary=summary,
        warnings=warnings,
        derived_targets=derived_targets,
    )


def build_run_snapshots(
    *,
    req: RebalancePreviewRequest,
    preview: RebalancePreviewResult,
) -> tuple[str, str, str]:
    policy_snapshot = {
        "rebalance_method": req.rebalance_method,
        "rotation": model_to_dict(req.rotation) if req.rotation is not None else None,
        "risk": model_to_dict(req.risk) if req.risk is not None else None,
        "budget_pct": req.budget_pct,
        "budget_amount": req.budget_amount,
        "drift_band_abs_pct": req.drift_band_abs_pct,
        "drift_band_rel_pct": req.drift_band_rel_pct,
        "max_trades": req.max_trades,
        "min_trade_value": req.min_trade_value,
    }
    inputs_snapshot = {
        "group_id": preview.group_id,
        "broker_name": preview.broker_name,
        "portfolio_value": preview.summary.portfolio_value,
        "warnings": preview.warnings,
    }
    return (
        _json_dump(policy_snapshot),
        _json_dump(inputs_snapshot),
        _json_dump(model_to_dict(preview.summary)),
    )


__all__ = [
    "preview_rebalance",
    "build_run_snapshots",
    "_json_dump",
    "_broker_list",
]
