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

### 7) AI Settings (ST Web UI)

SigmaTrader includes an **AI Settings** tab at `Settings → AI` (`/settings?tab=ai`) to configure and test AI subsystem settings.

**What it stores (server-side)**

* Feature flags: `ai_assistant_enabled`, `kite_mcp_enabled`, `monitoring_enabled`, `ai_execution_enabled`
* Execution kill switch (hard disable)
* Kite MCP connection profile (URL, scopes, adapter placeholder) + last test status + cached capabilities
* LLM provider config (placeholder; Phase 1 orchestrator will consume)

**Backend endpoints**

* `GET  /api/settings/ai`
* `PUT  /api/settings/ai`
* `POST /api/settings/ai/kite/test`
* `GET  /api/settings/ai/audit`

### 8) AI Provider + Model (real test path)

The **Model / Provider** panel in `Settings → AI` is now functional and lets you:

* Choose provider: OpenAI / Google (Gemini) / Ollama (local) / LM Studio (local)
* Store API keys securely server-side (encrypted; UI shows masked only)
* Discover models (dynamic list) with fallback to manual model entry
* Run a **Test Prompt** and see response + latency + token usage (best-effort)

**Backend endpoints**

* `GET  /api/ai/providers`
* `GET  /api/ai/config`
* `PUT  /api/ai/config`
* `GET  /api/ai/keys?provider=<id>`
* `POST /api/ai/keys`
* `PUT  /api/ai/keys/{id}`
* `DELETE /api/ai/keys/{id}`
* `POST /api/ai/models/discover`
* `POST /api/ai/test`

**Auditability**

* All config/key/test actions emit `SystemEvent` entries in category `AI_PROVIDER`.
* When “Do not send PII” is enabled, audit logs store only a `prompt_hash` (no prompt preview).

**How to test locally**

Kite MCP (MCP over SSE):
1. Start backend + frontend.
2. Open `Settings → AI → Kite MCP`.
3. Set MCP server URL to `https://mcp.kite.trade/sse` (note: this is an **MCP SSE** endpoint, not REST; do not append `/api/health`).
4. Click **Test Connection** (this performs MCP `initialize` over SSE + HTTP/2).
5. Click **Authorize**, open the login URL in your browser, and complete Kite login.
6. Click **Refresh status** until it shows **Authorized**.
7. Use **MCP Console**:
   - **List tools**
   - Call `get_holdings` / `get_positions` / `get_orders` / `get_margins`
8. Click **Fetch snapshot** (persists a broker snapshot in the audit store).

OpenAI:
1. `Settings → AI → Model / Provider`
2. Provider: **OpenAI**
3. Add key (name + API key), select it
4. Enable provider
5. Fetch models → pick a model (or type custom)
6. Run Test

Google (Gemini):
1. Provider: **Google (Gemini)**
2. Add key (AI Studio / Gemini API key), select it
3. Enable provider
4. Fetch models → pick a model
5. Run Test

Ollama:
1. Start Ollama locally (default `http://localhost:11434`)
2. Provider: **Ollama (local)**
3. Enable provider
4. Fetch models
5. Choose a model and Run Test

LM Studio:
1. Start LM Studio server in OpenAI-compatible mode (typically `http://localhost:1234/v1`)
2. Provider: **LM Studio (local)**
3. Enable provider
4. Fetch models
5. Choose a model and Run Test

Notes:
* Kite MCP requires HTTP/2 multiplexing for the SSE stream + message POST endpoint to share a session. Backend includes `h2` to enable httpx HTTP/2 support.
* Keep **AI execution enabled** OFF unless RiskGate + orchestrator are fully integrated.

---
