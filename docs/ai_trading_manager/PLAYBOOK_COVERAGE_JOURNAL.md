# Playbook + Coverage + Journal (Phase: cautious / default-off)

This document describes the **coverage**, **position playbooks**, and **journal** features for the AI Trading Manager subsystem.

## Core guarantees

- **RiskGate is supreme**: playbooks cannot override RiskGate. If RiskGate denies, execution is vetoed.
- **Default behavior is unchanged**: a playbook is **passive unless explicitly enabled** (`AI Managed = OFF` by default).
- **Exits reduce risk**: playbooks must not hard-block `REDUCE/EXIT` intents except invalid quantity/product/short-creation cases.
- **Remote LLM safety**: remote providers never receive raw broker payloads. (Operator vs LLM view split.)

## Concepts

### Coverage (unmanaged detector)

Coverage scans the latest stored broker snapshot(s) and maintains a local table of **shadow positions**:

- A **shadow position** represents an open broker-truth holding/position the system sees.
- If it has **no enabled playbook attached**, it is surfaced as **UNMANAGED**.

Coverage runs:

- after **Kite MCP snapshot fetch**
- after **reconcile**
- best-effort at **login** (from latest stored snapshot)
- periodically when monitoring is enabled (every ~15 minutes)

### Manage playbooks (position management)

Manage playbooks are attached by scope:

1. `POSITION` (highest priority)
2. `SYMBOL`
3. `PORTFOLIO_DEFAULT`

Each playbook has:

- `enabled` (AI Managed)
- `mode`: `OBSERVE` / `PROPOSE` / `EXECUTE` (conservative: proposals first)
- `review_cadence_min`
- versioned JSON policies: `exit_policy`, `scale_policy`
- `behavior_on_strategy_exit` (TV exits)

### Journal (notes + audit-lite learning)

The journal stores:

- `journal_event`: timeline of `ENTRY/ADD/REDUCE/EXIT/STOP_* / REVIEW` events (from coverage discovery + playbook reviews + execution pipeline)
- `journal_forecast`: optional outlook capture (user or AI)
- `journal_postmortem`: best-effort metrics on close (realized PnL, MFE/MAE, etc.)

## Precedence / intent pipeline (high-level)

For AI-driven execution (`/api/ai/chat → execute_trade_plan`), the intended ordering is:

1. **Intent** created (AI/internal)
2. **Playbook pre-trade** evaluation (passive unless enabled)
3. **RiskGate** deterministic evaluation (non-overridable)
4. **ExecutionEngine** (idempotent)
5. **Reconcile + snapshot**
6. **Coverage** sync (shadow positions)
7. **Journal** append + postmortem on close

Existing non-AI order flows are not modified by default.

## UI surfaces

- **Holdings / Positions**: shows an `Unmanaged: N` badge (click → `/ai?tab=coverage`).
- **AI Trading Manager → Coverage**: list open shadows, attach playbook templates, enable/disable, edit JSON.
- **AI Trading Manager → Journal**: select a shadow, view events, add forecast, view postmortem.

## How to test (manual)

1. Ensure AI is enabled in Settings → AI (assistant enabled).
2. Fetch a broker snapshot via Settings → AI → Kite MCP → **Fetch snapshot**.
3. Open `/ai?tab=coverage`:
   - Verify you see open items.
   - Verify UNMANAGED count matches the badge in Holdings/Positions.
4. Attach a playbook to an unmanaged row:
   - Template: `Swing CNC (ATR + ladder)` (default).
   - Verify row now shows a playbook and can be enabled/disabled.
5. Enable monitoring in Settings → AI and wait ~1–2 minutes:
   - Open `/ai?tab=journal` and select a managed position.
   - Verify `REVIEW` events appear on cadence (mode-dependent proposals).
6. Close a position outside ST (or via existing flows), fetch snapshot again, then:
   - Coverage should mark it closed.
   - Journal should show an `EXIT` event and (best-effort) a postmortem.

## Extending safely

- Add new playbook rule types by extending the deterministic engines:
  - `backend/app/services/ai_trading_manager/manage_playbook_engine.py` (pre-trade)
  - `backend/app/services/ai_trading_manager/manage_playbook_reviews.py` (review proposals)
- Keep all execution gated by feature flags and RiskGate.
- Do not rely on the remote LLM for any deterministic enforcement.

