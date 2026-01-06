export type EquityPeriod = 'WEEK' | 'MONTH'

export type EquityPeriodPnlRow = {
  id: string
  period: string
  start_ymd: string
  end_ymd: string
  start_equity: number
  end_equity: number
  pnl: number
  pnl_pct: number
}

export type ClosedTradeAnalysisRow = {
  id: number
  month: string
  week_start: string
  symbol: string
  entry_ts: string
  exit_ts: string
  side: string
  buy_price: number | null
  sell_price: number | null
  qty: number | null
  pnl_pct: number | null
  pnl_inr: number | null
  hold_days: number | null
  reason: string
}

export type TradePeriodSummaryRow = {
  id: string
  period: string
  trades: number
  wins: number
  losses: number
  pnl_inr: number
  avg_pnl_pct: number
  avg_hold_days: number
}

function safeYmdFromIso(ts: string): string {
  const s = (ts || '').trim()
  return s.length >= 10 ? s.slice(0, 10) : ''
}

function parseYmdToUtcDate(ymd: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return null
  const [y, m, d] = ymd.split('-').map((x) => Number(x))
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null
  return new Date(Date.UTC(y, m - 1, d))
}

function weekStartYmd(ymd: string): string {
  const dt = parseYmdToUtcDate(ymd)
  if (!dt) return ''
  const day = dt.getUTCDay() // 0=Sun, 1=Mon
  const delta = day === 0 ? -6 : 1 - day
  dt.setUTCDate(dt.getUTCDate() + delta)
  return dt.toISOString().slice(0, 10)
}

export function computeEquityPeriodPnlRows(
  ts: unknown[],
  equity: unknown[],
  period: EquityPeriod,
): EquityPeriodPnlRow[] {
  const buckets: Array<{
    key: string
    startYmd: string
    endYmd: string
    endEquity: number
  }> = []

  let firstEquity: number | null = null
  let lastKey: string | null = null

  for (let i = 0; i < Math.min(ts.length, equity.length); i++) {
    const t = String(ts[i] ?? '')
    const v = Number(equity[i] ?? NaN)
    if (!t || !Number.isFinite(v)) continue
    if (firstEquity == null) firstEquity = v

    const ymd = safeYmdFromIso(t)
    if (!ymd) continue
    const key =
      period === 'MONTH' ? ymd.slice(0, 7) : weekStartYmd(ymd)
    if (!key) continue

    if (key !== lastKey) {
      buckets.push({ key, startYmd: ymd, endYmd: ymd, endEquity: v })
      lastKey = key
    } else {
      const b = buckets[buckets.length - 1]
      b.endYmd = ymd
      b.endEquity = v
    }
  }

  if (!buckets.length || firstEquity == null) return []

  const out: EquityPeriodPnlRow[] = []
  let prevEndEquity = firstEquity

  for (const b of buckets) {
    const startEquity = prevEndEquity
    const endEquity = b.endEquity
    const pnl = endEquity - startEquity
    const pnlPct = startEquity > 0 ? (endEquity / startEquity - 1) * 100 : 0
    out.push({
      id: b.key,
      period: b.key,
      start_ymd: b.startYmd,
      end_ymd: b.endYmd,
      start_equity: startEquity,
      end_equity: endEquity,
      pnl,
      pnl_pct: pnlPct,
    })
    prevEndEquity = endEquity
  }

  return out
}

