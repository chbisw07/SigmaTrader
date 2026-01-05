# Trailing Stop-Loss & Trailing Take-Profit Strategy

## Intent
The intent of this design is to support **robust, flexible, and scalable trailing Stop-Loss (SL) and trailing Take-Profit (TP)** for strategy deployment, without forcing a single execution model on all users. The system should work reliably for real trading in Indian markets (NSE/BSE), align backtesting and live execution semantics, and remain performant even when monitoring **20–50+ symbols**.

The guiding philosophy is:
> **“I can cut profits, but I can’t take losses.”**

This means:
- Downside protection is non‑negotiable.
- Profits may be given back partially, but never allowed to turn into large losses.
- Trailing SL is the primary risk primitive; trailing TP is complementary and optional.

---

## Core Challenges

### 1. Broker limitations
- Zerodha (Kite Connect) does **not** provide a first‑class trailing SL/TP order type via API.
- Native BO-style trailing is unavailable; GTT supports fixed SL/TP (OCO) but **not dynamic trailing**.
- Therefore, true trailing must be **implemented by our application**, not delegated entirely to the broker.

### 2. Infrastructure vs precision trade‑off
- Tick-level trailing gives the best responsiveness but can overload systems when tracking many symbols.
- Bar-based trailing (1m/5m) is cheaper and more stable but reacts slower.
- We must balance **precision, safety, scalability, and operational simplicity**.

### 3. Failure safety
- If the app crashes or loses connectivity, positions must not be left unprotected.
- Trailing logic must not depend on continuous uptime.

### 4. Backtest ↔ live uniformity
- Trailing behavior must be definable in a way that backtesting can reasonably approximate.
- Lookahead bias and “perfect intrabar fills” must be avoided.

---

## Design Principles

1. **Broker-side protection is mandatory**
   - A broker-enforced hard SL (and optional TP via OCO/GTT) is always placed as a *disaster stop*.
   - This guarantees capital protection even if the app is down.

2. **Trailing logic lives in the app**
   - Trailing SL and trailing TP are calculated and enforced by the strategy engine.
   - The app may either:
     - update broker-side stops (modify GTT/SL), or
     - exit positions directly when a trailing condition is hit.

3. **Event-driven, not tick-spammed**
   - Trailing updates are evaluated on deterministic events (ticks or bar closes),
     gated by thresholds and cooldowns to avoid API spam.

4. **User choice, not one-size-fits-all**
   - Users can select the trailing precision mode that fits their symbol count, risk appetite, and infra.

---

## Trailing Modes (User-Selectable)

### Mode A — Scalable (Default)
**Label:** `Scalable / Low Infra`
- Internal resolution: **5-minute bars**
- Trailing updates: on 5m bar close
- Tick streaming: **disabled**
- Suitable for:
  - Group strategies
  - 50+ symbols
  - Long-term / swing systems

**Pros:** very stable, minimal load, easy reconciliation
**Cons:** slower reaction, more profit giveback

---

### Mode B — Balanced (Recommended Default for Single Symbols)
**Label:** `Balanced / Intrabar-lite`
- Internal resolution: **1-minute bars**
- Trailing updates: on 1m bar close
- Tick streaming:
  - enabled **only for open positions**
  - activated **only when price is near stop/TP threshold**

- Suitable for:
  - Single-symbol deployments
  - ~20–40 symbols total

**Pros:** near-intrabar behavior, good performance, controlled complexity
**Cons:** slightly higher infra cost than 5m

---

### Mode C — High Precision
**Label:** `High Precision / Tick-Level`
- Internal resolution: **ticks + 1m fallback**
- Trailing updates: on tick events
- Tick streaming: always on for open positions

- Suitable for:
  - Small universes (≤10–15 symbols)
  - Highly active strategies

**Pros:** fastest reaction, minimal giveback
**Cons:** higher complexity, higher API usage, needs stronger ops discipline

---

## Trailing Stop-Loss (Primary Risk Control)

### Logic
For a **long position**:
- Track `MFE` (Maximum Favorable Excursion): highest price since entry
- Compute trailing stop:
  ```
  trailing_SL = MFE - trail_distance
  ```

### Update rules
- Update trailing SL only if:
  - new SL improves by ≥ `trail_step`
  - cooldown since last update has elapsed

### Trigger
- If LTP (or bar close, depending on mode) ≤ `trailing_SL` → exit immediately

### Notes
- Trailing SL is always subordinate to the broker-side disaster SL.
- Once in profit, trailing SL ensures **profits never turn into losses**.

---

## Trailing Take-Profit (Secondary Profit Capture)

### Intent
Trailing TP is **not** a replacement for SL.
It exists to:
- capture gains earlier in volatile reversals
- reduce profit giveback after strong runs

### Logic
- Activate trailing TP only after profit ≥ `tp_activation_threshold`
- Track `profit_peak` (same as MFE)
- Compute trailing TP trigger:
  ```
  trailing_TP = profit_peak - tp_giveback
  ```

### Trigger
- If price falls back to `trailing_TP` → exit

### Interaction with SL
- Both trailing SL and trailing TP may coexist
- Whichever triggers first exits the trade

---

## Safety Layer (Non-Negotiable)

Immediately after entry confirmation:
- Place **broker-side hard SL** (and optional TP) via supported order types
- This stop is wider than app trailing logic
- Ensures protection during:
  - app crashes
  - restarts
  - network issues

---

## Performance & Scalability Considerations

To avoid choking the system:
- Trailing calculations run **only for active positions**
- Order modifications are throttled by:
  - minimum price improvement (`trail_step`)
  - minimum time between updates
- Tick streaming is **selectively enabled**, not global

