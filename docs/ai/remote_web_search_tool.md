# Remote Web Search Tool (OpenAI Responses API)

SigmaTrader can optionally enable OpenAI's `web_search` tool for the **remote reasoner** (HYBRID / REMOTE_ONLY modes where the provider is OpenAI).

Default behavior is unchanged: this feature is **off** unless explicitly enabled.

## Enable

Set these environment variables for the backend:

```bash
# master switch (default: false)
export ST_ENABLE_REMOTE_WEB_SEARCH=true

# optional: restrict web search sources to specific domains (CSV or JSON array)
export ST_REMOTE_WEB_SEARCH_ALLOWED_DOMAINS="reuters.com,bloomberg.com"
# export ST_REMOTE_WEB_SEARCH_ALLOWED_DOMAINS='["reuters.com","bloomberg.com"]'

# optional: disable live external web access (default: true)
export ST_REMOTE_WEB_SEARCH_LIVE_ACCESS=true

# optional: request source metadata via Responses API include mechanism (default: true)
export ST_REMOTE_WEB_SEARCH_INCLUDE_SOURCES=true
```

Notes:

- This uses the OpenAI **Responses API** (`POST /v1/responses`) when enabled.
- There is also a per-provider UI toggle in **Settings → AI → Remote Model / Provider** ("Enable web search"). Web search
  is active only when both the backend env flag and the UI toggle are enabled.
- If the configured provider is not `openai`, SigmaTrader keeps using the existing OpenAI-compatible `POST /v1/chat/completions` path and web search is not enabled.

## What It Does

- Adds `tools: [{"type":"web_search", ...}]` to the remote reasoner request.
- Keeps the existing remote reasoner contract stable by continuing to require a single JSON object in the prompt and validating/retrying when needed.
  (OpenAI currently rejects `web_search` when JSON mode/response format is forced.)
- Captures **only source domains** (not full URLs) into the decision trace metadata when available.

## Safety Notes

- This may increase cost/latency because the remote model can perform web lookups.
- Do not rely on web content for broker-write actions: execution remains gated by the existing policy engine + kill switches.
- No prompts/responses are logged; the trace stores only timing/usage indicators and (optionally) source **domains**.
