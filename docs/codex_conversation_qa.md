# SigmaTrader – Design Q&A (Market Data & Alerts)

---

## 1. Embedded price chart column in Holdings

**Question**  
I want a column to show the embedded price chart of the stock for trailing 1 month. I want this to be configurable for days, weeks, months, year. Can we do this?

**Answer**  
Yes, it’s doable, but only after we have a reliable historical price source wired into SigmaTrader. Right now the app only has current holdings and order history; it does not expose an OHLCV history API per symbol, so the frontend has nothing to draw charts from. The design would look like this:

- **Backend: price-history endpoint**
  - Add a `candles` or `prices` store (DB table or external service) that holds OHLCV for each `(symbol, exchange, timeframe, ts)`.
  - Expose a lightweight endpoint, for example:  
    `GET /api/market/history?symbol=INFY&exchange=NSE&timeframe=1D&period=1M`  
    returning a compact series like `[{ t, open, high, low, close, volume }, ...]`.
  - The data can come from Zerodha’s historical API (requires an instrument-token map) or another data provider.

- **Frontend: chart column + period selector**
  - Add a period selector above the Holdings grid (e.g. `1M / 3M / 6M / 1Y` or `Days / Weeks / Months / Year`).
  - Add a `Chart` column to the DataGrid whose `renderCell`:
    - Requests `/api/market/history` for `(symbol, period, timeframe)` the first time the row becomes visible.
    - Caches series per `(symbol, period)` to avoid refetching while scrolling.
    - Renders a small sparkline/mini-chart (e.g. using a tiny SVG component or a lightweight chart lib like `@mui/x-charts`).

Once the history endpoint is in place, the chart column and period configurability are straightforward UI work. The main effort is choosing and integrating the historical data source.

---

## 2. OHLCV store → indicator-based alerts and strategies

**Question**  
If I maintain OHLCV data for max 2 years, will I be able to generate alerts based on fulfillment of certain criteria? For example, I may want to set an alert on BSE for selling 10% of the equity when RSI(14) > 80. How complex is the implementation of the alerts for my holding stocks? Later, I may want to use some strategies to generate signals, apply them to one or more stocks and get into trade if signal or alert conditions are met. Can we do it? Can you show me a way on this?

**Answer**  
Yes, with ~2 years of OHLCV per symbol you can support indicator‑based alerts (like “Sell 10% when RSI(14) > 80”) and reusable strategy templates. Below is a concrete plan focused on: (a) which indicators and strategies we’ll support, (b) how alerts behave in the UI (TradingView‑style modal), and (c) how the backend alert engine and monitoring loop will work.

### 2.1 Indicators surfaced in the portfolio

Phase‑1 indicators that will appear as optional Holdings columns:

1. **Trend / regime**
   - `MA50%`: % distance of last close from 50‑day SMA.
   - `MA200%`: % distance of last close from 200‑day SMA.
   - `Trend tag`: `Uptrend / Sideways / Downtrend` derived from MA50 vs MA200 and (optionally) ADX.

2. **Momentum**
   - `RSI(14)`: classic daily RSI.
   - `RSI(14) zone`: label or color band – e.g. `Overbought` (>70), `Neutral`, `Oversold` (<30).

3. **Volatility & participation**
   - `Volatility 20D %`: standard deviation of daily log returns over 20 sessions, annualised or expressed as a % of price.
   - `ATR(14) %`: ATR(14) divided by last close, useful for stop sizing.
   - `Volume vs 20D avg`: today’s volume / 20‑day average volume.

4. **Time‑window performance**
   - `1W PnL %`, `1M PnL %`, `3M PnL %`, `1Y PnL %` for the underlying price (independent of your entry price).
   - Position‑level metrics you already have (`P&L %`, `Today P&L %`) remain; these new columns complement them.

All of these are computed from the `candles` store via `load_series(symbol, exchange, timeframe, start, end)` and cached per request so the grid stays fast.

### 2.2 Strategy templates built on top of indicators

These are reusable strategy “blueprints” that can later be mapped to `AUTO` or `MANUAL` execution using your existing `strategies` table:

1. **S1 – RSI mean reversion (trim / add)**
   - Universe: user’s holdings.
   - Timeframe: daily.
   - Logic:
     - If `RSI(14) > 80` → generate `Trim X%` signal (e.g. 10–20%).
     - If `RSI(14) < 30` → generate `Add X%` signal (subject to risk limits).
   - These become two rules per symbol, or one rule with a `direction` parameter.

