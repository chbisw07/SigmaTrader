# Holdings Exit Automation & Trade Control – Unified Master Design (Merged)

> **Design philosophy**  
> This system must be *boringly reliable* — like a Toyota Fortuner.  
> Predictable, safe, explainable, and resilient under stress.

This document is the **single authoritative design** that merges:
- the original Holdings Exit Automation design
- the later policy/regime analysis
- the control-plane model
- and the UX wireframes

There should be **no parallel or competing documents** after this.

---

## 1. Why This Exists (Intent)

In real trading, the hardest problem is not generating signals — it is **exiting positions rationally** while multiple automated and manual systems coexist.

BUY / SELL intents may originate from:

- (A) TradingView alerts
- (B) Exit alerts (SL / TP / risk policies)
- (C) SigmaTrader alerts
- (D) SigmaTrader deployments
- (E) Holdings Exit Automation (new)
- (F) Manual user actions

If unmanaged, these regimes can:
- conflict
- duplicate exits
- oversell
- erode trust

The goal of this design:

> *Allow all regimes to exist freely, while ensuring only one entry driver at a time, exits remain safe, and the user always understands why something happened.*

---

## 2. Core Architectural Insight

### 2.1 Two Planes, Not Six Systems

Instead of treating each regime independently, the system is split into:

### Control Plane (Intent Authority)
- Decides **who is allowed to create entry intents (BUY)**
- Decides which **exit overlays** are enabled

### Execution Plane (Safety & Mechanics)
- Enforces exit-only guarantees
- Prevents duplicate exits
- Respects broker holdings

This separation is the foundation of reliability.

---

## 3. Entry vs Exit – First-Class Distinction

### 3.1 Entry Sources (Mutually Exclusive)

For each `(user, broker, exchange, symbol, product)`:

- **Only one PRIMARY entry source is allowed**

Possible PRIMARY entry sources:
- TradingView alerts
- SigmaTrader alerts
- SigmaTrader deployments
- NONE (Manual-only)

All other entry sources are **masked by policy**.

---

### 3.2 Exit Overlays (Composable, Safe)

Exit mechanisms are overlays that may apply on top of any entry source:

- Risk exits (SL / TP / drawdown)
- Holdings Exit Automation
- Manual SELL by user

Exit overlays:
- can be enabled/disabled explicitly
- are always arbitrated to avoid duplicate exits

Manual SELL is **always allowed**.

---

## 4. Trade Control Policy (Single Source of Truth)

### 4.1 What It Is

A **Trade Control Policy** governs regime interaction.

It answers:
> “Who may BUY, and which exits may operate, for this symbol?”

---

### 4.2 Policy Scope

- Account / broker default
- Optional per-symbol override

---

### 4.3 Policy Fields

- `primary_entry_source`: TV | ST_ALERT | ST_DEPLOY | NONE
- `allow_secondary_entry_sources`: boolean (default false)
- `exit_overlays_enabled`:
  - `risk_exits`: on/off
  - `holdings_exit_automation`: on/off
- `execution_posture`: MANUAL_ONLY | AUTO_ALLOWED

---

### 4.4 Enforcement Choke Point

All order intents from **any subsystem** must pass through:

```
authorize_order_intent(intent)
  -> ALLOW | WAITING | DENY (with reason)
```

This prevents ambiguity and silent conflicts.

---

## 5. Holdings Exit Automation (Discipline Tool)

### 5.1 What It Is

A **Holdings Exit Subscription** is a persistent contract:

> “For an existing holding, when condition X occurs, create a SELL exit order.”

It is:
- exit-only
- auditable
- restart-safe
- conservative by default

---

### 5.2 What It Is Not

- Not a strategy engine
- Not driven by TradingView SELL alerts
- Not a re-arming multi-leg automation

Partial exits are achieved via **multiple single-leg subscriptions**, each created after user review.

---

## 6. Subscription Lifecycle

### 6.1 States

Status values must stay in sync with the DB `CHECK` constraint and UI filters.

