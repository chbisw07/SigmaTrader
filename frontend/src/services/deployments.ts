export type DeploymentKind = 'STRATEGY' | 'PORTFOLIO_STRATEGY'
export type DeploymentStatus = 'STOPPED' | 'RUNNING' | 'PAUSED' | 'ERROR'

export type DeploymentUniverseSymbol = {
  exchange?: string
  symbol: string
}

export type DeploymentUniverse = {
  target_kind: 'SYMBOL' | 'GROUP'
  group_id?: number | null
  symbols?: DeploymentUniverseSymbol[]
}

export type DeploymentExposureSymbol = {
  exchange: string
  symbol: string
  broker_net_qty: number
  broker_side: string
  deployments_net_qty: number
  deployments_side: string
  combined_net_qty: number
  combined_side: string
}

export type DeploymentExposureSummary = {
  as_of_utc?: string
  broker_name?: string
  execution_target?: string
  symbols?: DeploymentExposureSymbol[]
}

export type DeploymentState = {
  status: DeploymentStatus | string
  last_evaluated_at?: string | null
  next_evaluate_at?: string | null
  last_error?: string | null
  started_at?: string | null
  stopped_at?: string | null
  paused_at?: string | null
  resumed_at?: string | null
  pause_reason?: string | null
  runtime_state?: string | null
  last_decision?: string | null
  last_decision_reason?: string | null
  exposure?: DeploymentExposureSummary | null
}

export type DeploymentStateSummary = {
  open_positions: number
  positions: Array<Record<string, unknown>>
}

export type StrategyDeployment = {
  id: number
  owner_id: number
  name: string
  description?: string | null
  kind: DeploymentKind
  enabled: boolean
  universe: DeploymentUniverse
  config: Record<string, unknown>
  state: DeploymentState
  state_summary: DeploymentStateSummary
  created_at: string
  updated_at: string
}

export type DeploymentAction = {
  id: number
  deployment_id: number
  job_id?: number | null
  kind: string
  payload: Record<string, unknown>
  created_at: string
}

export type DeploymentJobsMetrics = {
  job_counts: Record<string, number>
  oldest_pending_scheduled_for?: string | null
  latest_failed_updated_at?: string | null
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

export async function listDeployments(params?: {
  kind?: DeploymentKind
  enabled?: boolean
}): Promise<StrategyDeployment[]> {
  const url = new URL('/api/deployments/', window.location.origin)
  if (params?.kind) url.searchParams.set('kind', params.kind)
  if (params?.enabled != null) url.searchParams.set('enabled', String(params.enabled))
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load deployments (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment[]
}

export async function getDeployment(id: number): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}`, { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function createDeployment(payload: {
  name: string
  description?: string | null
  kind: DeploymentKind
  enabled?: boolean
  universe: DeploymentUniverse
  config: Record<string, unknown>
}): Promise<StrategyDeployment> {
  const res = await fetch('/api/deployments/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to create deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function updateDeployment(
  id: number,
  payload: Partial<{
    name: string
    description: string | null
    enabled: boolean
    universe: DeploymentUniverse
    config: Record<string, unknown>
  }>,
): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to update deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function deleteDeployment(id: number): Promise<void> {
  const res = await fetch(`/api/deployments/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to delete deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
}

export async function startDeployment(id: number): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}/start`, { method: 'POST' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to start deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function stopDeployment(id: number): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}/stop`, { method: 'POST' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to stop deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function pauseDeployment(
  id: number,
  reason?: string,
): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason ?? null }),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to pause deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function resumeDeployment(id: number): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}/resume`, { method: 'POST' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to resume deployment (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function resolveDirectionMismatch(
  id: number,
  action: 'ADOPT_EXIT_ONLY' | 'FLATTEN_THEN_CONTINUE' | 'IGNORE',
): Promise<StrategyDeployment> {
  const res = await fetch(`/api/deployments/${id}/direction-mismatch/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to resolve direction mismatch (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as StrategyDeployment
}

export async function runDeploymentNow(id: number): Promise<{
  enqueued: boolean
  scheduled_for?: string
}> {
  const res = await fetch(`/api/deployments/${id}/run-now`, { method: 'POST' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to run deployment now (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as { enqueued: boolean; scheduled_for?: string }
}

export async function listDeploymentActions(
  id: number,
  limit = 50,
): Promise<DeploymentAction[]> {
  const url = new URL(`/api/deployments/${id}/actions`, window.location.origin)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load deployment actions (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as DeploymentAction[]
}

export async function getDeploymentJobsMetrics(id: number): Promise<DeploymentJobsMetrics> {
  const res = await fetch(`/api/deployments/${id}/jobs/metrics`, { cache: 'no-store' })
  if (!res.ok) {
    const detail = await readApiError(res)
    throw new Error(
      `Failed to load job metrics (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as DeploymentJobsMetrics
}
