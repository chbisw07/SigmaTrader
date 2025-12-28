# Backtesting v2 (SigmaTrader) — Group Index + Basket Strategy Design

This document captures the v2 backtesting direction discussed after implementing **Strategy backtest (Entry/Exit)**.
It is intended to be a long-term reference for:
- the intuition behind the design,
- the key edge cases (especially missing OHLCV),
- the final arrangement we plan to implement,
- and why it benefits real users (Smallcase + multi-portfolio realities).

---

## 1) Why Backtesting v2 is needed

Backtesting v1 already supports:
- **Signal backtest (EOD)**: “when condition is true, what happens next?”
- **Portfolio backtest**: target weights / rotation / risk parity (EOD), with costs and turnover.
- **Execution backtest**: fill timing + slippage + charges.
- **Strategy backtest (Entry/Exit)**: TradingView-like entry/exit rules for a **single symbol**, with close→next-open fills.

What’s still missing for “real-world portfolio decision making” is the ability to:
- treat a **Group** as an “index-like object” (for regime/timing decisions),
- and/or trade an entire **basket** (group constituents) based on entry/exit rules.

This v2 design adds those capabilities with explicit assumptions and guardrails.

---

## 2) The key conceptual split: Signal source vs Execution target

Backtesting becomes robust and unambiguous if we explicitly separate:

### A) Signal source (what produces Entry/Exit triggers)
- **Symbol**: a single tradable instrument (stock / ETF / index symbol).
- **Index symbol**: still a symbol, just an index/ETF that is tradable (same as above).
- **Synthetic Group Index**: computed from constituent OHLCV (not a single tradable instrument).

### B) Execution target (what is actually bought/sold)
- **Single instrument** (one symbol).
- **Basket** (trade the group constituents as multiple orders).
- (Future) **Multi-basket / rotate / risk-off group**.

This split prevents confusion such as “I selected a group—am I trading the group, or a symbol inside it?”

---

## 3) Synthetic Group Index: what it is (and what it is not)

### What it is
A deterministic time series computed from constituent OHLCV that behaves like an “index level”, so you can compute:
- RSI / MA / crossovers / other indicators
- regime signals like “oversold / overbought”
- trend filters like MA(50) > MA(200)

### What it is not
A tradable single instrument.

Even with perfect OHLCV for all constituents, the group index is still a *derived* series.
Trading it requires executing a **basket** (multiple buy/sell orders).

SigmaTrader v2 embraces this explicitly:
- “Index” can be used as a **signal source**
- “Basket” is the **execution target**

---

## 4) Index construction choices (agreed direction)

We will support two index families depending on what the group represents.

### 4.1 Basket groups (Watchlist/Basket): equal-weight returns index (agreed)

Use an equal-weight returns index:
- Compute each member’s return per bar.
- Index return is the average of available members’ returns.
- Index level compounds from a base (e.g., 100).

This matches the “shallow view” of a basket: treat all atoms equally unless you explicitly choose custom weights.

### 4.2 Holdings/Portfolio: weight-based index (agreed)

For holdings/portfolio, index should reflect the portfolio’s intended or actual composition:

- **Portfolio group**: use stored portfolio weights (e.g., `target_weight` as the baseline).
- **Holdings universe**: use value weights derived from holdings at the chosen start date (or equivalent snapshot), when applicable.

This yields an index that aligns with how the portfolio “should” behave, not just equal-weight.

---

## 5) Missing OHLCV: the biggest practical reality (and the v2 rule)

It is highly probable that one or more constituents will not have full OHLCV coverage over the full backtest window.

Example:
- You have N constituents.
- For 2 constituents, data is missing for `[T_start, T+k]`, but present for `[T+k+1, T_end]`.

### v2 Rule (agreed): dynamic availability set

At any time `T`:
- The index is computed using only the **available** constituents at `T`.
- When missing constituents become available later, they are included from that point onward.

So:
- Index uses `N-2` stocks for `[T_start, T+k]`
- Index uses `N` stocks for `[T+k+1, T_end]`

### Why this works (and its tradeoff)

This keeps the index continuous without “hard failing” due to missing data.

However, it implies the index composition can change over time due to data availability.
This can introduce bias if missing constituents are systematically different (illiquid, recently listed, etc.).

Therefore v2 must include:
- transparency (coverage metrics),
- and guardrails (a configurable minimum coverage threshold).

### 5.1 Minimum coverage threshold (configurable; default 90%)

Because missing data can distort indicators (RSI/MA) and create misleading entries/exits, Backtesting v2 will use a
**minimum coverage threshold** to decide when synthetic-index signals are “trustworthy enough”.

- Default: **90%**
- Configurable in UI (advanced setting).

Interpretation:
- If coverage at time `T` is **≥ threshold** → compute/update index and evaluate Entry/Exit signals.
- If coverage at time `T` is **< threshold** → skip signal evaluation for that bar (and record that the bar was “below threshold”).

Coverage definition:
- **Equal-weight basket index**: `coverage = available_members / total_members`.
- **Weight-based index**: `coverage = sum(weights of available members)`.

---

## 6) Exact computation rules (so results are deterministic)

### 6.1 Equal-weight returns index (basket)

Let `A(T)` be the set of constituents with valid candles at time `T` and previous candle at `T-1`.

For each symbol `i` in `A(T)`:
- `r_i(T) = close_i(T) / close_i(T-1) - 1`

