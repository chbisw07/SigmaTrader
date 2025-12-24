export type SignalStrategyScope = 'USER' | 'GLOBAL'
export type SignalStrategyOutputKind = 'SIGNAL' | 'OVERLAY'
export type SignalStrategyRegime = string
export type SignalStrategyParamType = 'number' | 'string' | 'bool' | 'enum' | 'timeframe'

export type SignalStrategyInputDef = {
  name: string
  type: SignalStrategyParamType
  default?: unknown
  enum_values?: string[] | null
}

export type SignalStrategyOutputDef = {
  name: string
  kind: SignalStrategyOutputKind
  dsl: string
  plot?: string | null
}

export type SignalStrategyVersion = {
  id: number
  strategy_id: number
  version: number
  inputs: SignalStrategyInputDef[]
  variables: import('./alertsV3').AlertVariableDef[]
  outputs: SignalStrategyOutputDef[]
  compatibility: Record<string, unknown>
  enabled: boolean
  created_at: string
}

export type SignalStrategy = {
  id: number
  scope: SignalStrategyScope
  owner_id?: number | null
  name: string
  description?: string | null
  tags: string[]
  regimes: SignalStrategyRegime[]
  latest_version: number
  created_at: string
  updated_at: string
  latest?: SignalStrategyVersion | null
  used_by_alerts?: number
  used_by_screeners?: number
}

export type SignalStrategyVersionCreate = {
  inputs: SignalStrategyInputDef[]
  variables: import('./alertsV3').AlertVariableDef[]
  outputs: SignalStrategyOutputDef[]
  enabled: boolean
}

export type SignalStrategyCreate = {
  name: string
  description?: string | null
  tags: string[]
  regimes: SignalStrategyRegime[]
  scope?: SignalStrategyScope
  version: SignalStrategyVersionCreate
}

export type SignalStrategyUpdate = Partial<{
  name: string
  description?: string | null
  tags: string[]
  regimes: SignalStrategyRegime[]
  scope: SignalStrategyScope
}>

export type SignalStrategyExport = {
  format: string
  name: string
  description?: string | null
  tags: string[]
  regimes: string[]
  scope: string
  versions: any[]
}

async function _parseError(res: Response): Promise<string> {
  const text = await res.text()
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // ignore
  }
  return text
}

export async function listSignalStrategies(opts?: {
  includeLatest?: boolean
  includeUsage?: boolean
}): Promise<SignalStrategy[]> {
  const url = new URL('/api/signal-strategies/', window.location.origin)
  if (opts?.includeLatest != null) url.searchParams.set('include_latest', String(opts.includeLatest))
  if (opts?.includeUsage != null) url.searchParams.set('include_usage', String(opts.includeUsage))
  const res = await fetch(url.toString())
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to load strategies (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategy[]
}

export async function listSignalStrategyVersions(strategyId: number): Promise<SignalStrategyVersion[]> {
  const res = await fetch(`/api/signal-strategies/${strategyId}/versions`)
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to load strategy versions (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategyVersion[]
}

export async function getSignalStrategyVersion(versionId: number): Promise<SignalStrategyVersion> {
  const res = await fetch(`/api/signal-strategies/versions/${versionId}`)
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to load strategy version (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategyVersion
}

export async function createSignalStrategy(payload: SignalStrategyCreate): Promise<SignalStrategy> {
  const res = await fetch('/api/signal-strategies/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to create strategy (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategy
}

export async function createSignalStrategyVersion(
  strategyId: number,
  payload: SignalStrategyVersionCreate,
): Promise<SignalStrategyVersion> {
  const res = await fetch(`/api/signal-strategies/${strategyId}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to create version (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategyVersion
}

export async function updateSignalStrategy(
  strategyId: number,
  payload: SignalStrategyUpdate,
): Promise<SignalStrategy> {
  const res = await fetch(`/api/signal-strategies/${strategyId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to update strategy (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategy
}

export async function deleteSignalStrategy(strategyId: number): Promise<void> {
  const res = await fetch(`/api/signal-strategies/${strategyId}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to delete strategy (${res.status})${detail ? `: ${detail}` : ''}`)
  }
}

export async function exportSignalStrategy(strategyId: number): Promise<SignalStrategyExport> {
  const res = await fetch(`/api/signal-strategies/${strategyId}/export`)
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to export strategy (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategyExport
}

export async function importSignalStrategy(payload: {
  payload: Record<string, unknown>
  replace_existing?: boolean
}): Promise<SignalStrategy> {
  const res = await fetch('/api/signal-strategies/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to import strategy (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as SignalStrategy
}
