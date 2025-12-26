# SigmaTrader Website Plan (Full Product)

This document is the complete plan for a product website for SigmaTrader (aka “SmartTrader” in some notes). It is intentionally **content-first** and **documentation-driven**, because SigmaTrader is a power tool: the website must explain concepts, not just show screenshots.

This plan is based on the current repository documentation and implemented surfaces, including (non-exhaustive):
- Holdings/Universe refactor direction (`docs/holdings_refactoring.md`, `docs/groups_and_universe_design.md`)
- Screener + DSL V3 (`docs/stock_screener.md`, `docs/DSL_improvement.md`, `docs/strategy_saving.md`)
- Alerts (design + v3 direction) (`docs/alert_system_design.md`, `docs/alerts_refactor_v3.md`)
- Trading workflow (webhook → queue → execution) (`docs/tvapp_prd.md`, `docs/sigma_trader_impl_report.md`)
- Multi-broker direction (`docs/angelone_support_prework.md`)
- Portfolio rebalancing (target weights, rotation, risk parity) (`docs/portfolio_rebalancing.md`, `docs/rebalance_dialog_help.md`)

You asked me to “scan the docs folder” and not build around rebalancing only. This plan treats rebalancing as one pillar among several.

This file contains **no code**.

---

## 0) Decisions captured (from you)

These choices are now fixed in this plan unless you change them later:
- **Public name**: SigmaTrader
- **Hosting**: local for now
- **Screenshots**: real screenshots from your portfolio are allowed
- **Logo**: `frontend/public/sigma_trader_logo.png`

Open decision (still needed):
- **Primary CTA** on the website: recommended default is **“Run locally”** (since hosting is local), but confirm if you prefer **“Read docs”** as the primary action.

## 1) What the website must accomplish

### 1.1 The “job to be done”
SigmaTrader is a personal trading + portfolio operating system. A good website should:
- Explain the mental model (Universe → Screener/Alerts → Orders → Execution → Analytics).
- Present the main modules and their benefits.
- Build trust with transparency (safety guardrails, auditability, privacy posture).
- Provide a help center that reduces misuse (especially for DSL and rebalancing).

### 1.2 Outcomes (success metrics)
For a personal/self-host tool, success is not “leads”; it is:
- Visitors understand what SigmaTrader is in 30 seconds.
- Visitors can self-serve answers (docs/help).
- You can share the website link with confidence when someone asks “what is SigmaTrader?”.

---

## 2) Positioning and messaging

### 2.1 One-line positioning (recommended)
**SigmaTrader helps you run a disciplined investing/trading workflow with explainable signals, safe execution, and portfolio-level controls.**

### 2.2 Product pillars (site will be organized around these)
1) **Unified Universe Viewer**
   - One rich grid that can show holdings, watchlists, baskets, portfolios, and holdings-views.
2) **Screener + DSL (V3)**
   - Find symbols with a deterministic, indicator-first DSL and saved strategies.
3) **Alerts**
   - Monitor symbols/universes with explainable conditions and an audit trail (and optional actions).
4) **Execution & Automation**
   - TradingView webhook ingest, manual queue, risk checks, broker execution.
5) **Portfolio Rebalancing**
   - Target weights, signal-driven rotation, and risk parity with previews and guardrails.
6) **Multi-broker**
   - Broker-aware holdings/positions/orders, broker-bound execution, broker-agnostic universes.
7) **Analytics & Dashboard**
   - Basket indices, symbol explorer, and “explainability-first” signal visualization.

### 2.3 Tone
- Practical, calm, “engineer’s clarity”.
- Avoid hype. Prefer “Here is the workflow” + “Here is how it protects you from mistakes”.

---

## 3) Site map (pages) — “typical product site”, but for a power tool

### Core pages
1) `/` — Landing
2) `/product` — Full product overview (pillars + workflow)
3) `/platform` — Architecture, privacy, safety, data model (build trust)
4) `/features/universe` — Unified holdings + portfolio viewer
5) `/features/screener` — Screener + DSL V3 + saved signal strategies
6) `/features/alerts` — Alerts system (universe monitoring + explainability)
7) `/features/execution` — Webhook → queue → execution + risk management
8) `/features/rebalance` — Target weights + signal rotation + risk parity
9) `/features/brokers` — Multi-broker story and capability model
10) `/dashboard` — Basket indices + symbol explorer (explainability)
11) `/docs` — Docs hub
12) `/faq` — FAQ + troubleshooting (searchable)
13) `/changelog` — What changed recently (build trust + momentum)
14) `/about` — Why you built it + philosophy

### Optional later
- `/use-cases` (or `/solutions`)
  - “Long-term investor allocation discipline”
  - “Swing trading workflow with alerts + queue”
  - “Rotation strategy portfolio”

