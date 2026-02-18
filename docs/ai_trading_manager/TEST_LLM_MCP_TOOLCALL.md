# Test: LLM + Kite MCP tool-calling (MVP)

This guide verifies that SigmaTrader’s AI assistant can:
1) take a natural-language prompt
2) choose Kite MCP tools via OpenAI tool-calling
3) execute those tools via the Kite MCP SSE session
4) return a structured answer
5) persist a DecisionTrace for audit

## Prereqs

- Backend + frontend running.
- `Settings → AI → Model / Provider`
  - Provider enabled
  - Provider: **OpenAI**
  - Model selected
  - API key saved + selected
- `Settings → AI → Kite MCP`
  - `kite_mcp_enabled` ON
  - MCP server URL: `https://mcp.kite.trade/sse`
  - **Test Connection** shows Connected
  - **Authorize** completed; **Refresh status** shows Authorized

## Manual tests (assistant panel)

Open the always-present AI Trading Manager panel and try:

1) **Top holdings**
   - Prompt: `fetch my top 5 holdings`
   - Expected:
     - Assistant calls `get_holdings`
     - Response includes a top-5 list (or a clear explanation if Kite has fewer holdings)
     - “Tool calls (latest)” section shows `get_holdings`

2) **Open MIS positions**
   - Prompt: `show my open MIS positions and biggest risk`
   - Expected:
     - Assistant calls `get_positions` (and possibly `get_margins`)
     - Response summarizes MIS positions and provides a conservative risk summary

3) **Margins summary**
   - Prompt: `summarize my margin and exposure`
   - Expected:
     - Assistant calls `get_margins` and responds with a short summary

4) **Blocked trade action**
   - Prompt: `cancel my last order`
   - Expected:
     - Any trade/execution tool call is **blocked** with a policy veto message
     - Tool call log shows status `blocked`

## Verify DecisionTrace

For any response:
- Click **View trace** in the assistant panel, or open:
  - `/ai/decision-traces/<decision_id>`
- Confirm the trace includes:
  - `user_message`
  - `tools_called` list
  - `final_outcome.assistant_message`

## Troubleshooting

- If tools are not called:
  - Ensure OpenAI provider is enabled and model is selected.
  - Ensure Kite MCP is Authorized and Connected.
- If you see “Kite MCP is not enabled/configured”:
  - Enable it in `Settings → AI → Kite MCP` and set the server URL.
- If you see “OpenAI unauthorized”:
  - Re-check key selection in `Settings → AI → Model / Provider`.
