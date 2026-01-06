# Strategy Deployment v3 — Simplicity by Default, Explicit When Dangerous

## Context & Motivation
This document captures the **amendments and clarifications** that emerged after deeper discussion around deployment runtime behavior, especially in response to Codex feedback about monitoring, direction semantics, and user intent.

The guiding principle is now explicitly locked as:

> **“Simple by default, explicit when dangerous.”**

The goal is to preserve an intuitive, low-friction user experience while ensuring that potentially risky situations are **clearly surfaced, never silent**, and always require **explicit user acknowledgement**.

---

## 1. Amendment: Market-Hours–Only Monitoring

### Previous understanding
Deployments conceptually “run” continuously once started.

### Updated decision
- **BAR_CLOSED–driven monitoring must occur only during market hours**.
- Market hours are defined by:
  - exchange calendar (weekday + holiday list)
  - session times (default 09:15–15:30 IST)
  - timeframe-specific bar boundaries

### What runs outside market hours
- Reconciliation sweeps (orphan orders, GTT sanity checks)
- Job TTL cleanup / requeue
- Health checks and preloading (optional)

### Why this matters
- Eliminates wasted jobs and noisy logs at night
- Prevents backfill churn and false “lag” alarms
- Aligns mental model: *strategy reacts to market events only when markets are open*

---

## 2. Amendment: Deployment Direction Semantics (LONG / SHORT)

### Direction = permission, not an action

- **LONG**: deployment is allowed to create and manage long (BUY→SELL) positions
- **SHORT**: deployment is allowed to create and manage short (SELL→BUY) positions
  - SHORT is valid **only for MIS**
  - SHORT + CNC is rejected at validation

Direction does **not** mean:
- auto-entry on start
- auto-reversal of existing positions

---

## 3. Core Runtime Model (Reconfirmed)

A deployment is a **looped, event-driven state machine**:

1. If **flat** → evaluate entry DSL on BAR_CLOSED
2. If **in position** → evaluate exits first (risk, trailing, exit DSL, forced windows)
3. After exit → return to flat and wait for next entry signal

This loop continues until the deployment is explicitly stopped.

---

## 4. Amendment: Handling Existing Positions on Start

### Key design choice
We explicitly **do not restrict** pyramiding or overlapping exposure by default.

Users may:
- run multiple deployments on the same symbol
- intentionally pyramid via different strategies or groups

### The real risk
Not pyramiding itself, but **silent pyramiding** and **hidden exposure coupling**.

### Locked mitigation

On deployment start, the runner must:
1. Detect any **existing net position** for the symbol (manual or other deployments)
2. Display a **clear, persistent warning banner**:
   - existing qty, avg price
   - combined exposure across all deployments

No automatic blocking occurs.

### Optional (advanced, off by default)
- Global cap: max total exposure per symbol across deployments

---

## 5. Amendment: Direction Mismatch Handling

### Case
- Deployment direction = SHORT
- Existing position = LONG (or vice versa)

### Decision
- The deployment must **pause immediately** in a visible state:
  - `PAUSED_DIRECTION_MISMATCH`

### Required explicit user choice
- Adopt existing position for exit-only management
- Flatten existing position and continue
- Ignore existing position and stay paused

No automatic reversal or flattening is allowed.

---

## 6. Amendment: Entry Timing & User Intent

### Default behavior
- Starting a deployment **does not place a trade immediately**.
- Entries occur **only when entry conditions are satisfied** on a valid BAR_CLOSED event.

### Advanced option (explicit)
- “Enter immediately on start”
  - market/limit order
  - requires confirmation (especially for SHORT)

This preserves simplicity while respecting user intent.

---

## 7. Amendment: initial_cash Semantics

- `initial_cash` is a **sizing reference**, not an account balance mirror.
- It is required **only when placing new entries**.
- It is **not required** when:
  - managing exits
  - adopting an existing position

Broker margin checks remain the ultimate authority.

---

## 8. Amendment: Short-Specific Safety Rules (MIS)

SHORT trades carry asymmetric risk and require extra friction.

Locked safeguards:
- Product must be MIS
- Explicit user acknowledgement of short risk
- Default smaller position size (configurable)
- Mandatory daily loss / circuit breaker (even if minimal)
- Forced auto-flatten between 15:25–15:30

---

## 9. Challenges Identified

