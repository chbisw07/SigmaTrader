export type OrderStatus =
  | 'WAITING'
  | 'VALIDATED'
  | 'SENDING'
  | 'SENT'
  | 'FAILED'
  | 'EXECUTED'
  | 'PARTIALLY_EXECUTED'
  | 'CANCELLED'
  | 'REJECTED'
  | 'REJECTED_RISK'

export type ExecutionMode = 'MANUAL' | 'AUTO'
export type ExecutionTarget = 'LIVE' | 'PAPER'

export type Order = {
  id: number
  alert_id?: number | null
  strategy_id?: number | null
  portfolio_group_id?: number | null
  broker_name?: string | null
  symbol: string
  exchange?: string | null
  side: string
  qty: number
  price?: number | null
  trigger_price?: number | null
  trigger_percent?: number | null
  order_type: string
  product: string
  gtt: boolean
  synthetic_gtt?: boolean
  trigger_operator?: string | null
  armed_at?: string | null
  last_checked_at?: string | null
  last_seen_price?: number | null
  triggered_at?: string | null
  status: OrderStatus
  mode: string
  execution_target?: ExecutionTarget
  simulated: boolean
  created_at: string
  updated_at: string
  broker_order_id?: string | null
  zerodha_order_id?: string | null
  broker_account_id?: string | null
  error_message?: string | null
}

export async function createManualOrder(payload: {
  broker_name?: string | null
  portfolio_group_id?: number | null
  symbol: string
  exchange?: string | null
  side: 'BUY' | 'SELL'
  qty: number
  price?: number | null
  trigger_price?: number | null
  order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  product: string
  gtt?: boolean
  mode?: ExecutionMode
  execution_target?: ExecutionTarget
}): Promise<Order> {
  const res = await fetch('/api/orders/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to create order (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Order
}

export async function fetchQueueOrders(
  strategyId?: number,
  brokerName?: string,
): Promise<Order[]> {
  const url = new URL('/api/orders/queue', window.location.origin)
  if (strategyId != null) {
    url.searchParams.set('strategy_id', String(strategyId))
  }
  if (brokerName) {
    url.searchParams.set('broker_name', brokerName)
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Failed to load queue (${res.status})`)
  }
  return (await res.json()) as Order[]
}

export async function cancelOrder(orderId: number): Promise<Order> {
  const res = await fetch(`/api/orders/${orderId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'CANCELLED' }),
  })
  if (!res.ok) {
    throw new Error(`Failed to cancel order (${res.status})`)
  }
  return (await res.json()) as Order
}

export async function executeOrder(orderId: number): Promise<Order> {
  const res = await fetch(`/api/orders/${orderId}/execute`, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to execute order (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Order
}

export async function updateOrder(
  orderId: number,
  payload: {
    qty?: number
    price?: number | null
    side?: 'BUY' | 'SELL'
    trigger_price?: number | null
    trigger_percent?: number | null
    order_type?: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
    product?: string
    gtt?: boolean
    execution_target?: ExecutionTarget
  },
): Promise<Order> {
  const res = await fetch(`/api/orders/${orderId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to update order (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as Order
}

export async function fetchOrdersHistory(options?: {
  status?: string
  strategyId?: number
  brokerName?: string
}): Promise<Order[]> {
  const url = new URL('/api/orders/', window.location.origin)
  if (options?.status) {
    url.searchParams.set('status', options.status)
  }
  if (options?.strategyId != null) {
    url.searchParams.set('strategy_id', String(options.strategyId))
  }
  if (options?.brokerName) {
    url.searchParams.set('broker_name', options.brokerName)
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Failed to load orders (${res.status})`)
  }
  return (await res.json()) as Order[]
}
