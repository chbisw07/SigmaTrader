from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Candle, Group, RiskCovarianceCache, User
from app.schemas.rebalance import RebalanceRiskConfig


def _norm_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _norm_exchange(exchange: Optional[str]) -> str:
    return (exchange or "NSE").strip().upper()


def _window_days(window: str) -> int:
    w = (window or "").strip().upper()
    if w == "6M":
        return 126
    if w == "1Y":
        return 252
    return 126


def _universe_hash(pairs: Iterable[Tuple[str, str]]) -> str:
    items = [f"{_norm_symbol(s)}@{_norm_exchange(e)}" for s, e in pairs]
    items = [x for x in items if x and not x.startswith("@")]
    raw = ";".join(sorted(items))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _json_dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(raw: str, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _load_closes(
    db: Session,
    *,
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int,
) -> List[Tuple[datetime, float]]:
    rows = (
        db.query(Candle.ts, Candle.close)
        .filter(
            Candle.symbol == symbol,
            Candle.exchange == exchange,
            Candle.timeframe == timeframe,
        )
        .order_by(Candle.ts.desc())
        .limit(limit)
        .all()
    )
    out: list[tuple[datetime, float]] = []
    for ts, close in rows:
        try:
            out.append((ts, float(close)))
        except Exception:
            continue
    out.reverse()
    return out


def _align_returns(
    series_by_pair: Dict[Tuple[str, str], List[Tuple[datetime, float]]],
    *,
    min_observations: int,
) -> Tuple[List[Tuple[str, str]], List[List[float]], datetime]:
    pairs = list(series_by_pair.keys())
    if not pairs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No symbols available for risk calculations.",
        )

    ts_sets = []
    close_maps: dict[tuple[str, str], dict[datetime, float]] = {}
    for p in pairs:
        closes = series_by_pair[p]
        m: dict[datetime, float] = {}
        for ts, c in closes:
            if c > 0:
                m[ts] = c
        close_maps[p] = m
        ts_sets.append(set(m.keys()))

    common = set.intersection(*ts_sets) if ts_sets else set()
    common_ts = sorted(common)
    if len(common_ts) < (min_observations + 1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Insufficient common price history across symbols for risk parity "
                f"(need >= {min_observations + 1} aligned candles)."
            ),
        )

    # Keep last aligned window.
    common_ts = common_ts[-(min_observations + 1) :]
    as_of_ts = common_ts[-1]

    aligned_pairs: list[tuple[str, str]] = []
    returns: list[list[float]] = []
    for p in pairs:
        m = close_maps[p]
        rets: list[float] = []
        for i in range(1, len(common_ts)):
            prev = m.get(common_ts[i - 1])
            cur = m.get(common_ts[i])
            if prev is None or cur is None or prev <= 0 or cur <= 0:
                rets.append(0.0)
            else:
                rets.append((cur / prev) - 1.0)
        aligned_pairs.append(p)
        returns.append(rets)

    return aligned_pairs, returns, as_of_ts


@dataclass(frozen=True)
class CovarianceResult:
    pairs: List[Tuple[str, str]]
    as_of_ts: datetime
    observations: int
    cov: List[List[float]]
    vol: List[float]
    corr: List[List[float]]
    cache_hit: bool


def _compute_covariance(
    returns: List[List[float]],
) -> Tuple[List[List[float]], List[float], List[List[float]]]:
    n = len(returns)
    t = len(returns[0]) if n else 0
    if n == 0 or t <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient returns to compute covariance.",
        )

    means = [sum(r) / t for r in returns]

    cov = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            s = 0.0
            for k in range(t):
                s += (returns[i][k] - means[i]) * (returns[j][k] - means[j])
            v = s / float(t - 1)
            cov[i][j] = v
            cov[j][i] = v

    vol = [math.sqrt(max(0.0, cov[i][i])) for i in range(n)]
    corr = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            denom = (vol[i] * vol[j]) if vol[i] > 0 and vol[j] > 0 else 0.0
            corr[i][j] = cov[i][j] / denom if denom else (1.0 if i == j else 0.0)
    return cov, vol, corr


