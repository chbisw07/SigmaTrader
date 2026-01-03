# Portfolio‑Level Strategy Backtest (Group Entry/Exit) — Design Reference

This document defines the intended behavior and UX for a **portfolio‑level strategy backtest** in SigmaTrader.

Unlike the current **Strategy backtest** (single symbol), this mode runs the **same Entry/Exit logic across a group of symbols** while sharing a single capital pool (cash), so trades **compete for funds**.

---

## 1) Intent (what question this answers)

> “If I traded a **set of stocks** using the same Entry/Exit rules, with realistic cash constraints and basic risk controls, what would my **portfolio equity curve** and **trade history** look like?”

Key differences vs single‑symbol strategy backtest:
- You trade **many symbols** concurrently.
- You have **shared cash** (funds available), so not every signal can be taken.
- Portfolio performance is the **combined** effect of all positions and costs.

---

## 2) Core concepts & notation

- Group `G = {s1…sn}`: a set of symbols selected via SigmaTrader Groups.
- `TF`: timeframe (e.g., `1d`, `1h`, `15m`).
- `D`: backtest date range (start→end).
- `cash`: funds available for new buys (starts at `initial_cash`).
- `positions`: open positions keyed by symbol (at most one position per symbol by default).
- `equity(t) = cash(t) + Σ position_value_i(t)` using mark‑to‑market prices.

We assume a TradingView‑style execution model:
- **Evaluate at close**, **fill at next open** (to avoid lookahead bias).

---

## 3) High‑level simulation loop (per bar)

For each bar `t` in the chosen range at timeframe `TF`:

1) **Update equity** using bar prices (mark‑to‑market).
2) **Process exits first** (free cash before considering new entries):
   - For each symbol with an open position:
     - If `exit_dsl(symbol, t)` is true (or stop/risk rule triggers), schedule/execute exit at **next open** (per fill timing).
3) **Determine entry candidates**:
   - For each symbol without an open position:
     - If `entry_dsl(symbol, t)` is true, mark as entry candidate.
4) **Select entries + size positions** based on allocation + sizing policy (see below).
5) **Apply fills** (next‑open) and update:
   - Decrease `cash` for buys, increase `cash` for sells.
   - Record trades, costs, and reasons.

Note: In implementation we model fills at the next bar’s open; the loop above is the conceptual order.

---

## 4) Execution model (agreed)

### 4.1 Evaluate at close, fill at next open
- Entry/exit conditions are evaluated using information available up to the bar close.
- Orders are filled at the next bar open (plus slippage/costs).

### 4.2 Product constraints (India equities)
- **CNC (delivery)**: long‑only.
- **MIS (intraday)**: long/short allowed; positions are **forced to square‑off end‑of‑day** (consistent with current strategy backtest rules).

---

## 5) Capital allocation & position sizing (tunable options)

This backtest needs two separate policies:
1) **Entry selection**: which candidates get filled when there are many.
2) **Sizing**: how much capital is assigned per filled entry.

### 5.1 Entry selection policy

**A) Equal weight (random‑free deterministic)**
- If multiple symbols trigger entries on the same bar, fill in a deterministic order:
  - e.g., sort by `exchange:symbol` and take the first `k` allowed by constraints.
- Capital assignment is handled by the sizing policy.

**B) Ranking‑based**
- If multiple symbols trigger entries, sort by a **score** and fill highest score first.
- Ranking score options (proposal):
  - `ranking_dsl` numeric expression (preferred, explicit).
  - Or a small set of built‑in “strength” heuristics for common indicators (optional).

This enables “strongest signal gets capital first”.

### 5.2 Sizing policy (qty rule)

**A) Percent of current equity (TradingView‑style)**
- Per new entry, allocate:
  - `trade_budget = equity(t) × position_size_pct / 100`
- Convert to quantity using next‑open price and integer share rounding.
- Enforce available cash: if `cash < trade_budget`, size down or skip (policy choice; default: size down to available cash).

**B) Fixed cash per trade**
- Per new entry, allocate:
  - `trade_budget = fixed_cash_per_trade`
- Enforce available cash; size down or skip.

**C) “Use all available up to max positions” (clarified)**
- Interpret “use all available” as **spreading remaining cash across remaining slots**:
  - Let `slots_remaining = max_open_positions − open_positions_count`
  - Let `budget_per_slot = cash / max(1, slots_remaining)`
  - For each new fill (in chosen entry order), allocate `budget_per_slot` (recompute as cash changes, or compute once per bar; default: compute once per bar for determinism).

