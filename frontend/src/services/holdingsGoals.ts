export type GoalLabel =
  | 'CORE'
  | 'TRADE'
  | 'THEME'
  | 'HEDGE'
  | 'INCOME'
  | 'PARKING'

export type GoalTargetType =
  | 'PCT_FROM_AVG_BUY'
  | 'PCT_FROM_LTP'
  | 'ABSOLUTE_PRICE'

export type HoldingGoal = {
  id: number
  user_id: number
  broker_name: string
  symbol: string
  exchange: string
  label: GoalLabel
  review_date: string
  target_type?: GoalTargetType | null
  target_value?: number | null
  note?: string | null
  created_at: string
  updated_at: string
}

export type HoldingGoalUpsert = {
  symbol: string
  exchange?: string | null
  broker_name?: string | null
  label: GoalLabel
  review_date?: string | null
  target_type?: GoalTargetType | null
  target_value?: number | null
  note?: string | null
}

export async function fetchHoldingGoals(params?: {
  broker_name?: string
}): Promise<HoldingGoal[]> {
  const url = new URL('/api/holdings-goals', window.location.origin)
  if (params?.broker_name) {
    url.searchParams.set('broker_name', params.broker_name)
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load holding goals (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoal[]
}

export async function upsertHoldingGoal(
  payload: HoldingGoalUpsert,
): Promise<HoldingGoal> {
  const res = await fetch('/api/holdings-goals', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to save holding goal (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoal
}

export async function deleteHoldingGoal(params: {
  symbol: string
  exchange?: string | null
  broker_name?: string | null
}): Promise<{ deleted: boolean }> {
  const url = new URL('/api/holdings-goals', window.location.origin)
  url.searchParams.set('symbol', params.symbol)
  if (params.exchange) url.searchParams.set('exchange', params.exchange)
  if (params.broker_name) {
    url.searchParams.set('broker_name', params.broker_name)
  }
  const res = await fetch(url.toString(), { method: 'DELETE' })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to delete holding goal (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as { deleted: boolean }
}
