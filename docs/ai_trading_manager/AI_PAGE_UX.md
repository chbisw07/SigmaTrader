# AI Trading Manager Page (`/ai`)

SigmaTrader now has a dedicated **AI Trading Manager** page with a ChatGPT‑style layout.

## Route + Navigation

- Left nav: **AI Trading Manager**
- Route: `/ai`
- Settings remain in **Settings → AI** (`/settings?tab=ai`)

The `/ai` page is the primary AI UX.

## UI Layout

- **Conversation (top):** scrollable, full height, messages grouped by role.
- **Composer (bottom):** sticky/pinned with:
  - multiline input (`Shift+Enter` newline, `Enter` to send)
  - send + stop (cancel) button
  - drag‑and‑drop file upload for `.csv` / `.xlsx`
  - attachment chips with remove action
- **Assistant messages:** rendered as **Markdown** (GFM), including real HTML tables.
- **Per message trace:** expandable **Tool calls & DecisionTrace** section with:
  - tool call list
  - RiskGate / TradePlan / Execution summaries (when present)
  - link to the full DecisionTrace viewer

## Attachments (CSV/XLSX)

### Upload API

- `POST /api/ai/files` (multipart form: `files[]`)
- Response includes per‑file metadata + a lightweight **summary**:
  - CSV: `columns`, `row_count`, `preview_rows` (first 5)
  - XLSX: `sheets`, `active_sheet`, `columns`, `row_count`, `preview_rows` (first 5)

Limits:
- Max file size defaults to 15MB (override: `ST_AI_FILE_MAX_BYTES`)
- Upload directory defaults to `backend/data/ai_uploads` (override: `ST_AI_FILE_UPLOAD_DIR`)
- Allowed extensions: `.csv`, `.xlsx`

### Chat behavior (LLM safety)

Files are stored server‑side and **never sent in full** to any remote LLM by default.

When an attachment is included in a chat:
- SigmaTrader injects only **attachment summaries** into the LLM prompt.
- If **“Do not send PII”** is enabled (Settings → AI), the LLM receives **schema‑only** summary (columns, row count, sheet names), and `preview_rows` is omitted.
- If **“Do not send PII”** is disabled, the LLM also receives `preview_rows` (first 5 rows) as part of the summary.

## How to Test Locally

1) Start SigmaTrader backend + frontend as usual.
2) Log in to the web UI.
3) Go to `/ai`.
4) Drag a small CSV (example):
   - `symbol,pnl`
   - `ABC,10`
5) Confirm an attachment chip appears in the composer.
6) Send a prompt like: `What columns are in the attached file?`
7) Expand **Tool calls & DecisionTrace** and confirm:
   - tool calls are listed (if any)
   - `inputs_used.attachments` shows the uploaded `file_id` + metadata

## Notes

- Attachments are access‑controlled: only the uploading user can fetch meta/download.
- The current “attachments to LLM” path is intentionally conservative; future phases can add deterministic server‑side tools for computing aggregates over full file contents without sending raw data to remote models.