- ACTIVE – monitoring
- PAUSED – temporarily disabled (user action or safety pause)
- TRIGGERED_PENDING – condition met, order intent not yet created (rare; short-lived)
- ORDER_CREATED – WAITING order created (manual queue), awaiting user action
- COMPLETED – finished (single-leg semantics)
- ERROR – unrecoverable issue (requires manual intervention)

---

### 6.2 Lifetime Rules

- Subscription monitors **only while holding exists**
- If broker holdings qty becomes `0`:
  - subscription expires safely
  - no order is created

---

### 6.3 Firing Semantics

- **Single-leg / sell-once**
- One trigger → one order → COMPLETED

---

## 7. Trigger Conditions

### 7.1 Supported Triggers (MVP)

To keep semantics unambiguous and implementation safe, MVP supports:

- Absolute target price reached (`TARGET_ABS_PRICE`)
- Target as % over avg buy (`TARGET_PCT_FROM_AVG_BUY`)

Phase 2 (after we lock reference price semantics):
- Absolute stop price (`DRAWDOWN_ABS_PRICE`)
- % drawdown from peak since subscription start (`DRAWDOWN_PCT_FROM_PEAK`)

---

### 7.2 Price Source

- Last Traded Price (LTP)
- Same price source across all checks

---

## 8. Adaptive Monitoring Strategy

Monitoring frequency scales with proximity to trigger:

- **Far Zone (>10%)**: daily check
- **Near Zone (≤10%)**: every 15 minutes
- **Very Near Zone (≤5%)**: every 5 minutes

Applies symmetrically to targets and stops.

Implementation note:
- The *scheduler* may run frequently (e.g., every 10-30 seconds), but each subscription stores a `next_eval_at`.
- Only subscriptions with `next_eval_at <= now()` are evaluated, which is how we implement the above zones without hammering broker/quotes APIs.

---

## 9. Order Creation Semantics

### 9.1 Exit-Only Guarantees

Every order created:
- is SELL-only
- sets `is_exit = true`
- clamps qty to **live broker holdings**

---

### 9.2 Order Type (MVP)

- MARKET orders only

---

### 9.3 Dispatch Mode

- **MANUAL by default** → creates WAITING order
- AUTO allowed rarely and explicitly

---

## 10. Exit Arbiter (Execution Safety)

Before creating any exit order:

- Check for existing in-flight SELL exits for same symbol/product
- If found:
  - do **not** auto-dispatch a second exit
  - create the new intent as a **WAITING** order with a clear annotation:
    - "Exit already pending for this holding; review before executing."
  - emit an audit event referencing the existing in-flight order id

This prevents overselling and duplicate exits.

Implementation detail (definition of "in-flight"):
- Consider an exit order "in-flight" if `side=SELL` and `is_exit=true` and `status` is one of:
  - `WAITING`, `VALIDATED`, `SENDING`, `SENT`, `PARTIALLY_EXECUTED`
- Treat `FAILED`, `REJECTED`, `REJECTED_RISK`, `CANCELLED`, `EXECUTED` as terminal for this purpose.

---

## 11. Manual Actions

Manual SELL by the user:
- always allowed
- still arbitrated
- never blocked silently

User autonomy is preserved.

---

## 12. UX Wireframes (Conceptual)

### 12.1 Holdings Page – At-a-Glance Control

```
┌──────────────────────────────────────────────────────────────┐
│ Holdings                                                      │
├────────┬───────┬────────┬─────────┬───────────┬────────────┤
│Symbol  │ Qty   │ LTP    │ P&L     │ Control   │ Actions    │
├────────┼───────┼────────┼─────────┼───────────┼────────────┤
│ INFY   │ 120   │ 1542   │ +18.4%  │ TV        │ Exit Plan  │
│        │       │        │         │ Risk ON   │ Sell       │
│        │       │        │         │ Goals ON  │            │
├────────┼───────┼────────┼─────────┼───────────┼────────────┤
│ HDFCBK │ 80    │ 1689   │ -6.2%   │ Manual    │ Exit Plan  │
│        │       │        │         │ Risk ON   │ Sell       │
└────────┴───────┴────────┴─────────┴───────────┴────────────┘
```

