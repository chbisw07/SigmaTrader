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
Yes, with ~2 years of OHLCV per symbol you can support rules like “Sell 10% when RSI(14) > 80” and general strategy-driven signals. Complexity is moderate and fits well into SigmaTrader’s existing alert/order architecture. A pragmatic design:

1. **Market data store**
   - Create a `candles` table (or equivalent store) with columns such as:  
     `symbol`, `exchange`, `timeframe` (`1D`, `1H`, …), `ts`, `open`, `high`, `low`, `close`, `volume`.
   - Backfill up to 2 years of data per symbol from Zerodha or another provider.
   - Keep it updated via a scheduled ingestion job (e.g. end-of-day for daily bars, or more frequently for intraday strategies).

2. **Indicator/analytics engine**
   - Implement a backend service layer that:
     - Loads recent candles for a given `(symbol, exchange, timeframe)`.
     - Computes indicators using `pandas` + a technical-analysis library (RSI, ADX, volatility, VWAP, moving averages, etc.).
   - Optionally expose an API like:  
     `GET /api/analytics/indicator?symbol=INFY&indicator=RSI&period=14&timeframe=1D&lookback=60`  
     for debugging and UI overlays.

3. **Rule / alert definitions**
   - Add a table such as `indicator_rules` describing per-user rules:
     - `user_id`, `name`.
     - `universe` (single symbol, `HOLDINGS`, watchlist, explicit list).
     - `indicator` (e.g. `RSI`) and `params` (e.g. `{ "period": 14 }`).
     - `timeframe` (`1D`, `1W`, etc.).
     - `condition` (e.g. `>`, `<`, `crosses_above`, `crosses_below`) and `threshold` (e.g. `80`).
     - `action` (`ALERT_ONLY`, `SELL_PERCENT`, `BUY`, etc.) plus `action_params` (e.g. `{ "percent": 10 }`).
     - `enabled` flag and evaluation schedule (e.g. end-of-day, every 15 minutes).

4. **Scheduler and evaluation loop**
   - Run a background job (e.g. APScheduler in the backend) that periodically:
     - Loads all active rules for each user.
     - For each rule, resolves its universe:
       - For holdings rules, query the user’s current holdings (symbols + quantities) from the positions/holdings APIs.
     - For each symbol in the universe:
       - Fetch the last N candles for the configured timeframe.
       - Compute the requested indicator series.
       - Check the rule condition; for “crosses above 80”, compare the last two values `prev`, `curr` and fire only when `prev <= 80` and `curr > 80`.
     - When a rule fires:
       - Create an `Alert` row (e.g. platform `INTERNAL`, reason `"RSI(14) crossed above 80"`).
       - If the rule’s action is trade-related (e.g. `SELL_PERCENT`):
         - Derive the trade size from holdings (e.g. `sell_qty = floor(current_qty * 0.10)`).
         - Create an `Order` row in `WAITING` (manual queue) or `AUTO` mode according to rule/strategy settings.

5. **Integration with existing strategies and execution**
   - You already have a `Strategy` model with `execution_mode` (`AUTO` / `MANUAL`) and `execution_target` (`LIVE` / `PAPER`), plus a robust order execution pipeline (risk checks, paper trading, Zerodha integration).
   - Rules can be:
     - Attached to strategies (e.g. each rule belongs to a strategy), or
     - Standalone but specifying whether to auto-execute or just enqueue manual orders.
   - Once an `Order` is created, everything else (risk engine, paper vs live routing, Zerodha execution, system events) is reused as-is.

In terms of effort, the main blocks are:
- Designing and populating the OHLCV store.  
- Implementing the indicator computation layer.  
- Creating a simple rule model + scheduler loop that ties indicators to `Alert`/`Order` creation.  

From there you can iteratively add more indicators, conditions, and strategy wiring without needing to change the core trading or broker integration logic.

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

