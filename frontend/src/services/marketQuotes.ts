export type MarketQuote = {
  symbol: string
  exchange: string
  ltp?: number | null
  prev_close?: number | null
  day_pct?: number | null
}

export async function fetchMarketQuotes(
  items: Array<{ symbol: string; exchange?: string | null }>,
): Promise<MarketQuote[]> {
  const norm: Array<{ symbol: string; exchange?: string | null }> = []
  const seen = new Set<string>()
  for (const it of items || []) {
    const sym = (it.symbol || '').trim().toUpperCase()
    if (!sym) continue
    const exch = (it.exchange || 'NSE').trim().toUpperCase() || 'NSE'
    const key = `${exch}:${sym}`
    if (seen.has(key)) continue
    seen.add(key)
    norm.push({ symbol: sym, exchange: exch })
  }

  const BATCH = 200
  const out: MarketQuote[] = []
  for (let i = 0; i < norm.length; i += BATCH) {
    const batch = norm.slice(i, i + BATCH)
    const res = await fetch('/api/market/quotes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: batch }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(
        `Failed to fetch market quotes (${res.status})${body ? `: ${body}` : ''}`,
      )
    }
    const data = (await res.json()) as { items?: MarketQuote[] }
    if (Array.isArray(data.items)) out.push(...data.items)
  }
  return out
}