---

## 4) Landing page (`/`) — exact section plan

### 4.1 Hero
Goal: make SigmaTrader understandable immediately.

Suggested headline options:
1) “A disciplined workflow for trading and portfolio management.”
2) “Signals you can explain. Trades you can control.”
3) “From ideas to execution: screener → alerts → queue → broker.”

Hero bullets (choose 3–5):
- Unified holdings + portfolio viewer across universes
- Screener + saved DSL strategies (deterministic, reusable)
- Alerts over universes with audit trail (“why did it fire?”)
- Manual queue and risk guardrails before execution
- Portfolio rebalancing: target weights, rotation, risk parity
- Multi-broker (broker-aware execution, broker-agnostic groups)

CTAs (pick one primary):
- **Run locally** (primary recommended for your current setup)
- Read the docs (secondary)

### 4.2 “How it works” (the loop)
A simple 4-step flow that matches your system:
1) Build universes (holdings/groups/portfolios)
2) Screen & define signals (DSL strategies)
3) Monitor and trigger (alerts)
4) Execute safely (queue + risk + broker)

### 4.3 Modules (feature tiles)
Each tile links to a feature page and includes:
- 1 sentence benefit
- 1 screenshot (or small crop)
- “Learn more”

Tiles:
- Universe Viewer
- Screener
- Alerts
- Execution & Queue
- Portfolio Rebalance
- Multi-broker
- Dashboard & Analytics

### 4.4 Proof and trust (for a trading tool)
Sections:
- Explainability: “Every decision has a reason and a snapshot.”
- Guardrails: budgets, bands, risk settings, idempotency.
- Local-first: “You run it; your broker tokens stay in your environment.”
- Auditability: history for alerts/runs/orders.

### 4.5 Product tour (screenshots)
Keep it short on the landing page: 5–7 slides with captions.
Full galleries live on feature pages.

### 4.6 FAQ (top 8)
Examples:
- Is this investment advice? (No)
- Can it execute automatically? (Yes, with risk settings)
- What brokers are supported? (Zerodha today; AngelOne planned; broker-aware architecture)
- What is the DSL? Is it safe? (deterministic, no arbitrary code)
- Does it require cloud? (No; local-first)

---

## 5) Feature pages — what each must explain + show

Each feature page follows the same structure:
1) What problem it solves
2) The mental model
3) Key capabilities (bullets)
4) Screenshots with labeled callouts
5) Example workflows
6) “Common mistakes” + “best defaults”
7) Links to docs

### 5.1 `/features/universe` — Unified holdings and portfolio viewer
Based on: `docs/holdings_refactoring.md`, `docs/groups_and_universe_design.md`.

Must cover:
- What “Universe” means (holdings, watchlist, basket, portfolio, holdings-view).
- One grid experience with overlays (holdings overlay, group metadata, portfolio target weights).
- Bulk actions: buy/sell, create group from selection, alert actions, export.

Screenshots:
- Holdings page with Universe dropdown
- Groups page (list + members)
- Example of same grid across different universes

### 5.2 `/features/screener` — Screener + DSL V3 + saved strategies
Based on: `docs/stock_screener.md`, `docs/strategy_saving.md`, `docs/select_winning_stocks.md`.

Must cover:
- Targets: holdings + groups as universe union (deduped)
- Variables + condition DSL
- Run → results → create group from results
- Saved signal strategies and reuse (screener/alerts/dashboard)

Screenshots:
- Screener page: target selection, DSL editor, results grid
- Create group from run

### 5.3 `/features/alerts` — Alerts over universes + explainability
Based on: `docs/alerts_refactor_v3.md`, `docs/alert_system_design.md`.

Must cover:
- Universe-scoped alerts (one alert runs over many symbols)
- Variables + condition builder
- Trigger modes and audit events
- Optional “actions” (alert-only vs order intent templates) — even if some parts are future, the concept matters

Screenshots:
- Alerts list
- Alert create wizard (target, variables, condition)
- Events/audit screen (why triggered)

### 5.4 `/features/execution` — Webhook → queue → broker execution + risk
Based on: `docs/tvapp_prd.md`, `docs/custom_bracket_orders.md`, `docs/sigma_trader_impl_report.md`.

Must cover:
- TradingView webhook ingestion (secure secret)
- Manual queue: review/edit/execute
- Auto mode vs manual mode
- Risk management: max order value, max qty, short selling policy, clamp vs reject
- Optional bracket + GTT workflow (profit target / re-entry)

Screenshots:
- Queue page (waiting orders)
- Order details + errors
- Risk settings UI
- Bracket order controls (if present in UI)