With this design:
- 20–50 symbols are safe on commodity hardware
- Your ThinkPad T15g Gen2 is more than sufficient

---

## Default Trailing Parameters (Recommended Presets)

These presets are designed to be **robust on NSE/BSE equities**, align with the philosophy **“cut profits, can’t take losses”**, and remain **operationally safe** (bounded order updates) across different trailing modes.

### Parameter meanings
- **trail_dist**: distance from the best favorable price used to compute the trailing SL.
- **trail_step**: minimum improvement required before we update the stop (prevents spam).
- **tp_activation**: profit threshold after which trailing TP becomes active.
- **tp_giveback**: allowed retracement from peak/trough before we exit via trailing TP.
- **cooldown**: minimum time between consecutive broker updates (only relevant if we push stop updates to broker; otherwise used to gate app decisions).

> Defaults below are **percent-based** (simpler, stable across symbols). We will also expose an **ATR-based mode** (trail_dist = k × ATR) as an alternative for users who prefer volatility-normalized trails.

---

### Long vs Short symmetry
We implement the same logic for longs and shorts with mirrored definitions:

**Long position**
- `MFE = highest_price_since_entry`
- `trailing_SL = MFE × (1 - trail_dist)`
- `trailing_TP_trigger = MFE × (1 - tp_giveback)` (active only after `profit >= tp_activation`)

**Short position**
- `MFE = lowest_price_since_entry`
- `trailing_SL = MFE × (1 + trail_dist)`
- `trailing_TP_trigger = MFE × (1 + tp_giveback)` (active only after `profit >= tp_activation`)

Profit thresholds (activation) are computed against entry:
- Long profit % = `(LTP/entry - 1)`
- Short profit % = `(entry/LTP - 1)`

---

### Presets by deployment type

#### 1) Single-symbol deployments (more responsive)
**Recommended default:** Balanced mode (1m + selective ticks)

- **Disaster SL (broker-side)**: `2.8%` (placed immediately after entry confirmation)
- **Trailing SL**
  - `trail_dist = 1.4%`
  - `trail_step = 0.25%`
  - `activation = 0.8%` profit (start tightening only after trade moves in favor)
- **Trailing TP**
  - `tp_activation = 2.0%` profit
  - `tp_giveback = 0.8%`
  - (optional) `tp_step = 0.25%` (if TP trigger is also updated/managed)
- **Update cadence / cooldown**
  - 1m mode: evaluate on each 1m bar close; update only if improvement ≥ `trail_step`
  - selective tick mode: when within **0.7%** of stop/TP trigger, allow tick-based trigger detection; throttle broker updates to **≥ 20s**

Rationale: tighter control, but still avoids excessive churn; trailing SL is primary, trailing TP captures reversals after decent profit.

---

#### 2) Group deployments (more stable, scalable)
**Recommended default:** Scalable mode (5m bars)

- **Disaster SL (broker-side)**: `3.5%`
- **Trailing SL**
  - `trail_dist = 1.9%`
  - `trail_step = 0.40%`
  - `activation = 1.2%` profit
- **Trailing TP**
  - `tp_activation = 2.5%` profit
  - `tp_giveback = 1.0%`
  - (optional) `tp_step = 0.40%`
- **Update cadence / cooldown**
  - Evaluate on each 5m bar close
  - Broker update cooldown effectively equals bar cadence (no intra-bar modifications)

Rationale: groups create more simultaneous activity; wider trails reduce whipsaws and keep API usage bounded.

---

### Presets by trailing mode (system behavior)

#### Mode A — Scalable (5m)
- Use the **Group** preset by default.
- Exit triggers fire on 5m bar close (unless user explicitly enables tick-trigger for open positions).

#### Mode B — Balanced (1m + selective ticks)
- Use the **Single-symbol** preset by default.
- Tick streaming is enabled only for:
  - symbols with an open position, AND
  - price is within **0.7%** of trailing SL/TP trigger.

#### Mode C — High Precision (tick-level)
- Start from **Single-symbol** preset.
- Reduce `trail_step` to `0.15%` and cooldown to **≥ 10s** (still bounded).
- Only recommended for small universes (≤10–15 active symbols).

---

### Volatility handling (ATR-first)

Volatility materially changes how tight/loose a trailing SL/TP should be. A fixed percent trail that works for a low-vol stock will either:
- **whipsaw** on a high-vol stock (too tight), or
- **give back too much** on a low-vol stock (too loose).

To handle this efficiently and robustly, we adopt an **ATR-first volatility model**.

#### What we do internally
- We compute **ATR(14)** per symbol on the engine’s internal bar resolution:
  - **1m** when trailing mode is Balanced / High Precision (or when user chooses 1m internal)
  - **5m** when trailing mode is Scalable (or when user chooses 5m internal)
- Tick-mode does **not** compute ATR on ticks; it reuses the **latest bar-updated ATR**.
- Trailing distances/steps are computed in **price units**, then applied to LTP/bar-close depending on the selected mode.

This keeps runtime cost low: ATR is O(1) per bar per symbol and is negligible compared to market-data IO.

#### What we expose in UX
We expose two user-facing ways to define trailing parameters:

1) **Percent mode (simple and intuitive)**
- User specifies: `trail_dist%`, `trail_step%`, `tp_activation%`, `tp_giveback%`
- Internally, we convert percent to price distance:
  - Long: `trail_dist_price = trail_dist% × reference_price`
  - Short: similarly

2) **ATR mode (volatility-adaptive)**
- User specifies ATR multiples:
  - `k_trail_sl`, `k_step`, `k_giveback_tp`, and optionally `k_disaster_sl`
