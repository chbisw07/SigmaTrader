from __future__ import annotations

import re
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Optional

# Default tick size for India equities in SigmaTrader.
# (Note: some instruments may differ; we can extend this later with
# per-instrument ticks.)
DEFAULT_TICK_SIZE = Decimal("0.05")

_TICK_SIZE_ERROR_RE = re.compile(
    r"tick size for this script is\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


def parse_tick_size_from_error(message: str | None) -> Decimal | None:
    """Best-effort parse of broker tick-size errors (e.g. Zerodha).

    Example message:
      "Tick size for this script is 0.10. Kindly enter price in the multiple ..."
    """

    msg = (message or "").strip()
    if not msg:
        return None
    m = _TICK_SIZE_ERROR_RE.search(msg)
    if not m:
        return None
    try:
        tick = Decimal(m.group(1))
    except Exception:
        return None
    if tick <= 0:
        return None
    return tick


def round_price_to_tick_mode(
    price: Optional[float],
    *,
    tick_size: Decimal,
    mode: str,
) -> Optional[float]:
    """Round a price to a tick using a specific mode.

    mode:
      - "nearest": half-up to nearest tick
      - "floor": toward -inf to the next tick
      - "ceil": toward +inf to the next tick
    """

    if price is None:
        return None

    try:
        p = Decimal(str(price))
    except Exception:
        return price

    if tick_size <= 0:
        return float(p)

    mode_u = (mode or "").strip().lower()
    if mode_u == "nearest":
        rounding = ROUND_HALF_UP
    elif mode_u == "floor":
        rounding = ROUND_FLOOR
    elif mode_u == "ceil":
        rounding = ROUND_CEILING
    else:
        raise ValueError("Invalid mode for round_price_to_tick_mode.")

    ticks = (p / tick_size).to_integral_value(rounding=rounding)
    out = ticks * tick_size

    # Keep stable JSON floats; prefer at least 2 decimals and never fewer than tick's.
    tick_decimals = max(0, -int(tick_size.as_tuple().exponent))
    decimals = max(2, tick_decimals)
    q = Decimal("1").scaleb(-decimals)  # e.g. 0.01 for 2 decimals
    out = out.quantize(q, rounding=ROUND_HALF_UP)
    return float(out)


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


__all__ = [
    "DEFAULT_TICK_SIZE",
    "parse_tick_size_from_error",
    "round_price_to_tick",
    "round_price_to_tick_mode",
]
