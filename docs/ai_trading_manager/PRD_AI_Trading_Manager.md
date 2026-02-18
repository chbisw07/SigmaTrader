# SigmaTrader AI Trading Manager (Always-Present Assistant)

## Product Requirements Document (PRD)

### 1) Summary

SigmaTrader (ST) will include an always-present AI assistant inside the ST web UI. The assistant acts as the user’s “Trading Manager”: it interfaces with the user, provides decision intelligence (analytics, suggestions, brainstorming), monitors markets/portfolio, and executes user-requested trades **through ST**, constrained by deterministic policy gates. Broker remains the ultimate truth (Phase 1: Kite MCP), with continuous reconciliation.

### 2) Goals

* **Always-present assistant** embedded in ST web UI (persistent panel).
* **Delegated execution**: “your message = authorization” for requested actions (no extra per-order confirmations), while still enforcing:

  * deterministic RiskGate,
  * audit trail,
  * idempotency/deduplication.
* **Broker-truth system**: Kite (via Kite MCP) is ultimate truth; ST maintains expected ledger and reconciles.
* **Policy veto**: assistant must veto trades that violate ST policy with clear explanation. Override requires trading outside ST (broker app).

### 3) Non-goals (Phase 1)

* F&O (roadmap only).
* Messaging integrations (Telegram/WhatsApp).
* Fully autonomous trading without explicit user instruction (Phase 2+ only with explicit “arming”).

### 4) Personas

* **Primary (now):** Power user (you) managing own portfolio; wants speed, control, auditability, and reliability.
* **Secondary (later):** ST users who want guided execution, portfolio insights, and safe automation.

### 5) Modes & Control Contract

#### 5.1 Observe Mode (default)

* Assistant can read, analyze, monitor, propose plans, and simulate.
* No order placement.

#### 5.2 Execute-on-Instruction Mode (default for trading requests)

* If user explicitly instructs an action (“Buy X with constraints”), ST treats that as authorization.
* Orders are executed only if RiskGate passes; otherwise veto.

#### 5.3 Automation Mode (Phase 2+)

* User explicitly arms a playbook/automation.
* Still governed by policy and kill switch.

### 6) Core Use Cases

#### UC1: Morning brief

* Pull broker snapshot + ST ledger + prior day actions.
* Output: key changes, drift, anomalies, due reviews, risk highlights.

#### UC2: Delegated trade execution

User: “Buy SBIN MIS if price reclaims VWAP and ADX > 20; risk 0.5%.”

* Assistant builds TradePlan → RiskGate → ExecutionEngine → verify → reconcile → audit.

#### UC3: Monitoring as a service

User: “Monitor RELIANCE and TCS; alert if trend flips; if drawdown > 1% intraday, propose risk-off plan.”

* Monitoring jobs with cadence; alert cards; user can say “do it”.

#### UC4: Veto

User asks for policy-violating trade. Assistant:

* returns “No trade”,
* explains which policies failed and why,
* proposes alternatives (reduce size, different product, wait condition).

### 7) Functional Requirements

#### 7.1 Assistant UI

* Persistent right panel (collapsible).
* Chat + action cards.
* “What I can do” quick menu (Analyze / Monitor / Plan / Execute / Explain / Reconcile).
* One-click “Open Decision Trace”.

#### 7.2 Tooling / Capabilities

* Read portfolio/ledger (ST).
* Read broker truth (Kite MCP): holdings/positions/orders/margins (+ quotes as needed).
* Create monitoring jobs.
* Create trade plans with constraints: entry conditions, sizing, product type (MIS/CNC), stop/target logic, time windows.
* Execute orders via BrokerAdapter (Kite MCP in Phase 1).
* Reconcile expected vs truth continuously.
* Generate audit-grade logs for every action.

#### 7.3 RiskGate (deterministic)

* Policy checks for:

  * product type constraints (CNC/MIS),
  * max per-trade risk,
  * daily loss cap,
  * max open positions,
  * symbol allow/deny list,
  * exposure constraints (sector/portfolio),
  * liquidity/price band sanity checks,
  * market hours & square-off constraints for MIS,
  * idempotency guardrails.

If failed → veto + explanation.

#### 7.4 Exceptions Center

* Shows mismatch types:

  * partial fills / missing fills,
  * rejected orders,
  * stale position state,
  * MIS risk approaching square-off,
  * manual broker trades not reflected in ST expected ledger.
* Provides remediation suggestions:

  * “sync now”, “recompute sizing”, “close/hedge”, “mark as acknowledged”.

### 8) Non-Functional Requirements

* **Reliability:** reconciliation and audit must survive restarts.
* **Idempotency:** no duplicate orders from retries/webhook dupes/UI resend.
* **Latency:** normal plan+execute path should feel “instant” for user operations (practical target: a few seconds; correctness > speed).
* **Explainability:** every trade must have a trace: inputs, checks, actions, outcomes.
* **Security:** least privilege, token safety, no secrets in client.

### 9) Success Metrics (Phase 1)

* 0 critical incidents of duplicated orders caused by ST.
* ≥ 95% of broker-order events reconciled automatically within a short window.
* “No-trade” veto explanations are actionable (user can adjust intent).
* User can perform daily workflow (brief → monitor → execute → review) without leaving ST for normal operations.

---
