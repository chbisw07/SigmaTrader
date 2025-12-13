# Portfolio Improvement Suggestions – Design Q&A

---

## 1. How can I stabilise my current portfolio and build a “profit‑making machinery” using SigmaTrader?

**Question**  
Right now many of my holdings are in loss (some deep, e.g. −40%). For some of them I still have conviction that they will appreciate again; for others I’m thinking of rotating funds and exiting slowly. My new tools (drawdown, Today P&L%, ATR, volatility, correlations, risk sizing, alerts, custom brackets) feel powerful for fresh trades, but my existing portfolio is messy. I don’t believe in magic profits; I believe in mathematics and discipline. How can I use what we’ve built to (a) stop the bleeding in the current book and (b) set up a more systematic profit‑making framework going forward?

**Answer**  
The situation you described is very common: a mix of high‑conviction names, tactical trades that drifted, and outright mistakes, all interacting with each other. The good news is that SigmaTrader already has most of the components needed to manage this mathematically rather than emotionally. A useful way to think about it is in two layers:

1. **Stabilise the existing portfolio (“stop the bleeding”).**
2. **Build a simple, repeatable “profit‑making machinery” for new decisions.**

Below is a structured plan for both layers.

---

### 1.1 Stabilising the current portfolio

#### 1.1.1 Classify every holding

Go through your holdings and assign each symbol to a coarse bucket:

- **A – High conviction, long‑term**
  - You still like the business and future prospects.
  - If you were starting from cash today, you would *consider* buying it at current levels (even if not at the same size).
- **B – Tactical / uncertain**
  - The original thesis is weaker now, or it was never high conviction (e.g. momentum, thematic punts).
  - You might hold or exit depending on technicals and risk, but you are not emotionally married to it.
- **C – Mistakes / no conviction**
  - You would *not* buy it today if you had cash.
  - You are mostly staying because of anchoring or loss aversion.

This classification doesn’t need to be perfect; it just forces you to be explicit about conviction.

#### 1.1.2 Define simple rules per bucket

Once A/B/C tags are in place, associate each bucket with clear, mechanical rules. Keep them simple so they are easy to implement in the app.

- **Bucket C – No conviction (controlled exit)**
  - Goal: *Get out over time, preferably into strength, not weakness.*
  - Example rule set:
    - Do not add more capital to C names.
    - When Today P&L% exceeds a threshold (e.g. +5–8%), use the holdings dialog to:
      - SELL a slice (e.g. 25–33% of the position), and
      - Optionally attach a **re‑entry BUY bracket GTT** at a significantly lower price if you still want to opportunistically trade the name.
    - Repeat on subsequent rallies until the position is closed.
  - This uses custom brackets and Today P&L% to *exit into strength* rather than panic selling after further drops.

- **Bucket B – Tactical / uncertain (strict risk limits)**
  - Goal: *Prevent B names from turning into new −40% disasters.*
  - Example rule set:
    - Define per‑name max position size (e.g. ≤ 5% of portfolio).
    - Attach hard stops based on **ATR** or a fixed % from recent swing lows:
      - For example, a stop at `entry - 2 × ATR` or `entry - 8%`, whichever is tighter.
    - Use the **Risk** sizing mode in the Buy/Sell dialog:
      - Target risk per trade (e.g. 0.5–1% of portfolio).
      - Entry + stop + risk budget ⇒ qty.
    - If the stop is hit, you accept the loss and re‑evaluate; no “averaging down” without a fresh thesis.

- **Bucket A – High conviction (sensible sizing and patience)**
  - Goal: *Hold good businesses in reasonable size without letting one name dominate risk.*
  - Example rule set:
    - Treat each A name as if you are deciding today: “Would I buy this now?” If not, ask why you are still holding a large underwater position.
    - Use your **drawdown from peak** and **P&L%** columns to understand where you are in the cycle.
    - Limit per‑name weight and cluster exposure (see 1.1.3).
    - Use brackets cautiously:
      - For strong uptrends, you can trim with a SELL + re‑entry BUY GTT bracket.
      - For deep losers with intact fundamentals, you might choose to hold or rebalance rather than aggressively trade the swings.

The core idea: every symbol has a *pre‑decided playbook* instead of ad‑hoc reactions.

