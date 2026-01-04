# Strategy Deployment (Internal Signals) — Design Reference

This document describes how SigmaTrader should **deploy** (run live / paper) the same Entry/Exit strategies used in strategy backtesting — with strong emphasis on:

- **SigmaTrader computes signals internally** from candles (no TradingView dependency).
- **Backtest ↔ Live parity**: execution timing, candle semantics, and fill rules should match as closely as possible.
- **Operational safety**: idempotency, reconciliation, audit trail, and risk controls.

---

## 1) Intent

> “Deploy a strategy so SigmaTrader continuously monitors Entry/Exit (+ stops/targets/trailing) and places orders automatically when conditions trigger.”

Deployment should support:
- Single‑symbol strategy deployment (existing “Strategy backtest” style).
- Portfolio‑level strategy deployment (group) as an extension (see `docs/backtesting_portfolio_strategy.md`).

---

## 2) Core concept: a Strategy Runner (state machine)

Deployment is not “fire an alert when condition is true”; it is a **stateful runner**.

Per strategy instance (symbol or group) SigmaTrader maintains:
- Current mode: `FLAT`, `LONG`, `SHORT` (short only where allowed).
- Positions (per symbol in group mode): qty, avg price, entry time, best‑price‑since‑entry for trailing.
- Cash / equity (for group mode).
- Cooldown / min holding counters (optional).
- Risk state (global kill‑switch, per‑trade dd tracking, etc.).

The runner processes **bar events** deterministically and produces **actions** (orders) exactly once.

---

## 3) Candle/timeframe model (internal signals)

SigmaTrader computes DSL conditions using its own candles:
- Intraday candles: `1m/5m/15m/30m/1h`
- Daily candle semantics must be clearly defined for deployment.

### 3.1 The deployment problem with `TF=1d`

A naive daily model does:
- evaluate signal at **3:30pm close**
- fill at **next day 9:15am open**

This is realistic but can feel “unreliable” because the fill may be far from the signal price due to overnight gaps.

### 3.2 Design choice: time‑gated execution with an intraday engine (recommended)

Keep the *logic* “daily”, but execute it using intraday data so live and backtest behave the same.

**Approach**
- Choose an intraday base timeframe (recommended default: `5m`).
- Define a **proxy daily close timestamp**: **15:25** (3:25pm).
- Build “daily” indicator values from intraday candles by treating the **15:25 bar close** as the day’s close.

This avoids lookahead while allowing orders to be placed in a controlled market‑hours window.

**Execution windows**
- **BUY window**: 15:25–15:30 (deploy entries near proxy close).
- **SELL / risk‑reduction window**: 09:15–09:20 (handle overnight gaps / open‑liquidity exits).

Notes:
- Signal‑based exits can also be executed in the 15:25–15:30 window if the exit signal is known at proxy close.
- The open window is primarily for **gap / emergency risk controls** (e.g., stop‑loss breach at open).

---

## 4) Evaluation and fill rules (deployment)

### 4.1 Evaluation cadence

- For intraday strategies (`TF < 1d`): evaluate on each bar close of `TF`.
- For “daily logic via intraday engine”:
  - Evaluate the daily Entry/Exit DSL at **15:25** using the latest intraday snapshot.
  - Optionally evaluate risk conditions again at **09:15** to react to gaps.

### 4.2 Fill timing

To preserve parity between backtest and deployment, deployment must use a consistent fill model:

- Intraday strategies: fills at next bar open (or configurable).
- Daily‑logic strategies:
  - Entry: place immediately in the 15:25–15:30 window (fill at market/limit per settings).
  - Exit: place immediately when signal triggers at 15:25; additionally allow “open risk” exits at 09:15–09:20.

---

## 5) Stops, trailing stops, take profit (broker vs Sigma)

Deployment needs an explicit stance on who enforces risk:

### 5.1 Broker‑managed (preferred when supported)
- Use broker features (SL/SL‑M/GTT/OCO) to ensure stops work even if SigmaTrader is down.

### 5.2 Sigma‑managed (flexible, higher operational burden)
- SigmaTrader monitors prices and places exit orders when stop/TP/trailing conditions trigger.

### 5.3 Recommended hybrid
- Always place a **hard broker stop** when possible.
- Optionally run Sigma‑managed trailing/TP logic and adjust broker orders.

