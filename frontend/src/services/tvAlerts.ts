export type TvAlert = {
  id: number
  user_id?: number | null
  strategy_id?: number | null
  strategy_name?: string | null
  symbol: string
  exchange?: string | null
  interval?: string | null
  action: string
  qty?: number | null
  price?: number | null
  platform: string
  source: string
  reason?: string | null
  received_at: string
  bar_time?: string | null
  raw_payload: string
}

export async function listTvAlerts(limit = 200): Promise<TvAlert[]> {
  const url = new URL('/api/tv-alerts', window.location.origin)
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load TV alerts (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as TvAlert[]
}

