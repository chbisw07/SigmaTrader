# Portfolio strategy backtest (group)

Runs the same Entry/Exit DSL across a **group of symbols** while sharing a single capital pool.

Key rules:
- **Signals evaluate at close; fills happen at next open** (no lookahead).
- **Exits are processed before entries** on the same bar.
- Positions compete for shared cash and `max_open_positions`.

## Inputs

- **Universe**: Group (required)
- **Timeframe**: `1m/5m/15m/30m/1h/1d` (MIS requires intraday)
- **Entry DSL / Exit DSL**: evaluated at close
- **Product / Direction**: CNC is long-only; MIS can be long/short and is squared off EOD
- **Initial cash**: starting capital
- **Max open positions**: portfolio-wide cap (default: 10)

## Allocation & sizing

- **Allocation**
  - `EQUAL`: fill alphabetically (deterministic)
  - `RANKING`: fill highest score first (v1 supports `PERF_PCT`)
- **Position sizing**
  - `CASH_PER_SLOT`: spreads available cash across remaining slots
  - `% equity`: budget per trade = equity × pct
  - `FIXED_CASH`: fixed cash per trade

## Risk controls (optional)

- Stops: stop loss / take profit / trailing stop (all in %)
- Equity drawdown: global kill-switch and per-trade equity DD (both in %)
- Constraints: min holding (bars), cooldown (bars), max allocation per symbol (%)

## Re-entry after trailing stop (optional)

Feature-gated (default **OFF**). When enabled, a symbol that exits due to `TRAILING_STOP` can be re-entered later without requiring the original Entry DSL to fire again.

High-level flow (evaluated at close, filled next open):
- Track symbols whose last exit reason was `TRAILING_STOP`.
- After `reentry_cooldown_bars`, a symbol becomes eligible if the re-entry trigger fires (default: close crosses above fast MA).
- Portfolio gates apply:
  - **Rank gate** (default ON): only re-enter if the symbol is within top `(max_open_positions + buffer)` for that bar’s ranking.
  - **Replace policy** (when portfolio is full): optionally rotate out the worst-ranked holding and enter the re-entry candidate.

Trade annotations:
- Re-entry entries are tagged as `REENTRY_TREND` (shown as `REENTRY_TREND → <exit_reason>`).
- Forced replacement exits use `PORTFOLIO_ROTATE_OUT`.

## Outputs

- Combined **equity curve** and **drawdown** curve
- Trades table (CSV export)
- Per-symbol stats (CSV export)