### 5.5 `/features/rebalance` — Portfolio rebalancing (technical)
Based on: `docs/portfolio_rebalancing.md`, `docs/rebalance_dialog_help.md`.

Must cover:
- Three methods:
  1) Target weights
  2) Signal rotation (top‑N)
  3) Risk parity (equal risk contribution)
- Preview explainability (drift, target, live weight)
- Safety controls (budget, drift bands, max trades, min trade value)
- Scheduling + history

Screenshots:
- Rebalance dialog tabs (Preview/History/Schedule)
- Signal rotation controls
- Risk parity controls
- Derived targets table (audit)

### 5.6 `/features/brokers` — Multi-broker design (Indian context)
Based on: `docs/angelone_support_prework.md`.

Must cover:
- Broker-aware vs broker-agnostic concepts:
  - holdings/positions/orders are broker-scoped
  - groups/universes are broker-agnostic
  - execution is always broker-bound
- UI approach: broker selector/tabs
- Capability model (GTT support, previews, margins)
- How you avoid “both brokers confusion” by design

Screenshots:
- Settings broker connections
- Holdings universe dropdown showing broker-specific holdings
- Any broker selector UI in dialogs (rebalance broker, etc.)

### 5.7 `/dashboard` — Dashboard + analytics
Based on: `docs/dashboard.md`.

Must cover:
- Basket indices (base 100) for holdings and groups
- Symbol explorer for explainability
- “Hydrate missing data” concept (local-first compute, optional fetch)
- Reuse of DSL strategies for overlays and signals

Screenshots:
- Basket index chart
- Symbol explorer panel with overlays/signals

---

## 6) Platform page (`/platform`) — build trust

This page answers: “Is this safe, deterministic, and explainable?”

Sections:
- Local-first architecture: where data lives, what is stored, and why
- Broker secrets handling (at-rest encryption, user-controlled environment)
- Deterministic DSL: safe subset, no arbitrary code execution
- Audit trail: orders, runs, alerts events
- Limitations and roadmap honesty (what exists vs planned)

---

## 7) Docs + Help center (`/docs`, `/faq`)

### 7.1 Docs hub structure (recommended)
Docs should mirror the mental model:
1) Getting started
2) Core concepts (Universe, groups, overlays)
3) Screener + DSL
4) Alerts
5) Execution + queue + risk
6) Rebalancing
7) Multi-broker
8) Troubleshooting

### 7.2 Website help search
Phase 1 (recommended):
- A simple client-side search over markdown headings and content.
- “Top questions” curated list.

Phase 2 (optional):
- A help “assistant” that only searches your docs content (no external services unless you choose).

---

## 8) Screenshot and asset plan (full product, not only rebalance)

You explicitly allowed taking and using screenshots. We will still apply a “privacy-safe” policy.

### 8.1 Privacy-safe screenshot policy (recommended)
Given you approved real screenshots, we’ll follow this safety approach:
- Prefer **cropping** to focus on the feature area (reduces personal/account leakage).
- Where cropping isn’t enough, apply **blur/redaction** for:
  - funds, quantities, P&L values
  - any account identifiers
  - any personal names shown in the UI header

This keeps screenshots “real” while still safe to share if you ever host the site publicly later.

### 8.2 Screenshot inventory (proposed)
Landing/product tour:
- Holdings page (Universe: Holdings (Zerodha))
- Groups page (watchlist/portfolio)
- Screener page (targets + results)
- Alerts page (list + create)
- Queue page (manual orders)
- Rebalance dialog (preview)
- Dashboard (basket index)
- Settings (broker connections)

Feature page deep shots:
- Rebalance: signal rotation + risk parity derived targets
- DSL: variables editor + expression examples
- Alerts events/audit
- Risk settings and clamp/reject behavior
- Bracket order UI (if used)

### 8.3 Asset folder convention
- `docs/website/assets/screenshots/`
- `docs/website/assets/diagrams/` (workflow diagrams)

### 8.4 Logo usage
Use `frontend/public/sigma_trader_logo.png` as the site logo.
If we later host the website as a separate frontend, we will copy or reference the same asset to keep branding consistent.

---

## 9) Content production plan (how we write it without getting stuck)

### 9.1 Copy strategy
For each module, write:
- “What you can do”
- “Why it matters”
- “How it works”
- “Common mistakes”
- “Best starting defaults”

### 9.2 Examples (critical for power tools)
Include examples with realistic numbers:
- Screener DSL examples (like in `docs/select_winning_stocks.md`)
- Alert condition examples
- Rebalance examples (budget/bands/top‑N/risk parity)
- Queue examples (manual vs auto, clamp vs reject)

---

## 10) Implementation plan (phased, low-risk)

