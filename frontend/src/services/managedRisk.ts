import type { RiskSpec } from './orders'

export type ManagedRiskPosition = {
  id: number
  user_id?: number | null
  entry_order_id: number
  exit_order_id?: number | null
  exit_order_status?: string | null
  broker_name: string
  symbol: string
  exchange: string
  product: string
  side: string
  qty: number
  execution_target: string
  entry_price: number
  stop_distance?: number | null
  trail_distance?: number | null
  activation_distance?: number | null
  current_stop?: number | null
  best_favorable_price: number
  trail_price?: number | null
  is_trailing_active: boolean
  last_ltp?: number | null
  status: string
  exit_reason?: string | null
  created_at: string
  updated_at: string
  risk_spec?: RiskSpec | null
}

export async function fetchManagedRiskPositions(params?: {
  status?: string
  broker_name?: string
  include_exited?: boolean
}): Promise<ManagedRiskPosition[]> {
  const url = new URL('/api/managed-risk/positions', window.location.origin)
  if (params?.status) {
    url.searchParams.set('status', params.status)
  }
  if (params?.broker_name) {
    url.searchParams.set('broker_name', params.broker_name)
  }
  if (params?.include_exited) {
    url.searchParams.set('include_exited', 'true')
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Failed to load managed risk (${res.status})`)
  }
  return (await res.json()) as ManagedRiskPosition[]
}

export async function exitManagedRiskPosition(
  positionId: number,
): Promise<ManagedRiskPosition> {
  const res = await fetch(`/api/managed-risk/positions/${positionId}/exit`, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to exit position (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as ManagedRiskPosition
}

export async function pauseManagedRiskPosition(
  positionId: number,
): Promise<ManagedRiskPosition> {
  const res = await fetch(`/api/managed-risk/positions/${positionId}/pause`, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to pause position (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as ManagedRiskPosition
}

export async function resumeManagedRiskPosition(
  positionId: number,
): Promise<ManagedRiskPosition> {
  const res = await fetch(`/api/managed-risk/positions/${positionId}/resume`, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to resume position (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as ManagedRiskPosition
}

export async function updateManagedRiskSpec(
  positionId: number,
  riskSpec: RiskSpec,
): Promise<ManagedRiskPosition> {
  const res = await fetch(`/api/managed-risk/positions/${positionId}/risk-spec`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(riskSpec),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(
      `Failed to update risk spec (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as ManagedRiskPosition
}
