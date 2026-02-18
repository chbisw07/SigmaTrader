# Codex Implementation Guide

## How to generate sprint_tasks_codex.xlsx + execute safely in a dedicated branch

### 1) Branch & feature-flag strategy

* Create branch: `feature/ai-trading-manager-kite-mcp`
* Introduce feature flags:

  * `ai_assistant_enabled`
  * `ai_execution_enabled`
  * `kite_mcp_enabled`
  * `monitoring_enabled`
* Phase 0 merges should not affect existing order flow unless flags enabled.

### 2) Epics (for sprint_tasks_codex.xlsx)

**E0: Data & Audit Foundation**

* DB schema: snapshots, decision traces, idempotency records, monitoring jobs, exceptions
* Storage + retention policy
* API endpoints to query traces and exceptions

**E1: Broker Adapter + Kite MCP**

* BrokerAdapter interface
* KiteMCPAdapter implementation
* Token lifecycle and server-side secrets
* Snapshot ingestion pipeline

**E2: Reconciler + Exceptions Center**

* Reconciliation rules engine
* Severity classification
* Exceptions UI + remediation stubs

**E3: RiskGate v1**

* Policy config format
* Deterministic evaluation engine
* Deny reasons & explanation codes
* Tests for policy rules

**E4: Execution Engine (Idempotent)**

* Plan → OrderIntent translator
* Idempotency keys + store
* Broker order placement + status polling
* Post-trade verification hook

**E5: Assistant UI + Orchestrator**

* Assistant panel (persistent)
* Tool router + orchestrator API
* Action cards + DecisionTrace viewer
* “Service model”: Analyze / Monitor / Execute / Explain

**E6: Monitoring Scheduler**

* MonitorJob creation/update/delete
* Cadence runner
* Trigger → Action card
* “Execute on instruction” integration

### 3) Task row format (Codex should follow)

Each task in `sprint_tasks_codex.xlsx` must include:

* Epic ID
* Task ID
* Title (imperative)
* Description (what, why)
* Dependencies
* Acceptance criteria (testable)
* Files touched (expected)
* Risk level (L/M/H)
* Rollout plan notes (flag gated)

### 4) Acceptance criteria examples (copy/paste patterns)

**Idempotency (Execution Engine)**

* Given same `idempotency_key`, repeated calls do not place more than one broker order.
* Audit shows single DecisionTrace with stable correlation IDs.

**Policy veto**

* For a policy-violating intent, system must:

  * place zero broker orders,
  * create a DecisionTrace with deny reasons,
  * show UI card with explanation.

**Reconciliation**

* After a successful trade, reconciler reaches “OK” state or produces a bounded set of actionable deltas.

### 5) Testing strategy (minimum)

* Unit tests:

  * RiskGate determinism
  * Plan → OrderIntent translation
  * Idempotency store logic
* Integration tests (mock broker):

  * partial fills
  * rejected orders
  * delayed order status
* E2E smoke:

  * assistant message → plan → execution → trace → reconciliation

### 6) Implementation constraints

* Never allow UI direct broker calls.
* Never allow execution without RiskGate pass.
* All actions must produce DecisionTrace.

---
