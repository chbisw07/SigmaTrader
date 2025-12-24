# Strategy Saving & Reuse (DSL V3)

This document answers:
1) Can we use the **same DSL expression** across **Screener / Alerts / Dashboard**?
2) Is it feasible to **save** DSL strategies and **reuse** them across those surfaces?
3) What UX/BE design best supports a “strategy register” with **tags/categories** and “where used”.

This is a **design/discussion** note (no implementation).

---

## TL;DR

- **Yes**: the Alerts/Screener already share the **same DSL V3 compiler** and a unified mental model (“Series + Signals”) is explicitly the direction in `docs/DSL_improvement.md`.
- Strategy reuse should be built around a new concept: **Saved Signal Strategy (DSL V3)**, distinct from the existing `Strategy` table (which is currently an *execution/risk template + legacy DSL* concept).
- Saved strategies should be **context-aware** (Screener vs Alerts vs Dashboard) via:
  - evaluation mode (latest-only vs full-series),
  - compatibility checks (market OHLCV-only vs holdings-only metrics).
- Add **tags** + optional **market-regime labels** to make a large strategy library manageable.

---

## 1) Can the same DSL expression be used in Screener / Alerts / Dashboard?

### Short answer
**Yes, with guardrails.**

### Why it’s feasible (current state)
- **Alerts V3 and Screener V3 already reuse the same compiler**: `backend/app/services/screener_v3.py` calls `compile_alert_expression_parts(...)` from `backend/app/services/alerts_v3_compiler.py`.
- The intended direction is explicitly “one unified mental model for Alerts V3, Screener V3, and Dashboard Symbol Explorer” (`docs/DSL_improvement.md`).

### Where “same expression” can break (context differences)
Even if the *syntax* is identical, the *available data* and *expected output* can differ:

1) **Evaluation mode**
- **Screener / Alerts** are “latest-only” (evaluate at bar-close / run-time over a universe).
- **Dashboard** often needs “full-series” to plot overlays/markers.

2) **Data source availability**
- Some operands are universal (OHLCV, indicators).
- Some operands are **contextual** (e.g. holdings-specific metrics like qty, pnl%, invested, etc).
  - These should not silently evaluate to `null`; they should be rejected (or explicitly marked “holdings-only”).

3) **Output semantics**
- Dashboard wants to decide: is the expression a `Series<float>` (plot line) or `Series<bool>` (markers/events)?
- Screener wants a boolean “match” plus optional “variable values” for columns.
- Alerts wants boolean triggers plus optional action routing.

### Recommended rule
Treat every saved strategy as **one of these contracts**:
- **Numeric strategy**: produces one or more `Series<float>` (overlays).
- **Signal strategy**: produces one or more `Series<bool>` (events/markers / triggers).

And every strategy declares its **supported contexts**:
- **Market-only** (OHLCV indicators): usable in all 3 surfaces.
- **Holdings-metrics**: usable only when the target universe provides those metrics (holdings overlays / holdings alerts).

---

## 2) Strategy saving: what problem are we solving?

Today, users repeat the same logic in 3 places:
- Screener: conditions + variables
- Alerts: conditions + variables
- Dashboard: signals/overlays for visual verification

If we store “the idea” once as a Saved Strategy:
- You can **prototype** in Dashboard, then **reuse** in Screener/Alerts.
- Alerts can show “this alert is driven by Strategy X”.
- You can manage strategies at scale using tags (“bullish”, “bearish”, “sideways”, “breakout”, “mean-reversion”, etc.).

---

## 3) Important reality check: we already have a `Strategy` table (but it’s not the right thing)

There is a `Strategy` model in `backend/app/models/trading.py` and a `backend/app/api/strategies.py` API.

However:
- That API compiles `dsl_expression` using the **legacy** parser (`backend/app/services/alert_expression_dsl.py`), not the V3 DSL engine.
- That `Strategy` also contains execution settings (`execution_mode`, `execution_target`, risk settings relationships, etc.).

### Recommendation
Introduce a separate concept for what you want here:
- **Saved Signal Strategy (V3)** = reusable “signal logic” and reusable “overlay variables”.
- Keep “execution strategy” (risk/automation template) as a separate concept, even if we later unify them under a single UX.

