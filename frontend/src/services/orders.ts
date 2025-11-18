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

export type Order = {
  id: number
  alert_id?: number | null
  strategy_id?: number | null
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
  status: OrderStatus
  mode: string
  simulated: boolean
  created_at: string
  updated_at: string
  zerodha_order_id?: string | null
  broker_account_id?: string | null
  error_message?: string | null
}

export async function fetchQueueOrders(
  strategyId?: number,
): Promise<Order[]> {
  const url = new URL('/api/orders/queue', window.location.origin)
  if (strategyId != null) {
    url.searchParams.set('strategy_id', String(strategyId))
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
    trigger_price?: number | null
    trigger_percent?: number | null
    order_type?: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
    product?: string
    gtt?: boolean
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
}): Promise<Order[]> {
  const url = new URL('/api/orders/', window.location.origin)
  if (options?.status) {
    url.searchParams.set('status', options.status)
  }
  if (options?.strategyId != null) {
    url.searchParams.set('strategy_id', String(options.strategyId))
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    throw new Error(`Failed to load orders (${res.status})`)
  }
  return (await res.json()) as Order[]
}
