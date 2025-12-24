export type SystemEvent = {
  id: number
  level: string
  category: string
  message: string
  details?: string | null
  correlation_id?: string | null
  created_at: string
}

export async function fetchSystemEvents(
  params?: { level?: string; category?: string; limit?: number },
): Promise<SystemEvent[]> {
  const url = new URL('/api/system-events/', window.location.origin)
  if (params?.level) {
    url.searchParams.set('level', params.level)
  }
  if (params?.category) {
    url.searchParams.set('category', params.category)
  }
  if (params?.limit) {
    url.searchParams.set('limit', String(params.limit))
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Failed to load system events (${res.status})`)
  }
  return (await res.json()) as SystemEvent[]
}

export async function cleanupSystemEvents(payload: {
  max_days: number
  dry_run?: boolean
}): Promise<{ deleted: number; remaining: number }> {
  const res = await fetch('/api/system-events/cleanup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`Failed to cleanup system events (${res.status})`)
  }
  return (await res.json()) as { deleted: number; remaining: number }
}