This avoids confusion where a “strategy” sometimes means:
- “a reusable signal expression”, vs
- “an execution configuration template”.

---

## 4) Proposed core concept: `SavedSignalStrategy` (DSL V3)

### What a saved strategy stores (conceptual fields)
- `name`, `description`
- `dsl_block` (variables + final expression), or `(variables_json + condition_dsl)` in the same shape Alerts V3 uses
- `compiled_ast_json` (optional cached)
- `kind`:
  - `SIGNAL` (boolean)
  - `OVERLAY` (numeric)
  - or “mixed” (variables for overlays + one boolean trigger)
- `default_cadence` (optional): e.g. `1d` or `1h` (acts as UX default, not a hard requirement)
- `tags[]` (freeform)
- `regime[]` (optional curated set): `BULL`, `SIDEWAYS`, `BEAR` (multi-select)
- `owner_id` and scope (private vs shared templates)
- `created_at`, `updated_at`

### Context compatibility metadata (recommended)
Store a derived compatibility summary computed from the AST:
- Uses only OHLCV? → `market_ok = true`
- Uses holdings metrics? → `holdings_ok = true`
- Uses broker-only concepts? → `broker_ok = true` (most strategies should remain broker-agnostic)

This lets the UI safely filter strategies depending on where the user is applying them.

---

## 5) UX proposal: “Strategies” tab and reuse flow

### A) Alerts page
Add a new tab:
- `Alerts | Indicators | Events | Strategies`

The **Strategies** tab is a “Strategy Register”:
- List with columns: Name, Tags, Regime, Type, Last updated, Used by (count)
- Search and filter by tags/regime/type
- Actions:
  - Create (new)
  - Edit
  - Duplicate (“fork”)
  - Delete (if user-owned)
  - “Show usage” (which alerts/screeners/dashboards reference it)

In **Create Alert**:
- If Target kind is “Single symbol” or “Group” or “Holdings”, show:
  - `Use saved strategy` dropdown (optional)
  - “Edit locally” vs “Link to strategy”
  - If linked, show: `Strategy: <name> (vX)` with “open strategy”

### B) Screener page
Add:
- `Load strategy` dropdown to prefill variables + condition.
- Optionally “Save as strategy” button after a run.

### C) Dashboard / Symbol Explorer
Add:
- `Apply strategy` dropdown:
  - For overlay strategies: automatically select which variables to plot.
  - For signal strategies: show markers; optionally add as a “DSL signal” entry in the UI.

---

## 6) Versioning & change management (this matters once strategies are reused)

If alerts/screeners “link to a strategy”, then updating that strategy can unexpectedly change behavior.

### Recommended default: “pin by version”
- A saved strategy has an incrementing `version`.
- When an Alert uses a strategy, it stores `strategy_id + pinned_version`.
- UI offers:
  - “Update to latest version” (explicit action)
  - “Detach and edit locally”

### Alternative: “always latest”
Pros:
- Simpler DB schema, less UI.
Cons:
- Surprising behavior changes; harder auditability (“why did this alert change?”).

Given SigmaTrader is a trading app, **predictability + auditability** is more important → prefer “pin by version”.

---

## 7) Tags, categories, and market regimes

### Recommended approach
Use two parallel classification systems:
1) **Freeform tags**: user-defined, unlimited (e.g. `breakout`, `volume`, `mean-reversion`, `rsi`, `trend-following`).
2) **Market regime** (optional curated labels): `BULL`, `SIDEWAYS`, `BEAR`.

Why both:
- Tags handle “what it is”.
- Regime handles “when it works”.

UX suggestion:
- Tag chips + autocomplete from your own tag history.
- Optional “Regime” multi-select with 3 labels.

---

## 8) “Same DSL everywhere” — compatibility matrix

| Strategy uses… | Screener | Alerts | Dashboard |
|---|---:|---:|---:|
| OHLCV indicators only | ✅ | ✅ | ✅ |
| Cross events (`CROSSOVER`, etc.) | ✅ (latest-only event) | ✅ (trigger) | ✅ (markers) |
| Holdings metrics (qty, pnl, invested, etc.) | ⚠️ only if screener target is holdings-backed | ✅ if target = holdings/group with holdings metrics | ⚠️ only in holdings overlay contexts |
| Broker/account state | ❌ (avoid) | ⚠️ sometimes needed for execution constraints | ❌ (avoid) |

