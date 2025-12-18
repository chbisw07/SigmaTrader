# SigmaTrader — Dashboard (Basket Indices + Symbol Explorer)

This document captures the **current Dashboard direction** and a **detailed implementation plan** for the next big UX step:

- Left panel: **Basket indices** (holdings + groups, equal‑weight, base 100).
- Right panel: **Symbol Explorer** (chart + performance + indicators + DSL signals).

The plan deliberately reuses **Alerts V3 DSL / variables / indicator definitions** so SigmaTrader stays conceptually consistent across:
Alerts → Screener → Dashboard.

---

## 0) Principles and guardrails

### 0.1 Product principles

- **Explainability first**: the Dashboard should help answer: “Why did this match?” and “What does the signal look like over time?”
- **Single mental model**: same DSL + variables system across Alerts and Screener and Dashboard.
- **Progressive complexity**: ship a useful v1 without becoming a full TradingView clone.

### 0.2 Charting library (commercial + branding safety)

We use **TradingView Lightweight Charts** as a *technical library* only, following strict rules:

- ❌ Do NOT embed TradingView widgets
- ❌ Do NOT copy TradingView UI pixel‑by‑pixel
- ❌ Do NOT use TradingView logos or trademarks
- ❌ Do NOT imply any affiliation with TradingView

Implementation detail:
- SigmaTrader UI should use its own layout, typography, spacing, and theming.
- Any mention of the library should be limited to `NOTICE` / third‑party attribution files, not the UI.

---

## 1) Current state (already in SigmaTrader)

The Dashboard currently includes **Basket indices (base 100)** computed from daily candles already present in the local DB.

- Universe selection: Holdings (optional) + one or more groups (deduped by `symbol+exchange`).
- Range: up to **2 years** (consistent with typical broker historical constraints).
- Output:
  - index series (base 100)
  - hover tooltip values
  - **coverage**: how many symbols contributed each day (`used/total`)
  - series labels using **actual group name**

Important note:
- Current basket indices computation is **local‑DB only** (“no fetch”) and may show incomplete coverage if candles are missing.

Confirmed:
- The daily candle source + DB storage used here is the **same** one used by Alerts V3 / Screener V3 computations.

---

## 2) Updated requirement: “If not local, fetch it”

### 2.1 User expectation

Current universe is ~110 symbols and their daily data exists locally, but the expected behavior going forward:

> If candle data is not available locally, SigmaTrader should fetch it and persist it so that eventually the full universe history is available locally.

### 2.2 Why this needs a careful design

Fetching “on demand” inside a user request can cause:
- slow UI (blocking fetches),
- burst load to upstream providers,
- unreliable behavior when the universe grows (500 → 2000).

So we split this into two related but separable responsibilities:

1) **Compute** (fast, deterministic): calculate indices/signals using whatever candles exist locally.
2) **Hydrate** (best effort, throttled): fetch missing candles into local DB in the background, then rerun compute for improved coverage.

### 2.3 Hydration policy (recommended)

Hydration is split into “small gaps” vs “big gaps”:

- **Small gaps (recent freshness)**: auto‑hydrate silently.
  - Definition: missing candles in the last **30–60 days** (typically the “tail” near today).
  - Behavior: fetch + persist automatically (fast path) so the dashboard stays fresh.

- **Big gaps (history backfill)**: do not auto‑fetch; show a banner + user action.
  - Definition: missing a large portion of the requested window (weeks/months/years).
  - Behavior: show a banner such as:
    - “Missing history. Hydrate now”
    - with a “Hydrate” button and clear expected time/impact.

This keeps the UX snappy while still allowing the system to converge toward “everything local”.

---

## 3) Dashboard UX: the 50/50 layout

### 3.1 Layout

- Make Dashboard a **resizable split view**:
  - Default: 50% (left) / 50% (right)
  - User can drag to resize.
  - On small screens: stack vertically.

### 3.2 Left panel: Basket indices (existing)

Keep as is, with a small UX upgrade:
- Add optional “Hydrate missing data” indicator if coverage is incomplete.
- Clicking on a series (Holdings or a group) can optionally “focus” related symbols for the right panel.

### 3.3 Right panel: Symbol Explorer (new)

Goal: provide “drill‑down / explainability” for symbols in the selected universe.

**Controls**
- Symbol picker (from deduped Universe).
- Range selector: `1W, 1M, 3M, 6M, 1Y, 2Y`.
- Timeframe: v1 fixed to `1D` (expand later only when intraday candles exist locally).

**Performance strip**
- Show: Today, 5D, 1M, 3M, 6M, 1Y, 2Y (bounded by available candles).

