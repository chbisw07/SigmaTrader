# Telemetry Tiers (Tier 1/2/3) Implementation Notes

Date: 2026-03-04  
Branch: `feature/hybrid-llm-telemetry-tiers`

Goal: extend the existing Hybrid LLM Gateway (Local Security Gateway + Remote Reasoner) with a **Tier 1/2/3 telemetry posture** system and explicit user-controlled switches, while preserving **exactly one execution pipeline** and backward compatibility.

Non-negotiable: **No parallel execution pipeline**. All modes (LOCAL_ONLY / REMOTE_ONLY / HYBRID) must feed the same pipeline:

`Intent/Plan -> (policy gate) -> ExecutionAgent -> Kite MCP`

## Current Architecture (Discovery)

### Where the AI orchestrator lives

* Primary orchestrator: `backend/app/services/ai_toolcalling/orchestrator.py`
  * Entry: `run_chat(...)`
  * Two behaviors:
    * Legacy tool-calling (OpenAI-style `tools`) when hybrid gateway is disabled.
    * Hybrid gateway (remote reasoner emits JSON ToolRequests; no tool handles) when hybrid gateway is enabled.

### Where LLM calls happen (remote/local connectors)

* OpenAI-compatible chat client: `backend/app/services/ai_toolcalling/openai_toolcaller.py`
* Orchestrator selects provider config slots via:
  * `backend/app/services/ai/active_config.py:get_active_config(...)`
  * Slots:
    * `default` (remote model/provider)
    * `hybrid_local` (local model/provider for LOCAL_ONLY; reserved for future hybrid formatting)
    * `hybrid_remote` (optional; otherwise falls back to `default`)

### Where Kite MCP tools are invoked today

* MCP sessions: `backend/app/services/kite_mcp/session_manager.py` (`kite_mcp_sessions`)
* Orchestrator initializes the session and loads tools from cache:
  * `backend/app/services/ai_toolcalling/tools_cache.py`
  * `backend/app/services/ai_toolcalling/mcp_tools.py`

Tool invocation does **not** occur in the remote model:

* In hybrid mode, the remote model returns JSON tool requests.
* All tool execution is performed locally by the Local Security Gateway (LSG).

### Local Security Gateway (LSG) / tool firewall

* LSG entry point: `backend/app/services/ai_toolcalling/lsg.py:lsg_execute(...)`
* Central policy gate: `backend/app/services/ai_toolcalling/lsg_policy.py:evaluate_lsg_policy(...)`
* Deterministic sanitizer:
  * `backend/app/services/ai_toolcalling/lsg_sanitizer.py:sanitize_kite_payload(...)`
  * `backend/app/services/ai_toolcalling/lsg_sanitizer.py:sanitize_digest_payload(...)`
* Envelope types:
  * `backend/app/services/ai_toolcalling/lsg_types.py` (`ToolRequestEnvelope`, `ToolResultEnvelope`, `ToolCapability`, etc.)

Remote cannot receive tool handles, and cannot directly call Kite MCP.

### Existing policy gating (tools + execution)

* Legacy safe tool allow/deny: `backend/app/services/ai_toolcalling/policy.py`
* Hybrid remote tool requests are gated in one place:
  * `backend/app/services/ai_toolcalling/lsg_policy.py`
  * Remote hard-deny:
    * identity/auth: `get_profile`, `login`
    * broker writes: `place_order`, `modify_order`, `cancel_order`, GTT writes
  * Remote allowlisted market-data tools (toggle-gated):
    * `search_instruments`, `get_ltp`, `get_quotes`, `get_ohlc`, `get_historical_data`
  * Remote digests (toggle-gated):
    * `portfolio_digest`, `orders_digest`, `risk_digest`

### Digests (Tier-2 summary endpoints)

* Implemented locally: `backend/app/services/ai_toolcalling/digests.py`
  * `portfolio_digest(...)`
  * `orders_digest(...)`
  * `risk_digest(...)`

In hybrid mode, the orchestrator may prefetch `portfolio_digest` (via LSG) for portfolio-analysis prompts.

### PII/secrets outbound blocking (current)

* Outbound LLM payload inspector: `backend/app/ai/safety/payload_inspector.py`
  * Blocks common secret keys + patterns; fail-closed for remote providers.
* LSG sanitizer (applied to payloads leaving local to remote):
  * Drops key-based identity/session fields, hashes order/trade/client identifiers, buckets digest-like numbers.

### Settings storage + UI

* Settings schema: `backend/app/schemas/ai_settings.py` (AiSettings + HybridLlmConfig)
* Persistence: `backend/app/services/ai_trading_manager/ai_settings_config.py`
* API: `backend/app/api/ai_settings.py` (`GET/PUT /api/settings/ai`)
* Frontend UI: `frontend/src/components/AiSettingsPanel.tsx`
* Frontend API/types: `frontend/src/services/aiSettings.ts`

### Audit logging + traces (auditable decisions)

* Decision trace store:
  * `backend/app/services/ai_trading_manager/audit_store.py`
  * Orchestrator writes:
    * inputs used (provider/model/tools hash, hybrid mode, etc.)
    * tool calls (`DecisionToolCall`)
    * final outcomes
