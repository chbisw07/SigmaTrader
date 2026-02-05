export type RiskSettingsBundleV1 = {
  schema_version: 1
  exported_at?: string | null
  exported_by?: string | null
  warnings?: string[]
  counts?: Record<string, number>

  global_settings: {
    enabled: boolean
    manual_override_enabled: boolean
    baseline_equity_inr: number
  }

  risk_profiles: unknown[]
  drawdown_thresholds: unknown[]
  source_overrides: unknown[]

  symbol_categories_global?: unknown[]
  symbol_categories_user?: unknown[]

  holdings_exit_config: {
    enabled: boolean
    allowlist_symbols?: string | null
  }
}

export type RiskSettingsImportResult = {
  ok: boolean
  imported_at: string
  counts: Record<string, number>
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

export async function exportRiskSettingsBundle(): Promise<RiskSettingsBundleV1> {
  const res = await fetch('/api/risk-backup/export', { cache: 'no-store' })
  await ensureOk(res, 'Failed to export risk settings')
  return (await res.json()) as RiskSettingsBundleV1
}

export async function importRiskSettingsBundle(
  payload: RiskSettingsBundleV1,
  opts?: { force?: boolean },
): Promise<RiskSettingsImportResult> {
  const url = new URL('/api/risk-backup/import', window.location.origin)
  if (opts?.force) url.searchParams.set('force', '1')
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await ensureOk(res, 'Failed to import risk settings')
  return (await res.json()) as RiskSettingsImportResult
}
