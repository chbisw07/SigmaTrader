from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Candle,
    Group,
    GroupMember,
    ScreenerRun,
    SignalStrategy,
    SignalStrategyVersion,
    User,
)
from app.schemas.rebalance import RebalanceRotationConfig
from app.services.alerts_v3_compiler import (
    _ensure_numeric_only,
    compile_alert_expression_parts,
    compile_custom_indicators_for_user,
)
from app.services.alerts_v3_expression import (
    CandleCache,
    IndicatorAlertError,
    _eval_numeric,
)
from app.services.signal_strategies import (
    load_inputs,
    load_outputs,
    load_variables,
    materialize_params,
    pick_output,
)


def _norm_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _norm_exchange(exchange: Optional[str]) -> str:
    return (exchange or "NSE").strip().upper()


def _get_group_or_404(db: Session, group_id: int) -> Group:
    g = db.get(Group, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return g


def _ensure_group_access(group: Group, user: User) -> None:
    if group.owner_id is not None and group.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _get_strategy_version_or_404(
    db: Session, *, user_id: int, version_id: int
) -> SignalStrategyVersion:
    v = db.get(SignalStrategyVersion, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    s = db.get(SignalStrategy, v.strategy_id)
    if s is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if s.scope == "USER" and s.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return v


def _json_load(raw: str, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


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


def _avg_volume_20d(
    db: Session,
    *,
    symbol: str,
    exchange: str,
) -> Optional[float]:
    rows = (
        db.query(Candle.volume)
        .filter(
            Candle.symbol == symbol,
            Candle.exchange == exchange,
            Candle.timeframe == "1d",
        )
        .order_by(Candle.ts.desc())
        .limit(20)
        .all()
    )
    vols = []
    for (v,) in rows:
        try:
            vols.append(float(v))
        except Exception:
            continue
    if not vols:
        return None
    return float(sum(vols) / len(vols))


@dataclass(frozen=True)
class RotationTarget:
    symbol: str
    exchange: str
    score: float
    rank: int
    target_weight: float


@dataclass(frozen=True)
class RotationDerivation:
    targets: List[RotationTarget]
    weight_by_pair: Dict[Tuple[str, str], float]
    meta_by_symbol: Dict[str, Dict[str, Any]]
    warnings: List[str]


def _resolve_universe_pairs(
    db: Session,
    settings: Settings,
    *,
    user: User,
    rebalance_group: Group,
    cfg: RebalanceRotationConfig,
) -> List[Tuple[str, str]]:
    # Default: use rebalance group.
    if cfg.universe_group_id is None and cfg.screener_run_id is None:
        group = rebalance_group
    elif cfg.universe_group_id is not None:
        group = _get_group_or_404(db, int(cfg.universe_group_id))
        _ensure_group_access(group, user)
    else:
        run = db.get(ScreenerRun, int(cfg.screener_run_id or 0))
        if run is None or run.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
        if run.status != "DONE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Screener run is not complete yet.",
            )
        rows = _json_load(run.results_json, [])
        pairs: list[tuple[str, str]] = []
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                if not bool(item.get("matched")):
                    continue
                sym = _norm_symbol(str(item.get("symbol") or ""))
                exch = _norm_exchange(item.get("exchange"))  # type: ignore[arg-type]
                if sym:
                    pairs.append((sym, exch))
        if not pairs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Screener run has no matched symbols.",
            )
        # De-dupe, preserve stable order.
        seen: set[tuple[str, str]] = set()
        deduped: list[tuple[str, str]] = []
        for p in pairs:
            if p in seen:
                continue
            seen.add(p)
            deduped.append(p)
        return deduped

    members = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id)
        .order_by(GroupMember.created_at.asc())
        .all()
    )
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in members:
        sym = _norm_symbol(m.symbol)
        if not sym:
            continue
        exch = _norm_exchange(m.exchange)
        key = (sym, exch)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    if not out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Universe has no symbols.",
        )
    return out