- Internally:
  - `trail_dist_price = k_trail_sl × ATR(14)`
  - `trail_step_price = k_step × ATR(14)`
  - `tp_giveback_price = k_giveback_tp × ATR(14)`
  - `disaster_sl_price = k_disaster_sl × ATR(14)`

**Decision:** ATR mode is a first-class option and is recommended for users deploying across a diverse universe.

---

### ATR guardrails for Percent mode (recommended default)
Even in Percent mode, we prevent pathological trails by clamping percent-derived distances to an ATR band:

- `trail_dist_price = clamp(trail_dist% × ref_price, min_k × ATR, max_k × ATR)`
- `trail_step_price = clamp(trail_step% × ref_price, min_step_k × ATR, max_step_k × ATR)`

Default clamp bands (can be tuned):
- Single-symbol: `trail_dist ∈ [1.2×ATR, 2.8×ATR]`, `step ∈ [0.25×ATR, 0.60×ATR]`
- Group: `trail_dist ∈ [1.5×ATR, 3.2×ATR]`, `step ∈ [0.35×ATR, 0.80×ATR]`

This keeps Percent mode intuitive while making it volatility-safe.

---

### ATR percentile regime (optional, but recommended for robustness)
ATR alone adapts continuously, but markets often shift between regimes (quiet vs volatile). We optionally classify volatility into regimes using an **ATR percentile** computed over a rolling lookback:

- Compute `atr_pct = percentile_rank(ATR(14), lookback=N)` per symbol
- Suggested `N`:
  - 100 bars for 1m engine
  - 60 bars for 5m engine

Define regimes (defaults):
- **Low vol:** `atr_pct < 30`
- **Normal:** `30 ≤ atr_pct ≤ 70`
- **High vol:** `atr_pct > 70`

Regime effect (simple multiplier on trailing distances):
- Low vol: tighten trails: `mult = 0.85`
- Normal: baseline: `mult = 1.00`
- High vol: widen trails: `mult = 1.20`

Apply:
- `trail_dist_price *= mult`
- `tp_giveback_price *= mult`
- `trail_step_price *= sqrt(mult)` (steps widen slower than distances)

**Rationale:**
- Tighten in calm markets to reduce idle giveback.
- Widen in high vol to reduce whipsaw.
- Keep steps less sensitive to avoid excess order updates.

**Decision:**
- ATR percentile regime is implemented as an optional toggle (default ON for group deployments, optional for single symbol).
- Regime transitions are smoothed (e.g., require 2 consecutive bars in new regime) to avoid flip-flopping.

---

### ATR-based alternative (optional user mode)
If user selects ATR-based trailing:
- **Single-symbol**
  - `trail_dist = 1.6 × ATR(14)`
  - `disaster_SL = 2.6 × ATR(14)`
  - `tp_giveback = 1.0 × ATR(14)`
- **Group**
  - `trail_dist = 2.0 × ATR(14)`
  - `disaster_SL = 3.0 × ATR(14)`
  - `tp_giveback = 1.2 × ATR(14)`

In ATR mode, `trail_step` is expressed as `0.4 × ATR(14)` (single) and `0.6 × ATR(14)` (group) to control update frequency.

---

### Practical guardrails (must-have)
To keep the system stable and costs predictable:
- Never modify broker-side stops unless the new stop improves by ≥ `trail_step`.
- Enforce per-symbol update cooldowns (10–60s depending on mode).
- Apply tick streaming only to **open positions**; never stream ticks for the entire universe by default.
- Always retain a broker-side disaster SL even when app trailing is enabled.

## Candle Event Source + Bar-Close Semantics

### Intent
The trading engine must be **event-driven**, not polling-based. All strategy decisions, trailing SL/TP updates, and volatility (ATR) updates should be triggered by **deterministic market events** so that backtests and live execution share the same clock and semantics.

### New / Updated Understanding
- Bar-close events are the **authoritative timing signal** for both strategy evaluation and trailing logic.
- Tick events are **optional accelerators**, not the primary clock.
- Daily strategies (`tf = 1d`) cannot rely on the official exchange close (15:30) if we want realistic same-day execution; instead, we use a **daily-via-intraday proxy close at 15:25**.

### What We Will Do (Decision)

#### Event Types
We define two classes of market events:

1) **Bar-close events (primary)**
- `BAR_CLOSED(symbol, internal_tf, bar_end_ts, ohlcv)`
- Emitted from the market data layer at each internal timeframe close.
- Internal timeframe depends on trailing mode:
  - Scalable: 5m
  - Balanced: 1m
  - High precision: 1m (ticks optional)

On every bar-close event, the runner:
- Updates indicators and strategy state
- Updates ATR(14)
- Updates ATR percentile regime (if enabled)
- Advances trailing SL/TP state using step + cooldown rules

2) **Tick events (optional, secondary)**
- `TICK(symbol, ts, ltp)`
- Enabled only for:
  - symbols with an open position
  - and only in Balanced (selective) or High Precision mode

Tick events:
- **Do not recompute indicators or ATR**
- Are used only to detect immediate trailing SL/TP breaches and trigger exits faster

#### Daily Timeframe (tf = 1d)
- We do not wait for the official daily candle close at 15:30.
- Internally, the runner operates on intraday bars (default 5m).
- The bar ending at **15:25** is treated as the **daily proxy close**.
- At that moment, we emit a synthetic event:
  - `DAILY_PROXY_CLOSED(symbol, date, ts=15:25, snapshot)`
- Strategy entry/exit logic for `tf = 1d` is evaluated on this event.

#### Execution Windows
- **Preferred BUY window:** 15:25–15:30 (based on proxy close)
- **Preferred SELL / risk window:** 09:15–09:20
- Trailing SL/TP continues to run throughout the session, but *new entries* are window-gated.

