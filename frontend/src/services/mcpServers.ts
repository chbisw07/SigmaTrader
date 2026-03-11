export type KiteMcpStatus = 'connected' | 'disconnected' | 'error' | 'unknown'

export type McpServerCard = {
  id: string
  label: string
  enabled: boolean
  transport: string
  configured: boolean
  status: KiteMcpStatus
  last_checked_ts?: string | null
  last_error?: string | null
  authorized?: boolean | null
  tools_available_count?: number | null
}

export type McpServersSummaryResponse = {
  monitoring_enabled: boolean
  servers: McpServerCard[]
}

export type KiteMcpServerConfig = {
  enabled: boolean
  monitoring_enabled: boolean
  server_url?: string | null
  transport_mode: string
  auth_method: string
  auth_profile_ref?: string | null
  scopes: { read_only?: boolean; trade?: boolean }
  broker_adapter: string
  last_status: KiteMcpStatus
  last_checked_ts?: string | null
  last_connected_ts?: string | null
  tools_available_count?: number | null
  last_error?: string | null
  capabilities_cache?: Record<string, unknown>
}

export type KiteMcpServerConfigUpdate = Partial<{
  enabled: boolean
  monitoring_enabled: boolean
  server_url: string | null
  transport_mode: string
  auth_method: string
  auth_profile_ref: string | null
  scopes: { read_only?: boolean | null; trade?: boolean | null }
  broker_adapter: string
}>

export type GenericMcpServerConfig = {
  label?: string | null
  enabled: boolean
  transport: 'sse' | 'stdio'
  url?: string | null
  command?: string | null
  args?: string[]
  env?: Record<string, string>
  auth_method?: string
  auth_profile_ref?: string | null
  ai_enabled?: boolean
  last_status?: KiteMcpStatus
  last_checked_ts?: string | null
  last_error?: string | null
  capabilities_cache?: Record<string, unknown>
}

export type McpJsonConfigResponse = {
  config: Record<string, unknown>
}

export type KiteMcpLiveStatus = {
  server_url?: string | null
  connected: boolean
  authorized: boolean
  last_connected_at?: string | null
  tools_available_count?: number | null
  server_info?: Record<string, unknown>
  capabilities?: Record<string, unknown>
  last_error?: string | null
}

export type McpTool = {
  name: string
  description?: string
  inputSchema?: any
  annotations?: any
}

async function readJson<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => null)) as any
  return data as T
}

async function throwHttp(res: Response, prefix: string): Promise<never> {
  const body = await res.text().catch(() => '')
  throw new Error(`${prefix} (${res.status})${body ? `: ${body}` : ''}`)
}

export async function listMcpServers(): Promise<McpServersSummaryResponse> {
  const res = await fetch('/api/mcp/servers')
  if (!res.ok) return throwHttp(res, 'Failed to load MCP servers')
  return await readJson<McpServersSummaryResponse>(res)
}

export async function fetchMcpJsonConfig(): Promise<McpJsonConfigResponse> {
  const res = await fetch('/api/mcp/config')
  if (!res.ok) return throwHttp(res, 'Failed to load MCP config')
  return await readJson<McpJsonConfigResponse>(res)
}

export async function updateMcpJsonConfig(config: Record<string, unknown>): Promise<McpJsonConfigResponse> {
  const res = await fetch('/api/mcp/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  })
  if (!res.ok) return throwHttp(res, 'Failed to update MCP config')
  return await readJson<McpJsonConfigResponse>(res)
}

export async function fetchKiteMcpServerConfig(): Promise<KiteMcpServerConfig> {
  const res = await fetch('/api/mcp/servers/kite/config')
  if (!res.ok) return throwHttp(res, 'Failed to load Kite MCP config')
  return await readJson<KiteMcpServerConfig>(res)
}

export async function updateKiteMcpServerConfig(payload: KiteMcpServerConfigUpdate): Promise<KiteMcpServerConfig> {
  const res = await fetch('/api/mcp/servers/kite/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) return throwHttp(res, 'Failed to update Kite MCP config')
  return await readJson<KiteMcpServerConfig>(res)
}

export async function fetchKiteMcpLiveStatus(): Promise<KiteMcpLiveStatus> {
  const res = await fetch('/api/mcp/servers/kite/status')
  if (!res.ok) return throwHttp(res, 'Failed to load Kite MCP status')
  return await readJson<KiteMcpLiveStatus>(res)
}

export async function startKiteMcpAuth(): Promise<{ warning_text: string; login_url: string }> {
  const res = await fetch('/api/mcp/servers/kite/auth/start', { method: 'POST' })
  if (!res.ok) return throwHttp(res, 'Failed to start Kite auth')
  return await readJson<{ warning_text: string; login_url: string }>(res)
}

export async function testKiteMcpConnection(payload?: {
  server_url?: string | null
  fetch_capabilities?: boolean
}): Promise<{
  status: KiteMcpStatus
  checked_ts: string
  error?: string | null
  capabilities?: Record<string, unknown>
}> {
  const res = await fetch('/api/mcp/servers/kite/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      server_url: payload?.server_url ?? null,
      fetch_capabilities: payload?.fetch_capabilities ?? true,
    }),
  })
  if (!res.ok) return throwHttp(res, 'Failed to test Kite MCP')
  return await readJson(res)
}

export async function fetchKiteMcpSnapshot(account_id?: string): Promise<any> {
  const url = new URL('/api/mcp/servers/kite/snapshot/fetch', window.location.origin)
  if (account_id) url.searchParams.set('account_id', account_id)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) return throwHttp(res, 'Failed to fetch snapshot')
  return await readJson(res)
}

export async function fetchGenericMcpServerConfig(serverId: string): Promise<GenericMcpServerConfig> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(serverId)}/config`)
  if (!res.ok) return throwHttp(res, 'Failed to load MCP server config')
  return await readJson<GenericMcpServerConfig>(res)
}

export async function updateGenericMcpServerConfig(serverId: string, payload: GenericMcpServerConfig): Promise<GenericMcpServerConfig> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(serverId)}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) return throwHttp(res, 'Failed to update MCP server config')
  return await readJson<GenericMcpServerConfig>(res)
}

export async function testMcpServer(serverId: string): Promise<{
  status: KiteMcpStatus
  checked_ts: string
  error?: string | null
  capabilities?: Record<string, unknown>
}> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(serverId)}/test`, { method: 'POST' })
  if (!res.ok) return throwHttp(res, 'Failed to test MCP server')
  return await readJson(res)
}

export async function listMcpTools(serverId: string): Promise<McpTool[]> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(serverId)}/tools/list`, { method: 'POST' })
  if (!res.ok) return throwHttp(res, 'Failed to list tools')
  const data = (await readJson<{ tools: McpTool[] }>(res)) as any
  return data.tools ?? []
}

export async function callMcpTool(payload: {
  serverId: string
  name: string
  arguments: Record<string, unknown>
}): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/mcp/servers/${encodeURIComponent(payload.serverId)}/tools/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: payload.name, arguments: payload.arguments }),
  })
  if (!res.ok) return throwHttp(res, 'Tool call failed')
  const data = (await readJson<{ result: Record<string, unknown> }>(res)) as any
  return data.result ?? {}
}
