export type HoldingsSummarySnapshot = {
  id: number
  user_id: number
  broker_name: string
  as_of_date: string // YYYY-MM-DD
  captured_at: string

  holdings_count: number

  funds_available?: number | null
  invested?: number | null
  equity_value?: number | null
  account_value?: number | null

  total_pnl_pct?: number | null
  today_pnl_pct?: number | null
  overall_win_rate?: number | null
  today_win_rate?: number | null

  alpha_annual_pct?: number | null
  beta?: number | null

  cagr_1y_pct?: number | null
  cagr_2y_pct?: number | null
  cagr_1y_coverage_pct?: number | null
  cagr_2y_coverage_pct?: number | null

  benchmark_symbol?: string | null
  benchmark_exchange?: string | null
  risk_free_rate_pct?: number | null
}

export type HoldingsSummarySnapshotsMeta = {
  broker_name: string
  today: string // YYYY-MM-DD
  min_date?: string | null
  max_date?: string | null
}

export async function captureHoldingsSummarySnapshot(params?: {
  broker_name?: string
  allow_fetch_market_data?: boolean
}): Promise<HoldingsSummarySnapshot> {
  const url = new URL('/api/holdings-summary/snapshots/capture', window.location.origin)
  if (params?.broker_name) url.searchParams.set('broker_name', params.broker_name)
  if (params?.allow_fetch_market_data != null) {
    url.searchParams.set(
      'allow_fetch_market_data',
      params.allow_fetch_market_data ? 'true' : 'false',
    )
  }
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to capture holdings summary snapshot (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingsSummarySnapshot
}

export async function fetchHoldingsSummarySnapshots(params?: {
  broker_name?: string
  start_date?: string
  end_date?: string
}): Promise<HoldingsSummarySnapshot[]> {
  const url = new URL('/api/holdings-summary/snapshots', window.location.origin)
  if (params?.broker_name) url.searchParams.set('broker_name', params.broker_name)
  if (params?.start_date) url.searchParams.set('start_date', params.start_date)
  if (params?.end_date) url.searchParams.set('end_date', params.end_date)
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to load holdings summary snapshots (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingsSummarySnapshot[]
}

export async function fetchHoldingsSummarySnapshotsMeta(params?: {
  broker_name?: string
}): Promise<HoldingsSummarySnapshotsMeta> {
  const url = new URL('/api/holdings-summary/snapshots/meta', window.location.origin)
  if (params?.broker_name) url.searchParams.set('broker_name', params.broker_name)
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to load holdings summary snapshots meta (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingsSummarySnapshotsMeta
}