### What This Section Answers
- How do we know *when* to evaluate strategies and trailing? → Bar-close events.
- How do we avoid polling and lookahead? → Event-driven bars + proxy close.
- How do daily strategies act intraday? → 15:25 proxy daily close.

---

## Runner ↔ Broker / Order Model Mapping

### Intent
Clearly separate **strategy intent**, **risk protection**, and **trailing intelligence**, so that:
- broker limitations do not constrain strategy design,
- trailing SL/TP can evolve without breaking execution,
- paper and live trading behave consistently.

### New / Updated Understanding
- Brokers (e.g., Zerodha) cannot natively express trailing SL/TP via API.
- Therefore, trailing must be **app-managed**, while brokers provide a **hard safety layer**.
- The runner must emit **idempotent, auditable actions**, not raw broker calls.

### What We Will Do (Decision)

#### Action Plan Model
On each evaluation event, the runner produces an **Action Plan** composed of three parts:

1) **TradeIntent (strategy-level)**
- `ENTER_LONG`, `ENTER_SHORT`, `EXIT`, `REVERSE`, or `NOOP`
- Derived from strategy logic (signals, windows, regime)

2) **RiskIntent (broker safety layer)**
- Ensure a broker-enforced **disaster stop-loss** exists after entry confirmation
- Optionally ensure a fixed TP (OCO/GTT) if supported
- This layer exists to protect capital if the app fails

3) **TrailingEngineUpdate (app-managed)**
- Maintain trailing state:
  - MFE / MAE
  - trailing SL / trailing TP thresholds
  - ATR-based or percent-based distances
  - ATR percentile regime adjustments
- Decide one of:
  - `ExitNow` (place broker exit order)
  - `ModifySafetyStop` (optional, step-gated)
  - `NoChange`

#### Order Types
- **Entry orders:** MARKET (default) or LIMIT (configurable)
- **Exit orders:** MARKET (default, for safety)
- **Safety orders:** broker-supported SL / GTT / OCO
- Trailing exits are usually executed as **market exits** when triggered

#### Idempotency & De-duplication
- Every Action Plan and broker interaction carries a stable idempotency key
- Suggested key components:
  - `deployment_id + symbol + action_type + event_ts + version`
- The runner stores:
  - last applied stop price
  - last modification timestamp
- Step and cooldown rules prevent repeated no-op updates

#### Paper vs Live
- Paper and live share the **same Action Plan generation**
- Differences are only in the broker adapter:
  - PaperBroker simulates fills
  - LiveBroker executes real orders
- Event sources (bars/ticks) and trailing logic are identical, ensuring parity

### What This Section Answers
- What exactly does the runner create when a deployment fires? → Action Plan.
- How are SL/TP/trailing represented without broker-native trailing? → App-managed trailing + broker safety stop.
- How do we avoid duplicate orders? → Idempotent intents + step/cooldown gating.

---

## State + Reconciliation Contract

### Intent
Ensure the trading system behaves **safely, predictably, and audibly** in the presence of real‑world broker behavior: partial fills, rejections, latency, and manual user actions. The goal is to avoid hidden divergence between strategy intent and actual positions.

### Source of Truth
- **Broker is the source of truth** for:
  - Net positions (quantity, average price)
  - Order status (OPEN / FILLED / PARTIAL / REJECTED / CANCELLED)
  - Executions and fills

- **Runner is the source of truth** for:
  - Strategy intent (why we entered/exited)
  - Desired target state (FLAT / LONG / SHORT)
  - Trailing SL/TP state (MFE, thresholds, volatility regime)
  - Deployment lifecycle state

On any mismatch, **broker state always wins**.

### Reconciliation Scenarios

#### Partial fills
- Runner updates its internal `PositionState` with:
  - filled quantity
  - broker-reported average price
  - remaining quantity
- Trailing SL/TP activates as soon as `filled_qty > 0`.
- Default behavior for remainder:
  - cancel remaining quantity at window end (configurable).

#### Order rejections
- Intent is marked `FAILED_REJECTED` with broker reason.
- Default policy:
  - no automatic retries for entries (prevents loops)
  - optional single retry for transient errors, only if still inside execution window.

#### Manual broker intervention
- Detected when broker position/order changes without a matching runner intent.
- Default policy:
  - mark deployment as `PAUSED_MANUAL`
  - stop further automation for affected symbols
- Resume requires explicit user action:
  - “Adopt broker state” **or**
  - “Flatten and resume”.

### Minimal State Model (per symbol per deployment)
- `desired_target`: FLAT / LONG(qty) / SHORT(qty)
- `observed_position`: broker net qty + avg price
- `phase`: FLAT | ENTERING | OPEN | EXITING | ERROR | PAUSED_MANUAL
- `open_orders`: broker order ids
- `intent_history`: recent intents with idempotency keys
- `trailing_state`: MFE, trailing SL/TP levels, last update timestamp

This state is sufficient to reconcile deterministically and restart safely.

---

## Operational Controls + Reliability

### Intent
Prevent runaway execution, duplicate orders, and unsafe behavior during crashes, restarts, or extreme market conditions.

### Kill Switches
- **Global kill switch** (env/config): immediately blocks all new orders.
- **Per‑deployment switch**: `deployment.enabled = false` stops scheduling and execution.
- **Per‑symbol pause** (optional): useful during manual intervention or abnormal behavior.

### Bounded Concurrency
- `max_active_deployments_per_user` (e.g., 10)
- `max_concurrent_symbols_per_user` (e.g., 5)
- `max_order_actions_per_minute` (rate limiting)

These limits protect both system stability and broker APIs.

### Durable Job Queue
- All evaluations are persisted as jobs:
  - `(user_id, deployment_id, symbol, event_ts, job_type)`
