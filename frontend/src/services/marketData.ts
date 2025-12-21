export type CandlePoint = {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type MarketHistoryParams = {
  symbol: string
  exchange?: string
  timeframe: '1m' | '5m' | '15m' | '1h' | '1d' | '1mo' | '1y'
  periodDays?: number
}

export type MarketSymbol = {
  symbol: string
  exchange: string
  name?: string | null
}

export type MarketDataStatus = {
  canonical_broker: string
  available: boolean
  error?: string | null
}

export async function fetchMarketHistory(
  params: MarketHistoryParams,
): Promise<CandlePoint[]> {
  const url = new URL('/api/market/history', window.location.origin)
  url.searchParams.set('symbol', params.symbol)
  url.searchParams.set('timeframe', params.timeframe)
  if (params.exchange) {
    url.searchParams.set('exchange', params.exchange)
  }
  if (params.periodDays != null) {
    url.searchParams.set('period_days', String(params.periodDays))
  }

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load market history (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as CandlePoint[]
}

export async function searchMarketSymbols(params: {
  q: string
  exchange?: string
  limit?: number
}): Promise<MarketSymbol[]> {
  const url = new URL('/api/market/symbols', window.location.origin)
  url.searchParams.set('q', params.q)
  if (params.exchange) url.searchParams.set('exchange', params.exchange)
  if (params.limit != null) url.searchParams.set('limit', String(params.limit))

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to search symbols (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as MarketSymbol[]
}

export async function fetchMarketDataStatus(): Promise<MarketDataStatus> {
  const res = await fetch('/api/market/status')
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load market data status (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as MarketDataStatus
}
