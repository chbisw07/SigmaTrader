# LLM PII Safety (Operator View vs LLM View)

SigmaTrader’s AI subsystem must be **safe-by-design**: broker/account payloads must not be accidentally sent to remote LLMs.

This document describes the enforced “two views” boundary and how to extend it safely.

## Core Principle

We maintain two representations of tool outputs:

### A) Operator View (server/UI truth)
- The **raw** payload returned by Kite MCP tools (`tools/call`).
- Used for:
  - UI rendering (tables/cards)
  - reconciliation + deterministic computations
  - exceptions + debugging
  - local DecisionTrace storage
- **Never** sent to remote LLM providers.

Operator payloads are stored locally in DB table `ai_tm_operator_payloads` and referenced from DecisionTrace tool calls via `operator_payload_meta` (id/bytes/count only).

### B) LLM View (safe representation)
- A **deterministic**, whitelisted **safe summary** derived from Operator View.
- Used for:
  - remote LLM reasoning
  - tool-calling loop tool results
  - UI trace display (“Summary sent to LLM”)
- Contains:
  - only approved fields
  - no unknown fields
  - no broker/account identifiers
  - hashed identifiers only where necessary (`ST_HASH_SALT`)

## Enforcement (Fail Closed)

Remote providers (OpenAI / Google / Anthropic) operate in `SAFE_SUMMARIES_ONLY`.

Before every outbound remote LLM request:
- `payload_inspector.inspect_llm_payload(...)` runs on the full request payload.
- If any forbidden keys/patterns are found, the request is **blocked** and the user sees a veto message.

When a tool is called:
- SigmaTrader executes the tool (Operator View).
- SigmaTrader stores the raw payload locally (`ai_tm_operator_payloads`).
- SigmaTrader generates the safe summary via `safe_summary_registry`.
- **Only** the safe summary is appended as the tool result message for the LLM.
- If there is no safe summary for the tool, SigmaTrader **blocks** remote LLM continuation (fail closed).

## Safe Summary Registry

Tool summaries live in:
- `backend/app/ai/safety/safe_summary_registry.py`

If a Kite MCP tool is not registered there, it is treated as **unsafe** for remote LLMs.

Currently summarized read tools:
- `get_holdings`
- `get_positions`
- `get_margins`
- `get_orders` (identifiers are hashed; raw ids are never sent)

## Forbidden Data

Outbound payload inspection blocks:
- secret/session fields like `request_token`, `access_token`, `refresh_token`, `session_id`, `api_key`, `authorization`, cookies, etc.
- broker/account identifiers like `user_id`, `account_id`, `client_id`
- instrument identifiers like `instrument_token`, `exchange_token`
- raw order identifiers like `order_id`, `exchange_order_id`
- common secret-like patterns (JWTs, OpenAI keys, etc.)

Implementation:
- `backend/app/ai/safety/payload_inspector.py`

## Adding a New Tool Safely

1) **Do not** expose the tool to remote LLMs until a safe summary exists.
2) Add a summarizer for the tool in `safe_summary_registry.py`.
3) Add golden tests:
   - no forbidden keys
   - no token-like patterns
4) Ensure orchestrator uses the summary only (never raw) for the LLM tool result.

## Troubleshooting

### “Blocked by PII safety policy”
This usually means:
- the outbound LLM request payload contains forbidden keys/patterns (attachments can trigger this), or
- a tool was attempted that lacks a safe summary.

Suggested fix:
- use a local provider (Ollama/LM Studio) for sensitive analysis, or
- remove/avoid sensitive data in prompts/attachments, or
- implement a safe summary for the required tool.