Index return:
- `r_idx(T) = average(r_i(T) for i in A(T))`

Index level (base = 100):
- `I(T_start) = 100`
- `I(T) = I(T-1) * (1 + r_idx(T))`

Notes:
- Indicators like RSI require a consistent close series; this gives it.
- For charting, we can construct OHLC minimally as `open=high=low=close=I(T)` (v1), then extend later if needed.

### 6.2 Weight-based index (portfolio/holdings)

Let baseline weights be `w_i` (sum to 1 over all constituents).
Let `A(T)` be available constituents at `T`.

Coverage at `T`:
- `coverage(T) = sum(w_i for i in A(T))`

Normalized effective weights:
- `w_i_eff(T) = w_i / coverage(T)` for `i in A(T)`

Member returns:
- `r_i(T) = close_i(T) / close_i(T-1) - 1`

Index return:
- `r_idx(T) = sum(w_i_eff(T) * r_i(T) for i in A(T))`

Index level compounds as above.

This exactly implements the rule “use only available stocks, but preserve the intended weight structure among the available set.”

---

## 7) UX: how users should experience this (to avoid confusion)

### 7.1 New Backtesting v2 surface areas

We should expose Group index behavior clearly via either:
- a new **Basket Strategy** tab, OR
- an expanded **Portfolio backtest** tab with “Gate signal” and “Index source” controls.

Recommended:
1) **Index analytics first** (EOD): show synthetic index chart + indicator values + coverage stats.
2) Add **Gate/Regime filter** to portfolio backtests (highest ROI).
3) Add full **Basket Entry/Exit Strategy** backtest (basket trading engine).

### 7.2 Controls needed (minimal, but explicit)

**Signal source**
- Type: `Symbol` | `Index symbol` | `Synthetic group index`
- If synthetic: choose group + index method:
  - Basket → Equal-weight returns (default)
  - Portfolio/Holdings → Weight-based (default)

**Missing data policy**
- Default: dynamic availability set (as described).
- Show:
  - “members used” (count)
  - “coverage” (for weight-based)
  - missing list (optional)
- Guardrail (recommended; default 90%):
  - “Minimum coverage % (default 90%)”
  - If coverage below threshold, skip signal evaluation for that bar.

**Execution target**
- Single symbol (existing strategy backtest)
- Basket (new):
  - Allocation mode: equal/custom weights OR equal/custom cash
  - Min trade value, max trades, slippage, costs

**Entry/Exit meaning for basket (agreed)**
- ENTRY = buy the basket (allocate)
- EXIT = sell the basket (de-allocate to cash)
- Resulting cash can later be used for other groups (future enhancement), but v2 core is “cash on exit”.

---

## 8) Corner cases & how v2 handles them

### A) Not enough cash to build the basket
When ENTRY triggers:
- compute target allocations
- translate to share quantities (integers)
- if cash is insufficient, do best-effort buying:
  - prioritize larger allocations first OR proportional rounding (to be defined)
- keep leftover cash (“cash drag”) and report it.

### B) Tiny allocations causing noise
Use `min_trade_value` (already a proven control in portfolio backtests).

### C) Thrashing (rapid entry/exit, high turnover)
This will show up as:
- high turnover %
- high total charges

We should highlight turnover and costs prominently and optionally add a “cooldown bars” later.

### D) Portfolio membership changes over history (survivorship bias)
If group membership and weights are taken from “today” for the whole history, results can be biased.

v2 should label clearly:
- “Uses current basket definition for full history (approx)”

Future v3:
- store membership snapshots over time (“as-of” group definition).

### E) Intraday scale
Synthetic index intraday requires large data and is more likely to have missing bars.

v2 recommendation:
- implement synthetic index for **EOD first**, then expand to intraday after caching is added.

---

## 9) Implementation plan (v2) — recommended phases

### Phase 1: Synthetic index (EOD) + transparency
- Build synthetic index close series from constituent EOD candles.
- Store or cache computed index series (so repeated runs are fast).
- Provide coverage metrics per bar:
  - equal-weight: `members_used / members_total`
  - weight-based: `coverage_pct` and members_used
- Add “Minimum coverage %” setting (default **90%**) to suppress signals on low-coverage bars.

### Phase 2: Gate/Regime filter for Portfolio backtests
- Add optional “Gate DSL” evaluated on:
  - index symbol OR synthetic group index
- On each rebalance date:
  - if gate false → skip rebalance (or “sell-only” later)
  - if gate true → execute rebalance as usual

This is high ROI and fits SigmaTrader’s current architecture well.

### Phase 3: Basket Entry/Exit Strategy backtest (new engine)
- Uses synthetic index (or symbol) as signal source.
- Trades group constituents as execution target:
  - Entry allocates to basket
  - Exit de-allocates to cash
- Reuse existing slippage + India charges model.
- Provide outputs:
  - equity curve, drawdown
  - turnover, total charges
  - trades list + “basket composition through time”

---

## 10) Why this arrangement benefits users

This v2 design:
- matches how real users think about Smallcases/portfolios (“theme timing”),
- handles real data gaps without silently breaking or lying,
- remains transparent about assumptions (coverage and membership),
- reuses proven portfolio execution controls (budget, min trade value, costs),
- and supports both “shallow” (basket as index-like) and “deep” (index as gate for rebalance) views.

It is a practical “decision tool” rather than a fragile academic backtester.
