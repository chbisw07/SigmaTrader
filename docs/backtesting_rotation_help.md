# Portfolio backtest (Rotation, EOD) — Help (SigmaTrader)

Rotation backtesting answers:

> “If I periodically rotated into the strongest stocks, would it outperform?”

In v1, SigmaTrader implements a simple, explainable rotation model:
- **Top‑N momentum** selection
- **Equal weights** among selected symbols
- Rebalance on a **weekly** or **monthly** cadence
- Portfolio constraints similar to live rebalancing (budget, max trades, min trade value, slippage/charges)

---

## 1) What Rotation means (in SigmaTrader)

On each rebalance date, SigmaTrader:
1) Scores each symbol by **momentum**:
   - `PERF_PCT(ranking_window)` i.e. % change over the last N trading days
2) Picks the **Top‑N** symbols by score
3) Sets target weights to **equal weights** across the picks
4) Trades the portfolio toward those weights (subject to your constraints)

This produces both:
- a realistic equity curve (portfolio simulation), and
- an audit trail of rebalance actions.

---

## 2) Inputs explained (Rotation-specific)

### Top N
How many symbols you want to hold after each rebalance.

Examples:
- `Top N = 5` → concentrated momentum basket
- `Top N = 20` → more diversified, often lower turnover

### Momentum window (days)
How far back to compute momentum.

Examples:
- `20` days ≈ about 1 trading month
- `60` days ≈ about 1 trading quarter

### Eligible DSL (optional)
A filter applied **before ranking**.

If provided, SigmaTrader ranks only those symbols where the DSL is true.

Example filters:
- Trend filter: `MA(50) > MA(200)`
- Avoid overbought: `RSI(14) < 80`
- Both: `MA(50) > MA(200) AND RSI(14) < 80`

Notes:
- For Rotation backtests, `Eligible DSL` supports **indicator operands** only (no `FIELD` operands like `INVESTED`, `PNL_PCT`, etc.).
- EOD only (`1d`) in this MVP.

---

## 3) Results: how to interpret Rotation

Rotation is often “lumpy”:
- it can look great in strong trending markets,
- and painful in sideways/choppy regimes.

Use the results to check:
- **CAGR vs Max drawdown**
- **Turnover** (high turnover is a red flag for real trading)
- Whether performance depends on a short period only

---

## 4) Comparing Rotation vs Target weights

SigmaTrader supports comparing runs on the equity curve.

Recommended workflow:
1) Run a **Rotation** backtest for a portfolio group and date range
2) Run a **Target weights** backtest on the same group and date range
3) Use **Compare run** to overlay them and inspect:
   - which one had lower drawdown
   - which one had better returns
   - whether Rotation’s edge is consistent