Recommendation: keep the DSL **market-data-first**; treat holdings/broker data as optional, explicitly gated operands.

---

## 9) “Strategy register” data model vs existing entities (conceptual mapping)

### Existing (today)
- Alerts V3 store:
  - `variables_json`, `condition_dsl`, optional `condition_ast_json` (`backend/app/models/alerts_v3.py`)
- Screener V3 accepts:
  - variables + condition DSL (shared compiler)
- Dashboard has “DSL signals” and overlay indicators (series/markers)

### Proposed (tomorrow)
- Add `SavedSignalStrategy` as a reusable template.
- Add references:
  - `AlertDefinition.strategy_id` (optional) + `strategy_version` (recommended)
  - `ScreenerRun.strategy_id` (optional)
  - Dashboard saved layouts may reference strategies (optional)

We can still keep a **copy** of the compiled expression on each AlertDefinition for resilience (denormalized snapshot):
- Pros: alerts keep running even if strategy is deleted/changed.
- Cons: duplication.

For trading safety, “snapshot on use” is a strong design.

---

## 10) Open questions (worth answering before implementation)

The items below were discussed and/or answered; where marked TBD we still need a decision.

| Topic | Decision / Preference | Recommended behavior in v1 | Notes / Follow-ups |
|---|---|---|---|
| Parameterizable strategies | **YES** | Add a strategy `inputs` schema and per-usage overrides (Alert/Screener/Dashboard) | Keep types simple: `number`, `string`, `enum`, `timeframe`, `bool`; validate at compile time. |
| Multiple outputs | **YES** | Allow multiple outputs, but make outputs explicit: overlays (`Series<float>`) + signals (`Series<bool>`) | Avoid “mystery last expression”: store named outputs and let UI pick which to plot/trigger. |
| “Is plotting only the final expression enough?” | **No (usually)** | Treat the “final expression” as one output among many | Users benefit from plotting key intermediate overlays + the signal markers; full-series evaluation stays single-symbol. |
| Dashboard plotting: line vs markers | **Should be type-based** | Numeric series ⇒ line/overlay; boolean series ⇒ markers; event helpers ⇒ event markers | Current behavior (DSL = dots/markers) should evolve to plot numeric DSL as a curve. |
| Sharing model | **Export/Import desired** | Support export/import of strategies (JSON) and optional “global templates” | Global templates can be curated read-only packs; consider signature/version metadata. |
| Naming collisions on merge | **Warn + ask user** | When merging into an existing alert: detect clashes and prompt user to rename conflicting vars or auto-rename | Default flow can be “replace” to avoid surprises; “merge” is advanced. |
| Strategy vs Execution Template | **TBD** | Keep separate surfaces in v1 (Signal Strategies vs Execution Templates) | Can unify later as 2 sections under “Strategies” once model stabilizes. |

### Remaining open questions
1) Parameter overrides in UI: should we support a “quick override” panel (recommended) vs forcing edits in a “usage editor” page?
2) Multiple outputs: should we allow one strategy to define *multiple signals* (e.g., entry + exit + risk-off), or keep exactly one signal output per strategy in v1?
3) Sharing: do you want a “public gallery” / curated global packs, or only file-based import/export for v1?
4) Versioning: do you want “edit in place when unused” (reduce noise) vs “always versioned” (max rollback/audit)?

---

## 11) Proposed phased rollout (pragmatic)

**Phase 1 (MVP)**
- Save/load DSL V3 strategies (variables + condition).
- Apply to Screener and Alerts.
- Tags + regime labels.
- “Used by” counts (basic).

**Phase 2**
- Dashboard integration: apply strategy overlays and markers.
- Strategy versioning + pinning.

**Phase 3**
- Parameterized strategies (inputs), export/import, sharing.

---

## Direct answer to your idea

Your “dedicated strategy tab + strategy register + tags/categories” is **feasible and aligned** with the core direction of SigmaTrader:
- It increases reuse and reduces duplication.
- It improves trust because strategies can be inspected in the dashboard.
- It scales the “soul of the app” (strategy experimentation) without turning the UI into a mess, as long as we keep:
  - a clean separation between **signal strategies** and **execution templates**, and
  - explicit context compatibility rules.
