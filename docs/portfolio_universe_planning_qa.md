# SigmaTrader – Portfolio Expansion & Universe Planning Q&A

---

## Question

Right now SigmaTrader is centered around my actual holdings. I’d like to evolve it into something closer to a full portfolio lab, but I’m unsure how to order the work and avoid spreading myself too thin.

Some of the ideas on my mind:

- I don’t yet have **watchlist / group / basket** support.  
  - I want to create multiple groups of stocks that have the potential to be portfolios.  
  - For a group, I’d like to add symbols and treat them as an equal‑weight basket by default.  
  - Given a fixed amount of capital, I want to distribute funds equally across the group, or based on target weights, and generate the corresponding orders.

- I’d like a **stock universe** sourced from TradingView and/or screener.in (via Excel/CSV):  
  - Pull a curated set of **fundamental** fields (market cap, ROE, debt/equity, growth, etc.).  
  - Maintain this fundamentals data for at least the **last 3 years**.  
  - Use it for advanced portfolio management, beyond what the current P&L‑centric view can do.

- I also have another app, **Tarkash (tarkash_web)**, which does RAG‑style Q&A.  
  - Perhaps we can use Tarkash’s backend as an AI helper on top of SigmaTrader’s data:  
    - For fundamentals Q&A.  
    - For suggesting screeners or strategies.  
    - For building our own Excel‑like fundamental tables.  
  - I’m not sure how much of this should be in SigmaTrader vs Tarkash.

I feel these ideas are important and potentially life‑changing if executed well, but my thoughts are scattered.  
How should we sequence this work? Which pieces should we tackle first? Where do my ideas make sense, and where should we be careful?

---

## Answer – high‑level guidance and sequencing

### 1. What’s strong in your ideas

Your direction is solid:

- **Groups / baskets / watchlists**  
  - High practical value and relatively low engineering risk.  
  - Turn SigmaTrader from “current holdings only” into a tool for prototyping portfolios and testing ideas before committing capital.  
  - Integrate naturally with things you already have: manual order queue, alerts, correlation clusters, bracket orders, risk sizing.

- **Universe + fundamentals (TV / screener.in)**  
  - Essential for serious portfolio work (factor tilts, quality/value screens, sector exposure).  
  - Heavier lift: requires a clean instrument master, a fundamentals schema, and a reliable ingest/update pipeline.  
  - Best approached incrementally, starting from *manual imports* of CSV/Excel you download yourself.

- **Tarkash / RAG as an assistant**  
  - Very good fit *on top* of structured data:  
    - Explain what the numbers mean.  
    - Help design DSL screeners and strategies in natural language.  
    - Provide “why” answers, not “what” numbers.  
  - Should **not** replace SigmaTrader as the source of truth for metrics; math and storage stay in SigmaTrader, explanation and exploration can live in Tarkash.

### 2. Dependencies and what can be done now

- You can build **Groups/Baskets** *today* using:
  - Existing instruments + holdings.  
  - Existing Buy/Sell dialog, bracket orders, manual queue, alerts, and correlation analytics.  
  - No dependency on fundamentals or Tarkash.

- To build **universe‑wide screeners** or **advanced portfolio reports**, you eventually need:
  - A **universe** table (all traded symbols you care about + metadata).  
  - At least one fundamentals snapshot per date, for key ratios and classification (sector/industry, cap bucket, etc.).

- **Tarkash integration** is most powerful once the above is in place:
  - Tarkash points at your structured data (DB or Parquet snapshots) and answers qualitative questions.  
  - AI can help you *interact* with the system, but should not be responsible for calculation or storage.

### 3. Recommended Phase‑1 path

In Phase‑1 we stay grounded in things that work entirely with your current data plus small, controlled extensions.

1. **Holdings screener (already designed in `stock_screener.md`)**  
   - Upgrade the Advanced Filters into a true screener *for holdings only*:  
     - Visual builder + DSL mode.  
     - Batch actions (apply alerts / create manual orders) for the screened subset.  
   - This is a direct upgrade to your daily workflow and uses indicators and metrics you already compute.

2. **Add Groups/Baskets + basic watchlists (without fundamentals yet)**  
   - Data model:  
     - `groups` table for named baskets / watchlists / model portfolios.  
     - `group_members` table linking `(group_id, symbol, exchange, target_weight)`.  
   - UI:  
     - A Groups page to create/edit groups and assign symbols.  
     - In Holdings, a `Group` column and filter; actions to “invest X equally across this group” using the existing Buy/Sell + manual queue.  
   - Result: you can construct candidate portfolios and allocate capital into them with math‑driven equal‑weight (or custom weight) sizing.

3. **Universe & fundamentals – start narrow and manual**  
   - Instead of building scrapers, start with:  
     - A fundamentals snapshot table.  
     - CSV/Excel imports from screener.in / TradingView that *you* download.  
   - Focus on a small, carefully chosen set of metrics (mcap, sector, ROE, debt/equity, EPS growth, maybe quality/momentum tags).  
   - Wire those metrics into the screener and group views as optional columns and filter keys.

4. **Portfolio analytics v1**  
   - Once groups and basic fundamentals snapshots exist:  
     - Extend the existing correlation & diversification card to support group‑level views.  
     - Add simple exposure summaries (sector/cap buckets, average ROE, etc.).  
   - Keep this purely mathematical and deterministic; defer AI involvement to explanation/insight.

5. **Tarkash / AI integration (Phase‑1 flavour)**  
   - After the above data exists, use Tarkash to:  
     - Answer questions like “Which stocks in Group A have improving ROE and low debt?”  
     - Help draft DSL screeners or alert strategies in natural language and translate them to expressions you paste into SigmaTrader.  
   - This keeps the boundary clean: SigmaTrader holds the numbers; Tarkash helps you understand and act on them.

### 4. Why this order makes sense

- It gives you **immediate trading value** (screener + groups/baskets) without waiting for the larger fundamentals/universe project.  
- Each step is **incremental and testable**:  
  - Screener enhances Holdings.  
  - Groups/baskets add candidate portfolios.  
  - Fundamentals snapshots enrich both without forcing you to solve every ingestion problem at once.  
- It keeps AI in a supportive role, which matches your preference for maths and discipline over “magic profits”.

In short, your instincts are right: these features are important and worth doing. The key is to anchor Phase‑1 around holdings, groups, and a simple universe, then let fundamentals and AI grow on top of that solid base.

