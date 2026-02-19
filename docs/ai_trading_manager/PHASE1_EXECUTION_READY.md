# Phase 1 — Execution Ready (Manual Test Checklist)

This document describes how to manually verify the **Phase 1 delegated execution** flow end-to-end in SigmaTrader:

`prompt → TradePlan → RiskGate → ExecutionEngine → Kite MCP (place_order) → post-trade reconcile → DecisionTrace`

## Preconditions

1) **AI Assistant enabled**
- Settings → AI → enable `ai_assistant_enabled`

2) **LLM provider configured**
- Settings → AI → Model / Provider
- Select `OpenAI`, choose a model, add/select an API key
- Confirm `Test Prompt` works

3) **Kite MCP connected + authorized**
- Settings → AI → Kite MCP
- Set MCP URL to `https://mcp.kite.trade/sse`
- Click `Authorize`, complete Zerodha login
- Click `Refresh status` and confirm:
  - `Connected`
  - `Authorized`

4) **Execution enabled**
- Settings → AI → enable `ai_execution_enabled`
- Ensure kill switch is **OFF**

## Test 1 — “Proposal only” (execution disabled)

1) Disable `ai_execution_enabled` in Settings → AI
2) In the AI Trading Manager panel, ask:
   - `Buy SBIN MIS risk 0.5% with ATR stop`
3) Expected:
   - Assistant produces a TradePlan proposal
   - Assistant does **not** place any broker orders
   - DecisionTrace exists and shows:
     - `final_outcome.trade_plan`
     - `final_outcome.authorization_message_id`

## Test 2 — “Delegated execution” (policy-gated)

1) Enable `ai_execution_enabled` in Settings → AI
2) In the AI Trading Manager panel, ask (explicit execution request):
   - `Buy SBIN MIS risk 0.5% with ATR stop`
3) Expected:
   - Assistant proposes a TradePlan
   - RiskGate runs deterministically and records:
     - `riskgate_result.outcome` (allow/deny)
     - `riskgate_result.policy_hash`
     - `riskgate_result.reason_codes[]`
   - If **DENY**:
     - No broker order is placed
     - Assistant explains veto (no override inside ST)
   - If **ALLOW**:
     - ExecutionEngine submits the order via Kite MCP `place_order`
     - Result is recorded in DecisionTrace:
       - `final_outcome.execution`
       - broker order ids
     - Post-trade reconcile runs:
       - `final_outcome.execution.reconciliation`
     - Exceptions (if any) show up in **Exceptions Center**

## Test 3 — Idempotency (no duplicate orders)

1) With `ai_execution_enabled` ON, run the same prompt again:
   - `Buy SBIN MIS risk 0.5% with ATR stop`
2) Expected:
   - No duplicate broker orders are placed for the same authorization+plan
   - DecisionTrace should show the prior execution outcome (idempotent replay)

## Test 4 — Kill Switch

1) Turn ON kill switch: Settings → AI → `Disable all AI execution now`
2) Ask:
   - `Buy SBIN MIS risk 0.5% with ATR stop`
3) Expected:
   - Assistant proposes the plan
   - Execution is vetoed with reason `EXECUTION_KILL_SWITCH`

## Where to Inspect

- **DecisionTrace viewer:** `/ai/decision-traces/<decision_id>`
- **Exceptions Center:** `/ai/exceptions`
- **AI audit log (settings audit):** Settings → AI → “View Audit Log”

## Notes / Current Limitations

- SigmaTrader never sends broker passwords or API secrets to the LLM. API keys/tokens stay server-side and encrypted.
- TradePlan ATR/entry price currently uses **local candle data (DB)**. If candles are missing for a symbol, the plan proposal may fail.
- Broker order lifecycle polling is best-effort; reconciliation is the source of truth for post-trade verification.