2. **S2 – Moving‑average trend following**
   - Universe: holdings or selected watchlists.
   - Timeframe: daily.
   - Signals:
     - `Golden cross`: MA50 crosses above MA200 → “Trend up” alert (optional add/buy).
     - `Death cross`: MA50 crosses below MA200 → “Trend down” alert (optional exit/trim).
     - Pullback in uptrend: MA50 > MA200 and ADX>20, price dips more than N% below MA50 → “Buy the dip” alert.

3. **S3 – Breakout with volatility filter**
   - Condition: `close` breaks above 20‑day high and volatility is within a configured band.
   - Usage: spot fresh momentum names within your holdings universe.

4. **S4 – VWAP deviation (intraday, optional later)**
   - For intraday use (e.g. 5m/15m candles):
     - Alert if price > X% above today’s VWAP (extended).
     - Alert if price < Y% below VWAP (potential add/mean‑revert).

Phase‑1 implementation will keep these as **alert‑only** strategies; mapping them to real trades is done by wiring `action_type` and `execution_mode` later.

### 2.3 Alert UX – TradingView‑style modal from Holdings

From the Holdings grid:

- Add an `Alerts` column with:
  - An `Alert` button on each row.
  - A small badge showing how many active rules exist for that symbol.

Clicking `Alert` opens a per‑symbol modal with three tabs:

1. **Settings**
   - `Symbol`: read‑only (e.g. `INFY / NSE`).
   - `Timeframe`: dropdown (`1D, 1W, 1H, 15m`).
   - `Condition`:
     - Indicator dropdown: `RSI, Price, MA, MA Cross, Volatility, Volume vs Avg, VWAP`.
     - Operator dropdown: `>`, `<`, `crosses above`, `crosses below`, `inside range`, `outside range`.
     - Threshold inputs: `value` or `[lower, upper]` for channel/range conditions.
   - `Trigger mode`:
     - `Only once`, `Once per bar`, or `Every time`.
   - `Action`:
     - `Alert only` (default).
     - `Prepare trade` (e.g. `SELL 10%`, `BUY 50 shares` – stored as `action_type` + parameters).
   - `Expiration`: date‑time picker or “No expiry”.

2. **Message**
   - Message template with placeholders: `{symbol}`, `{indicator}`, `{value}`, `{threshold}`.

3. **Notifications**
   - Toggles for:
     - In‑app banner and Holdings row highlight.
     - System event entry in the existing `system_events` log.
     - (Later) Email / Telegram / custom webhook.

These settings are persisted via a new API such as `POST /api/indicator-alerts/` and `GET /api/indicator-alerts?symbol=INFY`.

### 2.4 Backend design for indicator alerts

The backend builds on your existing alerts, orders, and strategies infrastructure.

1. **Rule storage (`indicator_rules` table)**
   - Columns:
     - `id, user_id, strategy_id (nullable)`.
     - `symbol` (or `universe` like `HOLDINGS` / watchlist).
     - `timeframe`.
     - `indicator` (enum: `RSI, MA, MA_CROSS, VOLATILITY, VWAP, PRICE, VOLUME_AVG`, etc.).
     - `indicator_params` (JSON – e.g. `{ "period": 14 }`).
     - `operator` (`GT, LT, CROSS_ABOVE, CROSS_BELOW, BETWEEN, OUTSIDE`).
     - `threshold_1`, `threshold_2` (floats).
     - `trigger_mode` (`ONCE, ONCE_PER_BAR, EVERY_TIME`).
     - `action_type` (`ALERT_ONLY, SELL_PERCENT, BUY_QUANTITY`, etc.).
     - `action_params` (JSON).
     - `last_triggered_at`, `expires_at`, `enabled`.

2. **Indicator engine**
   - Service that:
     - Groups rules by `(symbol, exchange, timeframe)`.
     - Calls `load_series(...)` once per group to fetch the needed candles.
     - Computes required indicators with `pandas`/TA helpers.
   - Returns the latest (and previous) values required for crossing logic.

