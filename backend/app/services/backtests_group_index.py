from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GroupIndexSeries:
    close: list[float]
    coverage: list[float]  # 0..1
    members_used: list[int]
    members_total: int
    coverage_kind: str  # "COUNT" or "WEIGHT"


def compute_equal_weight_returns_index(
    *,
    closes_by_key: dict[str, list[Optional[float]]],
    members_total: int,
    base: float = 100.0,
) -> GroupIndexSeries:
    """Compute an equal-weight returns index from constituent close series.

    - Uses only available constituents per time step (dynamic availability set).
    - For i>0, a constituent is "available" if both close[i-1] and close[i] are
      present and >0.
    - For i==0, a constituent is "available" if close[0] is present and >0.
    - If no members are available at a step, index level is held flat and coverage=0.
    """

    if members_total <= 0:
        raise ValueError("members_total must be > 0")

    n_steps = max((len(v) for v in closes_by_key.values()), default=0)
    level = float(base)

    close: list[float] = []
    coverage: list[float] = []
    members_used: list[int] = []

    keys = list(closes_by_key.keys())
    for i in range(n_steps):
        rets: list[float] = []
        for key in keys:
            series = closes_by_key.get(key) or []
            if i >= len(series):
                continue
            p1 = series[i]
            if p1 is None or p1 <= 0:
                continue
            if i == 0:
                rets.append(0.0)
                continue
            p0 = series[i - 1]
            if p0 is None or p0 <= 0:
                continue
            rets.append(float(p1 / p0 - 1.0))

        used = len(rets)
        members_used.append(used)
        coverage.append(float(used) / float(members_total))
        if used > 0:
            r_idx = sum(rets) / float(used)
            level *= 1.0 + float(r_idx)
        close.append(float(level))

    return GroupIndexSeries(
        close=close,
        coverage=coverage,
        members_used=members_used,
        members_total=int(members_total),
        coverage_kind="COUNT",
    )


def compute_weighted_returns_index(
    *,
    closes_by_key: dict[str, list[Optional[float]]],
    weights_by_key: dict[str, float],
    base: float = 100.0,
) -> GroupIndexSeries:
    """Compute a weight-based returns index from constituent close series.

    Rules:
    - Base weights are given by weights_by_key (not necessarily normalized).
    - Dynamic availability set: at each step use only available constituents.
    - Coverage(T) = sum(base_weight for available constituents) ∈ [0,1] after
      normalization.
    - Effective weights at T are renormalized among available set.
    - If coverage(T) == 0, index level is held flat and coverage=0.
    """

    if not weights_by_key:
        raise ValueError("weights_by_key is required for weighted index.")

    # Normalize base weights to sum to 1 across all members.
    base_sum = sum(max(0.0, float(w)) for w in weights_by_key.values())
    if base_sum <= 0:
        raise ValueError("weights_by_key must have positive weights.")
    w_norm = {k: max(0.0, float(w)) / base_sum for k, w in weights_by_key.items()}

    n_steps = max((len(v) for v in closes_by_key.values()), default=0)
    level = float(base)

    close: list[float] = []
    coverage: list[float] = []
    members_used: list[int] = []

    keys = list(weights_by_key.keys())
    for i in range(n_steps):
        available: list[str] = []
        for key in keys:
            series = closes_by_key.get(key) or []
            if i >= len(series):
                continue
            p1 = series[i]
            if p1 is None or p1 <= 0:
                continue
            if i == 0:
                available.append(key)
                continue
            p0 = series[i - 1]
            if p0 is None or p0 <= 0:
                continue
            available.append(key)

        cov = sum(float(w_norm.get(k, 0.0)) for k in available)
        members_used.append(len(available))
        coverage.append(float(cov))
        if cov > 0 and i > 0:
            r_idx = 0.0
            for key in available:
                series = closes_by_key.get(key) or []
                p0 = float(series[i - 1])  # available implies exists and >0
                p1 = float(series[i])
                ret = float(p1 / p0 - 1.0)
                r_idx += float(w_norm.get(key, 0.0)) / float(cov) * ret
            level *= 1.0 + float(r_idx)
        close.append(float(level))

    return GroupIndexSeries(
        close=close,
        coverage=coverage,
        members_used=members_used,
        members_total=len(keys),
        coverage_kind="WEIGHT",
    )


__all__ = [
    "GroupIndexSeries",
    "compute_equal_weight_returns_index",
    "compute_weighted_returns_index",
]
