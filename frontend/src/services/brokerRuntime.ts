import {
  fetchZerodhaLtp,
  fetchZerodhaMargins,
  previewZerodhaOrder,
  type ZerodhaOrderPreviewRequest,
  type ZerodhaOrderPreview,
  type ZerodhaMargins,
  type ZerodhaLtp,
} from './zerodha'

export type BrokerCapabilities = {
  supports_gtt: boolean
  supports_margin_preview: boolean
  supports_order_preview: boolean
  supports_ltp: boolean
}

export type BrokerCapabilitiesInfo = {
  name: string
  label: string
  capabilities: BrokerCapabilities
}

export async function fetchBrokerCapabilities(): Promise<BrokerCapabilitiesInfo[]> {
  const res = await fetch('/api/brokers/capabilities')
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load broker capabilities (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as BrokerCapabilitiesInfo[]
}

export async function syncOrdersForBroker(
  brokerName: string,
): Promise<{ updated: number }> {
  const url = new URL('/api/orders/sync', window.location.origin)
  url.searchParams.set('broker_name', brokerName)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to sync orders (${brokerName}) (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as { updated: number }
}

export async function fetchMarginsForBroker(
  brokerName: string,
): Promise<ZerodhaMargins> {
  if (brokerName === 'zerodha') {
    return fetchZerodhaMargins()
  }
  throw new Error(`Margins not implemented for broker: ${brokerName}`)
}

export async function previewOrderForBroker(
  brokerName: string,
  payload: ZerodhaOrderPreviewRequest,
): Promise<ZerodhaOrderPreview> {
  if (brokerName === 'zerodha') {
    return previewZerodhaOrder(payload)
  }
  throw new Error(`Order preview not implemented for broker: ${brokerName}`)
}

export async function fetchLtpForBroker(
  brokerName: string,
  symbol: string,
  exchange: string,
): Promise<ZerodhaLtp> {
  if (brokerName === 'zerodha') {
    return fetchZerodhaLtp(symbol, exchange)
  }
  throw new Error(`LTP not implemented for broker: ${brokerName}`)
}