- Job states: QUEUED → RUNNING → DONE / FAILED
- Unique `dedupe_key` enforces exactly‑once intent generation.

### Locks & Restart Safety
- Distributed lock per decision unit:
  - `(user_id, deployment_id, symbol, event_ts, job_type)`
- Locks prevent double‑fires across restarts.
- On restart:
  - stale RUNNING jobs (past TTL) return to QUEUED
  - idempotent intents ensure safe re‑execution

### Idempotency
- Every intent and broker action carries a stable idempotency key:
  - hash of `(user_id, deployment_id, symbol, action_type, event_ts, version)`
- Broker calls use this key as client reference where supported.

---

## Multi‑tenant / Per‑User Boundaries

### Intent
Design for future multi‑user support without complicating today’s single‑user execution.

### Decision
- **Deployments run only for the logged‑in user.**
- Execution today is single‑user, but all data is stored with per‑user isolation.

### What We Will Do
- Every entity includes `user_id`:
  - deployments
  - jobs
  - intents
  - orders
  - locks
- Runner loads and executes deployments **only for the authenticated user**.
- Lock keys and dedupe keys include `user_id` to ensure isolation.

### Why This Matters
- Avoids refactors when adding more users later.
- Prevents cross‑user interference.
- Keeps mental model simple today while remaining future‑proof.

---

## Market Hours, Timezone & Calendar Handling

### Intent
Ensure all strategy evaluation, execution windows, and trailing logic behave **correctly across real market schedules**, including holidays, half-days, and special sessions, while remaining transparent, configurable, and independent of fragile external APIs.

### Core Principles
- Time is always interpreted in the **exchange’s local timezone** (for NSE/BSE: `Asia/Kolkata`).
- Trading decisions must respect **actual trading sessions**, not hard-coded assumptions.
- Calendar and session rules must be **explicit, user-visible, and overridable**.

---

### Exchange Calendar (Holiday & Session Management)

#### Calendar Source
- The system provides a **Settings UI** to upload an **exchange holiday calendar CSV** (per exchange, e.g., NSE, BSE).
- Uploaded calendars are persisted in the database and treated as authoritative.

#### Recommended CSV Schema
- `date` (YYYY-MM-DD)
- `session_type` (`NORMAL`, `HALF_DAY`, `CLOSED`, `SPECIAL`)
- Optional:
  - `open_time` (HH:MM)
  - `close_time` (HH:MM)
  - `notes` (e.g., Diwali Muhurat, special settlement)

This allows clean handling of half-days and special sessions without hard-coded logic.

---

### Market Session Configuration (per exchange)

Via Settings, the user can configure default session parameters:
- `timezone` (default: Asia/Kolkata)
- `market_open` (default: 09:15)
- `market_close` (default: 15:30)
- `daily_proxy_close_time` (default: 15:25)
- `preferred_sell_window` (default: 09:15–09:20)
- `preferred_buy_window` (default: 15:25–15:30)

These defaults apply to **NORMAL** sessions unless overridden by the calendar.

---

### Half-Day / Special Session Handling

When the calendar marks a day as `HALF_DAY` or `SPECIAL`:
- Session `open_time` and `close_time` are taken from the calendar row.
- Execution windows are derived dynamically:
  - `daily_proxy_close = close_time − 5 minutes`
  - `preferred_buy_window = (close_time − 5 min) → close_time`
  - `preferred_sell_window` remains near open unless explicitly overridden

This keeps strategy behavior consistent even on shortened sessions.

---

### Runtime Behavior (How the App Uses the Calendar)

For each trading day and symbol:
1) Resolve the exchange (NSE/BSE).
2) Look up the date in the exchange calendar.
3) If `CLOSED`:
   - no jobs are scheduled
   - no strategy or trailing logic runs.
4) If trading session exists:
   - load that day’s open/close times
   - derive execution windows and proxy close
   - schedule bar-close–driven jobs accordingly.

All timestamps are:
- evaluated in exchange local time
- stored internally with both local time and UTC for audit/debugging.

---

### Safety Fallbacks

If no calendar is available:
- Default to Monday–Friday as trading days.
- If no market data is received by `market_open + 5 min`, skip trading for the day.

Calendar upload is strongly recommended for production use.

---

### Why This Design
- Avoids dependency on third-party calendar APIs.
- Makes special sessions explicit and testable.
- Keeps execution windows consistent with backtesting and live trading.
- Gives users full control while remaining safe by default.

---

## Engineering Decisions (Locked for MVP)

This section explicitly addresses the remaining engineering decisions raised during review. These are **non-blocking but must be locked early** to avoid ambiguity during implementation. All items below are now decided and should be treated as authoritative.

---

### 1) BAR_CLOSED Implementation & Data Source of Truth

**Decision:** Use a **deployment-scoped candle pump** with the **Candle DB as the single source of truth**.

**Details:**
- The bar-close engine emits `BAR_CLOSED(symbol, tf, bar_end_ts, ohlcv)` events.
- For determinism, the engine reads the **latest closed candle from the Candle DB**.
- If a candle is missing (bootstrap / cold start only):
  - Fetch from broker/market-data API
  - Persist immediately into Candle DB
  - Only then emit `BAR_CLOSED`

**Why:**
- Prevents two competing sources of truth
- Guarantees backtest/live parity
- Simplifies replay, backfill, and debugging

---

### 2) Job Queue + Locking Semantics (SQLite-safe)

**Decision:** Durable DB-backed job queue with atomic claim + idempotent execution.

**Job lifecycle:**
- States: `QUEUED → RUNNING → DONE / FAILED`
- Each job has a unique `dedupe_key` (UNIQUE constraint)