This is a portfolio‑friendly version of “all‑in”, but still respects diversification and `max_open_positions`.

---

## 6) Constraints & risk controls

### 6.1 Max concurrent positions (required)
- `max_open_positions` limits total open positions across the whole group.
- Default: **10**.

### 6.2 Min holding period (optional)
- Enforce `min_holding_bars` before an exit signal can close the position.
- Prevents “flip‑flopping” on noisy signals.

### 6.3 Per‑symbol cooldown (optional; clarification)
- After a symbol exits, block new entries for that symbol for `cooldown_bars`.
- Example: `cooldown_bars = 3` on `15m` means “wait 45 minutes after exit before re‑entering the same symbol”.
- This reduces churn in sideways regimes.

### 6.4 Max allocation per symbol (optional)
- Limit exposure to any one symbol:
  - `position_value(symbol) ≤ equity × max_symbol_alloc_pct / 100`
- Helps prevent one symbol dominating portfolio risk.

### 6.5 Sector caps (advanced; clarification)
- Limit exposure per sector:
  - `sector_value(sector) ≤ equity × sector_cap_pct / 100`
- Requires symbol→sector mapping.
  - Implementation choices: manual tagging in Groups, built‑in mapping file, or external provider (later).
- Recommended as “Advanced settings”.

### 6.6 Costs, slippage, and DP charges
- Use the same costs/slippage models already present in strategy/portfolio backtests:
  - Slippage in bps on fills.
  - Charges: broker estimate or manual bps.
  - DP charges (delivery sells) optional for CNC.

### 6.7 Equity drawdown controls (optional)
Carry over the existing strategy backtest concepts:
- Max equity DD (global): kill‑switch for new entries after breach.
- Max equity DD (per‑trade): exit when trade‑level equity drawdown breaches.

---

## 7) Ordering rules (agreed)

- On a bar where both exits and new entries are possible:
  - **Exits are processed first**, then entries are considered.
- Same‑day re‑entry:
  - Allowed for `TF < 1d` (intraday).
  - For `TF = 1d`, “same‑day” doesn’t apply because fills happen at next day open.

---

## 8) Outputs & visualization (what users will see)

### 8.1 Primary (portfolio‑level)
- **Combined equity curve** (single line).
- **Combined drawdown curve**.
- Summary chips similar to single‑symbol strategy backtest:
  - Total return, CAGR, Max DD, turnover, charges, trade count, win‑rate, profit.

### 8.2 Symbol activity on the combined curve
- Show entry/exit markers on the combined equity chart:
  - Markers labeled by symbol (filterable).
  - Only symbols that actually traded appear in the legend/markers.

### 8.3 Per‑symbol drilldown
- A per‑symbol table of:
  - trades, total P&L, win rate, max drawdown contribution (optional), time‑in‑market.
- Optional per‑symbol equity curve overlays:
  - Select symbols from a list to overlay (avoid visual clutter with 50+ symbols).

### 8.4 Trade blotter
- Single unified trades table including:
  - symbol, entry/exit time, side, qty, P&L %, exit reason, costs.
- Export CSV.

---

## 9) Proposed UI placement (separate tab)

Add a dedicated tab on Backtesting page:
- **“Portfolio strategy backtest”** (or “Group strategy backtest”)

This avoids overloading:
- “Strategy backtest” remains single‑symbol and simple.
- “Portfolio strategy backtest” becomes the multi‑symbol, capital‑constrained variant.

### 9.1 Inputs (left card) — suggested sections
- Universe: Group (and optionally Holdings/Both later)
- Group selector
- Timeframe `TF`
- Entry DSL / Exit DSL
- Product (CNC/MIS) and Direction (LONG/SHORT where allowed)
- **Allocation**
  - Entry selection: Equal / Ranking
  - (If ranking) ranking score DSL
- **Sizing**
  - % equity / fixed cash / cash‑per‑slot (“use all available up to max positions”)
- **Risk controls**
  - max open positions (default 10)
  - optional advanced: cooldown, min hold, max symbol alloc, sector caps
- Costs: slippage + charges model

### 9.2 Results (center) + Details (right drawer)
- Results list stays in the center.
- Detailed charts + tables open in the right drawer (consistent with Strategy/Portfolio drawer UX).

---

## 10) Open questions / future extensions

- Ranking score DSL: define numeric DSL semantics and common examples.
- Handling missing candles for some symbols:
  - Skip evaluation vs skip trading vs reduce coverage warnings.
- Sector mapping source and UI for tagging.
- Performance for large groups + intraday TF:
  - caching and downsampling strategies.