export function computeClosedTradeAnalysisRows(
  trades: Array<Record<string, unknown>>,
  opts?: { defaultSymbol?: string },
): ClosedTradeAnalysisRow[] {
  const defaultSymbol = (opts?.defaultSymbol ?? '').trim()

  const out: ClosedTradeAnalysisRow[] = []
  for (let idx = 0; idx < trades.length; idx++) {
    const t = trades[idx] ?? {}
    const entryTs = String(t.entry_ts ?? '')
    const exitTs = String(t.exit_ts ?? '')
    if (!entryTs || !exitTs) continue
    const entryYmd = safeYmdFromIso(entryTs)
    const exitYmd = safeYmdFromIso(exitTs)
    const month = exitYmd ? exitYmd.slice(0, 7) : ''
    const weekStart = exitYmd ? weekStartYmd(exitYmd) : ''

    const side = String(t.side ?? '')
    const isShort = side.toUpperCase() === 'SHORT'
    const entryPrice = Number(t.entry_price ?? NaN)
    const exitPrice = Number(t.exit_price ?? NaN)
    const qty = Number(t.qty ?? NaN)

    const buyPrice = isShort ? exitPrice : entryPrice
    const sellPrice = isShort ? entryPrice : exitPrice
    const buy = Number.isFinite(buyPrice) ? buyPrice : null
    const sell = Number.isFinite(sellPrice) ? sellPrice : null
    const qtyN = Number.isFinite(qty) ? qty : null

    const pnlInr =
      buy != null && sell != null && qtyN != null ? (sell - buy) * qtyN : null
    const pnlPctRaw = Number(t.pnl_pct ?? NaN)
    const pnlPct = Number.isFinite(pnlPctRaw) ? pnlPctRaw : null

    const holdDays =
      entryYmd && exitYmd ? daysBetweenIsoDates(entryYmd, exitYmd) : null

    const symbol =
      (String(t.symbol ?? '') || defaultSymbol).trim()

    out.push({
      id: idx,
      month,
      week_start: weekStart,
      symbol,
      entry_ts: entryTs,
      exit_ts: exitTs,
      side,
      buy_price: buy,
      sell_price: sell,
      qty: qtyN,
      pnl_pct: pnlPct,
      pnl_inr: pnlInr,
      hold_days: holdDays,
      reason: String(t.reason ?? ''),
    })
  }
  return out
}

export function computeTradePeriodSummaryRows(
  closedTrades: ClosedTradeAnalysisRow[],
  period: EquityPeriod,
): TradePeriodSummaryRow[] {
  const keyOf = (t: ClosedTradeAnalysisRow) => (period === 'MONTH' ? t.month : t.week_start)

  const order: string[] = []
  const byKey = new Map<
    string,
    {
      trades: number
      wins: number
      losses: number
      pnlInr: number
      pnlPctSum: number
      pnlPctN: number
      holdDaysSum: number
      holdDaysN: number
    }
  >()

  for (const t of closedTrades) {
    const key = keyOf(t)
    if (!key) continue
    if (!byKey.has(key)) {
      order.push(key)
      byKey.set(key, {
        trades: 0,
        wins: 0,
        losses: 0,
        pnlInr: 0,
        pnlPctSum: 0,
        pnlPctN: 0,
        holdDaysSum: 0,
        holdDaysN: 0,
      })
    }
    const agg = byKey.get(key)!
    agg.trades += 1
    const pnlPct = t.pnl_pct
    if (typeof pnlPct === 'number' && Number.isFinite(pnlPct)) {
      if (pnlPct > 0) agg.wins += 1
      else if (pnlPct < 0) agg.losses += 1
      agg.pnlPctSum += pnlPct
      agg.pnlPctN += 1
    }
    const pnlInr = t.pnl_inr
    if (typeof pnlInr === 'number' && Number.isFinite(pnlInr)) agg.pnlInr += pnlInr
    const hd = t.hold_days
    if (typeof hd === 'number' && Number.isFinite(hd)) {
      agg.holdDaysSum += hd
      agg.holdDaysN += 1
    }
  }

  return order.map((k) => {
    const agg = byKey.get(k)!
    return {
      id: k,
      period: k,
      trades: agg.trades,
      wins: agg.wins,
      losses: agg.losses,
      pnl_inr: agg.pnlInr,
      avg_pnl_pct: agg.pnlPctN ? agg.pnlPctSum / agg.pnlPctN : 0,
      avg_hold_days: agg.holdDaysN ? agg.holdDaysSum / agg.holdDaysN : 0,
    }
  })
}

export function daysBetweenIsoDates(startIso: string, endIso: string): number | null {
  const a = Date.parse(startIso)
  const b = Date.parse(endIso)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null
  const days = Math.round((b - a) / (24 * 60 * 60 * 1000))
  return days >= 0 ? days : null
}

