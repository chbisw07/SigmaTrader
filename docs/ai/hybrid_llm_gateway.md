# Hybrid LLM Gateway (LSG + Remote Reasoner)

This repo supports an optional **Hybrid LLM** mode where:

* The **remote reasoner** (OpenAI) has **no tool handles**.
* The reasoner emits **ToolRequest JSON**.
* The backend runs all tool execution through the **Local Security Gateway (LSG)**.
* Remote tool results are **sanitized** and every tool request/result is **audited**.

Default behavior is unchanged: if the hybrid gateway is disabled, SigmaTrader continues using the legacy OpenAI tool-calling loop.

## Settings (UI)

In the web UI:

1. Go to **Settings → AI**
2. Configure the LLM(s):
   * **Remote Model / Provider**: used for `REMOTE_ONLY` and `HYBRID` (unless you later enable a dedicated remote slot).
   * **Hybrid Local Model / Provider**: used for `LOCAL_ONLY` (and reserved for future hybrid formatting/summarization).
3. Enable **Hybrid LLM Gateway**
4. Pick a mode:
   * `LOCAL_ONLY`
   * `REMOTE_ONLY`
   * `HYBRID`
5. Enable the remote capability toggles you want:
   * Remote market-data tools
   * Remote account digests

## Settings (API)

You can also configure it via:

* `GET /api/settings/ai`
* `PUT /api/settings/ai`

Example payload:

```json
{
  "hybrid_llm": {
    "enabled": true,
    "mode": "REMOTE_ONLY",
    "allow_remote_market_data_tools": true,
    "allow_remote_account_digests": true
  }
}
```

### Provider Config Slots

The UI stores the active LLM provider config via:

* `GET /api/ai/config?slot=default`
* `PUT /api/ai/config?slot=default`
* `GET /api/ai/config?slot=hybrid_local`
* `PUT /api/ai/config?slot=hybrid_local`

If `hybrid_local` is not configured, `LOCAL_ONLY` will require you to either configure it or switch the default provider to a local provider.

## Modes

* `LOCAL_ONLY`
  * Intended for local reasoning (LM Studio).
  * Tool execution still goes through LSG.
* `REMOTE_ONLY`
  * Remote reasoning (OpenAI) emits ToolRequest JSON only.
  * Remote has no MCP tool handles.
* `HYBRID`
  * Remote reasoning via ToolRequest JSON; local assistance may be added later.
  * Tool execution still goes through LSG.

## Remote Tool Requests (Protocol)

The remote reasoner must output **only JSON**.

Tool request:

```json
{
  "tool_requests": [
    {
      "request_id": "r1",
      "tool_name": "get_ltp",
      "args": { "symbols": ["NSE:INFY"] },
      "reason": "Need the current price",
      "risk_tier": "LOW"
    }
  ]
}
```

Final response:

```json
{
  "final_message": "Here is what I found...",
  "order_intent": {
    "symbols": ["SBIN"],
    "side": "BUY",
    "product": "MIS",
    "constraints": { "qty": 10 },
    "risk_budget_pct": 0.5
  }
}
```

## Capability Policy (Remote)

Remote requests are capability-gated in `backend/app/services/ai_toolcalling/lsg_policy.py`.

Remote may request (when enabled by settings):

* Market data read-only:
  * `search_instruments`, `get_ltp`, `get_quotes`, `get_ohlc`, `get_historical_data`
* Account digests (sanitized summaries):
  * `portfolio_digest`, `orders_digest`, `risk_digest`

Remote is denied:

* Identity/auth:
  * `get_profile`, `login`
* Broker write tools:
  * `place_order`, `modify_order`, `cancel_order`
  * `place_gtt_order`, `modify_gtt_order`, `delete_gtt_order`
* Raw sensitive account reads:
  * `get_holdings`, `get_positions`, `get_orders`, `get_order_history`, `get_order_trades`, `get_trades`, `get_margins`, `get_mf_holdings`

## Security Guarantees

* Remote models never receive raw holdings/orders/margins/trades payloads.
* Remote tool results are sanitized:
  * secrets/session ids removed
  * identity fields removed
  * broker identifiers are hashed
* Execution remains deterministic and gated:
  * explicit user authorization check
  * `ai_execution_enabled` feature flag
  * kill switch checks
  * Playbook pre-trade + RiskGate

## Auditing

* Every LSG tool request/result emits a system event with category `AI_LSG`.
* Decision traces include tool-call summaries:
  * `GET /api/ai/decision-traces/{decision_id}`

## Tests

Backend:

```bash
cd backend
source .venv/bin/activate
pytest
```

Hybrid gateway tests:

```bash
cd backend
source .venv/bin/activate
pytest -q tests/test_lsg_policy_and_sanitizer.py tests/test_ai_hybrid_gateway.py
```
