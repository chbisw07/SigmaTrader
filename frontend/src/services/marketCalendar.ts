export type MarketDefaults = {
  timezone: string
  market_open: string
  market_close: string
}

export type ResolvedMarketSession = {
  exchange: string
  date: string
  session_type: string
  open_time: string | null
  close_time: string | null
  proxy_close_time: string | null
  preferred_sell_window: [string | null, string | null]
  preferred_buy_window: [string | null, string | null]
  mis_force_flatten_window: [string | null, string | null]
}

export type MarketCalendarRow = {
  date: string
  exchange: string
  session_type: string
  open_time?: string | null
  close_time?: string | null
  notes?: string | null
}

export async function fetchMarketDefaults(): Promise<MarketDefaults> {
  const res = await fetch('/api/market-calendar/defaults')
  if (!res.ok) {
    throw new Error(`Failed to load market defaults (${res.status})`)
  }
  return (await res.json()) as MarketDefaults
}

export async function resolveMarketSession(
  exchange: string,
  day: string,
): Promise<ResolvedMarketSession> {
  const res = await fetch(
    `/api/market-calendar/resolve?exchange=${encodeURIComponent(
      exchange,
    )}&day=${encodeURIComponent(day)}`,
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to resolve market session (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as ResolvedMarketSession
}

export async function listMarketCalendarRows(params: {
  exchange: string
  start?: string
  end?: string
  limit?: number
}): Promise<MarketCalendarRow[]> {
  const usp = new URLSearchParams()
  usp.set('exchange', params.exchange)
  if (params.start) usp.set('start', params.start)
  if (params.end) usp.set('end', params.end)
  if (typeof params.limit === 'number') usp.set('limit', String(params.limit))

  const res = await fetch(`/api/market-calendar/?${usp.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to load market calendar (${res.status})`)
  }
  return (await res.json()) as MarketCalendarRow[]
}

export async function uploadMarketCalendarCsv(
  exchange: string,
  file: File,
): Promise<{ inserted: number; updated: number }> {
  const csvText = await file.text()
  const res = await fetch(
    `/api/market-calendar/import?exchange=${encodeURIComponent(exchange)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv' },
      body: csvText,
    },
  )
  if (!res.ok) {
    const bodyText = await res.text()
    throw new Error(
      `Failed to import calendar (${res.status})${
        bodyText ? `: ${bodyText}` : ''
      }`,
    )
  }
  return (await res.json()) as { inserted: number; updated: number }
}

export async function downloadMarketCalendarCsv(exchange: string): Promise<Blob> {
  const res = await fetch(
    `/api/market-calendar/export?exchange=${encodeURIComponent(exchange)}`,
  )
  if (!res.ok) {
    throw new Error(`Failed to export calendar (${res.status})`)
  }
  return await res.blob()
}