1. **Silent coupling between deployments** → mitigated by exposure warnings
2. **Accidental shorts** → mitigated by explicit confirmations
3. **User surprise on start** → mitigated by signal-only entry by default
4. **Overengineering temptation** → avoided by keeping defaults permissive

---

## 10. Way Forward

### Immediate (implementation-ready)
- Add market-hours gating to BAR_CLOSED scheduler
- Add reconciliation-on-start with exposure detection
- Add PAUSED_DIRECTION_MISMATCH state + UI actions
- Add exposure warning banner (non-blocking)

### Near-term enhancements
- Exposure summary dashboard (per symbol across deployments)
- Optional global exposure caps
- Dry-run preview before starting deployment

### Long-term
- Portfolio-aware deployments
- Regime-based exposure scaling
- Advanced execution policies

---

## 11. Market Hours, Timezone & Holiday Calendar (Implementation)

### Intent
Ensure **BAR_CLOSED generation, entry/exit windows, and risk actions** are aligned with actual Indian market sessions (NSE/BSE), while keeping the system configurable, testable, and future-proof.

---

### Exchange & Timezone (Locked)
- **Timezone:** `Asia/Kolkata`
- **Exchanges:** NSE, BSE (equity)

All internal timestamps are stored in UTC with explicit IST conversion at boundaries.

---

### Default Market Session Settings (Per Exchange)
These defaults apply unless overridden by the holiday calendar.

- `market_open`: **09:15**
- `market_close`: **15:30**
- `proxy_close`: **15:25** (used for 1D evaluation & MIS flatten)
- `preferred_sell_window`: **09:15–09:20**
- `preferred_buy_window`: **15:25–15:30**
- `MIS_force_flatten_window`: **15:25–15:30**

These values are configurable via **Settings → Market Configuration**.

---

### Holiday Calendar (Settings & Storage)

#### Source
- User uploads **CSV holiday calendar** per exchange (NSE/BSE) via Settings.
- Calendar is persisted in DB and treated as **authoritative**.

#### Minimum CSV Schema
```
date,exchange,session_type,open_time,close_time,notes
```

- `session_type` values:
  - `CLOSED` – market closed (no trading, no BAR_CLOSED)
  - `SETTLEMENT_ONLY` – trading allowed, settlement disabled
  - `HALF_DAY` – shortened session (requires open/close)
  - `SPECIAL` – special session (e.g., Muhurat)

---

### MVP Scope (Explicit)
- **CLOSED** and **SETTLEMENT_ONLY** are supported in MVP.
- **HALF_DAY / SPECIAL** are honored **only if explicitly present** in the CSV.
- If not present, the day is treated as a NORMAL full session.

Weekends (Sat/Sun) are treated as non-trading even if not present in CSV.

---

### Runtime Resolution (`market_hours.py`)
At runtime, for each day and exchange:

1. Load calendar row for `(date, exchange)` if present.
2. Resolve session:
   - If `CLOSED` → no trading, no BAR_CLOSED jobs.
   - Else determine `open_time` / `close_time`:
     - from calendar row if provided
     - else from defaults.
3. Derive execution windows:
   - `proxy_close = close_time − 5 min`
   - `preferred_buy_window = proxy_close → close_time`
   - `preferred_sell_window = market_open → market_open + 5 min`

This resolver is the **single authority** for session logic.

---

### Interaction with BAR_CLOSED Engine

- BAR_CLOSED jobs are generated **only when `market_hours.is_trading_time(now)` is true**.
- Timeframe boundaries (1m/5m/1D-proxy) are evaluated against resolved session times.
- Outside market hours:
  - BAR_CLOSED generation is paused
  - reconciliation / sweeper jobs may still run (rate-limited)

---

### Why This Design
- Avoids hard-coded assumptions
- Keeps backtest and live behavior aligned
- Allows easy annual calendar updates via CSV
- Makes special sessions explicit and testable

---

## 12. Deployment Observability, Activity & Performance Reporting (Next Implementation)

### Intent
A deployment marked **RUNNING** must provide continuous *evidence of life* and clear introspection:
- when it last evaluated,
- what decision it made (even if “no action”),
- what orders/trades resulted,
- and what the current performance/equity looks like.

This is required for user trust, debugging, and safe live operation.

---

### Current Gap (What we observed)
- UI shows `RUNNING`, but **no visible activity**:
  - `Last Eval` is blank
  - no per-deployment event journal
  - no order/trade linkage to deployments
  - no equity curve / summary “as of now”