Each row answers: **Who is driving this symbol?**

---

### 12.2 Control Drawer – Regime Selection

```
┌──────────────────────────────────────────┐
│ Control: INFY (CNC)                      │
├──────────────────────────────────────────┤
│ ENTRY CONTROL                            │
│ ◉ TradingView Alerts                     │
│ ○ SigmaTrader Alerts                     │
│ ○ SigmaTrader Deployments                │
│ ○ None (Manual only)                     │
│                                          │
│ EXIT OVERLAYS                            │
│ ☑ Risk exits (SL / TP)                   │
│ ☑ Holdings exit automation               │
│                                          │
│ SAFETY POSTURE                           │
│ ◉ Manual confirmation required           │
│ ○ Auto allowed (advanced)                │
│                                          │
│ [ Save ]                 [ Cancel ]      │
└──────────────────────────────────────────┘
```

---

### 12.3 Exit Subscription Dialog – Single Leg

```
┌────────────────────────────────────────┐
│ Create Exit Plan — INFY                │
├────────────────────────────────────────┤
│ WHEN                                   │
│ Target price ≥ [ 1650 ]                │
│                                        │
│ SELL                                   │
│ ◉ 10 % of holding                      │
│ ○ Absolute qty [     ]                 │
│                                        │
│ EXECUTION                              │
│ ◉ Manual (recommended)                 │
│                                        │
│ NOTE                                   │
│ [ Leg 1: book partial profit ]          │
│                                        │
│ ℹ Triggers once, then expires          │
│                                        │
│ [ Create plan ]        [ Cancel ]      │
└────────────────────────────────────────┘
```

---

### 12.4 Managed Exits Page

```
┌──────────────────────────────────────────────────────┐
│ Managed Exits                                        │
├────────┬─────────┬─────────┬─────────┬──────────────┤
│Symbol  │ Trigger │ Size    │ Status  │ Last Action  │
├────────┼─────────┼─────────┼─────────┼──────────────┤
│ INFY   │ ≥1650   │ 10%     │ ACTIVE  │ Checked 15m  │
│ TCS    │ ≥4200   │ 25%     │ DONE    │ Order #9821 │
│ ICICI  │ ≤890    │ 100%    │ ERROR   │ No holdings │
└────────┴─────────┴─────────┴─────────┴──────────────┘
```

---

## 13. Observability & Audit

Every significant action emits an event:
- subscription_created
- trigger_evaluated
- trigger_met
- exit_suppressed
- order_created
- subscription_completed
- error

No silent behavior.

---

## 14. MVP Boundary (Guardrail)

**Build now:**
- Trade Control Policy
- Holdings Exit Automation (single-leg)
- Adaptive monitoring
- Manual-first execution
- Exit arbiter

**Defer:**
- Multi-leg automation
- Trailing stops
- Streaming prices
- Fancy pricing logic

---

## 15. Anchor Principle

> *If a feature makes the system exciting, it is probably wrong.*

The system exists to reduce cognitive load and financial risk, not to maximize automation.

---

## 16. Risk Review & Fortuner‑Grade Safeguards (Critical)

This section documents **potential failure modes** identified during design review and the **explicit safeguards** adopted to prevent financial loss. These are **non‑optional** and must be implemented as written.

---

### 16.1 Duplicate / Competing Exit Orders (Highest Risk)

**Risk**  
Multiple systems (Holdings Exit Automation, TV exits, ST deployments, manual) may attempt to SELL the same holding simultaneously, leading to duplicate WAITING orders or overselling.

**Decision (Final)**  
We keep signals independent but prevent accidental double execution.

This matches the product stance:
- TradingView SELL and Holdings Exit Automation triggers are both allowed to exist.
- When they collide, the user should still see the secondary intent (preferred), but it must not auto-execute.

