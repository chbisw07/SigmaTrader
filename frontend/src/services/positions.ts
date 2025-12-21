export type Position = {
  id: number
  symbol: string
  exchange: string
  product: string
  qty: number
  avg_price: number
  pnl: number
  last_updated: string
}

export type PositionSnapshot = {
  id: number
  as_of_date: string // YYYY-MM-DD
  captured_at: string
  symbol: string
  exchange: string
  product: string
  qty: number
  remaining_qty: number
  avg_price: number
  pnl: number
  last_price?: number | null
  close_price?: number | null
  value?: number | null
  m2m?: number | null
  unrealised?: number | null
  realised?: number | null
  buy_qty?: number | null
  buy_avg_price?: number | null
  sell_qty?: number | null
  sell_avg_price?: number | null
  day_buy_qty?: number | null
  day_buy_avg_price?: number | null
  day_sell_qty?: number | null
  day_sell_avg_price?: number | null

  traded_qty?: number
  order_type?: string
  avg_buy_price?: number | null
  avg_sell_price?: number | null
  pnl_value?: number | null
  pnl_pct?: number | null
  ltp?: number | null
  today_pnl?: number | null
  today_pnl_pct?: number | null
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
  broker_name?: string | null
}

export async function syncPositions(
  brokerName = 'zerodha',
): Promise<{ updated: number }> {
  const url = new URL('/api/positions/sync', window.location.origin)
  url.searchParams.set('broker_name', brokerName)
  const res = await fetch(url.toString(), {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to sync positions from ${brokerName} (${res.status})${
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

export async function fetchDailyPositions(params?: {
  start_date?: string
  end_date?: string
  symbol?: string
  include_zero?: boolean
}): Promise<PositionSnapshot[]> {
  const url = new URL('/api/positions/daily', window.location.origin)
  if (params?.start_date) url.searchParams.set('start_date', params.start_date)
  if (params?.end_date) url.searchParams.set('end_date', params.end_date)
  if (params?.symbol) url.searchParams.set('symbol', params.symbol)
  if (params?.include_zero != null) {
    url.searchParams.set('include_zero', params.include_zero ? 'true' : 'false')
  }

  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load daily positions (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as PositionSnapshot[]
}

export async function fetchHoldings(
  brokerName = 'zerodha',
): Promise<Holding[]> {
  const url = new URL('/api/positions/holdings', window.location.origin)
  url.searchParams.set('broker_name', brokerName)
  // Add a cache-buster so that each refresh button press forces a fresh
  // request to the backend and, in turn, to Zerodha.
  url.searchParams.set('_ts', String(Date.now()))

  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`Failed to load holdings (${res.status})`)
  }
  return (await res.json()) as Holding[]
}