**Atomic claim pattern (required):**
- Claim using a single SQL statement:
  - `UPDATE jobs SET status='RUNNING', claimed_at=now(), attempt_count=attempt_count+1 WHERE status='QUEUED' AND job_id=?`
  - Proceed only if `rows_affected == 1`

**Restart safety:**
- Jobs stuck in `RUNNING` beyond TTL are returned to `QUEUED`
- Reprocessing is safe because:
  - intents are idempotent
  - broker actions use idempotency keys

**Locks:**
- Lock key: `(user_id, deployment_id, symbol, event_ts, job_type)`
- Lock must be acquired before job execution

---

### 3) Zerodha Disaster SL Lifecycle (CNC + MIS)

**Decision (locked):**
- **CNC:** GTT-first disaster SL
- **MIS:** SL / SL-M day order

**Lifecycle rules:**
- Create disaster SL **only after entry fill confirmation**
- Persist broker reference:
  - `disaster_sl_ref` (GTT ID or order ID)
- On exit / flatten:
  - cancel the disaster SL

**Orphan prevention:**
- On each reconciliation cycle:
  - Position exists & no disaster SL → create it
  - Position flat & disaster SL exists → cancel it
- On manual broker intervention:
  - Mark deployment `PAUSED_MANUAL`
  - Do **not** auto-create or modify GTTs
  - Require explicit user action:
    - “Adopt broker state” or “Flatten and resume”

**Trailing interaction:**
- Trailing SL/TP is **app-managed only** in MVP
- Broker disaster SL is static and wide
- Trailing trigger → `ExitNow` (market exit)

---

### 4) Warm-up Lookback Calculation (DSL-aware)

**Decision:** Warm-up is mandatory for entries; exits are always allowed.

**Formula (locked):**
```
warmup_bars_required = max(
  ATR_len + 5,
  ATR_percentile_lookback,
  indicator_lookback_max
)
```

**Definition: `indicator_lookback_max`:**
- Computed by parsing the strategy DSL AST
- Extract the maximum lookback used by any indicator

**Examples:**
- `sma(close, 200)` → 200 bars
- `rsi(close, 14)` → 14 bars
- `highest(high, 50)` → 50 bars

**Multi-timeframe indicators:**
- Warm-up must be satisfied **per timeframe used**
- Conservative mapping to internal TF is acceptable for MVP

---

### 5) Calendar Scope — MVP vs Full Support

**Decision (MVP):**
- Use holiday JSON fallback
- Treat all days as NORMAL sessions unless explicitly marked
- **Half-days and special sessions are NOT supported in MVP** unless present in the JSON
- Dates marked `CLOSED` → no jobs, no trading

**Post-MVP:**
- CSV/UI-driven calendar
- Explicit half-day and special session handling

---

This section closes all remaining engineering ambiguities and is sufficient for Codex to proceed with a clean, deterministic, and production-safe implementation.

---

## Additional Gaps (Must Decide Early) — Implementation Guidance

This section captures remaining practical items that are small but critical for a robust, efficient, and highly performant strategy deployment system. The decisions below are now **explicitly locked** for MVP implementation.

### 1) Actual BAR_CLOSED Event Source (Implementation Detail)

**Decision:** Implement a **deployment-focused candle pump** as the authoritative event source for strategy execution, fully separate from the existing long-interval (6-hour) candle sync.

**Integration point (locked):**
- The bar-close engine should fetch the **latest closed bar from our Candle DB** (preferred for determinism and single source of truth).
- If the Candle DB is not yet populated for the required symbol/TF at runtime, the engine may temporarily fall back to **direct broker fetch**, but any fetched bars must be **persisted to Candle DB** before emitting `BAR_CLOSED`.

This avoids two sources of truth while allowing graceful bootstrap.

**Implementation:**
- A `BarCloseEngine` runs per deployment.
- Tracks **active symbols** (open positions + optional watchers).
- Supports internal timeframes: **1m and 5m (MVP)**.
- Computes the next bar boundary per TF, sleeps until boundary + small lateness tolerance (3–7s).
- Reads latest closed candles from Candle DB and emits `BAR_CLOSED(symbol, tf, bar_end_ts, ohlcv)` jobs.

**Reliability mechanics:**
- Backfill missing bars using `last_emitted_bar_end_ts` per `(user_id, deployment_id, symbol, tf)`.
- Enforce exactly-once processing via durable job queue with unique `dedupe_key`:
  - `(user_id, deployment_id, symbol, tf, bar_end_ts, job_type='BAR_CLOSED')`.
- Late candles are retried briefly; unresolved gaps are backfilled on the next cycle.

This engine becomes the **heartbeat** of deployments.

---

### 2) Tick Handling — MVP Stance

**Decision (locked):** MVP is **bar-only**.

- Mode A: 5m trailing
- Mode B: 1m trailing (bar-close only)
- **No tick streaming** and **no pseudo-tick polling** in MVP.

**Rationale:**
- Maximizes robustness and simplicity.
- Avoids reconciliation complexity.
- 1m trailing provides sufficient intrabar fidelity for v1.

Tick-based or near-threshold polling may be introduced in v2+.

---

### 3) Job Queue + Locking Semantics (SQLite Durability)

**Decision:** Use a DB-backed durable job queue with careful atomic “claim” semantics.

**Key requirements:**
- Exactly-once **intent generation** via unique `dedupe_key`.
- At-least-once **job execution** with idempotent actions.

**SQLite-safe claim pattern (recommended):**
- Jobs table contains: `status`, `claim_token`, `claimed_at`, `attempt_count`, `dedupe_key (UNIQUE)`.
- Claim a job using a single atomic update:
  - `UPDATE jobs SET status='RUNNING', claim_token=?, claimed_at=now(), attempt_count=attempt_count+1`
  - `WHERE status='QUEUED' AND job_id=?`
  - Check `rows_affected == 1` to confirm claim.