This is not a “bug” so much as **missing product surface area**.

---

### Requirements (MVP)

#### A) Deployment heartbeat (minimal, high leverage)
Every evaluation cycle must update a small set of fields on the deployment row.

**Fields to persist/update:**
- `last_eval_at`
- `last_eval_bar_end_ts` (what bar was evaluated)
- `state` enum:
  - `FLAT`, `IN_POSITION`, `WARMING_UP`, `PAUSED_*`, `ERROR`
- `last_decision` enum:
  - `ENTRY_TRUE`, `ENTRY_FALSE`, `EXIT_TRUE`, `EXIT_FALSE`, `NO_BAR`, `MARKET_CLOSED`, `HOLIDAY`, `WARMING_UP`, `BLOCKED_*`
- `last_decision_reason` (short human string)
- `next_eval_at` (optional but very useful)

**UI expectation:** The Deployments table should show at least:
- Status (RUNNING/STOPPED)
- State (FLAT/IN_POSITION/WARMING_UP/PAUSED)
- Last Eval (timestamp)
- Last Decision (short label)

#### B) Per-deployment activity journal
Persist a simple, append-only log of significant events:
- `BAR_CLOSED_RECEIVED`
- `EVAL_STARTED/EVAL_FINISHED`
- `ENTRY_SIGNAL=true/false`
- `EXIT_SIGNAL=true/false`
- `ORDER_INTENT_CREATED`
- `ORDER_SUBMITTED / REJECTED / PARTIAL_FILL / FILLED`
- `RISK_EXIT_TRIGGERED` (DSL stop-loss / trailing / forced window)
- `RECONCILIATION_ACTION` (cancel orphan, create disaster SL, pause on mismatch)

This can be a single table keyed by `(deployment_id, ts)`.

#### C) Orders & trades linkage
All order intents and broker/paper orders must carry:
- `deployment_id`
- `dedupe_key`
- `intent_id`

Trades (fills) must also be linked back to `deployment_id`.

#### D) Live performance summary
For each deployment:
- realized P&L
- unrealized P&L
- current position (qty, avg price, product)
- number of completed trades
- last trade time
- max drawdown (optional for MVP)

#### E) Equity curve (MVP-lite)
Persist periodic “equity points” so the user can see a curve.

**Minimal design:**
- Write an equity point on:
  - each exit (realized)
  - end-of-day / proxy close (mark-to-market)

---

### Challenges & Design Considerations

1) **Determinism vs. volume**
- Logging every bar for every deployment can be heavy.
- Use the heartbeat fields for the table, and keep journal entries lightweight.

2) **Paper vs live parity**
- Paper mode needs a proper fill/ledger model (fills + mark-to-market) so equity isn’t fictitious.

3) **Multi-deployment overlap**
- Same symbol held by multiple deployments should be surfaced in UI (warning banner), but P&L attribution remains per deployment using its own fills.

4) **Warm-up visibility**
- WARMING_UP should be first-class, e.g. “Warming up: 43/250 bars”.

5) **Backfill / late candles**
- Heartbeat should record “NO_BAR” or “LATE_BAR” clearly to avoid confusion.

---

### Proposed UI Surfaces (MVP)

#### A) Deployments table additions
- State
- Last Eval
- Last Decision

#### B) Deployment Detail as a Right Drawer (recommended)
Match the Backtesting UX pattern you already like: selecting a row opens a **right-side drawer** with all details for that deployment.

**Drawer tabs (MVP):**
- **Summary:** state, last eval, last decision, position, realized/unrealized P&L
- **Equity:** deployment equity curve + drawdown (deployment-scoped)
- **Journal:** ordered event log (bar-closed, DSL results, risk actions)
- **Orders:** orders/intents for this deployment only
- **Trades:** fills/trades for this deployment only
- **Diagnostics:** warm-up progress, last candle ts, data freshness, calendar/session status

**Key invariant:**
- Every artifact (events, orders, trades, equity points) is keyed by `deployment_id`, so **multiple deployments can overlap the same symbol(s) without clashing**. Each deployment tracks its own lifecycle and performance independently.

**Optional (advanced):**
- A separate “Exposure” panel that aggregates *combined* symbol exposure across deployments, but never mixes P&L attribution.

---

