export type ZerodhaStatus = {
  connected: boolean
  updated_at?: string | null
  user_id?: string
  user_name?: string
  error?: string
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