**Rule**
- If an in‑flight SELL exit order exists for `(user, broker, exchange, symbol, product)`:
  - Create the new intent as a **WAITING** order (MANUAL) with annotation:
    - "Exit already pending; review before executing."
  - Emit event: `EXIT_QUEUED_DUE_TO_PENDING_EXIT`
  - Reference the existing in-flight order id in the event

**Important nuance**
- A subscription must never create multiple orders for the *same trigger*:
  - within a subscription, idempotency remains strict (via `pending_order_id` / `trigger_key`)
  - the above rule is about *different origins* (subscription vs TradingView vs manual vs deployments)

**Rationale**  
This is the safest behavior and avoids confusing the user with multiple pending exits.

---

### 16.2 AUTO Execution Risk (Catastrophic If Misused)

**Risk**  
AUTO execution under stale data, bad mappings, or partial outages can cause unintended full exits.

**Decision (MVP)**  
- **MANUAL‑ONLY execution for Holdings Exit Automation**
- AUTO is feature‑flagged and disabled by default

**If AUTO is ever enabled (future)**, the following hard gates are mandatory:
1) Fresh broker holdings snapshot within configured TTL
2) Market/session open validation
3) Exit arbiter clear (no in‑flight exits)
4) Price sanity (non‑zero, non‑stale)
5) Quantity sanity (computed qty > 0 and ≤ holdings)
6) Max notional cap for AUTO exits

Failure of **any** gate → suppress exit and emit error event.

---

### 16.3 Holdings Source‑of‑Truth & Instrument Mapping

**Risk**  
Symbol mismatches or ambiguous holdings (e.g., corporate actions, broker naming differences) can cause incorrect quantity resolution.

**Rule**
- Holdings are resolved using a **canonical instrument identity** (normalized exchange + tradingsymbol / instrument_id)
- If holdings lookup is ambiguous, missing, or inconsistent:
  - Subscription transitions to `ERROR`
  - **No exit order is created**

**Rationale**  
Failing safe is always preferable to selling the wrong instrument.

---

### 16.4 Quote Staleness & False Triggers

**Risk**  
Triggering exits using stale LTP data may cause premature or incorrect exits.

**Reality check**
SigmaTrader's current quote fetch helpers return prices but do not always provide a reliable quote timestamp.

**Rule (MVP)**
- Use a conservative polling schedule + cooldown + idempotency to prevent repeated triggers.
- If quote fetch fails / missing price:
  - Skip evaluation for that cycle
  - Emit event: `EVAL_SKIPPED_MISSING_QUOTE`

**Phase 2**
- Add an optional quote timestamp and enforce freshness windows.

---

### 16.5 Quantity Resolution & Rounding Errors

**Risk**  
Rounding rules (especially for partial exits) may generate invalid or unintended quantities.

**Rules**
- Quantity calculation is **equity-aware** (SigmaTrader current scope):
  - Equity: integer quantities only
- If computed quantity is invalid:
  - Transition to `ERROR`
  - Do not create order

---

### 16.6 Subscription State Machine Ambiguity

**Risk**  
Unclear state transitions can cause duplicate triggers after restart or stuck subscriptions.

**Authoritative State Transitions**

- `ACTIVE` → `TRIGGERED_PENDING` (trigger condition met)
- `TRIGGERED_PENDING` → `ORDER_CREATED` (WAITING order created)
- `ORDER_CREATED` → `COMPLETED` (single‑leg semantics; subscription does not re-arm itself)
- `ANY` → `PAUSED` (user action)
- `ANY` → `ERROR` (hard failure)
- `ACTIVE` → `COMPLETED` (holding qty becomes 0)

**Rule**  
A subscription with an associated `pending_order_id` **must never create another order**.