**Retry/TTL:**
- A background sweeper moves stale RUNNING jobs back to QUEUED when:
  - `now() - claimed_at > TTL`
- Because intents and broker actions are idempotent, reprocessing is safe.

**Locking:**
- Locks are persisted with a unique key, e.g. `(user_id, deployment_id, symbol, event_ts, job_type)`.
- Claim requires acquiring lock first; lock release occurs after job completion.

---

### 4) Indicator & Trailing Warm-up Policy

**Decision:** Default is **no-trade-until-warm** for entries; exits and safety protection are always allowed.

**Warm-up requirement (per symbol, per internal TF):**
```
warmup_bars_required = max(
  ATR_len + 5,
  ATR_percentile_lookback,
  indicator_lookback_max
)
```

**Definition (locked): `indicator_lookback_max`**
- Computed from the strategy DSL AST by extracting the maximum lookback among all indicator calls.
- Examples:
  - `sma(close, 200)` → lookback 200
  - `rsi(close, 14)` → lookback 14
  - `atr(14)` → lookback 14
  - `highest(high, 50)` → lookback 50
- If the DSL contains multi-timeframe calls (e.g., `sma(close, 200, '1d')`), compute warm-up separately per TF used, or conservatively map it to the internal TF equivalent.

**Defaults:**
- ATR_len = 14
- ATR_percentile lookback:
  - 100 bars (1m engine)
  - 60 bars (5m engine)
- indicator_lookback_max derived from strategy config (fallback: 100)

**Startup / restart behavior:**
- Load `warmup_bars_required + buffer(20)` bars.
- Mark symbol state as `WARMING`.
- Enable entries only after warm.
- If a position exists, initialize trailing state and ensure disaster SL immediately.

---

### 5) Broker Disaster Stop Mechanics (Zerodha — CNC + MIS)

**Decision:** MVP supports **CNC + MIS**, with broker-side disaster protection always present.

#### CNC (Positional)
- Disaster SL uses **GTT SL** (persistent).
- Create GTT **only after entry fill confirmation**.
- Cancel GTT on exit/flatten.

#### MIS (Intraday)
- Disaster SL uses regular **SL / SL-M day orders**.
- Place immediately after entry fill confirmation.

#### Orphan prevention & lifecycle (locked)
- Store disaster protection refs in runner state:
  - `disaster_sl_ref` (gtt_id or order_id)
- On each reconciliation cycle:
  - If position exists and `disaster_sl_ref` missing → create it
  - If position is flat and `disaster_sl_ref` exists → cancel it
- Manual intervention handling:
  - If a manual position/order change is detected, mark `PAUSED_MANUAL`.
  - In PAUSED_MANUAL, the runner does **not** create new GTTs/orders automatically.
  - Provide UI actions:
    - “Adopt broker state” (re-link refs)
    - “Flatten and resume” (cancel orphan GTTs, exit positions, resume)

#### Trailing vs Broker Stop (explicit)
- **Trailing SL/TP is app-managed only** in MVP.
- Broker disaster stops are **not trailed**.
- When trailing triggers, the runner issues an `ExitNow` (market exit).

---

### 6) MIS End-of-Day Auto-Flattening (Locked)

**Decision (locked):** **YES — enforce auto-flatten for MIS positions between 15:25 and 15:30.**

**Behavior:**
- All MIS positions must be flat by market close.
- Runner enforces a final exit window (default 15:25–15:30).
- Any open MIS position at proxy close triggers an immediate exit.

---

### 7) Calendar MVP vs Full Calendar

**MVP decision (locked):**
- Use holiday JSON fallback + standard market hours.
- Half-days and special sessions are **not supported in MVP unless explicitly provided in the JSON**.
- Enforce a hard no-trade rule on `CLOSED` dates.

**Post-MVP:** Full calendar UI/CSV/DB support including half-days and special sessions.

---

### 8) Edge-Case Policy Defaults

**Partial fill at window end:**
- Cancel remaining quantity.
- Retain filled position and immediately place disaster SL.

**Retries:**
- No automatic retries for entries.
- Allow **one retry max** for transient errors (timeouts, rate limits) if still within window.
- Never retry on margin/RMS/validation errors.

**Daily loss / circuit breaker (recommended):**
- Supported in MVP (OFF by default).
- If enabled and breached, pause deployment for the day (optionally flatten).

---

### 9) MVP Readiness & Staged Rollout

**MVP (v1):**
- Deployment-scoped bar-close engine with backfill, dedupe, and lateness tolerance (Candle DB as source of truth)
- Mode A (5m) and Mode B (1m bar-only)
- Warm-up gating with DSL-derived `indicator_lookback_max`
- CNC + MIS disaster SL support + orphan prevention
- MIS auto-flatten at close
- App-managed trailing exits
- Durable job queue, locks, idempotency, reconciliation
- Holiday fallback calendar (no half-days unless present)

**v2+ roadmap:**
- Selective tick streaming near thresholds
- Richer exchange calendar UI and DB
- Advanced risk caps and broker optimizations

---

## Final Decision (What We Will Implement)

This section captures remaining practical items that are small but critical for a robust, efficient, and highly performant strategy deployment system.

### 1) BAR_CLOSED event generation (Candle Pump)

**Problem:** Current `market_data` is a 6‑hour sync; deployments need reliable, minute‑aligned bar events.

**Decision:** Implement a **deployment-scoped bar-close engine** (“candle pump”) that is event-driven and deterministic (not a global polling loop).

**How it works (recommended):**
- Maintain **active symbols** per deployment:
  - symbols with an open position, plus optionally symbols watched for new entries.
