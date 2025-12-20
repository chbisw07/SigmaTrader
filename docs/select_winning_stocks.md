# Selecting “Winning” Stocks with SigmaTrader DSL

This note captures our Q&A on “How to find pre‑market stocks which will rise today more than 5%?” and generalises it into practical, reusable strategies using the existing Screener + Alerts V3 + Dashboard tooling.

The goal is **not** to “predict with certainty” but to:

- Build **high‑quality candidate universes** before the session.
- Use **fast event detection** during the session (Alerts + Screener).
- Combine **trend, momentum, and volume** in a disciplined, testable way.

---

## 1. Reality Check: Prediction vs Detection

- A rule that says *“These stocks will rise >5% today”* is, in practice, a **prediction problem**. Even professional funds treat this probabilistically, not deterministically.
- What SigmaTrader can already do very well:
  - **Pre‑market preparation:** find symbols in strong trends / momentum regimes with decent liquidity.
  - **Intraday detection:** alerts and screeners that fire the moment price actually crosses +X%, combined with volume and context filters.
- In other words: aim for **“catch strong movers early”**, not “guarantee 5%”.

---

## 2. Building Blocks You Already Have

You already have enough DSL and features for rich strategies:

- **Universes / Sets**
  - Holdings (`Holdings (Zerodha)`).
  - Groups (watchlists like `KITE`, sectors, custom baskets).
  - Screener runs on *Holdings + selected groups (union, deduped)*.

- **Indicators & Functions (partial list)**
  - Trend / smoothing: `SMA`, `EMA`, `BOLLINGER`, `Z_SCORE`.
  - Momentum / returns: `RET`, `ROC`, `RSI`, `ATR`, `STDDEV`.
  - Volume / flow: `Volume("tf")`, `OBV`, `VWAP`.
  - Events / signals: `CROSSING_ABOVE(a, b)`, `CROSSING_BELOW(a, b)`.
  - OHLCV primitives: `open`, `high`, `low`, `close`, `volume` with timeframes such as `"1d"`, `"1h"`, `"15m"`, etc. (where data is available).

- **Execution Contexts**
  - **Screener:** one‑shot scans; lets you create a group from matches.
  - **Alerts V3:** persistent rules that emit events (and optionally auto‑trade).
  - **Dashboard / Symbol explorer:** visual inspection of signals on charts.

---

## 3. Core Concept: A “>5% Today” Play

Think of the >5% move as a **signal to detect**, not a prophecy to make.

High‑level structure:

1. **Condition A: Today’s move**  
   - Price change vs yesterday’s close is already >5%.  
   - In DSL: `RET(close, "1d") > 5`.

2. **Condition B: Trend / structure**  
   - Avoid pure junk spikes; require an uptrend or at least constructive structure.  
   - In DSL: e.g. `SMA(close, 20, "1d") > SMA(close, 50, "1d")`.

3. **Condition C: Volume confirmation**  
   - Today’s volume is high relative to recent history.  
   - In DSL: `Volume("1d") > 2 * SMA(Volume("1d"), 20, "1d")`.

4. **Optional Condition D: Momentum regime**  
   - e.g. mid‑range RSI, not already exhausted: `RSI(close, 14, "1d") BETWEEN 50 AND 80`.

### 3.1 Suggested Variables

Define these as **Variables** in Alert / Screener:

- `RET_1D = RET(close, "1d")`
- `VOL_1D = Volume("1d")`
- `VOL_20D = SMA(Volume("1d"), 20, "1d")`
- `RSI_14 = RSI(close, 14, "1d")`
- `SMA_20 = SMA(close, 20, "1d")`
- `SMA_50 = SMA(close, 50, "1d")`

### 3.2 Screener Condition (DSL)

In the Screener’s **Advanced (DSL)**:

```text
RET(close, "1d") > 5
AND Volume("1d") > 2 * SMA(Volume("1d"), 20, "1d")
AND SMA(close, 20, "1d") > SMA(close, 50, "1d")
AND RSI(close, 14, "1d") > 50
AND RSI(close, 14, "1d") < 80
```

Usage:

- Universe: your KITE watchlist, NIFTY500 groups, or other custom groups (union).
- Run intraday; enable *Matched only*.
- Use **“Create group from matches”** to snapshot a **“5% movers with volume & trend”** group.

### 3.3 Alert V3 Strategy (Saved & Reusable)

Turn the same rule into an **Alert V3**:

- Target kind: `Groups` or `Holdings (Zerodha)`.
- Trigger mode: `Once per bar` on `"1d"` candles (or `"15m"` for intraday granularity).
- Action:
  - Start with `Alert only`.
  - Later, connect to Buy/Sell templates for semi‑automated entries.
- Variables + Condition: reuse exactly the DSL above.

The alert becomes a **named, saved strategy**. You can:

- Edit it over time (change thresholds, add filters).
- Clone it for bearish variants (e.g. `RET(close,"1d") < -5` with appropriate conditions).
- Use the same variables and expression in Screener for one‑off scans.

---

## 4. Additional Strategy Patterns

Below are a few more patterns that fit well with your current DSL and engine design. These are intentionally simple building blocks you can mix and match.

