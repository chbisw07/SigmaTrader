# Strategy optimization discussion

This document summarizes practical, robust paths for finding “good” strategy parameters for a **symbol** or a **group/portfolio strategy backtest**, while minimizing overfitting and keeping results actionable in SigmaTrader.

## 1) What “optimal” means (define the target)

“Optimal” should be defined as an **objective** plus **constraints**.

### Common metrics
- Return: `Total return %`, `CAGR %`, `Profit (net)`
- Risk: `Max drawdown %`, time-in-drawdown, recovery time
- Friction: `Turnover (%)`, `Turnover (₹)`, `Charges (₹)`, slippage sensitivity
- Activity: `#Trades`, win-rate %, average trade %, holding time distribution

### Recommended optimization target
Prefer a *score* that balances return and risk, e.g.
- Maximize: `Profit (net)` or `CAGR %`
- Subject to: `Max DD <= X%`, `Turnover <= Y%` (or charges <= ₹Z), and a reasonable `Trades` range

This is usually better than “maximize profit only”, because it avoids parameter sets that are unrealistic after costs.

## 2) The core challenge: overfitting

Optimizing parameters on the same period you evaluate will almost always overfit.

### Best practice: out-of-sample validation
Use time splits:
- Single split: Train (first 70–80%) → Test (last 20–30%)
- Better: walk-forward / rolling validation:
  - Optimize on window A → validate on window B
  - Roll forward and repeat
  - Choose parameters that are consistently good across folds

This applies to both symbol-level and portfolio-level backtests.

## 3) Baseline path (low effort, high value)

### A) Manual + robust filtering
1. Define constraints (e.g., `Max DD < 20%`, `Turnover < 1500%`).
2. Try a small number of parameter variants (10–30).
3. Select a “robust region”:
   - nearby parameter values also work (not brittle)
   - performance doesn’t collapse out-of-sample

This often beats complex optimization early on.

## 4) Systematic search paths (no ML required)

### B) Random search (recommended first)
Random search is easy, parallelizable, and often outperforms grid search for the same budget.

Workflow:
1. Define parameter ranges (keep them realistic).
2. Run N trials (e.g., 200–2000).
3. Keep only runs that meet constraints.
4. Rank by objective (e.g., `Profit (net)`), then confirm on out-of-sample splits.

### C) Grid search (use sparingly)
Grid search grows exponentially with the number of parameters and is usually inefficient unless:
- you have very few parameters, or
- you’re doing a small “local refinement” near a good region.

## 5) ML-assisted optimization (you run this externally)

ML is best used as an **optimizer/surrogate model**, not as “a neural net that predicts prices”.

### D) Turn backtests into a dataset
Create rows like:
- Inputs:
  - backtest context (group, timeframe, dates, product, direction)
  - parameter set (DSL params, stop/trail, sizing, ranking window, max positions, etc.)
  - (optional) regime features computed from the train window (volatility, trend, breadth proxies)
- Outputs:
  - metrics on train window
  - metrics on test window (the real “label” you care about)
  - constraint flags (e.g., `max_dd_ok`, `turnover_ok`)

Once you have this dataset, you can:
- Train a model to predict **test score** given parameters (+ context).
- Use it for Bayesian optimization / active learning:
  - propose next trials where predicted score is high and/or uncertainty is high
  - always confirm with actual backtests

### E) Why this helps
- Reduces the number of expensive backtest runs needed to find good regions.
- Makes it easier to search high-dimensional parameter spaces.

### F) Key caveat: leakage
Never use information from the test window to build features for the train window.
If you compute regime features, compute them **inside** the train window only.

## 6) Monte Carlo simulation (robustness / risk, not prediction)

Monte Carlo is useful for answering:
- “How bad can the drawdown get if returns arrive in a different order?”
- “What’s the distribution of CAGR / Max DD / worst 5% outcomes?”

It does not forecast markets; it stress-tests the equity path.

### Recommended method (first)
**Equity-return resampling** from the existing equity curve (already net of charges):
- Build per-bar returns from the equity series.
- Use **block bootstrap** (resample blocks of bars) to preserve autocorrelation.
- Generate many equity paths (e.g., 500–5000) and compute percentiles:
  - Max DD distribution, return distribution, probability of DD > 20%, etc.

This works for both symbol-level and portfolio-level results because it operates on the final equity curve.

## 7) Portfolio/group optimization specifics

Portfolio-level strategy backtests have shared capital and overlapping positions, so:
- “Optimize per symbol and average” is not equivalent to “optimize the portfolio”.
- Any optimizer must run the **portfolio engine** end-to-end for each trial.

Recommended constraints for portfolio runs often include:
- `Max open positions`
- `Turnover` / `Charges`
- (optional) per-symbol caps and cooldown/min-hold to reduce churn

## 8) Practical implementation support inside SigmaTrader (future)

To enable external optimization without building a full optimizer UI immediately, SigmaTrader can support:
- Export a **run dataset row** (params + metrics + split info) as CSV/JSONL.
- Export a **batch dataset** for selected runs (multiple rows).
- Optional: walk-forward run mode that automatically produces train/test folds and returns fold metrics.

This keeps SigmaTrader focused on correct backtests, while data science tooling (you) handles optimization.

## 9) Suggested “best paths” (recommended order)

1. **Define objective + constraints** (Profit(net) + Max DD + Turnover/Charges).
2. Use **walk-forward splits** (even 2–3 folds is a big improvement).
3. Start with **random search** to generate baseline evidence and a dataset.
4. If needed, apply **ML-assisted optimization** as a surrogate-driven search over parameters.
5. Use **Monte Carlo (block bootstrap)** on the best candidates to compare robustness and tail risk.

