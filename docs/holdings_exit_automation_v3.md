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

- ACTIVE – monitoring
- PAUSED – temporarily disabled
- TRIGGERED – condition met
- ORDER_CREATED – WAITING order created
- COMPLETED – finished
- ERROR – unrecoverable issue

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

- Absolute target price reached
- Absolute drawdown threshold breached

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
  - suppress new exit
  - emit audit event

This prevents overselling and duplicate exits.

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
The **Exit Arbiter is strict**.

**Rule**
- If an in‑flight SELL exit order exists for `(user, broker, exchange, symbol, product)`:
  - **DO NOT create a new exit order**
  - **SUPPRESS** the new intent
  - Emit event: `EXIT_SUPPRESSED`
  - Reference the existing order id in the event

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

**Rule**
- Every trigger evaluation must validate quote freshness
- Quote timestamp must be within `2 × evaluation interval`
- If stale or missing:
  - Skip evaluation
  - Emit event: `EVAL_SKIPPED_STALE_QUOTE`

---

### 16.5 Quantity Resolution & Rounding Errors

**Risk**  
Rounding rules (especially for partial exits) may generate invalid or unintended quantities.

**Rules**
- Quantity calculation is **instrument‑aware**:
  - Equity: integer quantities only
  - Crypto: fractional quantities allowed per instrument precision
- If computed quantity violates instrument constraints:
  - Transition to `ERROR`
  - Do not create order

---

### 16.6 Subscription State Machine Ambiguity

**Risk**  
Unclear state transitions can cause duplicate triggers after restart or stuck subscriptions.

**Authoritative State Transitions**

- `ACTIVE` → `TRIGGERED_PENDING` (trigger condition met)
- `TRIGGERED_PENDING` → `ORDER_CREATED` (WAITING order created)
- `ORDER_CREATED` → `COMPLETED` (single‑leg semantics)
- `ANY` → `PAUSED` (user action)
- `ANY` → `ERROR` (hard failure)
- `ACTIVE` → `COMPLETED` (holding qty becomes 0)

**Rule**  
A subscription with an associated `pending_order_id` **must never create another order**.

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

**Document status:** Merged master design with explicit risk analysis and safeguards



---

## 19. Active Trading Sleeve (Per‑Symbol Exposure Partitioning) — *Deferred, Designed*

> **Intent**  
> Separate *protected capital* from *active trading risk* **within the same symbol**, so that tactical trading never contaminates long‑term holdings.

This section intentionally **designs now** but **defers implementation** until the system has settled and the current Holdings Exit Automation has been exercised in real usage.

---

### 19.1 Conceptual Model

For any holding, total exposure is logically partitioned into two sleeves:

- **Core (Protected) Sleeve**  
  - Long‑term holding
  - Governed by Holdings Exit Automation, risk exits, and manual decisions
  - Goal: capital preservation + disciplined exits

- **Active Trading Sleeve**  
  - Explicit risk budget for swing/positional trading
  - Governed by TradingView / SigmaTrader alerts or deployments
  - Goal: tactical alpha, experimentation

> This is **exposure partitioning**, not position splitting.  
> Broker sees one holding; SigmaTrader applies logical rules on top.

---

### 19.2 Per‑Symbol Active Trading Cap

Each symbol may optionally define an **Active Trading Cap**:

Example:
```
Symbol: RELIANCE
Total holding value: ₹100,000
Active trading cap: ₹30,000
Core protected value: ₹70,000
```

Rules:
- Active trading cap is **opt‑in per symbol**
- Default cap = 0 (pure long‑term holding)
- Cap may be expressed as:
  - absolute value (₹30,000), or
  - percentage of current holding value (e.g. 30%)

---

### 19.3 Policy Integration (Control Plane)

Extend **Trade Control Policy** with optional fields:

- `active_trading_cap_value`
- `active_trading_cap_type`: ABS_VALUE | PCT_VALUE
- `active_trading_enabled`: boolean

Behavior:
- Entry systems (TV / ST alerts / deployments) may **only operate within the active sleeve**
- If active sleeve is disabled or cap exhausted:
  - BUY intents are suppressed
  - SELL intents may only reduce active exposure, not core

Holdings Exit Automation remains an **exit overlay** and is unaffected by cap existence.

---

### 19.4 Order Authorization Rules (Critical)

When an **entry system** (e.g., TradingView) generates an order intent:

1) Compute **current active exposure** for the symbol
   - derived from historical orders attributed to active regimes
2) Compute remaining headroom:
   ```
   remaining_active_budget = active_cap − active_exposure
   ```
3) Authorization rules:
   - **BUY**:
     - clamp order qty/notional to remaining_active_budget
     - if remaining_active_budget ≤ 0 → suppress intent
   - **SELL**:
     - SELL only from active sleeve
     - must not reduce holdings below core protected quantity

All such decisions pass through `authorize_order_intent()` and are auditable.

---

### 19.5 Interaction with Holdings Exit Automation

Holdings Exit Automation must be explicit about **which sleeve it applies to**:

Subscription sizing modes (future‑ready, MVP default noted):
- `CORE_ONLY` *(default)*
- `ACTIVE_ONLY`
- `TOTAL_POSITION`

Default behavior:
- Holdings Exit Automation operates on **core sleeve only**
- Active sleeve positions are not auto‑liquidated by long‑term goals

This prevents tactical trades from accidentally dismantling long‑term intent.

---

### 19.6 UX Representation (Boring & Explicit)

On the Holdings row:
```
RELIANCE
Total holding: ₹100,000
Active trading cap: ₹30,000
Core protected: ₹70,000
```

In the Control Drawer:
```
Active Trading
[✔] Enable TradingView for this symbol
Active trading cap: ₹30,000

ℹ Trading alerts may operate only within this cap.
  Remaining quantity is protected by goals.
```

No sliders, no auto‑rebalance, no hidden promotions.

---

### 19.7 Explicit Non‑Goals (To Avoid Future Risk)

The system **must not**:
- auto‑promote active profits into core
- auto‑rebalance between sleeves
- auto‑increase cap after wins
- allow TV/ST alerts to liquidate core unless user explicitly overrides

Promotion from Active → Core is **manual only**, intentional, and rare.

---

### 19.8 Failure Modes & Safeguards

**Risk: Attribution drift**  
Active trades blur into core.

Mitigation:
- Track exposure attribution by order origin
- Never infer sleeve ownership implicitly

**Risk: Over‑complexity**  
System becomes harder to reason about.

Mitigation:
- Feature is opt‑in per symbol
- Default cap = 0
- Advanced UI hidden unless enabled

---

### 19.9 Implementation Status

- **Designed:** Yes (this section)
- **Implemented:** No
- **Recommended timing:** Phase 3, after Holdings Exit Automation has stabilized

This feature is intentionally deferred to avoid compounding risk during early adoption.

