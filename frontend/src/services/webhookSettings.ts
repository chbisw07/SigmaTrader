export type TradingViewWebhookSecret = {
  value: string | null
  source: 'db' | 'env' | 'unset'
}

export type TradingViewWebhookConfig = {
  mode: 'MANUAL' | 'AUTO'
  broker_name: string
  execution_target: 'LIVE' | 'PAPER'
  default_product: 'CNC' | 'MIS'
  fallback_to_waiting_on_error: boolean
}

export async function fetchTradingViewWebhookSecret(): Promise<TradingViewWebhookSecret> {
  const res = await fetch('/api/webhook-settings/tradingview-secret')
  if (!res.ok) {
    throw new Error(`Failed to load TradingView webhook secret (${res.status})`)
  }
  return (await res.json()) as TradingViewWebhookSecret
}

export async function fetchTradingViewWebhookConfig(): Promise<TradingViewWebhookConfig> {
  const res = await fetch('/api/webhook-settings/tradingview-config')
  if (!res.ok) {
    throw new Error(`Failed to load TradingView webhook config (${res.status})`)
  }
  return (await res.json()) as TradingViewWebhookConfig
}

export async function updateTradingViewWebhookSecret(
  value: string,
): Promise<TradingViewWebhookSecret> {
  const res = await fetch('/api/webhook-settings/tradingview-secret', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Failed to update TradingView webhook secret (${res.status})${
        detail ? `: ${detail}` : ''
      }`,
    )
  }
  return (await res.json()) as TradingViewWebhookSecret
}

export async function updateTradingViewWebhookConfig(
  payload: Partial<TradingViewWebhookConfig>,
): Promise<TradingViewWebhookConfig> {
  const res = await fetch('/api/webhook-settings/tradingview-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Failed to update TradingView webhook config (${res.status})${
        detail ? `: ${detail}` : ''
      }`,
    )
  }
  return (await res.json()) as TradingViewWebhookConfig
}
