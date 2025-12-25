# Portfolio Rebalancing (SigmaTrader) — Reference Notes

This document proposes a practical, maintainable approach to **periodic portfolio rebalancing** in SigmaTrader, including: rebalancing strategies, sizing/budgeting rules, candidate selection, constraints, scheduling, and what to store as rebalance history.

The goal is to support rebalancing in a way that is:
- predictable and explainable,
- configurable (so you can tune it over time),
- broker-aware (Zerodha + AngelOne simultaneously),
- safe (guardrails, preview, audit trail),
- and scalable (doesn’t explode in complexity for v1).

---

## 1) What “rebalance” means (choose the primary mode)

SigmaTrader can support multiple “rebalance modes”. Pick **one primary** for v1, then layer others later.

### A. Target-weight rebalance (recommended v1)
You have a portfolio definition (a Group kind `PORTFOLIO`) with target weights (or equal-weight default). Rebalancing brings the live holdings toward these targets.

Good for: model portfolios, long-term portfolios, systematic discipline, low maintenance.

### B. Signal/strategy-driven rebalance
Rebalancing rotates into/out of names based on strategy scores/signals (momentum, mean-reversion, quality). Targets are derived from ranking/score.

Good for: active rotation portfolios, alpha strategies.

### C. Risk-based rebalance (risk parity / risk contribution)
Rebalancing tries to keep each holding’s risk contribution stable (needs covariance/correlation; heavier).

Good for: risk-managed portfolios; generally “v2+”.

**Recommendation**: ship **A (target-weight + bands + budgeted trades)** first. It gives a stable base, and you can add B/C later without breaking UX or data model.

---

## 2) Core concepts & terminology

- **Target weights**: desired portfolio weight per symbol (summing to 100% or close).
- **Live weights**: current market-value weight from actual holdings.
- **Drift**: `live_weight - target_weight`.
- **Band / threshold**: drift tolerance to reduce churn.
- **Budgeted rebalance**: rebalance only up to X% of portfolio value (or INR).
- **Turnover**: sum of absolute buy+sell value / portfolio value.
- **Policy**: a named set of parameters that controls rebalance decisions.

---

## 3) Rebalancing triggers: ignore “today winners%” as a primary trigger

You raised a key point:
- A portfolio can have **x% winners overall** (since entry / since creation),
- while on a particular day it might show **y% winners today** (which may be very different).

**Important**: `y% winners today` is often noisy (market regime, gap moves, single-day spikes). If used as a primary rebalance trigger, it tends to cause over-trading and whipsaw.

Instead:
- Use **drift from target** as the primary trigger.
- Use “today winners/losers” only as optional **bias** (tilt buys vs sells) *after* drift-based trades are computed.

---

## 4) Recommended v1 rebalance policy (target-weight + drift bands + budget)

### 4.1 Compute “desired trades”
For each symbol `i` in the portfolio definition:

1. Compute `current_value_i` from holdings (qty × LTP).
2. Compute `portfolio_value = Σ current_value_i + cash` (cash optional v1).
3. Compute `live_weight_i = current_value_i / portfolio_value`.
4. Compute `target_weight_i`.
5. Compute `drift_i = live_weight_i - target_weight_i`.
6. Compute `desired_value_i = target_weight_i * portfolio_value`.
7. Compute `delta_value_i = desired_value_i - current_value_i`:
   - `delta_value_i > 0` means BUY this value,
   - `delta_value_i < 0` means SELL this value.

### 4.2 Apply drift bands (reduce churn)
Only generate trades when drift is “meaningfully” outside tolerance:

- **Absolute band**: e.g. `abs(drift_i) >= 2%` (0.02).
- **Relative band**: e.g. `abs(drift_i) >= 15% of target_weight_i`.

For v1, keep it simple:
- `abs(drift_i) >= 2%` OR `abs(drift_i) >= 0.15 * target_weight_i` (configurable).

### 4.3 Budgeted scaling (your “rebalance x% of portfolio value”)
Let `budget = rebalance_budget_pct * portfolio_value` (or fixed INR).

