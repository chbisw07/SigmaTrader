# Hybrid LLM (Local Security Gateway + Remote Reasoner)

Date: 2026-03-03  
Branch: `feature/hybrid-llm-gateway`

This document records the discovery pass and the exact integration points to implement:

* Modes: `LOCAL_ONLY`, `REMOTE_ONLY`, `HYBRID`
* Capability-based tool access for remote requests
* A Local Security Gateway (LSG) that is the only executor of MCP tools
* Local digest endpoints for account/portfolio data

Non-negotiable: **No parallel execution pipeline**. All modes must feed the same pipeline:

`Intent/Plan -> (policy gate) -> ExecutionAgent -> Kite MCP`

## Current Architecture (Discovery)

### Where LLM calls happen

* LLM tool-calling happens in:
  * `backend/app/services/ai_toolcalling/orchestrator.py`
    * `run_chat(...)` calls `openai_chat_with_tools(...)`
* OpenAI-compatible tool-calling client:
  * `backend/app/services/ai_toolcalling/openai_toolcaller.py`
    * `openai_chat_with_tools(...)` calls `/v1/chat/completions` with `"tools"`

Provider selection / model config:

* `backend/app/services/ai/active_config.py` + `backend/app/schemas/ai_provider.py`
  * stored in DB under broker secret `ai_provider/active_config_v1`
  * currently tool-calling supports `openai` and `local_lmstudio` only (enforced in orchestrator)

### How tools are called today

Kite MCP connectivity and tool list:

* MCP client (SSE + POST):
  * `backend/app/clients/mcp_sse.py`
* MCP session manager:
  * `backend/app/services/kite_mcp/session_manager.py` (imported by orchestrator as `kite_mcp_sessions`)
* Tool cache + conversion to OpenAI tool schema:
  * `backend/app/services/ai_toolcalling/tools_cache.py`
  * `backend/app/services/ai_toolcalling/mcp_tools.py` (`mcp_tools_to_openai_tools`)

Tool execution is currently done directly in the orchestrator:

* Direct deterministic portfolio display path:
  * `backend/app/services/ai_toolcalling/orchestrator.py`
    * `_call_json(...)` calls `session.tools_call(...)`
* LLM tool-calling loop path:
  * `backend/app/services/ai_toolcalling/orchestrator.py`
    * executes MCP tools via `session.tools_call(name=tc.name, arguments=tc.arguments)`
    * executes internal tools inline (e.g. `propose_trade_plan`, `execute_trade_plan`)

### The ONE execution pipeline (must remain)

Execution is only triggered by the internal tool `execute_trade_plan`:

* Entry point:
  * `backend/app/services/ai_toolcalling/orchestrator.py`
    * internal tool handler for `execute_trade_plan`
* Deterministic gates before execution:
  * explicit user execute check: `_is_explicit_execute(user_message)` inside orchestrator
  * feature flag + kill switches:
    * `backend/app/services/ai_trading_manager/ai_settings_config.py:is_execution_hard_disabled(...)`
    * `backend/app/core/config.py` has `ai_execution_kill_switch` env-backed default
  * broker connection check: `tm_cfg.kite_mcp.last_status == connected`
  * Playbook pre-trade:
    * `backend/app/services/ai_trading_manager/manage_playbook_engine.py:evaluate_playbook_pretrade(...)`
  * RiskGate:
    * `backend/app/services/ai_trading_manager/riskgate/engine.py:evaluate_riskgate(...)`
* Execution agent:
  * `backend/app/services/ai_trading_manager/execution/engine.py:ExecutionEngine`
* Broker adapter:
  * `backend/app/services/kite_mcp/trade.py:KiteMcpTradeClient` (placed inside an adapter wrapper in orchestrator)

This is the **single** broker-write path used by the assistant today.

### Policy gating (tools + execution)

MCP tool allow/deny in orchestrator:

* Tool classification / allowlist:
  * `backend/app/services/ai_toolcalling/policy.py`
    * `SAFE_READ_TOOL_ALLOWLIST` includes:
      `get_holdings`, `get_positions`, `get_orders`, `get_margins`,
      `get_ltp`, `get_quotes`, `get_ohlc`, `get_historical_data`, `search_instruments`
    * `evaluate_tool_policy(...)` blocks destructive tools; trade tools are not executed via MCP

Remote PII guardrails:

* Outbound payload inspection (fail-closed for remote providers):
  * `backend/app/ai/safety/payload_inspector.py:inspect_llm_payload(...)`
* Safe summaries (remote providers only get deterministic safe summaries):
  * `backend/app/ai/safety/safe_summary_registry.py`
  * Orchestrator blocks executing any tool for remote providers if no safe summary is registered.

### Audit logging (tool calls + decisions)

Decision trace:

* `backend/app/services/ai_trading_manager/audit_store.py`
  * `new_decision_trace(...)` and `persist_decision_trace(...)`
* Orchestrator stores:
  * `DecisionToolCall` entries (tool name, summaries, operator payload meta)
  * final outcome and explanations

Raw tool payload (operator-only):

* `backend/app/services/ai_trading_manager/operator_payload_store.py:persist_operator_payload(...)`
  * stores raw payload locally with `payload_id` (used as an audit reference)

