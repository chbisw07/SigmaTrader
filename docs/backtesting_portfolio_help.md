# Portfolio backtest (Target weights, EOD) — Help (SigmaTrader)

Portfolio backtesting answers:

> “If I maintained this portfolio method over time, how would it have performed?”

In v1, SigmaTrader implements **Target weights** portfolio backtesting using **EOD (daily) closes**.

---

## 1) What “Target weights” means

You provide a **Portfolio group** where each symbol has a **target weight** (from the Groups page).

On each rebalance date, SigmaTrader attempts to adjust holdings so the portfolio moves closer to the target weights.

This backtest mirrors the mental model of the live Rebalance workflow:
- “I want these weights”
- “I rebalance on a schedule”
- “I limit churn with constraints like budget, max trades, and min trade value”

---

## 2) Inputs explained

### Universe (must be `Group` in v1)
Portfolio backtests need a stable portfolio definition.

So in v1:
- Universe must be **Group**
- `Group` should be a **Portfolio** group (with target weights)

### Cadence (rebalance frequency)
- **Weekly**: rebalance on the last trading day of each week
- **Monthly**: rebalance on the last trading day of each month

SigmaTrader also performs an **initial allocation** on the first trading day of the backtest range.

### Initial cash
The starting capital for the backtest.

### Budget (%)
This limits how much can be traded on a rebalance date:
- Budget cap = `portfolio_value × (budget_pct / 100)`

Examples:
- `100%` means “full rebalance allowed”
- `10%` means “only trade up to 10% of the portfolio value per rebalance”

### Max trades
Limits the number of trades per rebalance date (highest-impact trades are attempted first).

### Min trade value
Skips tiny trades below this amount (helps avoid noise and churn).

### Slippage (bps)
A simple execution penalty applied to fills:
- BUY fill price = `close × (1 + slippage_bps/10000)`
- SELL fill price = `close × (1 - slippage_bps/10000)`

Example:
- `10 bps` = 0.10% slippage

### Charges (bps)
A simple cost model applied to the traded notional:
- charges = `abs(trade_notional) × (charges_bps/10000)`

---

## 3) Results explained

### Equity curve
Shows how the portfolio value changes over time.

### Rebalance actions
Each action is one rebalance date, showing:
- how many trades were done
- how much turnover occurred
- how much budget was used

Turnover here is measured as:
- `sum(abs(trade_notional)) / portfolio_value` (for that rebalance date)

---

## 4) Important notes and limitations (v1)

- Uses **EOD close prices** for rebalance sizing and valuation.
- Uses **integer quantities** (no fractional shares).
- Missing prices are handled conservatively (a symbol can’t be traded on days where its price is missing).
- This is a portfolio simulation (not a broker simulator). For realistic fills/delays, use **Execution backtest** (S28/G06).

