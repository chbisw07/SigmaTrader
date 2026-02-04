export type ExecutionMode = 'AUTO' | 'MANUAL'
export type ExecutionTarget = 'LIVE' | 'PAPER'
export type StrategyScope = 'GLOBAL' | 'LOCAL'

export type Strategy = {
  id: number
  name: string
  description?: string | null
  execution_mode: ExecutionMode
  execution_target: ExecutionTarget
  paper_poll_interval_sec?: number | null
  enabled: boolean
  scope?: StrategyScope | null
  dsl_expression?: string | null
  is_builtin: boolean
  available_for_alert: boolean
}

export type StrategyCreate = {
  name: string
  description?: string | null
  execution_mode?: ExecutionMode
  execution_target?: ExecutionTarget
  paper_poll_interval_sec?: number | null
  enabled?: boolean
  scope?: StrategyScope | null
  dsl_expression?: string | null
  available_for_alert?: boolean
}

export async function listStrategyTemplates(
  symbol?: string,
  scope?: StrategyScope,
): Promise<Strategy[]> {
  const url = new URL('/api/strategies/templates', window.location.origin)
  if (symbol) {
    url.searchParams.set('symbol', symbol)
  }
  if (scope) {
    url.searchParams.set('scope', scope)
  }

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load strategy templates (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as Strategy[]
}

export async function listStrategies(): Promise<Strategy[]> {
  const res = await fetch('/api/strategies/')
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load strategies (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Strategy[]
}

export async function createStrategyTemplate(
  payload: StrategyCreate,
): Promise<Strategy> {
  const res = await fetch('/api/strategies/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to create strategy (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Strategy
}

export async function deleteStrategy(id: number): Promise<void> {
  const res = await fetch(`/api/strategies/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to delete strategy (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
}
