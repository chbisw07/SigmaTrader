type BasketRange = '1d' | '1w' | '1m' | '3m' | '6m' | 'ytd' | '1y' | '2y'

export type BasketIndexRequest = {
  include_holdings: boolean
  group_ids: number[]
  range: BasketRange
  base?: number
}

export type BasketIndexPoint = {
  ts: string
  value: number
  used_symbols: number
  total_symbols: number
}

export type BasketIndexSeries = {
  key: string
  label: string
  points: BasketIndexPoint[]
  missing_symbols: number
  needs_hydrate_history_symbols: number
}

export type BasketIndexResponse = {
  start: string
  end: string
  series: BasketIndexSeries[]
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text()
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // ignore
  }
  return text
}

export async function fetchBasketIndices(
  payload: BasketIndexRequest,
): Promise<BasketIndexResponse> {
  const res = await fetch('/api/analytics/basket-indices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await parseError(res)
    throw new Error(
      `Failed to compute indices (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as BasketIndexResponse
}

type SymbolRange = BasketRange
type SymbolTimeframe = '1d'
type HydrateMode = 'none' | 'auto' | 'force'

export type SymbolSeriesRequest = {
  symbol: string
  exchange?: string
  range: SymbolRange
  timeframe?: SymbolTimeframe
  hydrate_mode?: HydrateMode
}

export type SymbolSeriesPoint = {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type SymbolSeriesResponse = {
  symbol: string
  exchange: string
  start: string
  end: string
  points: SymbolSeriesPoint[]
  local_first?: string | null
  local_last?: string | null
  head_gap_days: number
  tail_gap_days: number
  needs_hydrate_history: boolean
}

export async function fetchSymbolSeries(
  payload: SymbolSeriesRequest,
): Promise<SymbolSeriesResponse> {
  const res = await fetch('/api/analytics/symbol-series', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await parseError(res)
    throw new Error(
      `Failed to load candles (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as SymbolSeriesResponse
}

export type HydrateHistoryRequest = {
  include_holdings: boolean
  group_ids: number[]
  range: BasketRange
  timeframe?: SymbolTimeframe
}

export type HydrateHistoryResponse = {
  hydrated: number
  failed: number
  errors: string[]
}

export async function hydrateHistory(
  payload: HydrateHistoryRequest,
): Promise<HydrateHistoryResponse> {
  const res = await fetch('/api/analytics/hydrate-history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await parseError(res)
    throw new Error(
      `Failed to hydrate history (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as HydrateHistoryResponse
}
