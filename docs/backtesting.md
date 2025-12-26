# Backtesting (SigmaTrader) — Reference Plan

This document started as a Q&A about whether backtesting is a better ROI than LLM integration. It is now the **reference plan** for building backtesting in SigmaTrader based on your confirmed direction:

- **Primary data**: EOD (daily candles) for portfolio backtesting.
- **Portfolio methods to implement (in this order)**:
  1) Target weights
  2) Rotation (signal/strategy-driven)
  3) Risk parity (risk-based)
- **Product UI**: a new **Backtesting** page in the left sidebar, placed **below Alerts**.
- **Backtesting levels to support**:
  1) Signal backtest
  2) Portfolio backtest
  3) Execution backtest

The goal is to keep the feature **intuitive, explainable, and audit-friendly** (so you trust what you see).

---

## 1) Why backtesting in SigmaTrader (in plain language)

Backtesting answers: **“If I had followed these rules in the past, what would have happened?”**

SigmaTrader’s edge is that it already has:
- A deterministic **DSL** (screener/alerts)
- A portfolio **rebalance engine**
- A working execution pipeline and guardrails

Backtesting completes the loop:
**Idea → Rules → Simulated actions → Performance + diagnostics → Improve**

---

## 2) EOD vs intraday: what we do now, and what we add later

### What EOD is good for (MVP focus)
EOD backtests (daily candles) are excellent for:
- Weekly / monthly rebalances
- Portfolio rotation
- Long-only investing-style systems
- Most “portfolio construction” testing

### What EOD is NOT enough for (later extension)
EOD cannot reliably test:
- Intraday entries/exits
- Tight stop-loss / fast-moving systems
- Signals that depend on intraday structure (5m, 15m, 1h etc.)

### Design principle
Start with EOD for the **core portfolio backtesting**, and keep the UI/architecture “timeframe-ready” so we can later add intraday without redoing the whole feature.

---

## 3) The three backtesting levels (and what each should teach you)

### Level 1 — Signal backtest (“Is this idea good?”)
Purpose: evaluate signals/filters/rankings quickly without simulating complex execution.

Examples:
- “When RSI(14) < 30, what is the distribution of next-5-day returns?”
- “Monthly Top‑N momentum ranking — how does the ranking behave historically?”

Outputs (human-friendly):
- Hit rate and forward return distributions (1D/5D/20D)
- Rank stability (how often ranks change)
- Regime view (good periods vs bad periods)

### Level 2 — Portfolio backtest (“Does this portfolio method work?”)
Purpose: simulate portfolio value over time with realistic portfolio constraints and rebalance cadence.

This is SigmaTrader’s natural fit because it directly maps to your rebalance workflows.

Outputs:
- Equity curve + drawdown curve
- Turnover
- Rebalance action list (audit trail)
- Contributions (what helped/hurt)

### Level 3 — Execution backtest (“Will this survive real trading?”)
Purpose: simulate practical execution details (slippage, delays, partial fills, limit/market).

Outputs:
- Portfolio performance with execution friction
- A more realistic “gap between theory and practice”

Note: This is the hardest and most model-sensitive. We implement it last.

---

## 4) Where Backtesting lives in the app (navigation)

Add a new sidebar item:

- Dashboard
- Holdings
- Groups
- Screener
- Alerts
- **Backtesting**  ← new
- Orders
- Positions
- Settings

---

## 5) UX concept: one Backtesting page, three tabs

The Backtesting page is a workspace with:
- Left side: **inputs**
- Right side: **results**

### Wireframe (page-level)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Backtesting                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ [ Signal backtest ] [ Portfolio backtest ] [ Execution backtest ]            │
├───────────────────────────────┬─────────────────────────────────────────────┤
│ Inputs                         │ Results                                     │
│ - Universe selector            │ - Summary cards (CAGR/DD/Turnover/etc.)     │
│ - Time range                   │ - Charts (equity, drawdown, exposure)       │
│ - Timeframe (EOD now)          │ - Tables (rebalance actions / trades)       │
│ - Costs/slippage               │ - Compare runs (optional)                   │
│ - Strategy controls            │                                             │
│ [ Run backtest ]               │                                             │
└───────────────────────────────┴─────────────────────────────────────────────┘
```

### Core UX principle
Every backtest run must produce:
- A **simple answer** (“better/worse, riskier/safer”)
- A **why** (contributors, turnover, regime behavior)
- An **audit trail** (so you can trust it)

---

## 6) Universe selection (where does the strategy run?)

We support universes in a way that matches SigmaTrader’s mental model:

1) **Holdings** (Zerodha / AngelOne)
2) **Selected Group** (Portfolio / Watchlist / Holdings view)
3) **Both** (optional): treat “Holdings + Group” as a combined universe

This is presented as:

```
Universe:
  (•) Holdings (Zerodha)     ( ) Holdings (AngelOne)
  ( ) Group: [ PF_RAILWAY ▼ ]
  ( ) Both: [ Holdings + selected group ]
