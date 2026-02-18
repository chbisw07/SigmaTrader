export type KiteMcpStatus = {
  server_url?: string | null
  connected: boolean
  authorized: boolean
  server_info?: Record<string, unknown>
  capabilities?: Record<string, unknown>
  last_error?: string | null
}

export type KiteMcpAuthStart = {
  warning_text: string
  login_url: string
}

export type KiteMcpTool = {
  name: string
  description?: string
  inputSchema?: any
  annotations?: any
}

export async function fetchKiteMcpStatus(): Promise<KiteMcpStatus> {
  const res = await fetch('/api/mcp/kite/status')
  if (!res.ok) throw new Error(`Failed to load Kite MCP status (${res.status})`)
  return (await res.json()) as KiteMcpStatus
}

export async function startKiteMcpAuth(): Promise<KiteMcpAuthStart> {
  const res = await fetch('/api/mcp/kite/auth/start')
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to start auth (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as KiteMcpAuthStart
}

export async function listKiteMcpTools(): Promise<KiteMcpTool[]> {
  const res = await fetch('/api/mcp/kite/tools/list', { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to list tools (${res.status})${body ? `: ${body}` : ''}`)
  }
  const data = (await res.json()) as { tools: KiteMcpTool[] }
  return data.tools ?? []
}

export async function callKiteMcpTool(payload: {
  name: string
  arguments: Record<string, unknown>
}): Promise<Record<string, unknown>> {
  const res = await fetch('/api/mcp/kite/tools/call', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Tool call failed (${res.status})${body ? `: ${body}` : ''}`)
  }
  const data = (await res.json()) as { result: Record<string, unknown> }
  return data.result ?? {}
}

export async function fetchKiteMcpSnapshot(account_id?: string): Promise<any> {
  const url = new URL('/api/mcp/kite/snapshot/fetch', window.location.origin)
  if (account_id) url.searchParams.set('account_id', account_id)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to fetch snapshot (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as any
}