- For each internal timeframe we support (MVP: **1m and 5m**), compute the **next bar boundary**.
- Sleep until boundary + small **lateness tolerance** (e.g., 3–7 seconds).
- Fetch latest candle(s) for each active symbol and timeframe.
- Emit/queue a job: `BAR_CLOSED(symbol, tf, bar_end_ts, ohlcv)`.

**Backfill missing bars:**
- Track `last_emitted_bar_end_ts` per `(user_id, deployment_id, symbol, tf)`.
- On wakeup, fetch a small range from `last_emitted + tf` to `now` and emit all missing bars in order.

**Dedupe / exactly-once enqueue:**
- Persist jobs in a durable queue with `dedupe_key` unique constraint:
  - `dedupe_key = (user_id, deployment_id, symbol, tf, bar_end_ts, job_type='BAR_CLOSED')`
- This prevents double-fires on restart and simplifies correctness.

**Late candle handling:**
- If the candle for `bar_end_ts` isn’t available yet, retry fetch 1–3 times with short delay (bounded), then let the next cycle backfill.

### 2) Tick events MVP decision

**Decision (MVP):** Ship **bar-only trailing** first. No tick streaming and no “pseudo-tick polling” in v1.
- Supported in MVP:
  - Mode A: 5m trailing
  - Mode B: 1m trailing (bar-close only)
- Defer tick-mode to v2+ (selective tick streaming for open positions near thresholds).

**Rationale:** Keeps the system stable, simpler to reconcile, and still delivers strong practical performance with 1m trailing.

### 3) Warm-up rules (ATR, ATR percentiles, DSL indicators)

**Problem:** ATR(14), ATR percentiles, and strategy indicators need sufficient history; restart without warm-up can create bad signals.

**Decision:** Implement explicit **deployment warm-up** per `(deployment_id, symbol, tf)`.

**Warm condition:**
- A symbol is “warm” when we have at least:
  - `warmup_bars_required = max(ATR_len + 5, ATR_percentile_lookback, indicator_lookback_max)`
- Defaults:
  - ATR_len = 14
  - ATR percentile lookback: 100 bars (1m engine), 60 bars (5m engine)
  - indicator_lookback_max: derived from strategy config (or conservative min 100)

**Behavior until warm:**
- **No new entries** until warm.
- **Exits and disaster SL placement are allowed** (safety-first).

**On start/restart:**
- Load last N bars (warmup + buffer) for active symbols before enabling entries.

### 4) Broker-side “disaster SL” mechanics (CNC + MIS)

**Decision:** MVP must support **CNC + MIS**.

**Goal:** Always enforce a broker-side safety layer that protects capital even if the app crashes. Trailing SL/TP remains app-managed.

**CNC (positional) mechanics:**
- Prefer **GTT SL** for disaster stop.
- Optionally GTT OCO if placing a fixed TP (not trailing TP).
- Disaster SL is wider than trailing SL and is not frequently modified.

**MIS (intraday) mechanics:**
- Place a regular **SL / SL-M** order where supported for disaster stop.
- If broker/order constraints prevent reliable SL linkage, fall back to:
  - app-managed exits + conservative risk caps,
  - but still attempt broker-side protection whenever possible.

**Linking & lifecycle:**
- Store broker refs in runner state:
  - `disaster_sl_ref` (order_id or gtt_id)
  - optional `fixed_tp_ref`
- Reconcile each cycle:
  - position exists & disaster SL missing → create it
  - position flat → cancel leftover protection orders

**Modify vs cancel/replace:**
- MVP default: **cancel/replace** protection orders when change is necessary (simpler, fewer broker edge cases).
- Only apply modifications when broker API is known reliable for that order type.

### 5) Edge-case policy knobs (explicit defaults)

These must be explicit settings with safe defaults:

**Partial fill at window end (default):**
- Cancel remaining quantity at window end.
- Keep partial position and immediately place disaster SL for filled qty.

**Retries (default):**
- No automatic retries for entries.
- Allow **one retry max** for transient errors only (timeouts / rate limits), and only while still within the execution window.
- Never retry on:
  - insufficient funds/margin
  - RMS/validation rejections
  - trading disabled
  - invalid symbol

**Daily loss / circuit breaker caps (recommended):**
- Include in MVP (can be OFF by default):
  - `daily_max_loss_pct` → if breached, pause deployment for the day (optionally flatten).
- Add `max_trades_per_day` (default e.g., 3) to avoid runaway churn.

### 6) MVP readiness & staged rollout

**We are ready to start implementation** with a staged plan:

**MVP (v1):**
- Bar-close engine (“candle pump”) with backfill + dedupe + lateness tolerance
- Modes:
  - Mode A (5m)
  - Mode B (1m bar-only)
- Warm-up gating
- CNC + MIS disaster SL support + app-managed trailing exits
- Durable job queue + locks + idempotency + reconciliation
- Holiday calendar fallback initially (Mon–Fri) with CSV upload support

**v2+ iterations:**
- Selective tick streaming (open positions only; near thresholds)
- Richer calendar UI and special session support
- More advanced risk caps and broker-specific optimizations

---

## Final Decision (What We Will Implement)

1. **Both trailing SL and trailing TP will be supported**.
2. Trailing logic will be implemented **inside the app**, not assumed from broker APIs.
3. A broker-side hard SL is always mandatory.
4. Users can choose trailing precision mode:
   - Scalable (5m)
   - Balanced (1m + selective ticks)
   - High Precision (tick-level)
5. Defaults will favor safety, scalability, and consistency between backtest and live.

This architecture gives maximum flexibility without sacrificing robustness, and allows future expansion without breaking existing deployments.