3. **Rule evaluation**
   - For each rule:
     - Resolve universe:
       - If `symbol` is set → that symbol.
       - If `universe = HOLDINGS` → query holdings for that user.
     - For each symbol, get indicator values and test condition:
       - `GT`: `value > threshold_1`.
       - `CROSS_ABOVE`: `prev <= threshold_1` and `curr > threshold_1`.
       - Range operations for channels.
     - Apply `trigger_mode`:
       - `ONCE` → fire only when `last_triggered_at` is null.
       - `ONCE_PER_BAR` → fire when `bar_time > last_triggered_at`.
     - Successful evaluations produce a `Trigger` object containing symbol, values, and recommended action.

4. **Alert + order creation**
   - When a rule fires:
     - Insert a row into `alerts` (source = `INTERNAL_INDICATOR`, with `rule_id` and human‑readable message).
     - If `action_type != ALERT_ONLY`:
       - For `SELL_PERCENT`:
         - Look up the holding, compute `sell_qty = floor(current_qty * percent/100)`.
         - Create a `WAITING` order in the manual queue (or route to AUTO execution based on `strategy.execution_mode`).
       - Pass the draft order through the existing risk engine (`risk_settings`).
     - Record a `system_events` entry summarizing the trigger for later audit.

5. **Integration with existing strategies**
   - Each rule can optionally link to a `Strategy`:
     - If linked and the strategy is `AUTO` and `LIVE`, triggers may create orders that are immediately executed using the same path as TradingView AUTO alerts.
     - If `MANUAL` or `PAPER`, triggers only generate alerts and/or paper orders.
   - No changes are required to your core order execution or broker adapter; the alert engine only decides *when* to create alerts/orders.

### 2.5 Scheduling and monitoring

1. **In‑process scheduler (recommended for your setup)**
   - Add an `indicator_alerts` scheduler loop similar to the existing market‑data sync:
     - Runs every N minutes, grouped by timeframe:
       - E.g. every 5 min for intraday rules, every 30 min for 1h, once per day after close for daily rules.
     - Uses a fresh `SessionLocal` for each evaluation cycle.
     - Loads all `enabled` rules whose `expires_at` is in the future and evaluates them.
   - Uses IST (`UTC+5:30`) from `market_hours` for all scheduling.

2. **Optional external scheduler**
   - If you prefer not to run background threads inside the app:
     - Expose `POST /api/indicator-alerts/evaluate?timeframe=1d`.
     - Trigger it from cron, systemd timers, or a small worker container.
   - The evaluation service is written independent of how it is called, so switching to an external scheduler later is easy.

### 2.6 High‑level wire diagram

```text
Holdings Grid (UI)
    └─ "Alert" button per row
         └─ opens Alert Modal
               └─ POST /api/indicator-alerts
                     └─ writes indicator_rules

Background scheduler / cron
    └─ loads enabled indicator_rules
        └─ groups by (symbol, timeframe)
            └─ uses MarketData.load_series (candles)
                └─ indicator engine computes RSI/MA/etc.
                    └─ evaluation engine checks conditions
                        └─ when triggered:
                            ├─ insert alerts (source=INTERNAL_INDICATOR)
                            ├─ optional orders (via risk engine + orders API)
                            └─ log system_events

UI Alerts panel / Holdings badges
    └─ GET /api/alerts, /api/indicator-alerts
        └─ shows active alerts and any queued trades
```

This design keeps indicators, alerts, and strategies cleanly separated: the OHLCV store provides raw data, the indicator engine computes features, the rules engine decides *when* to act, and your existing orders/risk infrastructure handles *how* to trade when you opt into execution.

---

## 2a. Types of conditions, queries, and combined filters

**Question**  
What type of conditions will I be able to set? What kind of queries can I make using the indicators beyond the current filters? Can I combine multiple query/filter expressions?

**Answer**  
The alert and filtering system effectively becomes a mini screener on top of your holdings, and the same “condition language” is used both for one‑shot filters and for persistent alerts.

### 2a.1 Condition types for a single alert rule

For one symbol and timeframe, a rule is built from one or more basic conditions:

1. **Indicator vs value**
   - Examples:
     - `RSI(14) > 80`, `RSI(14) < 30`.
     - `Volatility20D% < 25`.
     - `ATR(14)% > 3`.
     - `1M PnL% > 10`, `1Y PnL% < -20`.
     - `Volume / 20D avg > 1.5`.

2. **Price vs indicator**
   - Examples:
     - `Close > MA50`, `Close < MA200`.
     - `Close crosses above MA50`, `Close crosses below MA200`.
     - `Close > VWAP * (1 + X%)` (when VWAP is enabled).

