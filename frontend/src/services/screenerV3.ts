import type { AlertVariableDef } from './alertsV3'

export type ScreenerRow = {
  symbol: string
  exchange: string
  matched: boolean
  missing_data: boolean
  error?: string | null
  last_price?: number | null
  rsi_14_1d?: number | null
  sma_20_1d?: number | null
  sma_50_1d?: number | null
  variables: Record<string, number | null>
}

export type ScreenerRun = {
  id: number
  status: 'RUNNING' | 'DONE' | 'ERROR'
  evaluation_cadence: string
  total_symbols: number
  evaluated_symbols: number
  matched_symbols: number
  missing_symbols: number
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  include_holdings?: boolean
  group_ids?: number[]
  variables?: AlertVariableDef[]
  condition_dsl?: string
  rows?: ScreenerRow[] | null
  signal_strategy_version_id?: number | null
  signal_strategy_output?: string | null
  signal_strategy_params?: Record<string, unknown>
}

export type ScreenerRunRequest = {
  include_holdings: boolean
  group_ids: number[]
  variables: AlertVariableDef[]
  condition_dsl: string
  evaluation_cadence?: string | null
  signal_strategy_version_id?: number | null
  signal_strategy_output?: string | null
  signal_strategy_params?: Record<string, unknown>
}

async function readApiError(res: Response): Promise<string> {
  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      const data = (await res.json()) as { detail?: unknown }
      if (typeof data.detail === 'string' && data.detail.trim()) return data.detail
      return JSON.stringify(data)
    } catch {
      // fall through
    }
  }
  try {
    const body = await res.text()
    return body.trim()
  } catch {
    return ''
  }
}

export async function runScreener(payload: ScreenerRunRequest): Promise<ScreenerRun> {
  const res = await fetch('/api/screener-v3/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to run screener (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as ScreenerRun
}

export async function getScreenerRun(
  runId: number,
  params?: { includeRows?: boolean },
): Promise<ScreenerRun> {
  const url = new URL(`/api/screener-v3/runs/${runId}`, window.location.origin)
  if (params?.includeRows) url.searchParams.set('include_rows', '1')
  const res = await fetch(url.toString())
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load screener run (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as ScreenerRun
}

export async function listScreenerRuns(params?: {
  limit?: number
  offset?: number
  includeRows?: boolean
}): Promise<ScreenerRun[]> {
  const url = new URL('/api/screener-v3/runs', window.location.origin)
  if (params?.limit != null) url.searchParams.set('limit', String(params.limit))
  if (params?.offset != null) url.searchParams.set('offset', String(params.offset))
  if (params?.includeRows) url.searchParams.set('include_rows', '1')
  const res = await fetch(url.toString())
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load screener runs (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as ScreenerRun[]
}

export async function deleteScreenerRun(runId: number): Promise<void> {
  const res = await fetch(`/api/screener-v3/runs/${runId}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to delete run (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
}

export async function cleanupScreenerRuns(payload: {
  max_runs?: number | null
  max_days?: number | null
  dry_run?: boolean
}): Promise<{ deleted: number; remaining: number }> {
  const res = await fetch('/api/screener-v3/runs/cleanup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to cleanup runs (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as { deleted: number; remaining: number }
}

export async function createGroupFromScreenerRun(
  runId: number,
  payload: { name: string; kind?: string; description?: string | null },
): Promise<{ id: number; name: string }> {
  const res = await fetch(`/api/screener-v3/runs/${runId}/create-group`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to create group (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as { id: number; name: string }
}