Order lifecycle nuance (important for implementation):
- If the WAITING order is later **CANCELLED** by the user, the subscription should transition to `PAUSED` (not back to ACTIVE automatically). This prevents the engine from immediately recreating the same exit if the trigger condition still holds.
- If the order becomes **REJECTED_RISK/FAILED/REJECTED** (risk/broker), the subscription should also transition to `PAUSED` with `last_error` populated.
- A user can explicitly Resume, which clears `pending_order_id`, recomputes `next_eval_at`, and continues monitoring.

---

### 16.7 Idempotency & Restart Safety

**Risk**  
Background jobs may restart or re‑evaluate the same condition multiple times.

**Rules**
- On trigger, compute a deterministic `trigger_key` and store it in the subscription
- Do not create a new order if:
  - `pending_order_id` exists OR
  - `last_trigger_key` matches current trigger
- Enforce DB uniqueness on `client_order_id`

---

### 16.8 Trade Control Policy Enforcement Gap

**Risk**  
If Holdings Exit Automation bypasses the Trade Control Policy, future regime conflicts reappear.

**Rule**
- All exit intents must pass through `authorize_order_intent()`
- Holdings Exit Automation is treated as an **exit overlay** and must be enabled in policy
- If overlay disabled:
  - Suppress exit
  - Emit policy suppression event

---

## 17. Implementation Readiness Verdict

With the safeguards in **Section 16** applied:

- The design is **safe to implement**
- Known catastrophic failure modes are explicitly blocked
- Behavior is predictable, explainable, and auditable

Without these safeguards, the system **must not be deployed**.

---

## 18. Implementation Blueprint (Build-Grade, Concrete)

This section is the missing "how to implement" layer: DB schema, API contracts, background engine behavior, and tests.

### 18.1 Data model (new tables)

Add two tables:

1) `holding_exit_subscriptions` (mutable configuration + state)
2) `holding_exit_events` (append-only audit; recommended)

#### 18.1.1 `holding_exit_subscriptions` (minimum columns)

Identity / scope:
- `id` INTEGER PK
- `user_id` INTEGER FK -> `users.id` (nullable only if you intentionally support global single-user mode)
- `broker_name` TEXT (default `zerodha`)
- `symbol` TEXT (canonical, uppercased, without exchange prefix)
- `exchange` TEXT (default `NSE`)
- `product` TEXT (default `CNC`)

Trigger config:
- `trigger_kind` TEXT with CHECK constraint, MVP values:
  - `TARGET_ABS_PRICE`
  - `TARGET_PCT_FROM_AVG_BUY`
  - `DRAWDOWN_ABS_PRICE` (Phase 2)
  - `DRAWDOWN_PCT_FROM_PEAK` (Phase 2)
- `trigger_value` REAL
- `price_source` TEXT (MVP: `LTP`)

Sizing:
- `size_mode` TEXT with CHECK constraint: `ABS_QTY` | `PCT_OF_POSITION`
- `size_value` REAL
- `min_qty` INTEGER DEFAULT 1

Data representation note (avoid hidden float bugs):
- For robust uniqueness and deterministic comparisons, prefer storing `trigger_value`/`size_value` as scaled integers (e.g., price in paise, percent in basis-points) or DECIMAL/NUMERIC once we move to Postgres.
- If we keep REAL/Float initially (SQLite), treat the UNIQUE constraint as "best-effort exact de-dup"; do not rely on float equality beyond this.

Order behavior:
- `order_type` TEXT (MVP: `MARKET`)
- `dispatch_mode` TEXT with CHECK constraint: `MANUAL` | `AUTO` (MVP default `MANUAL`)
- `execution_target` TEXT DEFAULT `LIVE`

State:
- `status` TEXT with CHECK constraint:
  - `ACTIVE`, `PAUSED`, `TRIGGERED_PENDING`, `ORDER_CREATED`, `COMPLETED`, `ERROR`
