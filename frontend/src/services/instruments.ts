export type InstrumentSearchResult = {
  symbol: string
  exchange: string
  tradingsymbol: string
  name?: string | null
  token?: string | null
}

async function readTextSafe(res: Response): Promise<string> {
  try {
    return await res.text()
  } catch {
    return ''
  }
}

export async function searchInstruments(params: {
  q: string
  broker_name?: string
  exchange?: string | null
  limit?: number
  signal?: AbortSignal
}): Promise<InstrumentSearchResult[]> {
  const q = params.q.trim()
  if (!q) return []
  const url = new URL('/api/instruments/search', window.location.origin)
  url.searchParams.set('q', q)
  url.searchParams.set('limit', String(params.limit ?? 20))
  if (params.broker_name) url.searchParams.set('broker_name', params.broker_name)
  if (params.exchange) url.searchParams.set('exchange', params.exchange)

  const res = await fetch(url.toString(), { cache: 'no-store', signal: params.signal })
  if (!res.ok) {
    const body = await readTextSafe(res)
    throw new Error(`Failed to search instruments (${res.status})${body ? `: ${body}` : ''}`)
  }
  const data = (await res.json()) as unknown
  return Array.isArray(data) ? (data as InstrumentSearchResult[]) : []
}

