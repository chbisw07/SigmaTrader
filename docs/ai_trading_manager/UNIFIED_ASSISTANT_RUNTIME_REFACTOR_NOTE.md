# Unified Assistant Runtime + Trust Policy (Refactor Note)

This note documents the **current SigmaTrader AI implementation** (as of branch `refactor/mcp-tools-section`) and identifies the **minimal change surface** required to move to a unified runtime with trust-based tool policy + Tavily guardrails.

## 1) Current implementation (what exists today)

### AI runtime / assistant orchestration
- **Entry points**
  - REST: `backend/app/api/ai_chat.py` → `run_chat(...)` in `backend/app/services/ai_toolcalling/orchestrator.py`
  - Streaming: `backend/app/api/ai_chat.py` `/chat/stream` also calls `run_chat(...)` with an event callback.
- **Orchestrator**
  - Central orchestrator is `backend/app/services/ai_toolcalling/orchestrator.py:run_chat`.
  - It builds a system prompt, chooses a provider, discovers tools, executes tools, and persists an `AiTmDecisionTrace` via `backend/app/services/ai_trading_manager/audit_store.py`.

### Model selection (local vs remote)
- Provider selection is resolved by `backend/app/services/ai/active_config.py:get_active_config(...)` (DB-backed) and then `backend/app/services/ai/provider_registry.py:get_provider(...)`.
- The orchestrator currently branches behavior based on:
  - `hybrid_llm.enabled` (HYBRID gateway on/off) from `AiSettings.hybrid_llm`
  - `provider.kind` (remote vs local) derived from the chosen provider implementation
- Two execution paths exist:
  1) **Hybrid gateway** (`hybrid_llm.enabled == True`): a “remote reasoner” emits JSON `tool_requests`; tools run through LSG; results are fed back as LSG envelopes.
  2) **Legacy toolcalling** (`hybrid_llm.enabled == False`): the provider uses function/tool calling (OpenAI-style) and the orchestrator executes tool calls.

### MCP server integration (general)
- MCP transport client(s):
  - Kite: `backend/app/services/kite_mcp/session_manager.py` (`kite_mcp_sessions`)
  - External servers: `backend/app/services/mcp/external_session_manager.py` (`external_mcp_sessions`)
  - SSE client: `backend/app/clients/mcp_sse.py` (supports remote SSE + Tavily’s POST/SSE behavior)
- Uniform MCP config API:
  - `backend/app/api/mcp_servers.py` under `/api/mcp/...`
  - Non-Kite server config is persisted encrypted via `backend/app/services/mcp/mcp_settings_store.py`

### Tool discovery and routing
- Tool list discovery/caching:
  - `backend/app/services/ai_toolcalling/tools_cache.py:get_tools_cached(...)`
  - Tool definitions are hashed by `backend/app/services/ai_toolcalling/mcp_tools.py:hash_tool_definitions(...)`
- Routing:
  - Kite tools route to Kite MCP session by default.
  - External tools route via `tool_session_by_name` mapping constructed in the orchestrator when Tavily tools are enabled.

### Kite MCP integration
- Kite MCP config lives in DB-backed AI settings:
  - `backend/app/schemas/ai_settings.py` → `AiSettings.kite_mcp`
  - stored via `backend/app/services/ai_trading_manager/ai_settings_config.py`
- Kite session management:
  - `backend/app/services/kite_mcp/session_manager.py` and `backend/app/services/kite_mcp/secrets.py`
- Kite tools are executed through the orchestrator via `mcp_session.tools_call(...)` and are optionally sanitized for remote models.

### Tavily MCP integration
- Tavily server config is stored as a generic MCP server config (non-Kite):
  - `/api/mcp/servers/...` + encrypted store (`mcp_settings_store.py`)
- Tool exposure to LLMs is gated by server toggle:
  - `ai_enabled` (“Allow AI to use Tavily tools”) in `McpServerConfig`
- `tavily_search` is treated as a Tier-1 “web” tool:
  - allowlist classification in `backend/app/services/ai_toolcalling/policy.py` and `backend/app/services/ai_toolcalling/lsg_policy.py`
- Safe summaries:
  - `backend/app/ai/safety/safe_summary_registry.py` contains a Tavily safe summary implementation.

### Conversation/session state
- Conversation threads are stored as messages:
  - Table: `backend/app/models/ai_trading_manager.py:AiTmChatMessage` with `thread_id` and `account_id`
  - Access helpers: `backend/app/services/ai_trading_manager/audit_store.py` (`append_chat_messages`, `get_thread`, `list_threads`, etc.)
- **No explicit persisted “thread/session state” object exists today** (beyond messages + decision traces).

### Approval / confirmation UI
- Execution safeguards exist (server-side):
  - `execute_trade_plan` requires explicit “execute” intent and is gated by kill switches + RiskGate (in orchestrator).
- There is **no generic “approval dialog” pipeline** for remote data access or Tavily overage today.
- Frontend uses MUI `Dialog` patterns elsewhere (settings, backtesting, managed risk) but not yet in AI chat for tool approvals.

### Logging / audit infrastructure
- Decision-level audit:
  - `AiTmDecisionTrace` persisted by `audit_store.persist_decision_trace(...)`
  - Operator payloads persisted in `AiTmOperatorPayload` via `persist_operator_payload(...)`
- System events:
  - `backend/app/services/system_events.py:record_system_event(...)` is used heavily by orchestrator + LSG.
- Remote PII boundary:
  - Outbound payload inspection: `backend/app/ai/safety/payload_inspector.py`
  - Tool safe summaries: `backend/app/ai/safety/safe_summary_registry.py`
  - Fail-closed behavior when no safe summary is registered.

## 2) Where policy enforcement occurs today

