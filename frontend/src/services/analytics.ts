export type AnalyticsSummary = {
  strategy_id: number | null
  total_pnl: number
  trades: number
  win_rate: number
  avg_win: number | null
  avg_loss: number | null
  max_drawdown: number
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
  strategyId: number | null = null,
): Promise<AnalyticsSummary> {
  const res = await fetch('/api/analytics/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_id: strategyId }),
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