**Chart**
- Support **both** line and candlestick.
- Default to **line chart** (close) for clarity and speed.
- Offer a chart‑type toggle (Line / Candles).
- Crosshair tooltip shows OHLC (if candle) + indicator values at cursor time.

**Indicators / overlays**
- Reuse the existing Alerts/Screener “Variables” builder UI.
- For each variable:
  - Plotting choice: overlay (price axis) or separate pane (e.g. RSI).
  - Visible toggle (so the panel doesn’t get cluttered).

**DSL signals**
- Monaco editor (same as Alerts/Screener).
- Run button evaluates the DSL historically across the visible range.
- Visualization:
  - boolean expression ⇒ markers (or highlight bands) where true.
  - cross conditions ⇒ markers at cross points.

Recommended helper functions in DSL:
- `CROSSOVER(a, b)`
- `CROSSUNDER(a, b)`

These avoid ambiguous user expressions and make signal visualization reliable.

---

## 4) Backend plan (APIs and computation model)

### 4.1 Basket indices (already exists)

- `POST /api/analytics/basket-indices`
  - Inputs: holdings/group IDs, range, base
  - Outputs: per-series points + coverage + missing symbols list

Planned enhancement:
- Add an optional `hydrate_missing: boolean` (or a separate endpoint) to trigger background fetches for missing symbols.

### 4.2 Symbol Explorer: candles endpoint

Add:
- `POST /api/analytics/symbol-series`
  - Input:
    - `symbol`, `exchange`
    - `range` (`1w..2y`)
    - `timeframe` (v1: `1d`)
    - `hydrate_missing` (default `true` for Symbol Explorer)
  - Output:
    - time‑aligned OHLCV series (daily)
    - coverage metadata (first/last candle, missing count)

### 4.3 Symbol Explorer: indicator values

Option A (recommended): return indicators in the same call as `symbol-series`.
- Input includes `variables` in the same format used by Alerts/Screener.
- Output adds `variable_series: { [varName]: (number|null)[] }`.

Option B: separate endpoint `POST /api/analytics/symbol-indicators`.

### 4.4 Symbol Explorer: historical DSL evaluation

Add:
- `POST /api/analytics/symbol-signals`
  - Input:
    - `symbol`, `exchange`, `range`, `timeframe`
    - `variables`
    - `dsl_expression`
  - Output:
    - `boolean[]` aligned to candles **or**
    - `markers[]` for cross events (`time`, `kind`, `label`, `color`)

Implementation approach:
- Reuse Alerts V3 parser/compiler.
- Evaluate **per bar across history** (distinct from “evaluate now” alerts).
- Cache intermediate arrays to avoid recomputing indicators for every DSL run.

---

## 5) Performance + scalability plan

Even though the current universe is ~110 symbols, we design for the realistic future: **1000–2000** symbols.

### 5.1 Non-blocking strategy

- Basket indices:
  - compute fast from local DB,
  - hydrate missing in background,
  - let user refresh.

- Symbol Explorer:
  - synchronous fetch is acceptable (single symbol),
  - cache candles and computed indicator arrays per session.

### 5.2 Caching strategy

- Cache candles in memory per `(symbol, exchange, range, timeframe)`.
- Cache computed indicator arrays per `(symbol, exchange, timeframe, variable_signature)`.
- DSL runs reuse cached arrays; only re-evaluate expression.

### 5.3 Hydration throttling

Hydration should be:
- rate-limited,
- concurrency-limited,
- deduped (don’t refetch the same `(symbol, exchange, range)` repeatedly).

---

## 6) Implementation phases (recommended)

### Phase 1 — Symbol Explorer v1 (highest ROI)
- Add right panel + symbol picker + range + timeframe (1D).
- Render chart (line or candle).
- Performance strip.
- Fetch missing candles for the symbol and persist to DB.

### Phase 2 — Indicators overlays
- Reuse Variables UI for chart overlays.
- Plot SMA/EMA/BOLL as overlays; RSI in a second pane.

### Phase 3 — DSL signals over history
- Add `CROSSOVER/CROSSUNDER`.
- Evaluate DSL per-bar across the visible window.
- Render markers/highlights.

### Phase 4 — Hydration improvements for baskets
- Background hydration job for missing symbols in basket indices.
- Clear progress messaging + refresh controls.

---

## 7) Open questions (to resolve before coding)

Resolved:
1) **Candles source / storage contract**: confirmed same storage as Alerts V3 / Screener V3.
2) **Hydration trigger**: auto‑hydrate small (30–60 day) gaps; for big gaps show “Hydrate now”.
3) **Chart**: support both; default to line.