```

---

## 7) Portfolio backtest methods (implementation order)

Your required order is:

### A) Target weights (Portfolio backtest v1)
You provide a target weight per symbol (from a portfolio group). The backtest:
- Rebalances periodically (weekly/monthly/custom)
- Uses a budget/bands/max-trades like the live rebalance dialog

Questions it answers:
- “If I maintained these weights, what would returns and drawdowns look like?”
- “How often does it trade? Is turnover acceptable?”

### B) Rotation (Portfolio backtest v2)
The target weights are not static; they are derived from a strategy/ranking.

Example rotation styles (conceptual):
- Hold Top‑N by momentum
- Hold Top‑N by “signal score”
- Replace losers periodically

Questions it answers:
- “Is the rotation edge real?”
- “Does it depend on a small period only?”

### C) Risk parity (Portfolio backtest v3)
Targets come from risk logic (equal risk / risk contributions).

Questions it answers:
- “Does risk balancing reduce drawdowns?”
- “Does it improve risk-adjusted outcomes vs plain weights?”

---

## 8) What “Execution backtest” should mean in SigmaTrader

Execution backtest should be framed as: **“Portfolio backtest + trading friction”**.

Start with simple, explainable toggles:
- Slippage (e.g., 5 bps / 10 bps / custom)
- Charges (simple approximation)
- Delay model (e.g., execute at next day open vs same day close for EOD)

UX goal: show the gap between “ideal” and “realistic”.

---

## 9) Reports (what the user sees)

Keep reporting explainable and aligned to user decisions.

### Summary cards (top)
- Total return, CAGR
- Max drawdown + drawdown duration
- Turnover
- Win rate (optional)
- “Costs impact” (only in execution mode)

### Charts
- Equity curve (portfolio value)
- Drawdown curve
- Exposure / concentration over time
- Rolling return (optional)

### Tables
- Rebalance actions list (date, buys, sells, turnover, reason)
- Trade list (for execution backtest)
- Top contributors / detractors (symbols)

---

## 10) MVP delivery plan (phased, user-visible increments)

The plan below is deliberately product-first (you can test it as it grows).

### Phase 0 — Backtesting page shell
- Add Backtesting menu item (below Alerts)
- Add 3 tabs with a consistent input layout
- “Run” triggers a dummy/no-op response until engines are implemented (so UX is validated early)

### Phase 1 — Signal backtest (EOD)
- Backtest a DSL condition or ranking on a selected universe
- Output forward returns and hit-rate distributions
- This provides immediate value even before portfolio simulation is complete

### Phase 2 — Portfolio backtest: Target weights
- Portfolio simulator (EOD)
- Rebalance schedule
- Constraints similar to rebalance dialog (budget/bands/max trades/min value)
- Reports: equity + drawdown + actions

### Phase 3 — Portfolio backtest: Rotation
- Ranking/selection logic to generate targets
- Turnover and regime analysis

### Phase 4 — Portfolio backtest: Risk parity
- Risk-based target generation
- Compare vs target weights baseline

### Phase 5 — Execution backtest (EOD first)
- Apply friction model to portfolio backtest
- Show “ideal vs realistic” comparison

### Phase 6 — Intraday extension (later)
- Add timeframe selector (1h/15m/5m…) where data exists
- Re-use the same UX and reporting concepts

---

## 11) Guardrails (trust and correctness)

Backtesting becomes dangerous when it feels “too perfect”. The UI should gently remind:
- Past performance ≠ future results
- Costs/slippage matter
- Avoid overfitting

Also, every run should clearly show:
- Universe used
- Dates
- Timeframe (EOD)
- Rebalance frequency
- Costs/slippage assumptions

---

## 12) UX wireframes (per tab)

### Tab 1 — Signal backtest

```
Inputs
  Universe: [ Holdings / Group / Both ]
  Date range: [ from ] [ to ]
  Timeframe: 1D (EOD)
  Signal:
    - Mode: [ DSL condition | Ranking ]
    - DSL:  [..............................]
    - Ranking: metric [....]  Top N [..]
  Forward windows: [1D] [5D] [20D]
  [ Run ]

Results
  - Hit rate cards
  - Forward returns distribution (histogram/percentiles)
  - “When it fails” table (worst periods)
```

### Tab 2 — Portfolio backtest

```
Inputs
  Universe: Group: [ PF_RAILWAY ▼ ]
  Method: [ Target weights | Rotation | Risk parity ]
  Date range: [ from ] [ to ]
  Timeframe: 1D (EOD)
  Rebalance cadence: [ Weekly | Monthly | Custom ]
  Constraints: budget %, bands, max trades, min trade value
  Costs: [ simple charges ]  Slippage: [bps]
  [ Run ]

Results
  - Equity + drawdown
  - Turnover
  - Rebalance actions list (audit)
  - Contributions (top help/hurt)
```

### Tab 3 — Execution backtest

```
Inputs
  Base: Select a portfolio backtest configuration
  Execution model:
    - Fill price: [ close | next open ]
    - Slippage: [bps]
    - Charges: [simple]
  [ Run ]

Results
  - Side-by-side: ideal vs realistic
  - Cost impact summary
  - Trade list
```

---

## 13) What you decided (for the record)

- EOD is the right starting point for your portfolio backtesting.
- Implementation order: target weights → rotation → risk parity.
- Backtesting page below Alerts.
- Three levels: signal → portfolio → execution.

This document should be treated as the product reference for building Backtesting in SigmaTrader.