* Append-only operator payloads (local audit references):
  * `backend/app/services/ai_trading_manager/operator_payload_store.py:persist_operator_payload(...)`
* System events:
  * `backend/app/services/system_events.py:record_system_event(...)`
  * Used for notable orchestration events and LSG denials.

### The ONE execution pipeline (must remain)

Execution is only triggered by the internal tool `execute_trade_plan`:

* Implemented inside orchestrator internal tool handling:
  * `backend/app/services/ai_toolcalling/orchestrator.py` (internal tool `execute_trade_plan`)
* Deterministic gates include:
  * explicit user execute check
  * `ai_execution_enabled` feature flag + kill switches
  * Playbook pre-trade gate + RiskGate
  * ExecutionEngine -> KiteMcpTradeClient broker path

This is the **only** broker-write path and must not be duplicated.

## Integration Points for Telemetry Tier System

Telemetry tiers apply to **what can be exposed to a remote model**. They do not alter the execution pipeline.

### Tier model (to implement as policy)

* Tier-1 (Always OK to remote): public market data tool results.
* Tier-3 (Always blocked): PII/secrets/session artifacts and hidden identifiers.
  * Must be redacted before leaving local under all settings.
* Tier-2 (Portfolio telemetry): holdings/positions/orders/trades/margins and derived analytics.
  * User-controlled via an explicit "Remote portfolio detail level" setting.

### A) Central Tier Policy Engine (single enforcement point)

Extend the existing single policy gate:

* `backend/app/services/ai_toolcalling/lsg_policy.py`
  * Add a central tier classification:
    * tool -> Tier-1/Tier-2/Tier-3 exposure class
  * Enforce remote exposure based on the new setting:
    * `OFF`: deny Tier-2 tool results to remote (digests may still be allowed only if explicitly enabled; decision to be encoded in policy).
    * `DIGEST_ONLY`: allow digest tools; deny raw account tools.
    * `FULL_SANITIZED`: allow raw account read tools *only via LSG* and always sanitize deterministically.
  * Keep hard denies:
    * identity/auth tools (`get_profile`, `login`)
    * broker write MCP tools (place/modify/cancel, GTT writes)

Important: **Remote models must never receive tool handles** (already enforced by the orchestrator’s hybrid loop).

### B) Deterministic Sanitizer (non-LLM)

Extend the existing sanitizer:

* `backend/app/services/ai_toolcalling/lsg_sanitizer.py`
  * Must hard redact Tier-3 under all exposure levels:
    * key-based drops (email/phone/name/address/pan/etc)
    * value-pattern drops (JWT-like, api keys, long opaque secrets)
    * hidden identifiers (instrument_token/exchange_token/etc)
  * Stable pseudonymization (salted hashes) for broker IDs:
    * order_id / trade_id / transaction_id etc
  * Optional bucketing:
    * timestamps (minute/day granularity)
    * quantities/prices (configurable)

This sanitizer must be applied to **any payload leaving local to remote**, including:
* tool results in hybrid loop
* digest outputs
* any "audit receipts" returned to remote (never include Tier-3 values)

### C) Tier-2 digests (local computation)

Digests already exist in `backend/app/services/ai_toolcalling/digests.py`.

Extend them (if needed) so DIGEST_ONLY remains useful:
* exposure summary, concentration, and other derived features that don't require raw payload leakage.

### D) Orchestrator wiring (no pipeline duplication)

All changes must remain inside the existing orchestrator:

* `backend/app/services/ai_toolcalling/orchestrator.py`
  * Hybrid loop already routes:
    * remote JSON ToolRequests -> LSG execute -> ToolResult -> remote
  * Extend the hybrid loop so Tier-2 requests behave according to:
    * `OFF`: deny Tier-2 to remote with explanation + audit
    * `DIGEST_ONLY`: route to digest endpoints
    * `FULL_SANITIZED`: allow raw read tools but sanitize deterministically
  * Trading write remains local-only via the existing `execute_trade_plan` path and gates.

### E) Settings + UI

Backend:
* `backend/app/schemas/ai_settings.py` (add a new setting under `hybrid_llm`):
  * `remote_portfolio_detail_level: OFF|DIGEST_ONLY|FULL_SANITIZED`
* `backend/app/api/ai_settings.py`:
  * include new value in audit `details`

Frontend:
* `frontend/src/components/AiSettingsPanel.tsx`:
  * add "Remote portfolio detail level" selector and explanatory text
* `frontend/src/services/aiSettings.ts`:
  * add type + serialization support

Defaults must preserve current behavior when hybrid gateway is disabled.

### F) Audit logging

Extend audit logs at existing points:
* LSG events in `lsg.py` via `record_system_event(...)`
* operator payload metadata stored by `persist_operator_payload(...)`

Audit records should include:
* tier classification (tier-1/2/3)
* allowed/denied + reason
* sanitization metadata (redacted fields, hashed fields, bucketed fields)

And must not include Tier-3 values in any log fields intended for remote/UI display.

## Confirmation: Single Execution Pipeline

The execution pipeline remains unchanged and is still only:

`execute_trade_plan -> ExecutionEngine -> Kite MCP broker-write tools`

Telemetry tiers only affect:
* what remote models may request, and
* what data may be returned to remote models after deterministic sanitization,

with all tool execution still routed through the single LSG executor.