#### 1.1.3 Portfolio‑level guardrails

To prevent future damage, combine your existing analytics with simple portfolio‑wide limits:

- **Position limits**
  - Max weight per stock (e.g. 8–10% of portfolio).
  - Max weight per correlated cluster (using your correlation/cluster analysis).

- **Risk limits**
  - Global max loss per day / week (e.g. if closed P&L for the day hits −2%, stop new discretionary trades).
  - Risk engine settings (already supported) can clamp per‑order size and daily loss.

These guardrails ensure that even if one idea goes wrong, it doesn’t jeopardise the entire account.

---

### 1.2 Building the “profit‑making machinery” for new trades

With the existing book under control, you can use SigmaTrader’s features to make new decisions more systematic.

#### 1.2.1 Entry discipline

Use your indicators and alert engine to define a *small* set of entry patterns. Examples:

- **Trend‑following entries**
  - MA50 above MA200 (uptrend) + price pulling back towards MA50 with moderated volatility.
  - PVT / volume confirming accumulation.

- **Mean‑reversion entries**
  - RSI(14) oversold (<30) in a longer‑term uptrend (MA50 > MA200).
  - ATR not exploding (avoid catching falling knives).

- **PVT / volume‑based entries**
  - Price drifting sideways/down while PVT remains in a strong uptrend (accumulation despite pullback).

Each of these can be mapped to indicator alerts and/or DSL expressions later, but the key is to have 2–3 patterns you actually use, not 20.

#### 1.2.2 Pre‑planned exits with brackets and stops

For new positions:

- On entry, use the Buy dialog to:
  - Choose a **target range** for profits (MTP band, e.g. 5–12% depending on volatility).
  - Optionally enable a **profit‑target SELL bracket**:
    - BUY primary + SELL LIMIT GTT at `entry × (1 + MTP%)`.
  - Define a **stop**:
    - Either via Risk mode (stop + risk budget ⇒ qty).
    - Or via a separate SL / SL‑M order.

For existing profitable positions:

- When Today P&L% or P&L% is high:
  - Use the SELL + re‑entry BUY bracket to lock gains and plan the next swing.
  - Combine with indicators (RSI overbought, volatility spike) to avoid systematically selling too early in strong trends.

Over time, this creates a habit: every position is born with a target and a stop, not just an entry.

#### 1.2.3 Risk‑based sizing

Your Risk sizing mode already encodes the key formula:

- Risk per share = `|entry - stop|`.
- Max shares = `risk_budget / risk_per_share`.

Practical set‑up:

- Decide a per‑trade risk budget (e.g. 0.5–1% of portfolio).
- Use risk mode to compute qty and max loss on *every* new position, especially B‑bucket tactical trades.
- Keep a rough cap on the number of concurrent trades to avoid risk stacking.

This is where mathematics shines: **size is dictated by risk, not by how much you like the story.**

#### 1.2.4 Feedback loop and backtesting

Once the planned backtest console (for custom brackets using Kite OHLCV) is implemented, you’ll be able to:

- Simulate “bracket + stop” behaviour on historical data for candidates like BSE and NETWEB.
- Measure:
  - How often bracket legs fill,
  - Resulting P&L and drawdowns,
  - Sensitivity to different MTP and stop distances.

That will allow you to refine:

- MTP ranges (e.g. is 7–10% better than 5–8% for certain volatility regimes?),
- ATR multiples for stops,
- Indicator filters for when brackets are active.

Instead of guessing, you’ll tune the machinery using real historical outcomes.

---

### 1.3 Practical next steps

Given where you are and the tools you have today, a realistic immediate plan is:

1. **Tag holdings A/B/C** and write down simple rules for each bucket (even on paper).
2. **Use the holdings page** to:
   - Start exiting C names into strength using Today P&L% + brackets.
   - Tighten risk on B names using ATR‑based stops and risk sizing.
3. For A names, decide:
   - Ideal position size by weight and cluster;
   - Whether you want to use brackets to trim and re‑enter or just hold with sensible stops.
4. After we have the backtest console in place, run focused experiments on a few symbols to validate and refine MTP and stop settings.

This won’t erase existing losses overnight, but it *constrains future downside* and lays the foundation for a repeatable, data‑driven approach to both exits and new entries.

