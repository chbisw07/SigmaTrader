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
  last_price?: number | null
  pnl?: number | null
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
  const res = await fetch('/api/positions/holdings')
  if (!res.ok) {
    throw new Error(`Failed to load holdings (${res.status})`)
  }
  return (await res.json()) as Holding[]
}

