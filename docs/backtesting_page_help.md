# Backtesting (SigmaTrader) — Help

SigmaTrader backtesting is designed to help you answer:

> “If I had followed these rules in the past, what would have happened?”

The Backtesting page is split into **Inputs** (left) and **Results** (right).  
You can run three kinds of backtests:

## 1) Signal backtest

Goal: evaluate an idea quickly.

Typical questions:
- “When this condition is true, what returns followed?”
- “Does a ranking look stable?”

Inputs (conceptual):
- Universe (Holdings / Group / Both)
- Date range
- EOD timeframe (daily candles)
- A signal definition (DSL condition / ranking preset)

Outputs:
- Hit-rate and forward return summaries
- Return distributions (so you understand best/worst cases)

## 2) Portfolio backtest

Goal: simulate a portfolio over time (rebalances, constraints, turnover).

This is the closest to SigmaTrader’s live Rebalance workflow.

Inputs:
- Universe (usually a Portfolio group)
- Backtest method:
  - Target weights
  - Rotation
  - Risk parity
- Rebalance cadence (weekly/monthly)
- Constraints (budget %, max trades, minimum trade value)
- Simple costs/slippage (optional)

Outputs:
- Equity curve and drawdowns
- Turnover and rebalance actions list
- Contributors (what helped/hurt)

## 3) Execution backtest

Goal: understand how “real-world friction” changes the results.

Inputs:
- A portfolio backtest configuration
- Execution assumptions:
  - Fill timing (close vs next open)
  - Slippage (bps)
  - Charges (simple approximation)

Outputs:
- “Ideal vs realistic” comparison
- Cost impact summary

## Universe selector (important)

Universe decides which symbols are eligible:
- **Holdings**: uses your current broker holdings as the symbol list.
- **Group**: uses the symbols in a selected group (Portfolio / Watchlist / etc.).
- **Both**: union of both lists.

If you changed your portfolio in the broker directly, the universe and results can change.  
For consistency, prefer testing on a **Group universe**.