---

## 6) Group/portfolio deployment specifics

Group strategy deployment uses the same policy as portfolio‑level strategy backtest:
- Shared cash pool.
- Entry selection policy: Equal vs Ranking.
- Sizing policy: % equity, fixed cash, cash‑per‑slot.
- Constraints: max open positions (default 10), optional cooldown/min hold/max symbol alloc/sector caps.

Implementation should reuse the same “portfolio strategy engine” in both:
- **simulation** (backtest), and
- **live runner** (deployment).

---

## 7) Operational requirements (must‑have)

- **Idempotency**: processing the same bar twice must not double‑trade.
  - Use a per‑strategy “last processed bar key” (symbol/timeframe/timestamp).
- **Single‑runner lock**: only one worker can run a strategy instance at a time.
- **Reconciliation**: continuously compare SigmaTrader’s state with broker orders/fills/positions.
- **Audit trail**:
  - record DSL evaluation snapshot, prices, and reason for every action.
- **Kill switch**:
  - global disable for a strategy instance and for the whole system.

### 7.1 Event‑driven (no busy loops)

To avoid performance bottlenecks, deployments should be evaluated in an **event‑driven** way:
- Wake only on **bar close events** (or the fixed windows like 09:15 / 15:25 for “daily‑via‑intraday”).
- Do not run tight polling loops per strategy.

### 7.2 Async & concurrency plan (performance)

Use concurrency where it is safe, and bound it where it is not:
- **Async I/O** for candle fetches, DB reads/writes, and broker API calls.
- **Bounded concurrency** for evaluating many symbols (group mode):
  - a worker pool / semaphore to prevent spawning unbounded tasks for very large groups.
- **Sharding by deployment**:
  - parallelize across deployments (different users/strategies) rather than within a single deployment without limits.
- **CPU isolation (if needed)**:
  - if DSL/indicator evaluation becomes CPU heavy, move it to a dedicated process pool (or service) instead of blocking async workers.

Correctness constraints for concurrency:
- A single deployment must be processed by **one worker at a time** (lock by deployment id).
- A broker order placement must be **idempotent** (dedupe by stable client order id).

### 7.3 Per‑user / multi‑tenant deployment model

Deployments are **per SigmaTrader user** (with optional “shared templates” that users can copy).

Requirements:
- Strict isolation of:
  - deployment configuration,
  - runtime state (positions/cash),
  - broker credentials,
  - logs/audit trails.
- Fairness and safety limits (configurable):
  - max active deployments per user,
  - max symbols per group deployment,
  - max order rate per user/broker account.

### 7.4 Practical runtime architecture (robust + scalable)

A robust implementation should separate concerns into components that can scale independently:

- **Scheduler**
  - Converts bar closes + fixed windows into “evaluation jobs”.
  - Example job keys: `(deployment_id, timeframe, bar_ts)` and `(deployment_id, window, date)`.

- **Job queue**
  - Persists jobs so restarts don’t lose them and retries are controlled.
  - Enables backpressure (if brokers are slow, jobs queue instead of exploding concurrency).

- **Strategy workers**
  - Consume evaluation jobs.
  - Load deployment config + last state, evaluate DSL, decide actions.
  - Persist updated state + an action plan (orders to place).

- **Order executor**
  - Places broker orders with dedupe keys, handles retries, and records order ids.
  - Optionally separate from strategy workers to isolate broker latency/failures.

- **Reconciler**
  - Periodically syncs broker orders/positions back into SigmaTrader state.
  - Resolves mismatches (partial fills, rejected orders, manual interventions).

- **Observability**
  - Metrics: job lag, evaluation latency, broker latency, error rates.
  - Alerts: “deployment stalled”, “repeated broker rejects”, “state mismatch”.

---

## 8) UX proposal

Add a separate section/page for deployments, or integrate a “Deploy” flow from backtest:

### 8.1 “Deploy strategy” workflow
- User chooses:
  - symbol or group
  - timeframe and execution mode (intraday vs daily‑via‑intraday)
  - entry/exit DSL + stops/TP/trailing
  - allocation/sizing policies (group mode)
  - broker, product, paper/live
  - trading hours / execution windows
  - risk controls and caps

