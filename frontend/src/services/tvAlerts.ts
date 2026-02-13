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

export async function listTvAlerts(options?: {
  limit?: number
  receivedFrom?: string
  receivedTo?: string
}): Promise<TvAlert[]> {
  const url = new URL('/api/tv-alerts', window.location.origin)
  url.searchParams.set('limit', String(options?.limit ?? 200))
  if (options?.receivedFrom) url.searchParams.set('received_from', options.receivedFrom)
  if (options?.receivedTo) url.searchParams.set('received_to', options.receivedTo)
  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load TV alerts (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as TvAlert[]
}
