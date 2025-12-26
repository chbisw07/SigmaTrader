# Signal backtest (EOD) — Help (SigmaTrader)

Signal backtesting answers a simple question:

> “When my condition is true, what typically happens next?”

This tab does **not** simulate a full portfolio. It evaluates a signal on each symbol and reports **forward return distributions** so you can judge whether an idea has an edge.

---

## 1) What the signal backtest does (mentally)

For every symbol in your selected universe and for every trading day in the selected date range:

1) SigmaTrader checks whether your signal is **true on that day** (using EOD candles).
2) If true, it records the return after `1D`, `5D`, `20D`… (whatever forward windows you selected).
3) It aggregates all these “events” into summary statistics per forward window.

Important:
- **“1D / 5D / 20D” are trading days**, not calendar days.
- “As‑of” behavior is enforced: the signal for day **D** is computed using data available **up to day D**, and forward returns are measured **after D** (no lookahead).

---

## 2) Inputs explained

### Universe
Which symbols are eligible:
- **Holdings**: your current broker holdings list.
- **Group**: members of a selected group (Portfolio / Watchlist / Holdings view).
- **Both**: union of Holdings + Group.

Recommendation: if you want stable, repeatable tests, prefer **Group** universes (because broker holdings can change due to actions outside SigmaTrader).

### Date range
Only events within the selected date range count.

### Signal mode

#### A) DSL condition
You provide a boolean expression like:
- `RSI(14) < 30`
- `MA(50) > MA(200) AND RSI(14) < 35`
- `MA(20) CROSS_ABOVE MA(50)`

Notes:
- Use `AND`, `OR`, and `NOT`.
- Supported comparisons: `>`, `>=`, `<`, `<=`, `==`, `!=`, plus `CROSS_ABOVE` / `CROSS_BELOW`.
- In v1, Signal backtests support **indicators only** (no `FIELD` operands like `INVESTED`, `PNL_PCT`, etc.).
- In v1, Signal backtests support **EOD only**: `1d`.

#### B) Ranking (Top‑N momentum)
This mode does not use an arbitrary DSL expression.

Instead, on each rebalance date (Weekly/Monthly), SigmaTrader:
- Computes `PERF_PCT(window)` for each symbol (example: 20D momentum).
- Picks the **Top‑N** symbols by that score.
- Treats each picked symbol as an “event” and computes its forward returns.

This helps answer questions like:
- “Does Top‑10 momentum have edge in this universe?”
- “Is monthly ranking better than weekly?”

### Forward windows
These are the future horizons after each event (example: 1D, 5D, 20D).

Interpretation:
- Short windows (1D/5D) show near‑term behavior.
- Longer windows (20D/60D) show whether the edge persists.

---

## 3) Results table (“by forward window”)

For each selected forward window (e.g. `1D`, `5D`, `20D`), SigmaTrader shows:

- **Count**: number of forward-return samples collected for that window.
- **Win %**: % of samples where the forward return was positive.
- **Avg %**: average forward return (%).
- **P10 / P50 / P90**: percentiles (help you understand best/worst cases):
  - `P10`: “bad case” (10% of outcomes are worse than this)
  - `P50`: median outcome
  - `P90`: “good case” (10% of outcomes are better than this)

### Example interpretation
If `5D` shows:
- Win %: 62%
- Avg %: 0.8%
- P10: -2.5%, P50: 0.6%, P90: 4.1%

That means:
- Most of the time it’s positive in 5 trading days (62% hit rate),
- Average is positive (0.8%),
- But you should still expect bad periods (10% of samples worse than -2.5%).

---

## 4) Common pitfalls (what to watch)

- **Too few samples**: a nice Avg% with Count=15 is not reliable.
- **Overfitting**: don’t keep tweaking DSL until it “looks perfect”.
- **Universe drift**: if the universe is holdings-based, results change when you buy/sell outside SigmaTrader.
- **Execution reality**: Signal backtests don’t include slippage/charges. Use Portfolio/Execution backtests for realistic outcomes.