### Way Forward (Implementation Steps)
1. Add heartbeat fields to DB + update them on every evaluation.
2. Add `deployment_event_log` table and write events.
3. Ensure order intent → order → fills all carry `deployment_id`.
4. Build deployment detail API endpoints.
5. Add UI: new columns + deployment detail modal/page.

---

## 13. Restart, Recovery & Operational Resilience

### Intent
Allow the operator to **stop, restart, or maintain the system safely**—especially during development and experimentation—without risking unintended trades or corrupting deployment state.

---

### Rationale
In real usage, especially for a solo developer–operator:
- Backend (BE) and Frontend (FE) restarts are frequent
- Changes, crashes, upgrades, and experiments are normal
- Off-market hours should be a guaranteed safe zone

Operational stress should not be part of running a trading system.

---

### Core Design Principle (Locked)

> **Deployments are stateful in the database, not in memory.**

Deployments must survive restarts because their intent and runtime state are persisted.

---

### FE Restart Semantics
- FE restart is always safe
- FE is a pure UI / state consumer
- No deployment logic executes in FE

---

### BE Restart Semantics

#### Off-market hours (guaranteed safe)
- No BAR_CLOSED events
- No entry/exit windows
- No broker order placement

Restarting BE during off-market hours has **zero trading impact**.

#### Market hours (safe with invariants)
- One evaluation cycle may be delayed
- No duplicate orders due to idempotency
- Reconciliation ensures state correctness

---

### Idempotency & Dedupe (Critical)
All trading actions must be idempotent:
- BAR_CLOSED evaluation
- Order intent creation
- Order submission
- Trailing updates
- MIS auto-flatten

Each action uses deterministic dedupe keys and state checks.

---

### Reconciliation-on-Start (BE Startup Routine)
On BE startup:
1. Load RUNNING deployments
2. Fetch broker positions and orders
3. Compare expected vs actual state
4. Repair mismatches or pause deployment if unsafe

This makes restarts self-healing.

---

## 14. Pause & Resume Semantics (Operator Safety Control)

### Intent
Provide a **deliberate, operator-controlled safe mode** that cleanly freezes strategy behavior during maintenance, debugging, or restarts—without tearing down deployments.

---

### Why Pause is Needed
- Restart-safety alone protects correctness
- Pause protects **operator confidence**
- Prevents any new strategy-driven actions during maintenance

Pause is especially useful during **market hours**.

---

### What PAUSE Means (Default)
When a deployment or alert is PAUSED:
- No BAR_CLOSED evaluations are processed
- No entry or exit decisions are made
- No new orders are created

Still allowed:
- Reconciliation (read-only)
- Status refresh
- UI inspection

---

### What PAUSE Does *Not* Do
Pause does NOT:
- Cancel broker-side disaster SL (GTT / SL orders)
- Cancel MIS auto-flatten schedule
- Modify or flatten existing positions

Broker-side protection remains intact.

---

### Optional Advanced Mode: PAUSE_SAFE
(Deferred; not required for MVP)
- One-time safety sync on pause
- Verify disaster SL exists
- Verify MIS flatten schedule

---

### UI Semantics
- Deployment status: RUNNING | PAUSED | STOPPED
- Actions:
  - ▶ Resume
  - ⏸ Pause
  - ⏹ Stop

Right drawer shows:
- Paused at timestamp
- What protections remain active

---

### Scheduler & Worker Rules
- Scheduler must not enqueue BAR_CLOSED jobs for PAUSED deployments
- Workers must re-check status before execution

This double gate prevents accidental execution.

---

### Interaction with Restart
Recommended safe workflow:
1. Pause deployments
2. Restart BE / FE
3. Resume deployments

Off-market hours: pause is optional
Market hours: pause strongly recommended

---

### Challenges & Trade-offs
- Pausing mid-bar may delay a trailing update
- Pause is not a replacement for disaster SL

These are accepted trade-offs for safety.

---

### Way Forward (Implementation)
1. Add PAUSED state to deployments and alerts
2. Enforce pause checks in scheduler and worker
3. Add Pause/Resume actions in UI
4. Document operator workflow (this section)

---

## Final Philosophy (Locked)

> **Simple by default. Explicit when dangerous.**

The system should never surprise the user, never silently take risk, and never require operational heroics to keep running.


> **Simple by default. Explicit when dangerous.**

The system should never surprise the user, never silently take risk, and never require operational heroics to keep running.

