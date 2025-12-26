# Portfolio backtest (Risk parity, EOD) — Help (SigmaTrader)

Risk parity backtesting answers:

> “If I sized positions by risk (instead of weights), would drawdowns improve?”

In v1, SigmaTrader implements **Equal Risk Contribution (ERC)** risk parity using **EOD (daily) closes**.

---

## 1) What Risk parity means (in SigmaTrader)

On each rebalance date, SigmaTrader:
1) Looks back over a rolling window of returns (your **Risk window**)
2) Computes the return covariance matrix
3) Solves for weights where each asset contributes roughly **equal risk** to the portfolio
4) Trades the portfolio toward those weights (subject to your constraints)

This is designed to reduce concentration risk and often improves risk-adjusted performance (but not always returns).

---

## 2) Inputs explained (Risk parity-specific)

### Risk window (days)
How many trading days of history are used to estimate risk.

Common choices:
- `126` days ≈ ~6 months
- `252` days ≈ ~1 year

Longer windows → smoother weights (slower to adapt).  
Shorter windows → weights react faster (but can be noisy).

### Min observations
How many daily returns must be available to compute risk.

Guideline:
- Use at least `60` for more stable risk estimates
- For experimentation, smaller values can work but are less reliable

### Min weight / Max weight (%)
Bounds applied to the optimized weights.

Why bounds matter:
- Prevent a single symbol from dominating (cap max weight)
- Prevent tiny “dust” allocations (set a small min weight)

Examples:
- Max weight `30%` keeps diversification.
- Min weight `0%` allows the optimizer to exclude assets if needed.

Note: Some constraints can become infeasible (example: min weight too high for the number of assets). SigmaTrader will fall back to a safer default when needed.

---

## 3) How to interpret results

Risk parity is usually judged by:
- **Max drawdown** (often improves)
- Drawdown “smoothness” and recovery
- Turnover (can increase if risk estimates are noisy)

If Risk parity improves drawdown but lowers returns, you can decide what matters more for your goals.

---

## 4) Limitations (v1)

- Uses **EOD close returns** (no intraday risk modeling).
- Uses a simple rolling covariance estimate (no advanced shrinkage models yet).
- Execution is still “portfolio simulation” (slippage/charges are simplified).

