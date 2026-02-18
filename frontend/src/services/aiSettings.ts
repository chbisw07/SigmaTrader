export type KiteMcpStatus = 'connected' | 'disconnected' | 'error' | 'unknown'

export type AiSettings = {
  feature_flags: {
    ai_assistant_enabled: boolean
    ai_execution_enabled: boolean
    kite_mcp_enabled: boolean
    monitoring_enabled: boolean
  }
  kill_switch: {
    ai_execution_kill_switch: boolean
    execution_disabled_until_ts?: string | null
  }
  kite_mcp: {
    server_url?: string | null
    transport_mode: string
    auth_method: string
    auth_profile_ref?: string | null
    scopes: { read_only: boolean; trade: boolean }
    broker_adapter: string
    last_status: KiteMcpStatus
    last_checked_ts?: string | null
    last_error?: string | null
    capabilities_cache?: Record<string, unknown>
  }
  llm_provider: {
    enabled: boolean
    provider: 'stub' | 'openai' | 'anthropic' | 'local'
    model?: string | null
    do_not_send_pii: boolean
    limits: {
      max_tokens_per_request?: number | null
      max_cost_usd_per_request?: number | null
      max_cost_usd_per_day?: number | null
    }
  }
}

export type AiSettingsUpdate = Partial<{
  feature_flags: Partial<AiSettings['feature_flags']>
  kill_switch: Partial<AiSettings['kill_switch']>
  kite_mcp: Partial<Pick<AiSettings['kite_mcp'], 'server_url' | 'transport_mode' | 'auth_method' | 'auth_profile_ref' | 'scopes' | 'broker_adapter'>>
  llm_provider: Partial<AiSettings['llm_provider']>
}>

export async function fetchAiSettings(): Promise<AiSettings> {
  const res = await fetch('/api/settings/ai')
  if (!res.ok) throw new Error(`Failed to load AI settings (${res.status})`)
  return (await res.json()) as AiSettings
}

export async function updateAiSettings(payload: AiSettingsUpdate): Promise<AiSettings> {
  const res = await fetch('/api/settings/ai', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to update AI settings (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as AiSettings
}

export async function testKiteMcpConnection(payload?: {
  server_url?: string
  fetch_capabilities?: boolean
}): Promise<{
  status: KiteMcpStatus
  checked_ts: string
  error?: string | null
  capabilities?: Record<string, unknown>
}> {
  const res = await fetch('/api/settings/ai/kite/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      server_url: payload?.server_url ?? null,
      fetch_capabilities: payload?.fetch_capabilities ?? true,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to test Kite MCP (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as {
    status: KiteMcpStatus
    checked_ts: string
    error?: string | null
    capabilities?: Record<string, unknown>
  }
}

export async function fetchAiSettingsAudit(params?: {
  category?: 'AI_SETTINGS' | 'KITE_MCP'
  level?: string
  limit?: number
  offset?: number
}): Promise<{ items: any[]; next_offset: number }> {
  const url = new URL('/api/settings/ai/audit', window.location.origin)
  if (params?.category) url.searchParams.set('category', params.category)
  if (params?.level) url.searchParams.set('level', params.level)
  if (params?.limit) url.searchParams.set('limit', String(params.limit))
  if (params?.offset) url.searchParams.set('offset', String(params.offset))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load AI audit (${res.status})`)
  return (await res.json()) as { items: any[]; next_offset: number }
}

