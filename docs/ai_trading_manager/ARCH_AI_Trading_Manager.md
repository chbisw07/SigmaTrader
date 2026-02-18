# SigmaTrader AI Trading Manager

## Architecture Specification

### 1) Architectural principles

* **Broker truth is canonical.** ST ledger is “expected state”.
* **AI reasons; deterministic systems decide.**
* **All actions are auditable and replayable.**
* **Tool access is explicit and scoped.**
* **Idempotency everywhere.**

### 2) Component overview

```
[ST Web UI]
  - Assistant Panel
  - Action Cards
  - Exceptions Center
        |
        v
[ST Backend API]
  ├─ AI Orchestrator
  │    ├─ Intent Parser → TradeIntent
  │    ├─ Tool Router (ST Tools + Broker Tools)
  │    └─ Decision Composer → TradePlan / MonitorPlan / Insights
  │
  ├─ RiskGate (deterministic)
  ├─ Plan Engine (normalizes & validates plan structure)
  ├─ Execution Engine (idempotent order placement)
  ├─ Reconciler (truth vs expected)
  ├─ Monitoring Scheduler (jobs + triggers)
  ├─ Audit/Decision Store (DecisionTrace, Snapshots, Plans)
  └─ BrokerAdapter Interface
         └─ KiteMCPAdapter (Phase 1)
```

### 3) Key services and responsibilities

#### 3.1 AI Orchestrator

* Inputs: user message, context (selected symbols, current page, portfolio focus).
* Outputs:

  * `InsightCard[]`
  * `TradePlan` / `MonitorPlan`
  * `DecisionTrace` (always)
* Calls:

  * ST tools: ledger, policies, positions view, analytics
  * broker tools: snapshot, quotes, order placement (via adapters)

#### 3.2 BrokerAdapter (multi-broker abstraction)

Interface (conceptual):

* `get_snapshot(account_id) -> BrokerSnapshot`
* `get_quotes(symbols[]) -> Quote[]`
* `place_order(OrderIntent) -> BrokerOrderAck`
* `get_orders(filter) -> BrokerOrder[]`
* `get_trades(filter) -> BrokerTrade[]`

KiteMCPAdapter implements these using Kite MCP endpoints.

#### 3.3 RiskGate (deterministic)

* Input: TradePlan + BrokerSnapshot + ST LedgerSnapshot
* Output: `RiskDecision { allow|deny, reasons[], computed_risk_metrics }`
* Must be pure-ish (same inputs → same output) for reproducibility.

#### 3.4 Execution Engine

* Converts `TradePlan` → `OrderIntent[]`
* Attaches idempotency keys and correlation IDs.
* Handles:

  * retries with backoff,
  * de-duplication,
  * partial fill tracking,
  * post-placement verification.

#### 3.5 Reconciler

* Periodically (and after each execution) compares:

  * ST expected ledger vs broker truth snapshot
* Emits:

  * `ReconciliationDelta[]` with severity
  * Exceptions for UI and remediation actions

#### 3.6 Monitoring Scheduler

* Stores `MonitorJob` (symbols, conditions, cadence, window).
* Executes condition evaluation using quotes + portfolio state.
* Emits Action Cards on triggers.

### 4) Data contracts (minimal required schemas)

#### 4.1 BrokerSnapshot

* `as_of_ts`
* `holdings[]`
* `positions[]`
* `orders[]`
* `margins`
* optional: `quotes_cache[]`

#### 4.2 LedgerSnapshot (ST expected state)

* `as_of_ts`
* `expected_positions[]`
* `expected_orders[]`
* `subscriptions/watchers[]`

#### 4.3 TradeIntent (from user)

* `symbols[]`
* `side` (BUY/SELL)
* `product` (MIS/CNC)
* `constraints` (entry condition, time window, max slippage, etc.)
* `risk_budget` (per-trade %, ₹, etc.)

#### 4.4 TradePlan

* `plan_id`
* `intent`
* `entry_rules[]`
* `sizing_method`
* `risk_model` (stop distance, ATR-based, etc.)
* `order_skeleton` (types, limits/market preference)
* `validity_window`
* `idempotency_scope`

#### 4.5 DecisionTrace (audit record)

* `decision_id`
* `user_message`
* `inputs_used` (snapshot ids, timestamps)
* `tools_called[]`
* `riskgate_result`
* `orders_submitted[]` + responses
* `reconciliation_result`
* `final_outcome`
* `explanations[]` (human-readable summary)

### 5) Idempotency & de-duplication strategy

* Every plan has `plan_id` + `idempotency_key`.
* Execution engine stores `IdempotencyRecord`:

  * key, first_seen_ts, status, broker_order_ids
* Any repeated call with same key returns prior result (or continues from known state).

### 6) Security model

* Kite MCP tokens stored server-side only.
* UI never sees broker credentials.
* Role-based scopes:

  * read-only broker scopes for observation/analytics,
  * execution scopes only when enabled for ST execution (still policy-gated).
* All tool calls logged.

### 7) Failure modes & recovery

* Broker API down → assistant degrades to “read-only ST ledger” with warning.
* Partial fills → reconciler detects, UI shows exception, execution engine continues safely.
* Duplicate webhooks → idempotency prevents duplicate orders.
* Stale quotes → RiskGate can deny if quote age exceeds threshold.

---

