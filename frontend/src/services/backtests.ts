export type BacktestKind = 'SIGNAL' | 'PORTFOLIO' | 'EXECUTION'
export type BacktestStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'

export type UniverseSymbol = {
  symbol: string
  exchange?: string
}

export type BacktestUniverse = {
  mode: 'HOLDINGS' | 'GROUP' | 'BOTH'
  broker_name?: 'zerodha' | 'angelone'
  group_id?: number | null
  symbols?: UniverseSymbol[]
}

export type BacktestRun = {
  id: number
  owner_id?: number | null
  kind: BacktestKind
  status: BacktestStatus | string
  title?: string | null
  config: Record<string, unknown>
  result?: Record<string, unknown> | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
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

export async function createBacktestRun(payload: {
  kind: BacktestKind
  title?: string | null
  universe: BacktestUniverse
  config: Record<string, unknown>
}): Promise<BacktestRun> {
  const res = await fetch('/api/backtests/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to create backtest run (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as BacktestRun
}

export async function listBacktestRuns(params?: {
  kind?: BacktestKind
  limit?: number
}): Promise<BacktestRun[]> {
  const url = new URL('/api/backtests/runs', window.location.origin)
  if (params?.kind) url.searchParams.set('kind', params.kind)
  if (params?.limit != null) url.searchParams.set('limit', String(params.limit))
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load backtest runs (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as BacktestRun[]
}

export async function getBacktestRun(id: number): Promise<BacktestRun> {
  const res = await fetch(`/api/backtests/runs/${id}`, { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load backtest run (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as BacktestRun
}