### Phase 0 — Decisions
Confirm:
- Brand name shown on website (SigmaTrader vs SmartTrader)
- Primary CTA (Run locally / Request access / Waitlist)
- Screenshot privacy approach

### Phase 1 — Core site skeleton + landing
- Navigation and footer
- Landing page + product tour
- Product overview page

### Phase 2 — Feature pages (pillars)
- Universe, Screener, Alerts, Execution, Rebalance, Brokers, Dashboard

### Phase 3 — Docs + FAQ + Changelog
- Markdown-driven docs hub
- Searchable FAQ

### Phase 4 — Polish
- Mobile responsiveness, SEO tags, image optimization, performance budget

---

## 11) Inputs needed from you (to finalize the website direction)

Remaining input:
1) Confirm the **primary CTA**: **Run locally** (recommended) vs **Read docs**.

---

## 12) Note about “docs/sprint_plans_codex.xlsx”

You referenced `docs/sprint_plans_codex.xlsx`, but it does not currently exist in the repo.

Closest “plans” sources present today:
- `docs/tvapp_sprint_plan.md`
- `docs/sprint_tasks_codex.xlsx`

If you add `docs/sprint_plans_codex.xlsx` later, we can incorporate it as an explicit “roadmap” section and render a public roadmap page.
- `rebalance-help.png`
- `rebalance-history.png`

---

## 7) Copywriting plan (what the site will actually say)

### Hero headline options (pick one later)
1) “Rebalance with discipline. Rotate with signals. Control risk.”
2) “A personal portfolio operating system for Indian markets.”
3) “Turn portfolio decisions into a repeatable process.”

### Supporting bullets (example)
- Explainable trade previews before execution
- Budget + drift guardrails to avoid churn
- Signal-driven top‑N rotation
- Risk parity targets (equal risk contribution)
- Scheduling + history for auditability

### “How it works” (simple)
1) Choose scope and method
2) Preview trades and derived targets
3) Create queued orders (or execute automatically)

### Trust section content
- “Not investment advice”
- “You control execution”
- “Your broker integration stays in your environment”

---

## 8) Help center plan (website-side)

### Phase 1 (recommended)
Static help center:
- Use your existing Markdown docs (including `docs/rebalance_dialog_help.md`)
- Add a small search over headings + content
- “Common questions” page (`/faq`)

### Phase 2 (optional)
Interactive assistant:
- A “Search docs” UX that suggests matching sections
- A chat experience only if you decide to use an LLM (requires policy decisions and possibly external services)

---

## 9) Implementation approach (high-level, maintainable)

### Architecture
- A separate “website frontend” that can be deployed independently from the app UI.
- Content-first: Markdown pages + screenshot assets.

Recommended stack (because you already use it):
- React + TypeScript + Vite
- Material UI (or a lightweight CSS system if you prefer)

### Content pipeline
- Website pages can be:
  - React pages for layout-heavy screens (Landing, Product)
  - Markdown for docs pages (Docs hub, Rebalance explainers, FAQ, Changelog)

### SEO basics
Include:
- Descriptive titles per page
- meta description
- OpenGraph tags
- sitemap

### Performance basics
- Use compressed images (webp if possible)
- Lazy-load screenshot sections

---

## 10) Deliverables (what you will get)

### Deliverable A: Complete website structure
- All core pages listed in section 3
- Navigation + footer
- Consistent design system

### Deliverable B: Landing page ready for sharing
- Clear CTAs
- Feature sections
- Screenshot tour

### Deliverable C: Documentation + help center
- Docs hub
- Rebalancing deep dive
- FAQ
- Changelog

### Deliverable D: Screenshot asset pack
- Labeled screenshots organized in the repo

---

## 11) Milestones (practical sequence)

1) Confirm brand + CTA (section 4)
2) Landing page (copy + layout + 3–4 screenshots)
3) Product page + Rebalancing page
4) Docs hub + FAQ + Changelog
5) Polish pass (mobile, SEO, performance)

---

## 12) Inputs I still need from you (to finalize copy and CTAs)

Answer these and I’ll lock the site direction:
1) Public name: **SigmaTrader** or **SmartTrader**?
2) Primary CTA: Run locally / Request access / Waitlist?
3) Are you okay with real screenshots from your portfolio, or should we anonymize / use demo data?
4) Any logo/mark available? If not, should I create a simple text logo treatment?
5) Hosting: will you deploy publicly (Netlify/Vercel/your server), or keep it local for now?

---

## 13) Notes on “commercial readiness”

Even if you’re building for yourself now, the website can be “commercial-ready” without changing the product:
- show a clear value proposition
- show trust and disclaimers
- show a roadmap and changelog
- keep docs strong

This will make it easy to commercialize later if you choose.
