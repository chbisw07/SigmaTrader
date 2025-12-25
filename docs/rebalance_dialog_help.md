# Rebalance Dialog Help (SigmaTrader)

This help is designed to remove every doubt you might have before using rebalancing.
It explains:
- what each rebalance mode does (and when to use which),
- what every input means,
- how the preview table is calculated,
- and how to interpret the results safely.

SigmaTrader rebalancing is designed to be:
- **Explainable**: you can trace each trade back to a target + drift.
- **Budgeted**: you can cap how much is traded.
- **Guardrailed**: drift bands, max trades, and min trade value reduce churn.

## Overview

### What “rebalance” means

Rebalancing is the act of moving your portfolio from its **current (“live”) weights** toward a **desired (“target”) allocation**.

In SigmaTrader:
- A **symbol’s value** is estimated as `qty × price`.
- **Portfolio value** is the sum of symbol values (cash is not modeled explicitly in v1).
- **Live weight** is `symbol_value / portfolio_value`.
- A rebalance proposes BUY/SELL orders that reduce the drift from target.

### Scope (where the rebalance applies)

SigmaTrader supports two scopes:
- **Group rebalance** (`target_kind=GROUP`): you rebalance the selected group (usually a `PORTFOLIO`).
- **Holdings rebalance** (`target_kind=HOLDINGS`): you rebalance your broker holdings universe (no saved targets).

### Rebalance methods (modes)

For `PORTFOLIO` groups, SigmaTrader supports 3 methods:
1) **Target weights**: “I already know my target weights.”
2) **Signal rotation**: “Pick top-N by a strategy signal and rotate into them.”
3) **Risk parity**: “Allocate weights so each symbol contributes similar risk.”

For holdings-universe rebalancing, SigmaTrader uses **Target weights** with an **equal-weight target**.

## Target weights

### When to use

Use this when you already have a desired allocation:
- you want stable weights (e.g., 30/30/40),
- you want to rebalance periodically,
- you want to slowly nudge the portfolio back to plan without over-trading.

### How targets are defined

**A) Group kind = `PORTFOLIO`**
- Targets come from the portfolio group members’ `target_weight`.
- If some weights are missing, SigmaTrader distributes leftover weight across unspecified members.
- If the sum of weights is above 1.0, SigmaTrader normalizes them back down to 1.0.

**B) Group kind = `HOLDINGS_VIEW` or target_kind=`HOLDINGS`**
- There are no saved targets.
- SigmaTrader assumes **equal-weight** across symbols in scope.

### What you should expect in preview

- Overweight symbols → mostly `SELL`.
- Underweight symbols → mostly `BUY`.
- If drift bands are set, small drifts are ignored (no trade).
- If the budget is small, trades are scaled down proportionally.

## Signal rotation

### The idea (what you are trying to achieve)

Signal rotation is a “switching” rebalance:
- you define a **candidate universe** (a group or a screener run),
- a **signal strategy output** ranks every candidate symbol,
- SigmaTrader selects **Top N** symbols as the “desired holdings”,
- SigmaTrader converts that selection into target weights (equal, score-based, or rank-based),
- then runs the same rebalance planner (budget + bands + constraints).

This is useful when your portfolio is meant to follow a strategy (momentum, relative strength, trend, etc.).

### Requirements

- You must pick a **Signal Strategy version** and an **OVERLAY output** (numeric).
- The OVERLAY output is treated as a **score**:
  - higher score ⇒ better rank ⇒ higher chance to be in Top N.

Tip: if your DSL needs a timeframe, define it as a strategy input and use it like:
```
TF = "1d"
score = CLOSE(TF)
```

### Universe selection (where candidates come from)

You can provide exactly one:
- **Universe group (optional)**: any group whose members form the candidate list.
- **Screener run id (optional)**: uses only the `matched=true` results from that screener run.

If you provide neither, SigmaTrader uses the current **portfolio group members** as the universe.

### Top N and weighting

- **Top N**: number of symbols selected after ranking.
- **Weighting**:
  - **Equal**: each selected symbol gets `1/N`.
  - **Score-proportional**: weights proportional to positive scores.
  - **Rank-based**: higher rank gets higher weight.

### Replacement rules and filters

These are the “guardrails” that make rotation controllable:
- **Sell positions not in Top N**:
  - ON: symbols outside Top N get target weight = 0 ⇒ the rebalance will try to sell them.
  - OFF: symbols outside Top N keep their existing group targets (rotation acts only on the selected ones).
- **Require positive score**:
  - ON: score must be `> 0` to be eligible.
- **Min price** (optional):
  - candidates with close price below this are excluded.
- **Min avg volume 20d** (optional):
  - candidates with low liquidity are excluded.
- **Whitelist / Blacklist**:
  - whitelist keeps only those symbols,
  - blacklist removes those symbols.

### What you should expect in preview

- Buys for newly selected symbols.
- Sells for symbols being rotated out (if “Sell not in Top N” is ON).
- Trade reasons include `rotation` metadata so you can explain “why is this being sold/bought?”.

## Risk parity

### The idea (what you are trying to achieve)

Risk parity (equal risk contribution, ERC) is a risk-based allocation:
- Instead of saying “AAA gets 30% weight”, you say:
  - “each symbol should contribute a similar amount of portfolio risk”.

