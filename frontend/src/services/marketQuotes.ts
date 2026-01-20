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
  const res = await fetch('/api/market/quotes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to fetch market quotes (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  const data = (await res.json()) as { items?: MarketQuote[] }
  return Array.isArray(data.items) ? data.items : []
}

