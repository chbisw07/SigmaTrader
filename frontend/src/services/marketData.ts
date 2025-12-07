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