Intuition:
- High-volatility assets get smaller weights.
- Low-volatility assets get larger weights.
- The goal is to avoid one asset dominating portfolio risk.

### What SigmaTrader does (v1)

1) Collects daily closes (`timeframe=1d`) for all portfolio symbols.
2) Aligns the symbols on common dates (same candle timestamps).
3) Computes daily returns and estimates a covariance matrix over a lookback window:
   - **6M** ≈ 126 trading days
   - **1Y** ≈ 252 trading days
4) Solves for weights where each symbol’s risk contribution share is ~equal.
5) Applies optional weight bounds (min/max weight).
6) Feeds the derived weights into the standard rebalance planner (budget + bands + constraints).

### Controls (what each field means)

- **Window**:
  - 6M reacts faster but can be noisy.
  - 1Y is smoother but reacts slower.
- **Min observations**:
  - Minimum number of aligned daily candles needed across *all* symbols.
  - If you choose a high value, you may get “insufficient history” errors.
- **Min weight (%) / Max weight (%)**:
  - Portfolio-level diversification guardrails.
  - Example: if Max weight is 25%, no single symbol can exceed 25%.

### What you should expect in preview

- Derived targets show:
  - `target_weight`
  - volatility estimates (`vol_daily`, `vol_annual`)
  - `risk_contribution_share` (should be close to equal across symbols)
  - cache/optimizer diagnostics (`cache_hit`, `iterations`, `max_rc_error`)

## Columns & calculations

### Preview table (each row is one proposed trade)

- **Broker**: which broker account the trade is for (`zerodha`, `angelone`).
- **Symbol**: the tradingsymbol that will be bought or sold.
- **Side**:
  - `BUY` ⇒ underweight vs target
  - `SELL` ⇒ overweight vs target
- **Qty**:
  - computed from `trade_value / price` and rounded down to an integer.
  - SELL qty is clamped to your available holding quantity.
- **Est. price**:
  - best-effort estimate (LTP preferred, else last daily close).
  - used for sizing, not a guarantee of execution price.
- **Est. notional**:
  - `Qty × Est. price`
- **Target**:
  - target weight for that symbol (derived from the selected rebalance method).
- **Live**:
  - `current_value / portfolio_value`
- **Drift**:
  - `Live − Target`
  - positive drift ⇒ overweight ⇒ usually SELL
  - negative drift ⇒ underweight ⇒ usually BUY

### Budgeting and scaling

SigmaTrader first computes “ideal” deltas, then scales them down to fit your budget.

Definitions:
- `budget_amount`:
  - if Budget amount is set, that value is used.
  - else `budget_pct × portfolio_value` is used.
- `scale`:
  - `scale = min(1, budget_amount / max(total_buy_value, total_sell_value))`
  - scale applies uniformly to all candidate trades.

### Drift bands

Two types of drift bands are combined:
- **Abs band**:
  - ignore if `abs(drift) < abs_band`
- **Rel band**:
  - ignore if `abs(drift) < rel_band × target_weight`

Effective threshold per symbol:
`threshold = max(abs_band, rel_band × target_weight)`

## Scheduling & history

### History tab

For group rebalances, SigmaTrader stores a “run history”:
- run id, timestamps, status, and order ids.
- this helps you audit what you did.

Holdings-universe rebalances currently create orders but do not store a rebalance run.

### Scheduling tab (PORTFOLIO groups)

You can configure a schedule:
- Weekly / Monthly / Quarterly / Custom interval
- Time and timezone

SigmaTrader shows:
- **Last** rebalance time
- **Next** scheduled time

Important:
- Scheduling stores the schedule and next/last timestamps.
- It does not auto-execute trades in the background yet (that is a future enhancement).

## FAQ

### “Budget used” vs “Turnover”

- `budget used = max(total_buy_value, total_sell_value)`
- `turnover = total_buy_value + total_sell_value`

If you sell ₹50k and buy ₹50k, “budget used” is ₹50k but “turnover” is ₹100k.

### Why did some symbols not generate trades?

Common reasons:
- drift is inside the band (ignored),
- estimated qty rounds to 0 after scaling,
- trade notional is below “Min trade value”,
- max trades clipped the smaller trades,
- missing price data for that symbol.

### Why does risk parity require “aligned” candles?

Risk parity uses covariance, which requires comparing returns on the same dates.
If one symbol has missing days, SigmaTrader needs enough overlap to compute a stable estimate.

### Safety checklist (recommended)

1) Confirm you selected the right broker and group.
2) Start with a low budget (2–5%) while learning.
3) Keep drift bands non-zero (1–2%) to avoid churn.
4) Prefer MANUAL at first; inspect orders before AUTO.
5) Be careful with LIMIT orders; MARKET is simpler for rebalance.
6) Consider taxes/conviction before selling.

### Known limitations (current)

- Cash is not modeled explicitly (portfolio value is derived from positions only).
- Prices are best-effort; execution can differ.
- Integer qty rounding can leave small residual drift.
- Signal rotation and risk parity are currently supported only for `PORTFOLIO` groups.
- Background auto-execution for schedules is not implemented yet.
