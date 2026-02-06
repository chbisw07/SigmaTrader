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
