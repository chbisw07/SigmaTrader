export type Position = {
  id: number
  symbol: string
  product: string
  qty: number
  avg_price: number
  pnl: number
  last_updated: string
}

export type Holding = {
  symbol: string
  quantity: number
  average_price: number
  exchange?: string | null
  last_price?: number | null
  pnl?: number | null
  last_purchase_date?: string | null
  total_pnl_percent?: number | null
  today_pnl_percent?: number | null
}

export async function syncPositions(): Promise<{ updated: number }> {
  const res = await fetch('/api/positions/sync', {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to sync positions from Zerodha (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as { updated: number }
}

export async function fetchPositions(): Promise<Position[]> {
  const res = await fetch('/api/positions/')
  if (!res.ok) {
    throw new Error(`Failed to load positions (${res.status})`)
  }
  return (await res.json()) as Position[]
}

export async function fetchHoldings(): Promise<Holding[]> {
  const url = new URL('/api/positions/holdings', window.location.origin)
  // Add a cache-buster so that each refresh button press forces a fresh
  // request to the backend and, in turn, to Zerodha.
  url.searchParams.set('_ts', String(Date.now()))

  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`Failed to load holdings (${res.status})`)
  }
  return (await res.json()) as Holding[]
}