### 8.2 “Deployments” page
- list deployments (status, last evaluated, open positions, P&L)
- start/stop toggle
- logs + actions + errors
- “dry run / preview” view: show the next evaluation times and what would happen

---

## 9) Recommended implementation order

**Recommended sequence**
1) Build a shared **strategy engine** API that can run in:
   - backtest mode (simulation), and
   - live mode (bar‑driven runner).
2) Implement **portfolio‑level strategy backtest** first (safer):
   - validates allocation/sizing/risk logic without broker complexity.
3) Implement **strategy deployment in paper mode** next:
   - validate scheduling, idempotency, and state reconciliation without real money.
4) Enable **live deployment** last:
   - broker order routing + safety checks + monitoring.

Why not “deployment first”:
- Deployment adds operational risk (broker state, retries, partial fills, outages).
- Portfolio‑level backtest hardens the engine and keeps behavior explainable.

---

## 10) Open questions (to finalize before implementation)

- Ranking score DSL: how to define numeric DSL consistently.
- Candle source/coverage guarantees for intraday “daily proxy close” computation.
- Exact order types for entry/exit (market vs limit vs SL‑M) and defaults per broker.
- How to enforce sector caps (sector mapping source and UI).

---

## 11) Implementation notes (current)

### 11.1 Backend API (Deployments)

Base CRUD:
- `GET /api/deployments/`
- `POST /api/deployments/`
- `GET /api/deployments/{deployment_id}`
- `PUT /api/deployments/{deployment_id}`
- `DELETE /api/deployments/{deployment_id}`
- `POST /api/deployments/{deployment_id}/start`
- `POST /api/deployments/{deployment_id}/stop`

Observability / troubleshooting:
- `GET /api/deployments/metrics` (job counts + oldest pending)
- `GET /api/deployments/{deployment_id}/actions` (recent evaluations/actions)
- `GET /api/deployments/{deployment_id}/jobs/metrics` (per-deployment job lag/errors)
- `POST /api/deployments/{deployment_id}/run-now` (enqueue an evaluation job)

### 11.2 Runtime switches

Deployment scheduler/worker runtime is opt-in (off by default) via env vars:
- `ST_ENABLE_DEPLOYMENTS_RUNTIME=1` to start the scheduler/worker/sweeper/reconciler.
- `ST_DEPLOYMENTS_RUNTIME_MODE=threads|once`
  - `threads`: starts background threads (normal usage)
  - `once`: runs a single pass (useful for smoke testing)

### 11.3 Safety notes

- Paper deployments create `orders` rows with `execution_target=PAPER` and `simulated=true`.
- Orders created by deployments use `client_order_id` for idempotency (prevents double-fires on retries).
- A “disaster stop” order row is created on entry when `stop_loss_pct > 0` (currently an internal scaffold for broker primitives; cancellation is best-effort).

## 12) Operator runbook (quick)

1) Create a deployment in the UI (or via `POST /api/deployments/`).
2) Start it (`POST /api/deployments/{id}/start`).
3) Ensure the runtime is enabled on the backend process:
   - `export ST_ENABLE_DEPLOYMENTS_RUNTIME=1`
   - (optional) `export ST_DEPLOYMENTS_RUNTIME_MODE=threads`
4) Use:
   - Deployments → Details → “Run now” to force an evaluation job
   - System Events for warnings/errors and deployment reconciliations

### Troubleshooting checklist

- **Deployment shows RUNNING but nothing happens**
  - Confirm `ST_ENABLE_DEPLOYMENTS_RUNTIME=1` is set on the backend process.
  - Check `GET /api/deployments/{deployment_id}/jobs/metrics` for pending jobs.
  - Check `GET /api/deployments/{deployment_id}/actions` for recent evaluations.

- **“Run now” errors**
  - For intraday (`TF != 1d`), “Run now” aligns to the latest closed bar and may fail if the timeframe is unsupported.
  - For daily (`TF=1d` with daily‑via‑intraday enabled), “Run now” is only available after the proxy close time (default `15:25` IST).

- **Repeated failures**
  - Check `StrategyDeploymentState.last_error` (shown in UI) and `latest_failed_updated_at` (jobs metrics).
  - Stop the deployment (`/stop`), fix config/DSL, then start again.