Compute:
- `total_buy = Σ max(delta_value_i, 0)` (after bands),
- `total_sell = Σ max(-delta_value_i, 0)`.

Then scale all trade deltas by a factor:
- `scale = min(1, budget / max(total_buy, total_sell))` (or use `min(1, budget / total_turnover)` depending on definition).

Final trade value:
- `trade_value_i = delta_value_i * scale`.

This approach:
- keeps trades proportional,
- respects a strict budget,
- and avoids “partial logic” where you rebalance only some names without a coherent rule.

### 4.4 Convert value to qty
For each symbol:
- `qty = floor(trade_value_i / LTP)` with `qty >= 1` constraint for buys, and `qty <= holdings_qty` for sells.

If rounding causes the budget to deviate, apply a small reconciliation:
- adjust the smallest trades down to keep within budget.

---

## 5) Winner/loser logic: how to incorporate it (optional bias knobs)

You want policies like “how much profit to realize”, “rebalance winners vs losers”, etc.

Treat these as *optional overlays* on top of drift-based rebalancing:

### 5.1 Profit-taking overlay (optional)
If a holding is a winner and over target:
- allow a slightly stronger sell allocation.

Example rule:
- If `total_pnl_pct >= +X%` AND `drift_i > 0`, then multiply sell `trade_value_i` by `(1 + profit_take_boost)` within budget.

### 5.2 Loss-trimming overlay (optional)
If a holding is a loser and under target:
- you may choose either to buy more (mean-reversion) or avoid adding to losers.

This is a key philosophical choice:
- **Mean-reversion tilt**: buy losers when they’re underweight.
- **Momentum tilt**: avoid losers; rebalance by trimming winners less aggressively.

Make it a policy switch:
- `tilt_mode = neutral | mean_reversion | momentum`

### 5.3 Using “today winners%” as a macro bias (optional)
If `today winners%` is unusually high:
- allow more profit-taking (increase sells slightly).
If it’s unusually low:
- allow more buy scaling (within budget).

But this should never override core constraints (budget, max trades, drift bands).

---

## 6) What can be bought/sold during rebalance (universes)

### 6.1 In-portfolio-only rebalance (recommended v1)
Only buy/sell among symbols already in the portfolio group.

This keeps:
- predictable outcomes,
- minimal UX complexity,
- and a stable “target weights” interpretation.

### 6.2 Allow “replacement” from other groups (v2)
Allow adding new symbols during rebalance from:
- a “replacement universe group” (watchlist/basket),
- or a “screener run top-N”.

If you allow replacements, define:
- when to replace (sell rule),
- and how to pick replacements (rank rule).

---

## 7) Constraints and guardrails (high value, low complexity)

Recommended v1 constraints:
- **Max trades**: e.g. 10 per rebalance.
- **Min trade value**: e.g. ₹2,000 to avoid tiny dust trades.
- **Max position weight**: e.g. 15% per symbol.
- **No-buy list / no-sell list**: optional (manual overrides).
- **Respect broker constraints**: integer qty, CNC/MIS, allowed exchanges, etc.

Risk/valuation constraints (optional, later):
- Keep portfolio beta within range (e.g. 0.8–1.2).
- Keep portfolio alpha above threshold.
- Sector constraints (needs sector metadata).
- PE/valuation constraints (needs fundamentals source).

---

## 8) Scheduling: “next rebalance opportunity”

Each portfolio group should show:
- `last_rebalanced_at`
- `next_rebalance_at` (computed and shown)

Recommended schedule configuration:
- Frequency: `weekly | monthly | quarterly | custom_days`
- Optional “day rule”: e.g. `Friday` for weekly or `last trading day` for monthly.
- Execution time: e.g. `15:10` (local)
- Timezone: `Asia/Kolkata`

Trading-day adjustment:
- If scheduled time lands on weekend/holiday, roll to next trading day (or previous, configurable).

---

## 9) Rebalance history: what to store (audit + learning)

You explicitly want rebalance history. Treat each run like a first-class “RebalanceRun”.