- `pending_order_id` INTEGER FK -> `orders.id` (nullable)
- `last_error` TEXT (nullable)
- `last_evaluated_at` DATETIME (UTC) (nullable)
- `last_triggered_at` DATETIME (UTC) (nullable)
- `next_eval_at` DATETIME (UTC) (nullable; drives adaptive monitoring)
- `cooldown_seconds` INTEGER DEFAULT 300
- `cooldown_until` DATETIME (UTC) (nullable)
- `trigger_key` TEXT (nullable; deterministic idempotency key for "this trigger fired")

Bookkeeping:
- `created_at`, `updated_at` UTC

Indexes/constraints:
- UNIQUE (exact de-dup only): `(user_id, broker_name, exchange, symbol, product, trigger_kind, trigger_value, size_mode, size_value)`
- Index: `(status, broker_name, user_id)`
- Index: `(broker_name, exchange, symbol, product)`

Concurrency note (burst safety):
- Processing must run inside a DB transaction and lock subscription rows while evaluating/transitioning.
- On Postgres: use `SELECT ... FOR UPDATE SKIP LOCKED` to safely run multiple workers.
- On SQLite: run a single worker only (until migration) and rely on strict idempotency (`pending_order_id` + `trigger_key`).

#### 18.1.2 `holding_exit_events` (minimum columns)

- `id` INTEGER PK
- `subscription_id` INTEGER FK -> `holding_exit_subscriptions.id`
- `event_type` TEXT with CHECK constraint (examples):
  - `SUB_CREATED`, `SUB_UPDATED`, `EVAL`, `TRIGGER_MET`
  - `ORDER_CREATED`, `ORDER_DISPATCHED`, `ORDER_FAILED`
  - `EXIT_QUEUED_DUE_TO_PENDING_EXIT`
  - `SUB_COMPLETED`, `SUB_ERROR`
- `event_ts` DATETIME UTC
- `details_json` TEXT (JSON)
- `price_snapshot_json` TEXT (JSON; optional)
- `created_at` UTC

Indexes:
- `(subscription_id, event_ts)`
- `(event_type, event_ts)`

Alembic:
- Implement as TEXT + CHECK constraints (matches the current codebase style).
- Ensure defaults are cross-dialect safe (Postgres migration work already noted elsewhere).

### 18.2 API endpoints (backend)

Create `backend/app/api/holdings_exit_subscriptions.py` and wire it into routes:

- `GET /api/holdings-exit-subscriptions`
- `POST /api/holdings-exit-subscriptions` (create or upsert by unique scope)
- `PATCH /api/holdings-exit-subscriptions/{id}`
- `POST /api/holdings-exit-subscriptions/{id}/pause`
- `POST /api/holdings-exit-subscriptions/{id}/resume`
- `DELETE /api/holdings-exit-subscriptions/{id}`
- `GET /api/holdings-exit-subscriptions/{id}/events`

Pydantic schemas (new):
- `HoldingExitSubscriptionCreate`
- `HoldingExitSubscriptionPatch`
- `HoldingExitSubscriptionRead`
- `HoldingExitEventRead`

Auth:
- Follow existing user scoping patterns: only the owner can modify.

### 18.3 Engine (background scheduler)

Add a scheduler like `managed_risk` and `synthetic_gtt`:

Module: `backend/app/services/holdings_exit_engine.py`

Functions:
- `process_holdings_exit_once() -> int`
- `schedule_holdings_exit() -> None`

Config flags (new Settings/envs):
- `ST_HOLDINGS_EXIT_ENABLED` (default false until stable)
- `ST_HOLDINGS_EXIT_POLL_INTERVAL_SEC` (default e.g. 10-30; drives loop cadence only)
- `ST_HOLDINGS_EXIT_MAX_PER_CYCLE` (default e.g. 200)

Core loop outline:

1) Load subscriptions with `status in (ACTIVE, TRIGGERED_PENDING)` AND `next_eval_at <= now()` up to max_per_cycle
2) Group by `(user_id, broker_name)` to batch broker calls
3) Fetch live holdings once per group
4) Fetch quotes in bulk for the relevant symbols (LTP)
5) Evaluate trigger -> if met, create WAITING order and update subscription state
6) If AUTO is enabled (future), dispatch with hard gates; else leave WAITING

