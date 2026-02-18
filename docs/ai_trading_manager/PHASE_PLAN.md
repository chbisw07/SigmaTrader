# Phased Implementation Plan

## Phase 0 — Foundation (Reliability First)

**Objectives**

* Build audit + snapshot + reconciliation backbone.

**Deliverables**

* Snapshot store: BrokerSnapshot + LedgerSnapshot
* Audit/Decision store schema
* Reconciler MVP
* Exceptions Center UI (read-only)
* BrokerAdapter interface + stub adapter

**Exit criteria**

* You can see broker vs ST differences, consistently and clearly.

---

## Phase 1 — “Wow MVP” (Always-present assistant + broker-aware DI)

**Objectives**

* Assistant panel + orchestrator + monitoring + delegated execution (policy-gated).

**Deliverables**

* Assistant panel UI (chat + action cards)
* AI Orchestrator with tool registry
* KiteMCPAdapter (Phase 1 broker)
* TradePlan generation + Plan Viewer
* RiskGate v1 policy engine
* Execution engine (idempotent)
* Post-trade verification + reconciliation hook
* Monitoring scheduler v1
* DecisionTrace viewer

**Exit criteria**

* “Monitor these symbols” works.
* “Buy/Sell with constraints” works.
* Veto works and is understandable.
* No duplicates; reconciliation passes for typical day.

---

## Phase 2 — Playbooks + Cautious Automation

**Objectives**

* Repeatable workflows and “armed” automations.

**Deliverables**

* Playbook library (saved intents/plans)
* Arming model (explicit enable per playbook)
* Portfolio DI: drift/correlation/risk budgets
* Remediation actions from Exceptions Center (“Fix & retry”, “Resync”, etc.)

---

## Phase 3 — Moat Hardening

**Objectives**

* Advanced decision intelligence while staying deterministic at execution boundary.

**Deliverables**

* Regime + volatility context overlays
* Smarter sizing suggestions (still policy-gated)
* Additional broker adapters
* Roadmap entry for F&O once you’re ready

---
