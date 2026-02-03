import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AppThemeProvider } from '../themeContext'
import { TimeSettingsProvider } from '../timeSettingsContext'
import { SettingsPage } from './SettingsPage'

function makeCompiledFixture() {
  return {
    context: { product: 'CNC', category: 'LC', scenario: null, symbol: null, strategy_id: null },
    inputs: {
      compiled_at: '2026-01-27T10:00:00Z',
      risk_policy_source: 'db',
      risk_policy_enabled: true,
      risk_engine_v2_enabled: true,
      manual_equity_inr: 1_000_000,
      drawdown_pct: 0.0,
    },
    effective: {
      allow_new_entries: true,
      blocking_reasons: [],
      risk_policy_by_source: {
        TRADINGVIEW: {
          max_daily_loss_pct: 1,
          max_daily_loss_abs: null,
          max_exposure_pct: 60,
          max_open_positions: 6,
          max_concurrent_symbols: 6,
          max_risk_per_trade_pct: 0.5,
          hard_max_risk_pct: 0.75,
          stop_loss_mandatory: true,
          stop_reference: 'ATR',
          atr_period: 14,
          atr_mult_initial_stop: 2,
          fallback_stop_pct: 1,
          trailing_stop_enabled: true,
          max_trades_per_symbol_per_day: 2,
          min_bars_between_trades: 10,
          cooldown_after_loss_bars: 20,
          max_consecutive_losses: 3,
          pause_after_loss_streak: true,
          pause_duration: 'EOD',
        },
        SIGMATRADER: {},
        MANUAL: {},
      },
      risk_engine_v2: {
        drawdown_pct: 0.0,
        drawdown_state: 'NORMAL',
        allow_new_entries: true,
        throttle_multiplier: 1.0,
        profile: { id: 1, name: 'CNC_DEFAULT', product: 'CNC', enabled: true, is_default: true },
        thresholds: { caution_pct: 6, defense_pct: 10, hard_stop_pct: 14 },
        capital_per_trade: 20000,
        max_positions: 6,
        max_exposure_pct: 60,
        risk_per_trade_pct: 0.5,
        hard_risk_pct: 0.75,
        daily_loss_pct: 1,
        hard_daily_loss_pct: 1,
        max_consecutive_losses: 3,
        entry_cutoff_time: null,
        force_squareoff_time: null,
        max_trades_per_day: null,
        max_trades_per_symbol_per_day: 2,
        min_bars_between_trades: 10,
        cooldown_after_loss_bars: 20,
        slippage_guard_bps: null,
        gap_guard_pct: null,
      },
    },
    overrides: [],
    provenance: {},
  }
}

function renderRiskSettings() {
  render(
    <MemoryRouter initialEntries={['/settings?tab=risk']}>
      <AppThemeProvider>
        <TimeSettingsProvider>
          <SettingsPage />
        </TimeSettingsProvider>
      </AppThemeProvider>
    </MemoryRouter>,
  )
}

