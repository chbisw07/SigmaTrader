from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskSizingResult:
    qty: int
    notional: float
    risk_per_share: float
    max_loss: float


def compute_risk_position_size(
    entry_price: float,
    stop_price: float,
    risk_budget: float,
    max_qty: int | None = None,
) -> RiskSizingResult:
    """Compute position size given entry, stop, and risk budget.

    All monetary values are assumed to be in the same currency (INR).

    The calculation is:

    * risk_per_share = abs(entry_price - stop_price)
    * qty = floor(risk_budget / risk_per_share)
    * capped by max_qty when provided
    * notional = qty * entry_price
    * max_loss = qty * risk_per_share
    """

    if entry_price <= 0 or stop_price <= 0:
        raise ValueError("entry_price and stop_price must be positive.")

    if risk_budget <= 0:
        raise ValueError("risk_budget must be positive.")

    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share == 0:
        raise ValueError("entry_price and stop_price must not be equal.")

    qty = int(risk_budget // risk_per_share)
    if max_qty is not None:
        qty = min(qty, max_qty)

    if qty <= 0:
        return RiskSizingResult(
            qty=0, notional=0.0, risk_per_share=risk_per_share, max_loss=0.0
        )

    notional = qty * entry_price
    max_loss = qty * risk_per_share

    return RiskSizingResult(
        qty=qty,
        notional=notional,
        risk_per_share=risk_per_share,
        max_loss=max_loss,
    )
