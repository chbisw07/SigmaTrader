export type AngeloneStatus = {
  connected: boolean
  updated_at?: string | null
  client_code?: string | null
  name?: string | null
  error?: string | null
}

export async function fetchAngeloneStatus(): Promise<AngeloneStatus> {
  const res = await fetch('/api/angelone/status')
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to fetch AngelOne status (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as AngeloneStatus
}

export async function connectAngelone(payload: {
  client_code: string
  password: string
  totp: string
}): Promise<void> {
  const res = await fetch('/api/angelone/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to connect AngelOne (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
}