def get_or_compute_covariance(
    db: Session,
    *,
    user: User,
    pairs: List[Tuple[str, str]],
    cfg: RebalanceRiskConfig,
) -> CovarianceResult:
    if cfg.timeframe != "1d":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only timeframe=1d is supported for risk parity in v1.",
        )

    window_days = _window_days(cfg.window)
    min_obs = int(cfg.min_observations or 0)
    if min_obs <= 0:
        min_obs = min(60, window_days)
    min_obs = min(min_obs, window_days)

    uhash = _universe_hash(pairs)
    limit = window_days + 1

    series_by_pair: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for sym, exch in pairs:
        symbol = _norm_symbol(sym)
        exchange = _norm_exchange(exch)
        if not symbol:
            continue
        series_by_pair[(symbol, exchange)] = _load_closes(
            db,
            symbol=symbol,
            exchange=exchange,
            timeframe=cfg.timeframe,
            limit=limit,
        )

    aligned_pairs, returns, as_of_ts = _align_returns(
        series_by_pair,
        min_observations=min_obs,
    )

    cached: RiskCovarianceCache | None = (
        db.query(RiskCovarianceCache)
        .filter(
            RiskCovarianceCache.universe_hash == uhash,
            RiskCovarianceCache.timeframe == cfg.timeframe,
            RiskCovarianceCache.window_days == window_days,
            RiskCovarianceCache.as_of_ts == as_of_ts,
        )
        .one_or_none()
    )
    if cached is not None:
        symbols = _json_load(cached.symbols_json, [])
        cov = _json_load(cached.cov_json, [])
        vol = _json_load(cached.vol_json, [])
        corr = _json_load(cached.corr_json, [])
        if (
            isinstance(symbols, list)
            and isinstance(cov, list)
            and isinstance(vol, list)
            and isinstance(corr, list)
        ):
            try:
                parsed_pairs = [
                    (str(x.get("symbol")), str(x.get("exchange")))
                    for x in symbols
                    if isinstance(x, dict)
                ]
                parsed_cov = [[float(v) for v in row] for row in cov]
                parsed_vol = [float(v) for v in vol]
                parsed_corr = [[float(v) for v in row] for row in corr]
                if parsed_pairs and parsed_cov and parsed_vol and parsed_corr:
                    return CovarianceResult(
                        pairs=parsed_pairs,
                        as_of_ts=as_of_ts,
                        observations=int(cached.observations or 0),
                        cov=parsed_cov,
                        vol=parsed_vol,
                        corr=parsed_corr,
                        cache_hit=True,
                    )
            except Exception:
                # fall through to recompute
                pass

    cov, vol, corr = _compute_covariance(returns)
    symbols_json = [{"symbol": s, "exchange": e} for s, e in aligned_pairs if s and e]

    row = RiskCovarianceCache(
        universe_hash=uhash,
        timeframe=cfg.timeframe,
        window_days=window_days,
        as_of_ts=as_of_ts,
        symbols_json=_json_dump(symbols_json),
        cov_json=_json_dump(cov),
        vol_json=_json_dump(vol),
        corr_json=_json_dump(corr),
        observations=len(returns[0]) if returns else 0,
    )
    db.add(row)
    db.commit()

    return CovarianceResult(
        pairs=aligned_pairs,
        as_of_ts=as_of_ts,
        observations=len(returns[0]) if returns else 0,
        cov=cov,
        vol=vol,
        corr=corr,
        cache_hit=False,
    )


def _mat_vec(cov: List[List[float]], w: List[float]) -> List[float]:
    n = len(w)
    out = [0.0 for _ in range(n)]
    for i in range(n):
        s = 0.0
        row = cov[i]
        for j in range(n):
            s += row[j] * w[j]
        out[i] = s
    return out


def _project_simplex_bounds(
    w: List[float],
    *,
    min_w: float,
    max_w: float,
) -> List[float]:
    n = len(w)
    if n == 0:
        return []
    if min_w * n > 1.0 + 1e-12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_weight is too high for the number of assets.",
        )
    if max_w * n < 1.0 - 1e-12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_weight is too low for the number of assets.",
        )

    w2 = [float(x) if math.isfinite(float(x)) else 0.0 for x in w]
    w2 = [max(min(x, max_w), min_w) for x in w2]

    eps = 1e-12
    for _ in range(200):
        total = sum(w2)
        if abs(total - 1.0) <= 1e-12:
            break
        if total < 1.0:
            add = 1.0 - total
            free = [i for i in range(n) if w2[i] < (max_w - eps)]
            if not free:
                break
            weights = [max(w2[i], eps) for i in free]
            denom = sum(weights) or float(len(free))
            for i, base in zip(free, weights, strict=False):
                w2[i] = min(max_w, w2[i] + add * (base / denom))
        else:
            sub = total - 1.0
            free = [i for i in range(n) if w2[i] > (min_w + eps)]
            if not free:
                break
            weights = [max(w2[i] - min_w, eps) for i in free]
            denom = sum(weights) or float(len(free))
            for i, base in zip(free, weights, strict=False):
                w2[i] = max(min_w, w2[i] - sub * (base / denom))

    total = sum(w2) or 1.0
    w2 = [x / total for x in w2]
    return w2


