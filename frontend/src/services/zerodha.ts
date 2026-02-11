export type ZerodhaStatus = {
  connected: boolean
  updated_at?: string | null
  user_id?: string
  user_name?: string
  error?: string
  postback_path?: string
  last_postback_at?: string | null
  last_postback_details?: unknown
  last_postback_reject_at?: string | null
  last_postback_reject_details?: unknown
  last_postback_noise_at?: string | null
  last_postback_noise_details?: unknown
}

export type ZerodhaPostbackEvent = {
  id: number
  created_at: string
  level: string
  category: string
  message: string
  correlation_id?: string | null
  details?: unknown
  raw_details?: string | null
}

export type ZerodhaMargins = {
  available: number
  raw: unknown
}

export type ZerodhaOrderPreviewRequest = {
  symbol: string
  exchange: string
  side: string
  qty: number
  product: string
  order_type: string
  price?: number | null
  trigger_price?: number | null
}

export type ZerodhaOrderPreview = {
  required: number
  charges?: unknown
  currency?: string | null
  raw: unknown
}

export type ZerodhaLtp = {
  ltp: number
}

export async function fetchZerodhaLoginUrl(): Promise<string> {
  const res = await fetch('/api/zerodha/login-url')
  if (!res.ok) {
    throw new Error(`Failed to fetch Zerodha login URL (${res.status})`)
  }
  const data = (await res.json()) as { login_url: string }
  return data.login_url
}

export async function fetchZerodhaStatus(): Promise<ZerodhaStatus> {
  const res = await fetch('/api/zerodha/status')
  if (!res.ok) {
    throw new Error(`Failed to fetch Zerodha status (${res.status})`)
  }
  return (await res.json()) as ZerodhaStatus
}

export async function fetchZerodhaPostbackEvents(params?: {
  limit?: number
  include_ok?: boolean
  include_error?: boolean
  include_noise?: boolean
  include_legacy?: boolean
}): Promise<ZerodhaPostbackEvent[]> {
  const url = new URL('/api/zerodha/postback/events', window.location.origin)
  if (params?.limit != null) url.searchParams.set('limit', String(params.limit))
  if (params?.include_ok != null) url.searchParams.set('include_ok', params.include_ok ? 'true' : 'false')
  if (params?.include_error != null) url.searchParams.set('include_error', params.include_error ? 'true' : 'false')
  if (params?.include_noise != null) url.searchParams.set('include_noise', params.include_noise ? 'true' : 'false')
  if (params?.include_legacy != null) url.searchParams.set('include_legacy', params.include_legacy ? 'true' : 'false')

  const res = await fetch(url.toString(), { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`Failed to fetch Zerodha postback events (${res.status})`)
  }
  return (await res.json()) as ZerodhaPostbackEvent[]
}

export async function clearZerodhaPostbackFailures(params?: { include_legacy?: boolean }): Promise<{ deleted: number }> {
  const url = new URL('/api/zerodha/postback/clear-failures', window.location.origin)
  if (params?.include_legacy != null) url.searchParams.set('include_legacy', params.include_legacy ? 'true' : 'false')

  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to clear Zerodha postback failures (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as { deleted: number }
}

export async function connectZerodha(requestToken: string): Promise<void> {
  const res = await fetch('/api/zerodha/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_token: requestToken }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to connect Zerodha (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
}

export async function syncZerodhaOrders(): Promise<{ updated: number }> {
  const res = await fetch('/api/zerodha/sync-orders', {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to sync orders from Zerodha (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as { updated: number }
}

export async function fetchZerodhaMargins(): Promise<ZerodhaMargins> {
  const res = await fetch('/api/zerodha/margins')
  if (!res.ok) {
    throw new Error(`Failed to fetch Zerodha margins (${res.status})`)
  }
  return (await res.json()) as ZerodhaMargins
}

export async function previewZerodhaOrder(
  payload: ZerodhaOrderPreviewRequest,
): Promise<ZerodhaOrderPreview> {
  const res = await fetch('/api/zerodha/order-preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to preview Zerodha order (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as ZerodhaOrderPreview
}

export async function fetchZerodhaLtp(
  symbol: string,
  exchange: string,
): Promise<ZerodhaLtp> {
  const url = new URL('/api/zerodha/ltp', window.location.origin)
  url.searchParams.set('symbol', symbol)
  url.searchParams.set('exchange', exchange)
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Failed to fetch Zerodha LTP (${res.status})`)
  }
  return (await res.json()) as ZerodhaLtp
}
