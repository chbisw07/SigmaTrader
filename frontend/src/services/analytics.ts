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
