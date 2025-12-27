# Execution backtest help (SigmaTrader)

Execution backtesting answers a simple question:

> “If I run a *portfolio strategy* (target weights / rotation / risk parity), how much difference do fills and costs make compared to an ideal backtest?”

This tab **does not change the strategy**. It re-runs the *same base portfolio backtest config* under two execution assumptions and compares the results.

---

## 1) What is a “Base portfolio run”?

The **Base portfolio run** is any **completed** `PORTFOLIO` backtest run you already executed in the Portfolio backtest tab.

SigmaTrader will take the base run’s portfolio config (method, cadence, window, etc.) and run two variants:

- **Ideal**
  - Fill timing: `CLOSE`
  - Slippage: `0`
  - Charges: `0` (manual/bps mode)
- **Realistic**
  - Uses the inputs you set in this dialog (fill timing + slippage + charges model)

So, you can see how much performance is “real” vs “backtest optimism”.

---

## 2) Dialog controls

### Preset
Quickly sets a reasonable combination of:
- Fill timing
- Slippage (bps)
- Charges (bps) (manual mode)

Use presets when you want a fast sanity-check without tuning numbers.

### Fill timing
Controls **when** an order is assumed to fill (in an EOD backtest):

- `Same day close (CLOSE)`
  - The strategy decides and executes at the end-of-day close.
  - Usually “optimistic” because in real life your fill may be worse than the official close.

- `Next day open (NEXT_OPEN)`
  - The strategy decides at the day’s close, but orders fill at the **next trading day open**.
  - This is often **more realistic** for EOD strategies.

### Slippage (bps)
An additional price impact on each trade:
- BUY fills at `price * (1 + slippage)`
- SELL fills at `price * (1 - slippage)`

**bps** = basis points. `10 bps = 0.10%`.

### Charges (bps)
SigmaTrader supports two charge models:

#### A) Broker estimate (recommended)
Estimates **India equity** charges per trade based on:
- Broker (`Zerodha` / `AngelOne`)
- Product (`CNC` delivery / `MIS` intraday)
- Side (BUY/SELL)
- Optional DP charges (delivery sells)

Includes (approx): brokerage, STT, exchange charges, SEBI, stamp duty (WB buy-side), GST, and optional DP.

#### B) Manual (bps)
Simple cost model applied per trade notional:
- charges = `abs(trade_notional) × (charges_bps/10000)`

Notes:
- Broker estimates are still approximations and rates can change.
- Manual bps is intentionally simple for quick sensitivity checks.

---

## 3) Outputs you should look at

### Equity curve (realistic vs ideal)
The chart overlays:
- **Realistic equity** (your chosen fill timing + costs)
- **Ideal equity** (CLOSE, 0 costs)

### Δ End equity / Δ End (%)
This shows the “execution penalty”:

- **Δ End equity** = `Realistic final equity - Ideal final equity`
- **Δ End (%)** = `Δ End equity / Ideal final equity`

Typically, these deltas are **negative** (costs and slippage reduce performance).

---

## 4) How to interpret results (practical guidance)

- If your strategy looks great in Ideal but weak in Realistic:
  - It may be too sensitive to turnover, costs, or the open/close gap.
  - Consider reducing turnover (lower rebalance frequency, wider bands, tighter trade filters).

- If Ideal and Realistic are close:
  - The strategy is more robust and less dependent on perfect fills.

---

## 5) Example

Suppose your base portfolio backtest ends with:
- Ideal end equity: `₹120,000`

After applying:
- Fill timing: `NEXT_OPEN`
- Slippage: `10 bps`
- Charges: `5 bps`

Realistic end equity becomes:
- `₹117,000`

Then:
- Δ End equity = `117,000 - 120,000 = -₹3,000`
- Δ End (%) = `-3,000 / 120,000 = -2.5%`

Interpretation:
- About **2.5%** of the backtest performance may be “lost” to execution assumptions and costs.