Idempotency within a subscription:
- If `pending_order_id` is set, do not create another order.
- Use `trigger_key` to prevent repeated triggers across restarts.

### 18.4 Trigger evaluation details (MVP)

Canonical symbol handling:
- Always normalize to `(exchange, symbol)` without prefix, uppercased.
- Do not assume TradingView-style `NSE:INFY` in this engine; holdings already have exchange+symbol.

Trigger kinds:
- `TARGET_ABS_PRICE`: trigger when `ltp >= trigger_value`
- `TARGET_PCT_FROM_AVG_BUY`: requires holdings `average_price`:
  - compute `target_price = avg_buy * (1 + trigger_value/100)`
  - trigger when `ltp >= target_price`
- `DRAWDOWN_ABS_PRICE`: trigger when `ltp <= trigger_value` (Phase 2)
- `DRAWDOWN_PCT_FROM_PEAK`: stop at X% down from the best favorable price observed since subscription start (Phase 2; requires persisting `peak_price` and updating it on evaluations)

Recommendation:
- MVP should ship with `TARGET_ABS_PRICE` + `TARGET_PCT_FROM_AVG_BUY` first.
- Add drawdown triggers after reference price semantics are locked (avg-buy vs peak vs last).

### 18.5 Quantity resolution (MVP)

Authoritative qty:
- Use broker holdings qty (live fetch) at evaluation time.

Sizing:
- ABS_QTY: `qty = min(int(size_value), int(holdings_qty))`
- PCT_OF_POSITION:
  - `qty = floor(holdings_qty * (size_value/100))`
  - clamp `qty` to `[min_qty, holdings_qty]` when holdings_qty > 0

If qty resolves to 0:
- set subscription to ERROR (or keep ACTIVE and log), do not create order.

### 18.6 Creating the Order row

Create orders consistent with current order execution pipeline:

- `side=SELL`
- `status=WAITING`
- `mode=MANUAL` (MVP)
- `order_type=MARKET`
- `product=CNC`
- `is_exit=True`
- `client_order_id` deterministic:
  - `HEX:{subscription_id}:{trigger_ts_iso}` truncated to 128 chars
- `error_message` explains cause for UI:
  - "Holdings exit automation: target reached (LTP=..., target=...)."

Origin tagging (for UI/ops):
- Orders created by this engine should have `client_order_id` prefix `HEX:` (as above).
- TradingView SELL exits already use a different prefix; the queue can group/sort by this prefix to show "subscription exits" first if needed (subscription priority).

### 18.7 Exit Arbiter (concrete behavior)

When a new exit is triggered but another exit is already in-flight:
- still create the order in WAITING (user preference B)
- annotate order.error_message:
  - "Exit already pending for this holding; review before executing."
- record event: `EXIT_QUEUED_DUE_TO_PENDING_EXIT` referencing existing order id

Important:
- This rule is about different origins (TV vs subscription vs manual).
- Within a subscription, idempotency remains strict (pending_order_id/trigger_key).

### 18.8 Frontend implementation mapping

Holdings page:
- Add "Exit Plan" button to open the subscription dialog
- Display subscription status badge per row

Managed Exits page:
- List subscriptions with their trigger, size, status, and last action
- Show event history (optional but valuable)

Frontend service module:
- `frontend/src/services/holdingsExit.ts` CRUD endpoints

### 18.9 Testing tasks (must-have)

Unit tests (backend):
- Trigger evaluation
- Qty resolution + clamping
- Arbiter behavior: pending exit -> new order is WAITING + annotated

Integration tests:
- Monkeypatch broker holdings and quotes
- Validate subscription creates WAITING order on trigger
- Validate subscription + TV SELL same symbol results in 2 WAITING orders with correct annotations/priority

---

**Document status:** Merged master design with explicit risk analysis, safeguards, and build-grade blueprint
