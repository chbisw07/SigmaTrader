# Strategy backtest (Entry/Exit) — Help (SigmaTrader)

Strategy backtesting answers a different question than “Signal backtest”:

> “If I **traded** a single stock using these Entry + Exit rules, what would my equity curve look like?”

This tab is meant for TradingView‑style strategy thinking: **enter**, **exit**, re‑enter, and compare against simple buy‑and‑hold baselines.

---

## 1) What this backtest simulates (high level)

SigmaTrader runs a simple, repeatable simulation over your chosen date range and timeframe:

- You start with `Initial cash`.
- SigmaTrader checks your **Entry DSL** and **Exit DSL** on every bar.
- When Entry becomes true, it **enters on the next bar open**.
- While in a position, when Exit becomes true, it **exits on the next bar open**.
- After an exit, SigmaTrader allows **immediate re‑entry** the next time Entry becomes true.

Important: it’s a **single‑symbol, single‑position** backtest:
- It holds at most **one position at a time** for the symbol (no pyramiding / stacking multiple entries).
- It does **not** run a multi‑symbol portfolio in this tab.

---

## 2) “Evaluate at close, fill at next open” (very important)

To avoid lookahead bias, SigmaTrader does:

- **Evaluate at close**: Entry/Exit signals are computed using information available up to the bar close.
- **Fill at next open**: The simulated trade price is the next bar’s open (plus optional slippage).

Examples:
- Timeframe `1d`: signal on day D close → trade fills on day D+1 open.
- Timeframe `15m`: signal on 10:15 close → trade fills on 10:30 open.

This mimics how a real system can act: you can only place the trade *after* you know the close.

---

## 3) Product & market constraints (India)

### CNC (delivery)
- **Long only** (short selling not allowed in delivery equity).
- Positions can be held across days.

### MIS (intraday)
- Long or Short is allowed (intraday).
- SigmaTrader forces **end‑of‑day square‑off** (no overnight position).  
  If a position is open near the end of the trading day, it will be closed as a “square‑off” action.

Note: MIS backtests require an intraday timeframe (≤ `1h`).

---

## 4) How “Entry true for many days” behaves (dry run)

Assume Entry DSL is `RSI(14) < 30`, Exit DSL is `RSI(14) > 70`, timeframe `1d`.

Say Entry is true on days: `1, 2, 7, 12, 15`.

What happens:
1) On day **1** close, Entry is true → SigmaTrader schedules a BUY at **day 2 open**.
2) On day **2**, you are now **in position** → SigmaTrader will **not** keep buying again just because Entry is still true.
3) It stays in position until Exit becomes true on some later day close → then it schedules an exit at the **next day open**.
4) After exiting, if Entry becomes true again (e.g., day 12 close), SigmaTrader can enter again at day 13 open.

So you can think of Entry/Exit as a **state machine**:
- `FLAT` → (Entry) → `IN_POSITION` → (Exit) → `FLAT` → …

---

## 5) Inputs explained (what each control means)

### Universe + Symbol
Universe is used only to populate the **Symbol** dropdown:
- Holdings, Group, or Both.
- Strategy backtest runs on **exactly one** selected symbol.

### Timeframe
Choose how often you want the strategy to evaluate and trade:
`1m, 5m, 15m, 30m, 1h, 1d`

### Entry DSL / Exit DSL
These are boolean conditions, for example:
- `RSI(14) < 30`
- `MA(20) CROSS_ABOVE MA(50)`
- `PRICE() CROSS_BELOW VWAP(20) AND RSI(14) < 50`

Supported comparisons include `>`, `<`, `==`, `!=`, and `CROSS_ABOVE` / `CROSS_BELOW`.

### Initial cash
Starting capital for the simulation.

### Position size (%)
How much of your current cash to allocate on each entry:
- `100%` means “all‑in”.
- `25%` means “use about 25% of available cash per trade”.

### Stop loss / Take profit / Trailing stop (%)
Optional risk controls (set to `0` to disable):
- **Stop loss %**: exit if price moves against you by this % from entry.
- **Take profit %**: exit if price moves in your favor by this % from entry.
- **Trailing stop %**: exit if price retraces by this % from the best favorable price since entry.

Note: in v1 these are evaluated at **bar close** and filled at **next open** (not intrabar).

### Slippage (bps)
Execution friction added to simulated fills:
- `10 bps` = `0.10%`
- `50 bps` = `0.50%`

### Charges
Two choices:
- **Broker estimate (India equity)**: approximates brokerage + STT + exchange + SEBI + stamp duty (WB buy‑side) + GST, and optional DP on delivery sell.
- **Manual (bps)**: apply a fixed bps charge per trade.

DP charges only apply to **CNC delivery sells**.

---

## 6) Outputs explained (how to read results)

### Equity curve
Your simulated account value over time (cash + position mark‑to‑market).

### Drawdown (%)
How far equity fell from its previous peak.

### Summary chips
Typical metrics shown:
- **Total**: total return over the run.
- **CAGR**: annualized return (mostly meaningful for long durations like 1d).
- **Max DD**: worst drawdown magnitude.
- **Turnover**: how much you traded relative to average equity (higher turnover = more churn).
- **Charges**: total trading costs deducted.

### Baselines (comparisons)
To keep you honest, SigmaTrader overlays:
- **Buy & hold (start→end)**: buy once at start, hold to end.
- **Buy & hold (first entry→end)**: buy at the strategy’s first entry time, hold to end.

If your strategy doesn’t beat these, it’s often not worth the extra complexity/effort.

### Trades table
Every executed trade pair (entry→exit), including:
- entry/exit timestamps
- side (LONG/SHORT)
- qty
- P&L %
- exit reason (EXIT_SIGNAL, STOP_LOSS, TAKE_PROFIT, TRAILING_STOP, EOD_SQUARE_OFF, END_OF_TEST)

---

## 7) Presets (starting points)

Presets are templates to help you get started quickly. You can pick one and then edit:

- Swing (1d): RSI 30/70 mean reversion
- Swing (1d): MA cross trend follow
- Intraday (MIS): VWAP reclaim long / VWAP breakdown short
- Sideways intraday: RSI mean reversion

Use presets as learning tools, not as “guaranteed profitable systems”.

---

## 8) Limitations (v1)

- Single symbol only (no portfolio of strategies).
- One position at a time (no pyramiding / scaling in/out).
- Stops/targets are evaluated at close and filled at next open (no intrabar stop simulation yet).
- No limit/market microstructure modeling (this is for research intuition, not precise execution modeling).

