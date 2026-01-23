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

export type GoalReviewAction = 'EXTEND' | 'SNOOZE' | 'REVIEWED'

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

export type HoldingGoalReview = {
  id: number
  goal_id: number
  user_id: number
  broker_name: string
  symbol: string
  exchange: string
  action: GoalReviewAction
  previous_review_date: string
  new_review_date: string
  note?: string | null
  created_at: string
}

export type HoldingGoalReviewActionResponse = {
  goal: HoldingGoal
  review: HoldingGoalReview
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

export type HoldingGoalImportMapping = {
  symbol_column: string
  exchange_column?: string | null
  label_column?: string | null
  label_default?: GoalLabel | null
  review_date_column?: string | null
  review_date_default_days?: number | null
  target_value_column?: string | null
  target_type?: GoalTargetType | null
  note_column?: string | null
}

export type HoldingGoalImportError = {
  row_index: number
  symbol?: string | null
  reason: string
}

export type HoldingGoalImportResult = {
  matched: number
  updated: number
  created: number
  skipped: number
  errors: HoldingGoalImportError[]
}

export type HoldingGoalImportPreset = {
  id: number
  name: string
  mapping: HoldingGoalImportMapping
  created_at: string
  updated_at: string
}

export async function fetchHoldingGoals(params?: {
  broker_name?: string
}): Promise<HoldingGoal[]> {
  const url = new URL('/api/holdings-goals/', window.location.origin)
  if (params?.broker_name) {
    url.searchParams.set('broker_name', params.broker_name)
  }
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load holding goals (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoal[]
}

export async function importHoldingGoals(payload: {
  broker_name?: string | null
  mapping: HoldingGoalImportMapping
  rows: Array<Record<string, string>>
  holdings_symbols?: string[]
}): Promise<HoldingGoalImportResult> {
  const res = await fetch('/api/holdings-goals/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to import holding goals (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoalImportResult
}

export async function fetchGoalImportPresets(): Promise<
  HoldingGoalImportPreset[]
> {
  const res = await fetch('/api/holdings-goals/presets', {
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load goal presets (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoalImportPreset[]
}

export async function createGoalImportPreset(payload: {
  name: string
  mapping: HoldingGoalImportMapping
}): Promise<HoldingGoalImportPreset> {
  const res = await fetch('/api/holdings-goals/presets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to save preset (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoalImportPreset
}

export async function deleteGoalImportPreset(
  presetId: number,
): Promise<{ deleted: boolean }> {
  const res = await fetch(`/api/holdings-goals/presets/${presetId}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to delete preset (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as { deleted: boolean }
}

export async function upsertHoldingGoal(
  payload: HoldingGoalUpsert,
): Promise<HoldingGoal> {
  const res = await fetch('/api/holdings-goals/', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
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
  const url = new URL('/api/holdings-goals/', window.location.origin)
  url.searchParams.set('symbol', params.symbol)
  if (params.exchange) url.searchParams.set('exchange', params.exchange)
  if (params.broker_name) {
    url.searchParams.set('broker_name', params.broker_name)
  }
  const res = await fetch(url.toString(), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to delete holding goal (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as { deleted: boolean }
}

export async function applyHoldingGoalReviewAction(payload: {
  symbol: string
  exchange?: string | null
  broker_name?: string | null
  action: GoalReviewAction
  days?: number | null
  note?: string | null
}): Promise<HoldingGoalReviewActionResponse> {
  const res = await fetch('/api/holdings-goals/review-actions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to apply review action (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoalReviewActionResponse
}

export async function listHoldingGoalReviews(params: {
  symbol: string
  exchange?: string | null
  broker_name?: string | null
  limit?: number
}): Promise<HoldingGoalReview[]> {
  const url = new URL('/api/holdings-goals/reviews', window.location.origin)
  url.searchParams.set('symbol', params.symbol)
  if (params.exchange) url.searchParams.set('exchange', params.exchange)
  if (params.broker_name) url.searchParams.set('broker_name', params.broker_name)
  if (params.limit) url.searchParams.set('limit', String(params.limit))
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load review history (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as HoldingGoalReview[]
}
