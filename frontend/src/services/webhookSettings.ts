export type TradingViewWebhookSecret = {
  value: string | null
  source: 'db' | 'env' | 'unset'
}

export async function fetchTradingViewWebhookSecret(): Promise<TradingViewWebhookSecret> {
  const res = await fetch('/api/webhook-settings/tradingview-secret')
  if (!res.ok) {
    throw new Error(`Failed to load TradingView webhook secret (${res.status})`)
  }
  return (await res.json()) as TradingViewWebhookSecret
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

