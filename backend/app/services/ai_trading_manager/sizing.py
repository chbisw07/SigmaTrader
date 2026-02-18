from __future__ import annotations

import math
from typing import Any, Dict


def extract_equity_value(margins: Dict[str, Any]) -> float | None:
    """Best-effort extraction of equity/available capital from broker margins payload.

    This is intentionally conservative and schema-agnostic because different
    broker backends return different shapes. For deterministic sizing suggestions
    callers may pass equity_value explicitly.
    """

    if not isinstance(margins, dict):
        return None

    candidates: list[float] = []

    def _maybe_add(v: Any) -> None:
        try:
            f = float(v)
        except Exception:
            return
        if math.isfinite(f) and f > 0:
            candidates.append(f)

    def _walk(obj: Any, *, depth: int) -> None:
        if depth <= 0:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key in {"live_balance", "cash", "net", "available", "equity", "opening_balance"}:
                    _maybe_add(v)
                _walk(v, depth=depth - 1)
        elif isinstance(obj, list):
            for it in obj:
                _walk(it, depth=depth - 1)

    _walk(margins, depth=4)
    if not candidates:
        return None
    # Prefer the largest positive candidate.
    return max(candidates)


def suggest_qty(
    *,
    entry_price: float,
    stop_price: float,
    risk_budget_pct: float,
    equity_value: float,
    max_qty: int | None = None,
) -> tuple[int, dict[str, float]]:
    if entry_price <= 0 or stop_price <= 0:
        raise ValueError("entry_price and stop_price must be positive.")
    if equity_value <= 0:
        raise ValueError("equity_value must be positive.")
    if risk_budget_pct <= 0:
        raise ValueError("risk_budget_pct must be positive.")

    risk_per_share = abs(float(entry_price) - float(stop_price))
    if risk_per_share <= 0:
        raise ValueError("stop_price must be different from entry_price.")

    risk_amount = float(equity_value) * (float(risk_budget_pct) / 100.0)
    qty = int(math.floor(risk_amount / risk_per_share))
    qty = max(qty, 1)
    if max_qty is not None:
        qty = min(qty, int(max_qty))

    metrics = {
        "risk_per_share": float(risk_per_share),
        "risk_amount": float(risk_amount),
        "notional_value": float(qty) * float(entry_price),
    }
    return qty, metrics