def derive_rotation_targets(
    db: Session,
    settings: Settings,
    *,
    user: User,
    rebalance_group: Group,
    cfg: RebalanceRotationConfig,
) -> RotationDerivation:
    # Keep v2 scoped to portfolio rotation until we decide how to persist other kinds.
    if rebalance_group.kind != "PORTFOLIO":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signal-driven rebalance is supported only for PORTFOLIO groups.",
        )

    candidates = _resolve_universe_pairs(
        db,
        settings,
        user=user,
        rebalance_group=rebalance_group,
        cfg=cfg,
    )

    whitelist = {
        _norm_symbol(s) for s in (cfg.symbol_whitelist or []) if _norm_symbol(s)
    }
    blacklist = {
        _norm_symbol(s) for s in (cfg.symbol_blacklist or []) if _norm_symbol(s)
    }

    if whitelist:
        candidates = [p for p in candidates if p[0] in whitelist]
    if blacklist:
        candidates = [p for p in candidates if p[0] not in blacklist]

    v = _get_strategy_version_or_404(
        db, user_id=user.id, version_id=int(cfg.signal_strategy_version_id)
    )
    inputs = load_inputs(v.inputs_json)
    variables = load_variables(v.variables_json)
    outputs = load_outputs(v.outputs_json)
    output = pick_output(outputs, name=str(cfg.signal_output), require_kind="OVERLAY")

    params = materialize_params(inputs=inputs, overrides=cfg.signal_params or {})

    custom = compile_custom_indicators_for_user(
        db,
        user_id=user.id,
        dsl_profile=settings.dsl_profile,
    )
    raw_vars = [
        vv.model_dump() if hasattr(vv, "model_dump") else vv.dict() for vv in variables
    ]
    ast, _cadence, _var_map = compile_alert_expression_parts(
        db,
        user_id=user.id,
        variables=raw_vars,
        condition_dsl=str(output.dsl or ""),
        evaluation_cadence="1d",
        custom_indicators=custom,
        dsl_profile=settings.dsl_profile,
    )
    _ensure_numeric_only(ast, context=f"Rotation output '{output.name}'")

    warnings: list[str] = []

    price_map: dict[tuple[str, str], float] = {}
    if cfg.min_price is not None and cfg.min_price > 0:
        price_map = _load_latest_close_prices(db, candidates)

    eligible: list[tuple[str, str, float]] = []
    for symbol, exchange in candidates:
        if cfg.min_price is not None and cfg.min_price > 0:
            price = price_map.get((symbol, exchange))
            if price is None or price < float(cfg.min_price):
                continue

        if cfg.min_avg_volume_20d is not None and cfg.min_avg_volume_20d > 0:
            avg_vol = _avg_volume_20d(db, symbol=symbol, exchange=exchange)
            if avg_vol is None or avg_vol < float(cfg.min_avg_volume_20d):
                continue

        try:
            cache = CandleCache(
                db=db,
                settings=settings,
                symbol=symbol,
                exchange=exchange,
                allow_fetch=False,
            )
            score = _eval_numeric(
                ast,
                db=db,
                settings=settings,
                cache=cache,
                holding=None,
                params=params,
                custom_indicators=custom,
                allow_fetch=False,
            ).now
        except IndicatorAlertError as exc:
            warnings.append(f"{symbol}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"{symbol}: {exc}")
            continue

        if score is None:
            continue
        try:
            score_f = float(score)
        except Exception:
            continue
        if cfg.require_positive_score and score_f <= 0:
            continue

        eligible.append((symbol, exchange, score_f))

    if not eligible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No eligible symbols for rotation "
                "(check filters and data availability)."
            ),
        )

    eligible.sort(key=lambda x: (x[2], x[0]), reverse=True)
    top_n = min(int(cfg.top_n or 0), len(eligible))
    selected = eligible[:top_n]

    scores = [s for _sym, _exch, s in selected]
    weights_raw: list[float] = []
    if str(cfg.weighting).upper() == "SCORE":
        pos = [max(0.0, float(s)) for s in scores]
        denom = sum(pos)
        weights_raw = [p / denom if denom > 0 else 0.0 for p in pos]
        if denom <= 0:
            weights_raw = [1.0 / len(selected) for _ in selected]
    elif str(cfg.weighting).upper() == "RANK":
        # Higher rank (1) gets larger weight.
        raw = [float(len(selected) - idx) for idx in range(len(selected))]
        denom = sum(raw) or 1.0
        weights_raw = [r / denom for r in raw]
    else:
        weights_raw = [1.0 / len(selected) for _ in selected]

    weight_by_pair: dict[tuple[str, str], float] = {}
    targets: list[RotationTarget] = []
    meta_by_symbol: dict[str, dict[str, Any]] = {}
    for idx, ((sym, exch, score), w) in enumerate(
        zip(selected, weights_raw, strict=False)
    ):
        rank = idx + 1
        tw = float(w)
        key = (sym, exch)
        weight_by_pair[key] = tw
        targets.append(
            RotationTarget(
                symbol=sym,
                exchange=exch,
                score=float(score),
                rank=rank,
                target_weight=tw,
            )
        )
        meta_by_symbol[sym] = {
            "rotation": {
                "included": True,
                "rank": rank,
                "score": float(score),
                "target_weight": tw,
                "universe": {
                    "universe_group_id": cfg.universe_group_id,
                    "screener_run_id": cfg.screener_run_id,
                },
                "strategy": {
                    "signal_strategy_version_id": int(cfg.signal_strategy_version_id),
                    "signal_output": str(cfg.signal_output),
                    "weighting": str(cfg.weighting),
                    "top_n": int(cfg.top_n),
                },
            }
        }

    return RotationDerivation(
        targets=targets,
        weight_by_pair=weight_by_pair,
        meta_by_symbol=meta_by_symbol,
        warnings=warnings,
    )


__all__ = ["RotationDerivation", "RotationTarget", "derive_rotation_targets"]