Store:
- **Metadata**: `group_id`, `created_at`, `executed_at`, `status`, `initiator` (manual/auto), `broker_scope` (all brokers vs specific).
- **Policy snapshot**: all parameters used (bands, budget, max trades, tilt mode, etc.).
- **Inputs snapshot**:
  - portfolio value estimate,
  - cash available (if used),
  - holdings snapshot (symbol, qty, price, value, weight, pnl metrics),
  - target weights.
- **Proposed orders**:
  - symbol, side, qty, price type, estimated notional,
  - reason tags (drift, profit-taking, replacement, etc.).
- **Execution outcome**:
  - created orders, broker order ids, failures/errors,
  - partial fills (if tracked), final status.
- **Summary metrics**:
  - turnover %, max drift before/after, #trades, %budget used.

This makes the system explainable and debuggable over time.

---

## 10) Multi-broker considerations (Zerodha + AngelOne simultaneously)

You want both brokers active. There are 3 viable approaches:

### A. Rebalance per broker (recommended v1)
Each broker has its own holdings and cash; run rebalance separately:
- `Group targets` are broker-agnostic,
- but execution is broker-scoped (place orders per broker).

Pros: clean accounting, fewer surprises.
Cons: two separate rebalances if user uses both brokers.

### B. Combined portfolio (advanced)
Compute combined weights across brokers then allocate trades across brokers.

Pros: “single portfolio view”.
Cons: hard: cash split, execution routing, mapping, and partial availability.

**Recommendation**: v1: **broker-specific rebalance** with a UI toggle:
- “Rebalance broker: Zerodha / AngelOne / Both (run separately)”

---

## 11) UI / UX proposal (v1)

On a portfolio group view:

### 11.1 Rebalance card/panel
- Next rebalance: date/time + countdown (optional)
- Last rebalance: date/time + status
- Buttons:
  - `Preview rebalance`
  - `Run now`
  - `History`

### 11.2 Preview dialog
- Parameters:
  - budget (% or INR),
  - drift band,
  - max trades,
  - broker selection (Zerodha/AngelOne/Both).
- Proposed trade list with:
  - before/after weight, qty, notional,
  - filter “buys only / sells only”.
- Confirm → creates orders (manual queue or auto broker, depending on execution mode).

### 11.3 History tab
Table: run id, created at, policy name, turnover, drift reduced, status, “View details”.

---

## 12) Suggested default policy values (starter)

These should be **configurable settings** (per portfolio, with global defaults).

- `rebalance_frequency`: monthly
- `rebalance_time_local`: 15:10
- `rebalance_budget_pct`: 10%
- `drift_band_abs_pct`: 2%
- `drift_band_rel_pct`: 15%
- `max_trades`: 10
- `min_trade_value_inr`: 2000
- `tilt_mode`: neutral
- `profit_take_threshold_pct`: 20% (off by default)
- `profit_take_boost_pct`: 20% (if enabled)

---

## 13) Open questions (to resolve before implementation)

1) **Target weights source**
- Are target weights mandatory for `PORTFOLIO` groups?
- If missing, should we default to equal-weight for members?

2) **Cash modeling**
- Should cash be included as a “position” (target cash%), or assume fully invested?
- If broker cash differs (Zerodha vs AngelOne), do we show cash per broker only?

3) **Scope of rebalance**
- Portfolio-only trades (recommended v1), or allow adding/removing symbols from a replacement universe?

4) **Execution path**
- Manual queue vs Auto broker execution for rebalances?
- If Auto, should we “dry-run/preview” always before submitting?

5) **Tax/holding period**
- Do we want constraints like “don’t sell positions held < N days”?

6) **Metric definitions**
- Winners/losers: based on `total_pnl_percent` (since entry) vs group reference price vs last rebalance?
- For rebalancing, “since last rebalance” is often the most meaningful, but requires history snapshots.

---

## 14) Practical recommendation to start (v1)

Implement:
- Target-weight rebalance with drift bands + budget scaling + max trades + min trade value.
- Per-broker execution (Zerodha/AngelOne/Both separately).
- Full rebalance preview + run history log.

Defer:
- replacement universe,
- PE/fundamental constraints,
- risk parity / covariance heavy logic,
- combined multi-broker allocation.