1) **LSG policy gate** (capability + remote restrictions)
   - `backend/app/services/ai_toolcalling/lsg.py:lsg_execute(...)`
   - `backend/app/services/ai_toolcalling/lsg_policy.py:evaluate_lsg_policy(...)`
   - Remote hard-denies and tool-tier posture are enforced here.

2) **Tool category policy gate** (read/web/trade allowlists)
   - `backend/app/services/ai_toolcalling/policy.py:evaluate_tool_policy(...)`
   - Used by orchestrator to decide what to expose/permit (and by new external web tools).

3) **Remote PII enforcement**
   - Safe summaries (`safe_summary_registry.py`) + outbound payload inspection (`payload_inspector.py`)
   - Remote providers effectively run “SAFE_SUMMARIES_ONLY”.

## 3) How MCP tool calls are executed today

### Hybrid gateway path (remote reasoner)
1) Remote reasoner emits JSON `tool_requests`.
2) Orchestrator executes each tool request through `_lsg_call_mcp_payload(...)`.
3) `_lsg_call_mcp_payload(...)` wraps the MCP tool call in `lsg_execute(...)`:
   - schema validation + normalization (`lsg.py`)
   - remote policy checks (`lsg_policy.py`)
   - rate limiting (remote only)
4) Tool results are appended back to the reasoner as an LSG `ToolResultEnvelope`.

### Legacy toolcalling path (tools API)
1) Provider emits tool calls (OpenAI-style).
2) Orchestrator executes tool calls via `_lsg_call_mcp_payload(...)`.
3) For remote providers, raw payloads are converted to safe summaries before being sent back.

## 4) Minimal change surface for the requested refactor

### Modules likely to change (backend)
- Unified trust-tier derivation (LOCAL_MODEL vs REMOTE_MODEL):
  - `backend/app/services/ai_toolcalling/orchestrator.py` (derive trust tier once; pass to policy)
  - Potentially `backend/app/services/ai/provider_registry.py` or `active_config.py` (if needed)
- Tool policy matrix enforcement:
  - `backend/app/services/ai_toolcalling/lsg_policy.py` (remote denies/approvals)
  - `backend/app/services/ai_toolcalling/policy.py` (web + Tavily gating + thresholds)
- Session-level state required by the spec:
  - Add a persisted thread/session state record (new model/table) or extend an existing store.
  - Update `backend/app/services/ai_trading_manager/audit_store.py` to read/write it with the thread.
- Tavily guardrails:
  - A small Tavily limiter + cache module (likely under `backend/app/services/ai_toolcalling/` or `backend/app/services/mcp/`)
  - Integrate into the MCP tool execution path when `tool_name == "tavily_search"`
- Approval flows:
  - Extend AI chat API (`backend/app/api/ai_chat.py`) to return “approval_required” responses in-band, OR add dedicated endpoints to approve/deny and resume.
  - Log via `record_system_event(...)` + store decisions in thread state.

### Modules likely to change (frontend)
- `frontend/src/views/AiTradingManagerPage.tsx`
  - Show two MUI dialogs:
    1) Remote portfolio detailed access approval
    2) Tavily over-limit approval
  - Do not repeat once session-approved.
- `frontend/src/services/aiTradingManager.ts`
  - Add API calls for “approve once / approve session / deny” if implemented server-side.

## 5) Constraints & safety notes
- Current system already has strong primitives (LSG + safe summaries + outbound inspection).
- The spec requires **session-level counters and approvals**, which currently do not exist; a minimal persisted thread-state record is the cleanest fit.
- The refactor should avoid “new orchestrator architecture”; it should:
  - keep `run_chat(...)` as the single runtime,
  - add a trust-tier derived policy layer,
  - add Tavily usage guardrails and approvals as small, well-scoped extensions.

---

## 6) Implemented refactor (unified runtime + trust policy layer)

### Unified Assistant Runtime
- `run_chat(...)` remains the single runtime entry for both legacy toolcalling and hybrid gateway modes.
- A `thread_id` is now passed into the orchestrator so guardrails can be enforced at a session/thread level.

### Trust tiers (LOCAL_MODEL vs REMOTE_MODEL)
- Trust tier is derived from the active provider’s `kind`:
  - `LOCAL_MODEL` for local providers
  - `REMOTE_MODEL` for remote providers
- Tool access decisions are layered into `_lsg_call_mcp_payload(...)` before executing the tool through LSG.

### Approval flows (new)
1) **Remote portfolio detailed access**
   - When a remote model requests raw/detailed portfolio tools (e.g. holdings/positions/orders/margins), the orchestrator pauses and returns an approval request.
   - UI options: Allow once / Allow for this session / Deny.
2) **Tavily over-limit**
   - When session Tavily calls exceed the configured limit (default 10), the orchestrator pauses and returns an approval request.
   - UI options: Allow once / Allow 5 more / Deny.

Implementation hooks:
- Backend approval endpoint: `POST /api/ai/approvals`
- Resume endpoint (no duplicate user message): `POST /api/ai/chat/resume`

### Tavily guardrails (implemented)
- Session counters are persisted per thread:
  - `tavily_calls_session`
  - `tavily_extra_calls_allowed`
- Soft warning events are logged as the threshold approaches.
- Duplicate query optimization:
  - In-memory cache (~120s TTL) avoids repeated Tavily calls for near-identical queries.
  - Cache hits do **not** require over-limit approval and do **not** increment `tavily_calls_session`.

### Session state storage (new)
- New DB table: `ai_tm_thread_state` (per `account_id` + `thread_id`) for guardrail counters and approvals.

### Config (new)
- DB-backed AI settings now include:
  - `tool_guardrails.tavily_max_calls_per_session` (default 10)
  - `tool_guardrails.tavily_warning_threshold` (default 8)

