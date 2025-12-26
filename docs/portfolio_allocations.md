# Portfolio allocations (X/Y) and guardrails

SigmaTrader portfolios can overlap: the same symbol may appear in multiple portfolios.

To keep this intuitive and consistent with broker holdings, SigmaTrader treats:

- **Holdings (Y)** as the source of truth (from broker).
- **Portfolio reference qty/price (X)** as an *allocation baseline* (your internal ledger per portfolio).

## The X/Y display

Wherever you see **X/Y**:

- **Ref Qty** is shown as `portfolio_ref_qty / broker_holding_qty`
- **Ref Price** is shown as `portfolio_ref_price / broker_avg_price`

This makes it obvious how much of the current holdings you consider to belong to the portfolio.

## The key invariant (what must always be true)

For a given `(broker, exchange, symbol)`:

```
Σ portfolio_ref_qty  ≤  broker_holding_qty
```

If the sum across portfolios exceeds broker holdings, SigmaTrader flags it as an **allocation mismatch**.

## Unassigned qty

SigmaTrader implicitly treats any leftover as **unassigned**:

```
unassigned_qty = broker_holding_qty - Σ portfolio_ref_qty
```

External buys (done directly in broker UI) typically increase `unassigned_qty`.

## Selling guardrails (why SigmaTrader asks “which portfolio?”)

If you sell directly in the broker UI, SigmaTrader cannot know which portfolio the sell should reduce.
So SigmaTrader:

- Encourages selling from the **portfolio universe** when you intend to reduce a portfolio allocation.
- When selling from the **holdings universe**, SigmaTrader asks for an **allocation bucket**:
  - **Unassigned** (default)
  - or one of the portfolios that currently contains that symbol

## Reconciling mismatches (external trades)

If you sell via the broker UI and that sell reduces holdings below the sum of allocations, SigmaTrader will show:

- A warning banner in Holdings.
- A red `Alloc (ΣX/Y)` chip in Groups → Portfolio members.

Click the red chip to open **Reconcile portfolio allocations**, then reduce portfolio quantities until `ΣX ≤ Y`.

If the symbol appears in exactly **one** portfolio, the reconcile dialog also offers **Auto-set to holdings** to quickly set that portfolio’s `ref_qty` to the effective broker qty (Y). This is a convenience shortcut; for overlapping portfolios, SigmaTrader requires manual reconcile.

## When portfolio baselines update automatically

SigmaTrader updates `ref_qty` (and updates `ref_price` on BUY via weighted average) when:

- An order is created with **portfolio attribution** (portfolio bucket selected / portfolio universe),
- and the order later reaches **EXECUTED** state.

If you don’t see the baseline update yet, run **Orders → Sync** to pull the latest broker statuses.
