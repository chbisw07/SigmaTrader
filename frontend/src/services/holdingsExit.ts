export type HoldingExitSubscriptionStatus =
  | 'ACTIVE'
  | 'PAUSED'
  | 'TRIGGERED_PENDING'
  | 'ORDER_CREATED'
  | 'COMPLETED'
  | 'ERROR'

export type HoldingExitTriggerKind =
  | 'TARGET_ABS_PRICE'
  | 'TARGET_PCT_FROM_AVG_BUY'
  | 'DRAWDOWN_ABS_PRICE'
  | 'DRAWDOWN_PCT_FROM_PEAK'

export type HoldingExitSizeMode = 'ABS_QTY' | 'PCT_OF_POSITION'
export type HoldingExitDispatchMode = 'MANUAL' | 'AUTO'
export type HoldingExitExecutionTarget = 'LIVE' | 'PAPER'
export type HoldingExitPriceSource = 'LTP'
export type HoldingExitOrderType = 'MARKET'

export type HoldingExitSubscriptionRead = {
  id: number
  user_id: number | null
  broker_name: string
  symbol: string
  exchange: string
  product: string

  trigger_kind: string
  trigger_value: number
  price_source: string

  size_mode: string
  size_value: number
  min_qty: number

  order_type: string
  dispatch_mode: string
  execution_target: string

  status: HoldingExitSubscriptionStatus
  pending_order_id: number | null
  last_error: string | null
  last_evaluated_at: string | null
  last_triggered_at: string | null
  next_eval_at: string | null
  cooldown_seconds: number
  cooldown_until: string | null
  trigger_key: string | null

  created_at: string
  updated_at: string
}

export type HoldingExitSubscriptionCreate = {
  broker_name?: string
  symbol: string
  exchange?: string
  product?: 'CNC' | 'MIS'

  trigger_kind: HoldingExitTriggerKind
  trigger_value: number
  price_source?: HoldingExitPriceSource

  size_mode: HoldingExitSizeMode
  size_value: number
  min_qty?: number

  order_type?: HoldingExitOrderType
  dispatch_mode?: HoldingExitDispatchMode
  execution_target?: HoldingExitExecutionTarget

  cooldown_seconds?: number
}

export type HoldingExitSubscriptionPatch = Partial<
  Pick<
    HoldingExitSubscriptionCreate,
    | 'trigger_kind'
    | 'trigger_value'
    | 'price_source'
    | 'size_mode'
    | 'size_value'
    | 'min_qty'
    | 'dispatch_mode'
    | 'execution_target'
    | 'cooldown_seconds'
  >
>

export type HoldingExitEventRead = {
  id: number
  subscription_id: number
  event_type: string
  event_ts: string
  details: Record<string, unknown>
  price_snapshot?: Record<string, unknown> | null
  created_at: string
}

function extractFastApiDetail(text: string): string {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed?.detail === 'string') return parsed.detail
  } catch {
    // ignore
  }
  return text
}

async function ensureOk(res: Response, prefix: string): Promise<void> {
  if (res.ok) return
  const body = await res.text().catch(() => '')
  const detail = body ? extractFastApiDetail(body) : ''
  throw new Error(`${prefix} (${res.status})${detail ? `: ${detail}` : ''}`)
}

export async function listHoldingsExitSubscriptions(params?: {
  status?: string
  broker_name?: string
  exchange?: string
  symbol?: string
}): Promise<HoldingExitSubscriptionRead[]> {
  const url = new URL('/api/holdings-exit-subscriptions', window.location.origin)
  if (params?.status) url.searchParams.set('status', params.status)
  if (params?.broker_name) url.searchParams.set('broker_name', params.broker_name)
  if (params?.exchange) url.searchParams.set('exchange', params.exchange)
  if (params?.symbol) url.searchParams.set('symbol', params.symbol)
  const res = await fetch(url.toString(), { cache: 'no-store' })
  await ensureOk(res, 'Failed to load holdings exit subscriptions')
  return (await res.json()) as HoldingExitSubscriptionRead[]
}

export async function createHoldingsExitSubscription(
  payload: HoldingExitSubscriptionCreate,
): Promise<HoldingExitSubscriptionRead> {
  const res = await fetch('/api/holdings-exit-subscriptions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await ensureOk(res, 'Failed to create holdings exit subscription')
  return (await res.json()) as HoldingExitSubscriptionRead
}

export async function patchHoldingsExitSubscription(
  id: number,
  patch: HoldingExitSubscriptionPatch,
): Promise<HoldingExitSubscriptionRead> {
  const res = await fetch(`/api/holdings-exit-subscriptions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  await ensureOk(res, 'Failed to update holdings exit subscription')
  return (await res.json()) as HoldingExitSubscriptionRead
}

export async function pauseHoldingsExitSubscription(
  id: number,
): Promise<HoldingExitSubscriptionRead> {
  const res = await fetch(`/api/holdings-exit-subscriptions/${id}/pause`, {
    method: 'POST',
  })
  await ensureOk(res, 'Failed to pause holdings exit subscription')
  return (await res.json()) as HoldingExitSubscriptionRead
}

export async function resumeHoldingsExitSubscription(
  id: number,
): Promise<HoldingExitSubscriptionRead> {
  const res = await fetch(`/api/holdings-exit-subscriptions/${id}/resume`, {
    method: 'POST',
  })
  await ensureOk(res, 'Failed to resume holdings exit subscription')
  return (await res.json()) as HoldingExitSubscriptionRead
}

export async function deleteHoldingsExitSubscription(id: number): Promise<void> {
  const res = await fetch(`/api/holdings-exit-subscriptions/${id}`, {
    method: 'DELETE',
  })
  if (res.status === 204) return
  await ensureOk(res, 'Failed to delete holdings exit subscription')
}

export async function listHoldingsExitEvents(
  id: number,
  limit = 200,
): Promise<HoldingExitEventRead[]> {
  const url = new URL(
    `/api/holdings-exit-subscriptions/${id}/events`,
    window.location.origin,
  )
  url.searchParams.set('limit', String(limit))
  const res = await fetch(url.toString(), { cache: 'no-store' })
  await ensureOk(res, 'Failed to load holdings exit events')
  return (await res.json()) as HoldingExitEventRead[]
}