@dataclass(frozen=True)
class RiskParityResult:
    weights: List[float]
    converged: bool
    iterations: int
    max_rc_error: float


def solve_risk_parity_erc(
    cov: List[List[float]],
    *,
    min_weight: float,
    max_weight: float,
    max_iter: int,
    tol: float,
) -> RiskParityResult:
    n = len(cov)
    if n == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No assets for risk parity.",
        )

    w = [1.0 / n for _ in range(n)]
    w = _project_simplex_bounds(w, min_w=min_weight, max_w=max_weight)
    target_share = 1.0 / n

    converged = False
    max_err = 1.0
    iterations = 0
    for _it in range(1, max_iter + 1):
        iterations = _it
        m = _mat_vec(cov, w)
        rc = [w[i] * m[i] for i in range(n)]
        total = sum(rc)
        if total <= 0 or not math.isfinite(total):
            break
        shares = [r / total for r in rc]
        max_err = max(abs(s - target_share) for s in shares)
        if max_err <= tol:
            converged = True
            break

        for i in range(n):
            s = shares[i]
            if s > 0:
                w[i] *= target_share / s
            else:
                w[i] *= 1.1
        w = _project_simplex_bounds(w, min_w=min_weight, max_w=max_weight)

    return RiskParityResult(
        weights=w,
        converged=converged,
        iterations=iterations,
        max_rc_error=float(max_err),
    )


@dataclass(frozen=True)
class RiskTargetsDerivation:
    weight_by_pair: Dict[Tuple[str, str], float]
    derived_targets: List[Dict[str, object]]
    warnings: List[str]


def derive_risk_parity_targets(
    db: Session,
    *,
    user: User,
    group: Group,
    members: List[Tuple[str, str]],
    cfg: RebalanceRiskConfig,
) -> RiskTargetsDerivation:
    if group.kind != "PORTFOLIO":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Risk parity is supported only for PORTFOLIO groups.",
        )

    cov_res = get_or_compute_covariance(
        db,
        user=user,
        pairs=members,
        cfg=cfg,
    )

    rp = solve_risk_parity_erc(
        cov_res.cov,
        min_weight=float(cfg.min_weight),
        max_weight=float(cfg.max_weight),
        max_iter=int(cfg.max_iter),
        tol=float(cfg.tol),
    )

    w = rp.weights
    m = _mat_vec(cov_res.cov, w)
    rc = [w[i] * m[i] for i in range(len(w))]
    total_rc = sum(rc) or 1.0
    rc_share = [r / total_rc for r in rc]

    ann_factor = math.sqrt(252.0)
    derived: list[dict[str, object]] = []
    weight_by_pair: dict[tuple[str, str], float] = {}
    for idx, (pair, weight) in enumerate(zip(cov_res.pairs, w, strict=False)):
        sym, exch = pair
        weight_by_pair[(sym, exch)] = float(weight)
        vol = float(cov_res.vol[idx]) if idx < len(cov_res.vol) else 0.0
        derived.append(
            {
                "symbol": sym,
                "exchange": exch,
                "target_weight": float(weight),
                "vol_daily": vol,
                "vol_annual": vol * ann_factor,
                "risk_contribution_share": (
                    float(rc_share[idx]) if idx < len(rc_share) else 0.0
                ),
                "as_of": cov_res.as_of_ts.isoformat(),
                "observations": cov_res.observations,
                "cache_hit": bool(cov_res.cache_hit),
                "optimizer": {
                    "converged": bool(rp.converged),
                    "iterations": int(rp.iterations),
                    "max_rc_error": float(rp.max_rc_error),
                },
                "config": {
                    "window": cfg.window,
                    "timeframe": cfg.timeframe,
                    "min_weight": float(cfg.min_weight),
                    "max_weight": float(cfg.max_weight),
                },
            }
        )

    warnings: list[str] = []
    if not rp.converged:
        warnings.append(
            "Risk parity optimizer did not fully converge; weights are approximate."
        )
    return RiskTargetsDerivation(
        weight_by_pair=weight_by_pair,
        derived_targets=derived,
        warnings=warnings,
    )


__all__ = [
    "CovarianceResult",
    "RiskParityResult",
    "RiskTargetsDerivation",
    "derive_risk_parity_targets",
    "get_or_compute_covariance",
    "solve_risk_parity_erc",
]
