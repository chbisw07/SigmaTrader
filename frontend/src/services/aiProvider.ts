export type ProviderDescriptor = {
  id: 'openai' | 'google' | 'local_ollama' | 'local_lmstudio' | string
  label: string
  kind: 'remote' | 'local' | string
  requires_api_key: boolean
  supports_base_url: boolean
  default_base_url?: string | null
  supports_model_discovery: boolean
  supports_test: boolean
}

export type AiProviderKey = {
  id: number
  provider: string
  key_name: string
  key_masked: string
  created_at: string
  updated_at: string
}

export type AiActiveConfig = {
  enabled: boolean
  provider: string
  model?: string | null
  base_url?: string | null
  active_key_id?: number | null
  do_not_send_pii: boolean
  limits: {
    max_tokens_per_request?: number | null
    max_cost_usd_per_request?: number | null
    max_cost_usd_per_day?: number | null
  }
  active_key?: AiProviderKey | null
}

export type AiActiveConfigUpdate = Partial<{
  enabled: boolean
  provider: string
  model: string | null
  base_url: string | null
  active_key_id: number | null
  do_not_send_pii: boolean
  limits: AiActiveConfig['limits']
}>

export type ModelEntry = {
  id: string
  label: string
  source: 'discovered' | 'curated' | string
}

export async function fetchAiProviders(): Promise<ProviderDescriptor[]> {
  const res = await fetch('/api/ai/providers')
  if (!res.ok) throw new Error(`Failed to load AI providers (${res.status})`)
  return (await res.json()) as ProviderDescriptor[]
}

export async function fetchAiConfig(): Promise<AiActiveConfig> {
  const res = await fetch('/api/ai/config')
  if (!res.ok) throw new Error(`Failed to load AI config (${res.status})`)
  return (await res.json()) as AiActiveConfig
}

export async function updateAiConfig(payload: AiActiveConfigUpdate): Promise<AiActiveConfig> {
  const res = await fetch('/api/ai/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to update AI config (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as AiActiveConfig
}

export async function listAiKeys(provider: string): Promise<AiProviderKey[]> {
  const url = new URL('/api/ai/keys', window.location.origin)
  url.searchParams.set('provider', provider)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load keys (${res.status})`)
  return (await res.json()) as AiProviderKey[]
}

export async function createAiKey(payload: {
  provider: string
  key_name: string
  api_key_value: string
  meta?: Record<string, unknown>
}): Promise<AiProviderKey> {
  const res = await fetch('/api/ai/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: payload.provider,
      key_name: payload.key_name,
      api_key_value: payload.api_key_value,
      meta: payload.meta ?? {},
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to create key (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as AiProviderKey
}

export async function updateAiKey(
  id: number,
  payload: { key_name?: string; api_key_value?: string; meta?: Record<string, unknown> | null },
): Promise<AiProviderKey> {
  const res = await fetch(`/api/ai/keys/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to update key (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as AiProviderKey
}

export async function deleteAiKey(id: number): Promise<void> {
  const res = await fetch(`/api/ai/keys/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to delete key (${res.status})${body ? `: ${body}` : ''}`)
  }
}

export async function discoverAiModels(payload: {
  provider: string
  base_url?: string | null
  key_id?: number | null
}): Promise<ModelEntry[]> {
  const res = await fetch('/api/ai/models/discover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: payload.provider,
      base_url: payload.base_url ?? null,
      key_id: payload.key_id ?? null,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to discover models (${res.status})${body ? `: ${body}` : ''}`)
  }
  const data = (await res.json()) as { models: ModelEntry[] }
  return data.models ?? []
}

export async function runAiTest(payload: {
  provider: string
  model: string
  base_url?: string | null
  key_id?: number | null
  prompt: string
}): Promise<{ text: string; latency_ms: number; usage: any; raw_metadata: any }> {
  const res = await fetch('/api/ai/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: payload.provider,
      model: payload.model,
      base_url: payload.base_url ?? null,
      key_id: payload.key_id ?? null,
      prompt: payload.prompt,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`AI test failed (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { text: string; latency_ms: number; usage: any; raw_metadata: any }
}

