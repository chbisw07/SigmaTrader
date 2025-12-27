from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BrokerName = Literal["zerodha", "angelone"]
ProductType = Literal["CNC", "MIS"]
Side = Literal["BUY", "SELL"]
Exchange = Literal["NSE", "BSE"]
StampDutyState = Literal["WEST_BENGAL"]


@dataclass(frozen=True)
class ChargeBreakdown:
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp_duty: float
    gst: float
    dp: float

    @property
    def total(self) -> float:
        return float(
            self.brokerage
            + self.stt
            + self.exchange_txn
            + self.sebi
            + self.stamp_duty
            + self.gst
            + self.dp
        )


def _clamp_nonneg(x: float) -> float:
    return float(x) if x > 0 else 0.0


def _pct(turnover: float, bps: float) -> float:
    return _clamp_nonneg(turnover) * (float(bps) / 10000.0)


def estimate_india_equity_charges(
    *,
    broker: BrokerName,
    product: ProductType,
    side: Side,
    exchange: Exchange,
    turnover: float,
    stamp_state: StampDutyState = "WEST_BENGAL",
    include_dp: bool = True,
) -> ChargeBreakdown:
    """Estimate Indian equity charges (approx).

    This is an approximate calculator intended for backtesting.
    Rates can change; keep values centralized here for easy updates.
    """

    t = _clamp_nonneg(float(turnover))
    side_u = side.upper()
    ex_u = exchange.upper()

    broker_l = str(broker).lower()

    # Brokerage (approx; keep broker-specific knobs centralized here).
    # NOTE: These are *approximate* backtest defaults, not guaranteed broker rate cards.
    # For delivery (CNC), most discount brokers charge 0 brokerage.
    # For intraday (MIS), many charge ~0.03% with a ₹20 cap per order.
    if product == "CNC":
        brokerage_rate = 0.0
        brokerage_cap = 0.0
    else:
        # Default discount-broker intraday.
        brokerage_rate = 0.0003
        brokerage_cap = 20.0

        # Broker-specific overrides (only where they differ).
        if broker_l == "angelone":
            brokerage_rate = 0.0003
            brokerage_cap = 20.0

    brokerage = (
        min(t * brokerage_rate, brokerage_cap)
        if brokerage_cap > 0
        else t * brokerage_rate
    )

    # Exchange transaction charges (NSE/BSE equity).
    # Approx: NSE 0.00322%, BSE 0.0030% of turnover.
    exchange_txn = t * (0.0000322 if ex_u == "NSE" else 0.00003)

    # SEBI charges: ~₹10 per crore => 0.000001 of turnover.
    sebi = t * 0.000001

    # STT:
    # - CNC delivery: 0.1% on both buy and sell.
    # - MIS intraday: 0.025% on sell only.
    if product == "CNC":
        stt = t * 0.001
    else:
        stt = t * 0.00025 if side_u == "SELL" else 0.0

    # Stamp duty: buy-side, varies by state.
    # West Bengal (approx):
    # - Delivery: 0.015% (0.00015)
    # - Intraday: 0.003% (0.00003)
    if side_u == "BUY":
        if stamp_state == "WEST_BENGAL":
            stamp_duty = t * (0.00015 if product == "CNC" else 0.00003)
        else:
            stamp_duty = 0.0
    else:
        stamp_duty = 0.0

    # DP charges: delivery sells only (fixed per scrip, approx incl GST).
    dp_charge = 15.93
    if broker_l == "angelone":
        dp_charge = 15.93
    dp = dp_charge if include_dp and product == "CNC" and side_u == "SELL" else 0.0

    # GST: 18% on (brokerage + exchange + sebi). Not on STT/stamp/DP.
    gst_base = brokerage + exchange_txn + sebi
    gst = gst_base * 0.18

    return ChargeBreakdown(
        brokerage=float(brokerage),
        stt=float(stt),
        exchange_txn=float(exchange_txn),
        sebi=float(sebi),
        stamp_duty=float(stamp_duty),
        gst=float(gst),
        dp=float(dp),
    )


__all__ = [
    "BrokerName",
    "ChargeBreakdown",
    "Exchange",
    "ProductType",
    "Side",
    "StampDutyState",
    "estimate_india_equity_charges",
]