3. **Indicator vs indicator** (advanced / later)
   - Examples:
     - `MA50 > MA200` (trend confirmation).
     - `RSI(14) crosses above RSI(50)` (short‑term vs long‑term momentum).

4. **Range / channel**
   - Examples:
     - `RSI(14)` inside `[40, 60]` (sideways regime).
     - `Close` inside or outside a band `[lower, upper]`.

Each condition is expressed as:

```text
indicator_expression + operator + threshold(s)
```

where `operator ∈ { GT, LT, CROSS_ABOVE, CROSS_BELOW, BETWEEN, OUTSIDE }`.  
The rule also specifies `trigger_mode ∈ { ONCE, ONCE_PER_BAR, EVERY_TIME }` and an optional `expires_at`.

### 2a.2 Combining multiple conditions in one alert

Yes, you can combine multiple conditions within a single rule:

- **AND (all conditions must hold)** – default
  - Example:
    - `MA50 > MA200`
    - `RSI(14) > 60`
    - `Volatility20D% < 30`
  - Meaning: “Strong uptrend + strong momentum + volatility under control.”

- **OR (any condition can hold)** – configurable
  - Example:
    - `RSI(14) < 30` OR `1M PnL% < -10`.
  - Meaning: “Oversold OR heavy one‑month drawdown.”

The UI models this as a single group:

```text
Match: [ All conditions ]  or  [ Any condition ]
Conditions:
  - ...
  - ...
```

Phase‑1 keeps this to a single AND/OR group for clarity. Later, we can extend to nested groups (e.g. `(A & B) OR (C & D)`) by adding a small expression builder.

### 2a.3 Portfolio queries and filters using indicators

The same indicators used for alerts are also exposed as Holdings columns, which turns the grid into a lightweight screener:

1. **Column filters on indicator fields**
   - Examples:
     - Show holdings where `RSI(14) < 30` and `1M PnL% < -10` (deep pullbacks).
     - Show holdings where `MA50% > 0` and `MA200% > 0` (price above both MAs).
     - Show holdings where `Volatility20D% < 20` and `1Y PnL% > 15` (steady compounders).
   - Implemented via the DataGrid filter panel (`>=`, `<=`, ranges) on the new columns.

2. **Saved filters / named views (future enhancement)**
   - Example views:
     - “Strong uptrend”: `MA50 > MA200`, `1M PnL% > 5`, `RSI(14)` between 50 and 70.
     - “High‑risk trades”: `Volatility20D% > 40`, `ATR(14)% > 4`, `Position PnL% < -5`.
   - Internally, these are stored as filter JSON using the same condition schema as alerts, but evaluated immediately in the UI rather than on a schedule.

### 2a.4 Filters vs alerts

- **Filters/queries**
  - Evaluate immediately on the current holdings snapshot.
  - Use indicator values already computed for the grid.
  - No scheduler involved; driven by user interactions (changing filters, reloading the page).

- **Alerts**
  - Are persistent rules stored in `indicator_rules`.
  - Evaluated periodically by the background scheduler or an external cron.
  - When conditions are met:
    - An alert is recorded (and shown in Alerts / System events).
    - If the rule carries a trade action, a `WAITING` order is added to the same queue used by TradingView alerts.

Practically, you can:

1. Use filters to **discover** interesting holdings right now (e.g. oversold, high‑volatility, strong uptrends).
2. Convert those same conditions into **persistent alerts** so the system notifies you (and optionally prepares trades) whenever any holding meets those criteria in the future.

---

## 3. Implementing and maintaining the OHLCV store (Kite, timeframes, and updates)

**Question**  
Earlier I said “if I maintain OHLCV data for max 2 years”. Now I want to know more on this: how are we going to implement it? How do we ensure our OHLCV data is always updated? We could use last data access datetime or a scheduler to update it. I want to maintain Kite data for a given interval/timeframe (`1min, 5min, 15min, 1h, 1d, 1mo, 1y`) and period/duration (`today, previous nn days, nn months, nn years`). Kite API has limits on the number of days you can fetch in a single request. Use an appropriate technique to loop through different date ranges and fetch the data in chunks, then combine them into a single dataset.

**Answer**  
The core idea is to treat your OHLCV as a canonical “candles” store backed by chunked calls to Kite’s historical API, with a lightweight layer that fills gaps on demand and/or via a scheduler. A practical design:

