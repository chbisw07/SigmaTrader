export type AlertVariableDef = {
  name: string
  dsl?: string | null
  kind?: string | null
  params?: Record<string, unknown> | null
}

export type AlertDefinition = {
  id: number
  name: string
  broker_name: string
  target_kind: string
  target_ref: string
  symbol?: string | null
  exchange?: string | null
  action_type: 'ALERT_ONLY' | 'BUY' | 'SELL'
  action_params: Record<string, unknown>
  evaluation_cadence: string
  variables: AlertVariableDef[]
  condition_dsl: string
  trigger_mode: 'ONCE' | 'ONCE_PER_BAR' | 'EVERY_TIME'
  throttle_seconds?: number | null
  only_market_hours: boolean
  expires_at?: string | null
  enabled: boolean
  last_evaluated_at?: string | null
  last_triggered_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type AlertDefinitionCreate = {
  name: string
  broker_name?: string
  target_kind: string
  target_ref?: string | null
  symbol?: string | null
  exchange?: string | null
  action_type: 'ALERT_ONLY' | 'BUY' | 'SELL'
  action_params: Record<string, unknown>
  evaluation_cadence?: string | null
  variables: AlertVariableDef[]
  condition_dsl: string
  trigger_mode: 'ONCE' | 'ONCE_PER_BAR' | 'EVERY_TIME'
  throttle_seconds?: number | null
  only_market_hours: boolean
  expires_at?: string | null
  enabled: boolean
}

export type AlertDefinitionUpdate = Partial<AlertDefinitionCreate>

export type CustomIndicator = {
  id: number
  name: string
  description?: string | null
  params: string[]
  body_dsl: string
  enabled: boolean
  created_at?: string | null
  updated_at?: string | null
}

export type CustomIndicatorCreate = Omit<CustomIndicator, 'id' | 'created_at' | 'updated_at'>
export type CustomIndicatorUpdate = Partial<CustomIndicatorCreate>

export type AlertEvent = {
  id: number
  alert_definition_id: number
  symbol: string
  exchange?: string | null
  evaluation_cadence?: string | null
  reason?: string | null
  snapshot: Record<string, unknown>
  triggered_at: string
  bar_time?: string | null
}

export type AlertV3TestRequest = {
  broker_name?: string
  target_kind: string
  target_ref?: string | null
  symbol?: string | null
  exchange?: string | null
  evaluation_cadence?: string | null
  variables: AlertVariableDef[]
  condition_dsl: string
}

export type AlertV3TestResult = {
  symbol: string
  exchange: string
  matched: boolean
  bar_time?: string | null
  snapshot: Record<string, unknown>
  error?: string | null
}

export type AlertV3TestResponse = {
  evaluation_cadence: string
  results: AlertV3TestResult[]
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

export async function listAlertDefinitions(): Promise<AlertDefinition[]> {
  const res = await fetch('/api/alerts-v3/')
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to load alerts (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as AlertDefinition[]
}

export async function createAlertDefinition(
  payload: AlertDefinitionCreate,
): Promise<AlertDefinition> {
  const res = await fetch('/api/alerts-v3/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to create alert (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as AlertDefinition
}

export async function updateAlertDefinition(
  id: number,
  payload: AlertDefinitionUpdate,
): Promise<AlertDefinition> {
  const res = await fetch(`/api/alerts-v3/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to update alert (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as AlertDefinition
}

export async function deleteAlertDefinition(id: number): Promise<void> {
  const res = await fetch(`/api/alerts-v3/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to delete alert (${res.status})${detail ? `: ${detail}` : ''}`)
  }
}

export async function listCustomIndicators(): Promise<CustomIndicator[]> {
  const res = await fetch('/api/alerts-v3/indicators/')
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(
      `Failed to load custom indicators (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as CustomIndicator[]
}

export async function createCustomIndicator(
  payload: CustomIndicatorCreate,
): Promise<CustomIndicator> {
  const res = await fetch('/api/alerts-v3/indicators/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(
      `Failed to create custom indicator (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as CustomIndicator
}

export async function updateCustomIndicator(
  id: number,
  payload: CustomIndicatorUpdate,
): Promise<CustomIndicator> {
  const res = await fetch(`/api/alerts-v3/indicators/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(
      `Failed to update custom indicator (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as CustomIndicator
}

export async function deleteCustomIndicator(id: number): Promise<void> {
  const res = await fetch(`/api/alerts-v3/indicators/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(
      `Failed to delete custom indicator (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
}

export async function listAlertEvents(params?: {
  alertId?: number
  symbol?: string
  limit?: number
}): Promise<AlertEvent[]> {
  const url = new URL('/api/alerts-v3/events/', window.location.origin)
  if (params?.alertId != null) url.searchParams.set('alert_id', String(params.alertId))
  if (params?.symbol) url.searchParams.set('symbol', params.symbol)
  if (params?.limit != null) url.searchParams.set('limit', String(params.limit))

  const res = await fetch(url.toString())
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to load events (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as AlertEvent[]
}

export async function testAlertExpression(
  payload: AlertV3TestRequest,
  options?: { limit?: number },
): Promise<AlertV3TestResponse> {
  const url = new URL('/api/alerts-v3/test', window.location.origin)
  if (options?.limit != null) url.searchParams.set('limit', String(options.limit))

  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await _parseError(res)
    throw new Error(`Failed to test expression (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as AlertV3TestResponse
}