### 4.1 Opening Range Breakout + Trend Filter

Idea: Catch stocks that break above their **first‑hour high** with strong trend behind them.

Approximate DSL approach (conceptual, assuming `"15m"` data):

- Variables:

  - `RET_1D = RET(close, "1d")`
  - `RSI_14 = RSI(close, 14, "1d")`
  - `SMA_20 = SMA(close, 20, "1d")`
  - `SMA_50 = SMA(close, 50, "1d")`

- Condition:

  ```text
  RET(close, "1d") > 3
  AND SMA(close, 20, "1d") > SMA(close, 50, "1d")
  AND RSI(close, 14, "1d") > 55
  ```

Then, on the Dashboard / Symbol explorer, you can use **DSL signals** with `CROSSING_ABOVE` to place markers when intraday price crosses key levels (once you define those as series).

This pattern is less about a single CDS formula and more about:

- Pre‑market: screen for stocks with **strong daily context**.
- Intraday: use chart‑level DSL markers for breakout confirmation.

### 4.2 Volatility Contraction + Breakout (Bollinger / Z‑Score)

Idea: Find stocks whose **daily volatility has contracted** and are now starting to expand upward.

- Variables:

  - `RET_1D = RET(close, "1d")`
  - `Z_RET_20 = Z_SCORE(RET(close, "1d"), 20)`
  - `ATR_14 = ATR(14, "1d")`
  - `ATR_50 = ATR(50, "1d")`

- Conditions for “coiled spring + starting to expand”:

  ```text
  ATR(14, "1d") < ATR(50, "1d")
  AND Z_SCORE(RET(close, "1d"), 20) > 1.0
  AND RET(close, "1d") > 3
  ```

Interpretation:

- Average volatility has been low (`ATR_14 < ATR_50`), i.e., contracted.
- Today’s return is **positively significant** relative to its own past (`Z_SCORE > 1`).
- The raw move is already noticeable (`RET_1D > 3`).

This tends to surface “quiet → sudden strong move” names.

### 4.3 Relative Volume + Trend

Idea: Look for **unusual volume** in the direction of the major trend.

- Variables:

  - `VOL_1D = Volume("1d")`
  - `VOL_20D = SMA(Volume("1d"), 20, "1d")`
  - `RET_1D = RET(close, "1d")`
  - `SMA_50 = SMA(close, 50, "1d")`
  - `SMA_200 = SMA(close, 200, "1d")`

- Condition:

  ```text
  Volume("1d") > 1.5 * SMA(Volume("1d"), 20, "1d")
  AND RET(close, "1d") > 2
  AND SMA(close, 50, "1d") > SMA(close, 200, "1d")
  ```

This finds names that:

- Are in a **longer‑term uptrend** (50d above 200d).
- Are trading on **unusually high volume today**.
- Are already moving up meaningfully today.

You can tighten or loosen the multipliers depending on how many candidates you want.

---

## 5. Pre‑Market vs Live‑Session Workflow

Putting it all together:

1. **Before market open**
   - Use Screener with daily‑only signals (RSI, trend, ATR, Z‑Score, etc.) to build:
     - A “high‑potential movers” group based on momentum + volatility.
   - This becomes your **focus universe** for the day.

2. **During the session**
   - Alerts V3:
     - Run the “>5% move with volume + trend” alert on this narrowed universe.
     - Optionally attach Buy/Sell templates (manual or auto modes).
   - Screener:
     - On demand, re‑run intraday DSL filters to see fresh matches.
   - Dashboard / Symbol explorer:
     - Inspect a few names visually with chart overlays and DSL markers.

3. **After the session**
   - Review which signals performed well.
   - Tweak thresholds (e.g., move 5% → 4% or 6%, adjust RSI ranges).
   - Promote stable rules into **named strategies** (Alerts), and keep ad‑hoc experiments in Screener.

---

## 6. Saving and Reusing Strategies

- **Alerts V3** are effectively your **strategy library**:
  - Each Alert definition = variables + DSL + trigger mode + universe + action.
  - You can duplicate an alert, change only the universe (e.g., from `Holdings` to a specific watchlist group).
  - Screener can reuse the same variables / expression by copy–paste for now.

- Over time we can add UX sugar:
  - “Load from alert” in Screener (and vice‑versa).
  - A small “strategy catalogue” section linking Alerts, Screeners, and Dashboard signal presets.

---

## 7. Next Possible Enhancements

If you later want to push this further, natural extensions are:

- **Factor‑style ranking** inside Screener:
  - Sort matches by `RET_1D`, `Z_SCORE`, `relative volume`, etc.
  - Export to CSV and analyse further if needed.
- **Multi‑timeframe DSL signals on charts**:
  - e.g. “5% daily move, but 15‑minute RSI > 60 with VWAP support”.
- **Preset strategy templates**:
  - Saved named configurations for the examples above so you can apply them quickly to different universes.

For now, the existing Indicator + DSL set is already **powerful enough for 80–90% of these “catch strong movers” use‑cases**, especially when combined with your new Dashboard, Screener, and Alerts V3 machinery.