1. **Data model**
   - Table `candles` (or `market_candles`):  
     `symbol`, `exchange`, `timeframe` (`1m`, `1d`, etc.), `ts`, `open`, `high`, `low`, `close`, `volume`.  
     Use a composite unique key on `(symbol, exchange, timeframe, ts)` to support idempotent upserts.
   - Optional `instrument_map` table mapping `(symbol, exchange)` → `instrument_token` required by Kite’s historical API.
   - Retention: periodic cleanup job removing rows older than 2 years (`ts < now - 2y`).

2. **Chunked backfill using Kite limits**
   - Choose a maximum span per request, e.g. `max_days_per_call = 60` (or Kite’s documented limit).
   - For a requested window `(start, end)` and base timeframe (`minute` or `day` in Kite terms):
     - Build non-overlapping chunks `[start_i, end_i]` of at most `max_days_per_call`.
     - For each chunk call `kite.historical_data(token, from_date=start_i, to_date=end_i, interval=...)`.
     - Normalize to your schema (`ts`, `open`, `high`, `low`, `close`, `volume`) and collect all bars.
     - Sort by `ts`, drop duplicates, then upsert into `candles`.
   - This function can be reused for initial 2-year backfill and for filling new gaps.

3. **Timeframes and periods**
   - Store base granularities from Kite, typically:
     - `minute` → your `1m` base candles.
     - `day` → your `1d` base candles.
   - Derive higher intervals on read:
     - `5min`, `15min`, `1h` aggregated from `1m` candles.
     - `1mo`, `1y` aggregated from `1d` candles.
   - For a UI selection like “timeframe = 15min, period = last 3 months”:
     - Compute `(start, end)` dates.
     - Ensure `1m` candles exist for `[start, end]` (see step 4 below).
     - Aggregate into 15-minute buckets: open = first open, high = max(high), low = min(low), close = last close, volume = sum(volume).

4. **Keeping OHLCV up-to-date**
   - **Lazy gap-filling on read (on-demand):**
     - When a request for `(symbol, exchange, base_timeframe, start, end)` arrives:
       - Query `candles` for that key and check the min/max `ts` you have.
       - If `min_ts > start` or `max_ts < end`, identify missing segments and call the chunked fetcher for those ranges.
       - Upsert new bars, then return the complete series.
     - Pros: no scheduler needed, you only fetch what you actually use.  
       Cons: first request for a symbol/period can be slower because backfill runs during the request.
   - **Scheduled sync (proactive):**
     - Run a small job (cron, APScheduler, etc.) daily after market close:
       - For each symbol in your “universe” (holdings, watchlists, major indices) and each stored timeframe:
         - Look up last `ts` in `candles`.
         - Fetch from `last_ts + interval` to “now” via the chunked fetcher.
     - Pros: queries are fast and data is fresh.  
       Cons: needs a small background process or cron integration.
   - In practice, combining both works best: nightly sync for your main universe plus lazy gap-filling for rarely used symbols or new timeframes.

5. **User-facing periods (“today”, “last N days/months/years”)**
   - Translate the user’s period into `(start, end)`:
     - `today` → from market open today to now (or close).
     - `last N days` → from `today - N days` to now.
     - `last N months` / `last N years` → subtract calendar months/years from today.
   - Call `ensure_history(symbol, exchange, base_timeframe, start, end)` which:
     - Detects gaps.
     - Uses chunked Kite calls to fill them.
   - After that, load from `candles` and aggregate to the requested timeframe (`1m, 5m, 15m, 1h, 1d, 1mo, 1y`) before sending to the chart or indicator engine.

6. **Where this plugs into SigmaTrader**
   - Backend:
     - Implement `candles` schema and `instrument_map`.
     - Add a `market_data` service with functions like:
       - `ensure_history(symbol, exchange, base_timeframe, start, end)`.
       - `load_series(symbol, exchange, timeframe, start, end)` that internally aggregates from base candles.
     - Optional REST endpoint `/api/market/history` on top of `load_series`.
   - Frontend:
     - Period/timeframe selector on the Holdings page.
     - Chart column that calls `/api/market/history` and renders the sparkline.
   - Indicators and alerts:
     - The indicator engine and rule scheduler from the previous Q&A will use `load_series(...)` as their data source, so keeping `candles` up-to-date automatically keeps alerts accurate.