System events:

* `backend/app/services/system_events.py:record_system_event(...)`
  * used for notable orchestration events: PII blocks, tool blocks, execution evaluation, settings updates, etc.

### Settings storage + UI

Backend settings model and persistence:

* `backend/app/schemas/ai_settings.py` (`AiSettings`, `AiSettingsUpdate`)
* `backend/app/services/ai_trading_manager/ai_settings_config.py`
  * stored in DB under broker secret `ai_trading_manager/ai_settings_v1`
* API:
  * `backend/app/api/ai_settings.py` (`GET/PUT /api/settings/ai`)
* Frontend:
  * `frontend/src/services/aiSettings.ts` (types + API calls)
  * `frontend/src/components/AiSettingsPanel.tsx` (settings UI)

## Integration Points for Hybrid LLM Gateway

### 1) Mode selection (LOCAL_ONLY / REMOTE_ONLY / HYBRID)

Add config under `AiSettings`:

* Backend:
  * `backend/app/schemas/ai_settings.py` add a new section (defaults must preserve current behavior).
  * `backend/app/api/ai_settings.py` include the new fields in audit `details`.
* Orchestrator:
  * `backend/app/services/ai_toolcalling/orchestrator.py:run_chat(...)`
    * if hybrid gateway is enabled: use the new remote-reasoner loop (no OpenAI tool handles)
    * else: keep existing legacy tool-calling behavior unchanged

### 2) LSG interception for tool calls (single executor for MCP tools)

Centralize tool execution through an LSG wrapper called from:

* direct deterministic portfolio display path:
  * `orchestrator.py` `_call_json(...)`
* tool-calling loop:
  * `orchestrator.py` where it currently calls `session.tools_call(...)`
* any new remote-reasoner tool loop (HYBRID/REMOTE_ONLY):
  * same LSG function must be used

LSG responsibilities to implement:

* accept a ToolRequest envelope (request_id, source, mode, capability, tool_name, args, reason, risk_tier)
* validate args against a JSON-schema-like definition (fail-closed for remote)
* enforce capability allow/deny centrally (config-driven)
* rate limiting (per tool + per symbol)
* execute Kite MCP tools ONLY inside LSG
* sanitize output before returning to remote
* write an append-only audit entry for request + result (use `persist_operator_payload` + `record_system_event`)

### 3) Digest endpoints (local-only computation)

Add internal (SigmaTrader) tools callable via LSG:

* `portfolio_digest()`
* `orders_digest(last_n)`
* `risk_digest()`

Implementation should:

* fetch broker snapshot locally (`fetch_kite_mcp_snapshot(...)`) and/or ledger snapshot (`build_ledger_snapshot(...)`)
* return only sanitized/bucketed aggregates suitable for remote providers
* never return raw holdings/orders/margins/trades payloads to remote

### 4) Tool policy + capability model (central enforcement)

Introduce a single policy map (code or config file, consistent with repo conventions):

* capability tiers:
  * `MARKET_DATA_READONLY`, `ACCOUNT_DIGEST`, `TRADING_INTENT`, `TRADING_WRITE`, `IDENTITY_AUTH`
* remote allow/deny rules:
  * allow market-data read tools only when toggle enabled:
    * `search_instruments`, `get_ltp`, `get_quotes`, `get_ohlc`, `get_historical_data`
  * hard deny identity auth:
    * `get_profile`, `login`
  * hard deny trading write MCP tools:
    * `place_order`, `modify_order`, `cancel_order`,
      `place_gtt_order`, `modify_gtt_order`, `delete_gtt_order`
  * deny raw sensitive account reads:
    * `get_holdings`, `get_positions`, `get_orders`, `get_order_history`, `get_order_trades`, `get_trades`, `get_margins`, `get_mf_holdings`
    * allow only digests (`portfolio_digest`, `orders_digest`, `risk_digest`) when digest toggle enabled

### 5) Remote tool loop wiring (no parallel execution pipeline)

When hybrid gateway is enabled:

* Orchestrator calls the remote reasoner WITHOUT tool handles.
* Remote returns `ToolRequest` JSON objects, not OpenAI tool calls.
* Orchestrator passes each ToolRequest through LSG, returns ToolResult envelopes back to remote.
* If remote proposes an `OrderIntent` (or requests `propose_trade_plan`), it must still flow into the existing:
  * plan normalization
  * policy gates (playbook + RiskGate)
  * `ExecutionEngine` -> `KiteMcpTradeClient`

### 6) UI Settings updates

Extend `AiSettingsPanel`:

* add a new "Hybrid LLM Gateway" section:
  * enable toggle (default OFF)
  * mode selection: Local / Remote / Hybrid
  * toggles:
    * “Remote may request market-data tools”
    * “Remote may request portfolio digests”
* persist using existing `PUT /api/settings/ai`
* display the effective mode/toggles alongside existing "AI execution enabled" + kill switch.

## Confirmation: No Parallel Execution Pipeline

All changes will be implemented by:

* adding LSG as a wrapper around the existing orchestrator tool execution points, and
* adding a remote-reasoner tool request loop inside the existing orchestrator,

while keeping `execute_trade_plan -> ExecutionEngine -> Kite MCP` as the **only** broker-write pipeline.

