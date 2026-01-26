export type TradingViewHintFieldV1 = {
  key: string
  type: 'string' | 'number' | 'boolean' | 'enum'
  value: unknown
  enum_options?: string[] | null
}

export type TradingViewAlertPayloadBuilderConfigV1 = {
  version: '1.0'
  signal: Record<string, unknown>
  signal_enabled: Record<string, boolean>
  hints: TradingViewHintFieldV1[]
}

export type TradingViewAlertPayloadTemplateSummary = {
  id: number
  name: string
  updated_at: string
}

export type TradingViewAlertPayloadTemplateRead = {
  id: number
  name: string
  config: TradingViewAlertPayloadBuilderConfigV1
  updated_at: string
}

export async function listTradingViewAlertPayloadTemplates(): Promise<
  TradingViewAlertPayloadTemplateSummary[]
> {
  const res = await fetch('/api/webhook-settings/tradingview-alert-payload-templates')
  if (!res.ok) {
    throw new Error(`Failed to load payload templates (${res.status})`)
  }
  return (await res.json()) as TradingViewAlertPayloadTemplateSummary[]
}

export async function fetchTradingViewAlertPayloadTemplate(
  id: number,
): Promise<TradingViewAlertPayloadTemplateRead> {
  const res = await fetch(`/api/webhook-settings/tradingview-alert-payload-templates/${id}`)
  if (!res.ok) {
    throw new Error(`Failed to load payload template (${res.status})`)
  }
  return (await res.json()) as TradingViewAlertPayloadTemplateRead
}

export async function upsertTradingViewAlertPayloadTemplate(payload: {
  name: string
  config: TradingViewAlertPayloadBuilderConfigV1
}): Promise<TradingViewAlertPayloadTemplateRead> {
  const res = await fetch('/api/webhook-settings/tradingview-alert-payload-templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Failed to save payload template (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
  return (await res.json()) as TradingViewAlertPayloadTemplateRead
}

export async function deleteTradingViewAlertPayloadTemplate(id: number): Promise<void> {
  const res = await fetch(`/api/webhook-settings/tradingview-alert-payload-templates/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Failed to delete payload template (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
}

