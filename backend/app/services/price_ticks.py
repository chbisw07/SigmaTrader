from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# Default tick size for India equities in SigmaTrader.
# (Note: some instruments may differ; we can extend this later with
# per-instrument ticks.)
DEFAULT_TICK_SIZE = Decimal("0.05")


def round_price_to_tick(
    price: Optional[float],
    *,
    tick_size: Decimal = DEFAULT_TICK_SIZE,
) -> Optional[float]:
    """Round a price to the nearest tick (0.05 by default), half-up."""

    if price is None:
        return None

    try:
        p = Decimal(str(price))
    except Exception:
        return price

    if tick_size <= 0:
        return float(p)

    # Round to nearest tick with half-up behaviour.
    ticks = (p / tick_size).to_integral_value(rounding=ROUND_HALF_UP)
    out = ticks * tick_size

    # Match the user's expectation: 2 decimal places for 0.05 tick.
    # This keeps stable JSON output (e.g., 320.30) even though we store floats.
    out = out.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(out)


__all__ = ["DEFAULT_TICK_SIZE", "round_price_to_tick"]
