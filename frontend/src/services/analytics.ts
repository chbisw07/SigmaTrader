export type AnalyticsSummary = {
  strategy_id: number | null
  total_pnl: number
  trades: number
  win_rate: number
  avg_win: number | null
  avg_loss: number | null
  max_drawdown: number
}

export type AnalyticsTrade = {
  id: number
  strategy_id: number | null
  strategy_name: string | null
  symbol: string
  product: string
  pnl: number
  opened_at: string
  closed_at: string
}

export type CorrelationPair = {
  symbol_x: string
  symbol_y: string
  correlation: number
}

export type SymbolCorrelationStats = {
  symbol: string
  average_correlation: number | null
  most_correlated_symbol: string | null
  most_correlated_value: number | null
  cluster: string | null
  weight_fraction: number | null
}

export type CorrelationClusterSummary = {
  id: string
  symbols: string[]
  weight_fraction: number | null
  average_internal_correlation: number | null
  average_to_others: number | null
}

export type HoldingsCorrelationResult = {
  symbols: string[]
  matrix: (number | null)[][]
  window_days: number
  observations: number
  average_correlation: number | null
  diversification_rating: string
  summary: string
  recommendations: string[]
  top_positive: CorrelationPair[]
  top_negative: CorrelationPair[]
  symbol_stats: SymbolCorrelationStats[]
  clusters: CorrelationClusterSummary[]
  effective_independent_bets: number | null
}

export type RiskSizingRequest = {
  entry_price: number
  stop_price: number
  risk_budget: number
  max_qty?: number | null
}

export type RiskSizingResponse = {
  qty: number
  notional: number
  risk_per_share: number
  max_loss: number
}

export type HoldingsScreenerResult = {
  matches: string[]
}

export async function rebuildAnalyticsTrades(): Promise<{ created: number }> {
  const res = await fetch('/api/analytics/rebuild-trades', {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to rebuild analytics trades (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as { created: number }
}

export async function fetchAnalyticsSummary(
  params?: {
    strategyId?: number | null
    dateFrom?: string | null
    dateTo?: string | null
    includeSimulated?: boolean
  },
): Promise<AnalyticsSummary> {
  const body = {
    strategy_id:
      params && typeof params.strategyId === 'number'
        ? params.strategyId
        : null,
    date_from: params?.dateFrom ?? null,
    date_to: params?.dateTo ?? null,
    include_simulated: params?.includeSimulated ?? false,
  }
  const res = await fetch('/api/analytics/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load analytics summary (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as AnalyticsSummary
}

export async function fetchAnalyticsTrades(
  params?: {
    strategyId?: number | null
    dateFrom?: string | null
    dateTo?: string | null
    includeSimulated?: boolean
  },
): Promise<AnalyticsTrade[]> {
  const body = {
    strategy_id:
      params && typeof params.strategyId === 'number'
        ? params.strategyId
        : null,
    date_from: params?.dateFrom ?? null,
    date_to: params?.dateTo ?? null,
    include_simulated: params?.includeSimulated ?? false,
  }
  const res = await fetch('/api/analytics/trades', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const bodyText = await res.text()
    throw new Error(
      `Failed to load analytics trades (${res.status})${
        bodyText ? `: ${bodyText}` : ''
      }`,
    )
  }
  return (await res.json()) as AnalyticsTrade[]
}

export async function fetchHoldingsCorrelation(params?: {
  windowDays?: number
  minWeightFraction?: number
  clusterThreshold?: number
}): Promise<HoldingsCorrelationResult> {
  const url = new URL(
    '/api/analytics/holdings-correlation',
    window.location.origin,
  )
  if (params?.windowDays != null) {
    url.searchParams.set('window_days', String(params.windowDays))
  }
   if (params?.minWeightFraction != null) {
     url.searchParams.set(
       'min_weight_fraction',
       String(params.minWeightFraction),
     )
   }
   if (params?.clusterThreshold != null) {
     url.searchParams.set('cluster_threshold', String(params.clusterThreshold))
   }

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load holdings correlation (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as HoldingsCorrelationResult
}

export async function computeRiskSizing(
  payload: RiskSizingRequest,
): Promise<RiskSizingResponse> {
  const res = await fetch('/api/analytics/risk-sizing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let message = `Failed to compute risk sizing (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string }
      if (data.detail) {
        message = data.detail
      }
    } catch {
      // Ignore parse errors.
    }
    throw new Error(message)
  }
  return (await res.json()) as RiskSizingResponse
}

export async function evaluateHoldingsScreenerDsl(
  dslExpression: string,
): Promise<HoldingsScreenerResult> {
  const res = await fetch('/api/analytics/holdings-screener-eval', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dsl_expression: dslExpression }),
  })
  if (!res.ok) {
    let message = `Failed to evaluate holdings screener (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string }
      if (data.detail) {
        message = data.detail
      }
    } catch {
      // Ignore parse errors.
    }
    throw new Error(message)
  }
  return (await res.json()) as HoldingsScreenerResult
}