describe('SettingsPage Risk settings (unified)', () => {
  beforeEach(() => {
    let v2Enabled = true
    let unifiedGlobal = {
      enabled: true,
      manual_override_enabled: false,
      baseline_equity_inr: 1_000_000,
      updated_at: null,
    }
    let sourceOverrides: unknown[] = []
    let holdingsExitCfg = { enabled: false, allowlist_symbols: null, source: 'db', updated_at: null }

    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()

      if (url.includes('/api/risk/global') && (!init || !init.method || init.method === 'GET')) {
        return { ok: true, json: async () => unifiedGlobal } as unknown as Response
      }
      if (url.includes('/api/risk/global') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        unifiedGlobal = { ...unifiedGlobal, ...(body ?? {}) }
        return { ok: true, json: async () => unifiedGlobal } as unknown as Response
      }

      if (url.includes('/api/risk/source-overrides') && (!init || !init.method || init.method === 'GET')) {
        return { ok: true, json: async () => sourceOverrides } as unknown as Response
      }
      if (url.includes('/api/risk/source-overrides') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        const key = `${body?.source_bucket}:${body?.product}`
        sourceOverrides = (sourceOverrides as any[]).filter(
          (r) => `${r?.source_bucket}:${r?.product}` !== key,
        )
        sourceOverrides.push({ ...body, updated_at: null })
        return { ok: true, json: async () => ({ ...body, updated_at: null }) } as unknown as Response
      }
      if (url.includes('/api/risk/source-overrides/') && init?.method === 'DELETE') {
        const parts = url.split('/api/risk/source-overrides/')[1]?.split('/') ?? []
        const key = `${decodeURIComponent(parts[0] ?? '')}:${decodeURIComponent(parts[1] ?? '')}`
        sourceOverrides = (sourceOverrides as any[]).filter(
          (r) => `${r?.source_bucket}:${r?.product}` !== key,
        )
        return { ok: true, json: async () => ({ deleted: true }) } as unknown as Response
      }

      if (url.includes('/api/holdings-exit/config') && (!init || !init.method || init.method === 'GET')) {
        return { ok: true, json: async () => holdingsExitCfg } as unknown as Response
      }
      if (url.includes('/api/holdings-exit/config') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        holdingsExitCfg = { ...holdingsExitCfg, ...(body ?? {}) }
        return { ok: true, json: async () => holdingsExitCfg } as unknown as Response
      }

      if (url.includes('/api/risk-engine/v2-enabled') && (!init || !init.method || init.method === 'GET')) {
        return {
          ok: true,
          json: async () => ({ enabled: v2Enabled, source: 'db', updated_at: null }),
        } as unknown as Response
      }
      if (url.includes('/api/risk-engine/v2-enabled') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        v2Enabled = Boolean(body?.enabled)
        return {
          ok: true,
          json: async () => ({ enabled: v2Enabled, source: 'db', updated_at: null }),
        } as unknown as Response
      }

      if (url.includes('/api/risk/compiled')) {
        return { ok: true, json: async () => makeCompiledFixture() } as unknown as Response
      }

      if (url.includes('/api/risk-engine/risk-profiles')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.includes('/api/risk-engine/drawdown-thresholds')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.includes('/api/risk-engine/decision-log')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }

      return { ok: true, json: async () => ({}) } as unknown as Response
    })

    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders unified risk panels and hides legacy execution defaults', async () => {
    renderRiskSettings()

    await waitFor(() => {
      expect(screen.getByText('Risk globals')).toBeInTheDocument()
    })

    expect(screen.getByText('Product risk profiles')).toBeInTheDocument()
    expect(screen.getByText('Source overrides')).toBeInTheDocument()

    // Only one equity baseline input should exist in the unified UI.
    expect(screen.getAllByLabelText('Baseline equity (INR)')).toHaveLength(1)

    // Legacy panel removed from the unified settings flow.
    expect(screen.queryByText('Execution defaults')).toBeNull()
    expect(screen.queryByText('Equity baseline (manual)')).toBeNull()
  })

  it('persists global enforcement toggle via /api/risk/global', async () => {
    renderRiskSettings()

    const toggle = await screen.findByRole('checkbox', { name: /enable risk enforcement/i })
    expect(toggle).toBeChecked()

    fireEvent.click(toggle)
    expect(toggle).not.toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: /save globals/i }))

    await waitFor(() => {
      const putCall = (globalThis.fetch as any).mock.calls.find(
        (c: any[]) => String(c[0]).includes('/api/risk/global') && c[1]?.method === 'PUT',
      )
      expect(putCall).toBeTruthy()
    })
  })

  it('disables product risk profiles when v2 is OFF', async () => {
    const fetchMock = vi.fn()
    let v2Enabled = false
    const unifiedGlobal = {
      enabled: true,
      manual_override_enabled: false,
      baseline_equity_inr: 1_000_000,
      updated_at: null,
    }

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/api/risk/global')) {
        return { ok: true, json: async () => unifiedGlobal } as unknown as Response
      }
      if (url.includes('/api/risk/source-overrides')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.includes('/api/holdings-exit/config')) {
        return { ok: true, json: async () => ({ enabled: false, allowlist_symbols: null, source: 'db', updated_at: null }) } as unknown as Response
      }
      if (url.includes('/api/risk-engine/v2-enabled') && (!init || !init.method || init.method === 'GET')) {
        return {
          ok: true,
          json: async () => ({ enabled: v2Enabled, source: 'db', updated_at: null }),
        } as unknown as Response
      }
      if (url.includes('/api/risk-engine/v2-enabled') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        v2Enabled = Boolean(body?.enabled)
        return {
          ok: true,
          json: async () => ({ enabled: v2Enabled, source: 'db', updated_at: null }),
        } as unknown as Response
      }
      if (url.includes('/api/risk/compiled')) {
        const compiled = makeCompiledFixture()
        compiled.inputs.risk_engine_v2_enabled = false
        return { ok: true, json: async () => compiled } as unknown as Response
      }
      if (url.includes('/api/risk-engine/risk-profiles')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.includes('/api/risk-engine/drawdown-thresholds')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      if (url.includes('/api/risk-engine/decision-log')) {
        return { ok: true, json: async () => [] } as unknown as Response
      }
      return { ok: true, json: async () => ({}) } as unknown as Response
    })

    vi.stubGlobal('fetch', fetchMock)

    renderRiskSettings()

    await waitFor(() => {
      expect(screen.getByText('Product risk profiles')).toBeInTheDocument()
    })

    const createBtn = screen.getByRole('button', { name: /create profile/i })
    await waitFor(() => {
      expect(createBtn).toBeDisabled()
    })
  })
})
