import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AppThemeProvider } from '../themeContext'
import { TimeSettingsProvider } from '../timeSettingsContext'
import type { RiskPolicy } from '../services/riskPolicy'
import { SettingsPage } from './SettingsPage'

function makePolicy(): RiskPolicy {
  return {
    version: 1,
    enabled: true,
    enforcement: {
      account_level: true,
      per_trade: true,
      position_sizing: true,
      stop_rules: true,
      trade_frequency: true,
      loss_controls: true,
      correlation_controls: true,
      execution_safety: true,
      emergency_controls: true,
      overrides: true,
    },
    equity: { equity_mode: 'MANUAL', manual_equity_inr: 1_000_000 },
    account_risk: {
      max_daily_loss_pct: 1,
      max_daily_loss_abs: null,
      max_open_positions: 6,
      max_concurrent_symbols: 6,
      max_exposure_pct: 60,
    },
    trade_risk: {
      max_risk_per_trade_pct: 0.5,
      hard_max_risk_pct: 0.75,
      stop_loss_mandatory: true,
      stop_reference: 'ATR',
    },
    position_sizing: {
      sizing_mode: 'FIXED_CAPITAL',
      capital_per_trade: 20000,
      allow_scale_in: false,
      pyramiding: 1,
    },
    stop_rules: {
      atr_period: 14,
      initial_stop_atr: 2,
      fallback_stop_pct: 1,
      min_stop_distance_pct: 0.5,
      max_stop_distance_pct: 3,
      trailing_stop_enabled: true,
      trail_activation_atr: 2.5,
      trail_activation_pct: 3,
    },
    trade_frequency: { max_trades_per_symbol_per_day: 2, min_bars_between_trades: 10, cooldown_after_loss_bars: 20 },
    loss_controls: { max_consecutive_losses: 3, pause_after_loss_streak: true, pause_duration: 'EOD' },
    correlation_rules: { max_same_sector_positions: 2, sector_correlation_limit: 0.7 },
    execution_safety: {
      allow_mis: false,
      allow_cnc: true,
      allow_short_selling: true,
      max_order_value_pct: 2.5,
      reject_if_margin_exceeded: true,
    },
    emergency_controls: { panic_stop: false, stop_all_trading_on_error: true, stop_on_unexpected_qty: true },
    overrides: {
      TRADINGVIEW: { MIS: {}, CNC: {} },
      SIGMATRADER: { MIS: {}, CNC: {} },
    },
  }
}

function makeCompiledFixture() {
  return {
    context: { product: 'CNC', category: 'LC', scenario: null, symbol: null, strategy_id: null },
    inputs: {
      compiled_at: '2026-01-27T10:00:00Z',
      risk_policy_source: 'db',
      risk_policy_enabled: true,
      risk_engine_v2_enabled: true,
      manual_equity_inr: 1000000,
      drawdown_pct: 0.0,
    },
    effective: {
      allow_new_entries: true,
      blocking_reasons: [],
      risk_policy_by_source: {
        TRADINGVIEW: {
          allow_product: true,
          allow_short_selling: true,
          manual_equity_inr: 1000000,
          max_daily_loss_pct: 1,
          max_daily_loss_abs: null,
          max_exposure_pct: 60,
          max_open_positions: 6,
          max_concurrent_symbols: 6,
          max_order_value_pct: 2.5,
          max_order_value_abs_from_pct: null,
          max_order_value_abs_override: null,
          max_quantity_per_order: null,
          max_risk_per_trade_pct: 0.5,
          hard_max_risk_pct: 0.75,
          stop_loss_mandatory: true,
          capital_per_trade: 20000,
          allow_scale_in: false,
          pyramiding: 1,
          stop_reference: 'ATR',
          atr_period: 14,
          atr_mult_initial_stop: 2,
          fallback_stop_pct: 1,
          min_stop_distance_pct: 0.5,
          max_stop_distance_pct: 3,
          trailing_stop_enabled: true,
          trail_activation_atr: 2.5,
          trail_activation_pct: 3,
          max_trades_per_symbol_per_day: 2,
          min_bars_between_trades: 10,
          cooldown_after_loss_bars: 20,
          max_consecutive_losses: 3,
          pause_after_loss_streak: true,
          pause_duration: 'EOD',
        },
        SIGMATRADER: {
          allow_product: true,
          allow_short_selling: true,
          manual_equity_inr: 1000000,
          max_daily_loss_pct: 1,
          max_daily_loss_abs: null,
          max_exposure_pct: 60,
          max_open_positions: 6,
          max_concurrent_symbols: 6,
          max_order_value_pct: 2.5,
          max_order_value_abs_from_pct: null,
          max_order_value_abs_override: null,
          max_quantity_per_order: null,
          max_risk_per_trade_pct: 0.5,
          hard_max_risk_pct: 0.75,
          stop_loss_mandatory: true,
          capital_per_trade: 20000,
          allow_scale_in: false,
          pyramiding: 1,
          stop_reference: 'ATR',
          atr_period: 14,
          atr_mult_initial_stop: 2,
          fallback_stop_pct: 1,
          min_stop_distance_pct: 0.5,
          max_stop_distance_pct: 3,
          trailing_stop_enabled: true,
          trail_activation_atr: 2.5,
          trail_activation_pct: 3,
          max_trades_per_symbol_per_day: 2,
          min_bars_between_trades: 10,
          cooldown_after_loss_bars: 20,
          max_consecutive_losses: 3,
          pause_after_loss_streak: true,
          pause_duration: 'EOD',
        },
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

describe('SettingsPage Risk settings selective enforcement', () => {
  beforeEach(() => {
    let currentPolicy = makePolicy()
    let v2Enabled = true

    const fetchMock = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
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
      if (url.includes('/api/risk-policy') && (!init || !init.method || init.method === 'GET')) {
        return {
          ok: true,
          json: async () => ({ policy: currentPolicy, source: 'db' }),
        } as unknown as Response
      }
      if (url.includes('/api/risk-policy') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        currentPolicy = body as RiskPolicy
        return { ok: true, json: async () => currentPolicy } as unknown as Response
      }
      if (url.includes('/api/risk-policy/reset') && init?.method === 'POST') {
        currentPolicy = makePolicy()
        return { ok: true, json: async () => currentPolicy } as unknown as Response
      }
      if (url.includes('/api/risk/compiled')) {
        return { ok: true, json: async () => makeCompiledFixture() } as unknown as Response
      }
      return { ok: true, json: async () => ({}) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders all 10 risk groups', async () => {
    render(
      <MemoryRouter initialEntries={['/settings?tab=risk']}>
        <AppThemeProvider>
          <TimeSettingsProvider>
            <SettingsPage />
          </TimeSettingsProvider>
        </AppThemeProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Account-level risk')).toBeInTheDocument()
    })

    expect(screen.getByText('Per-trade risk')).toBeInTheDocument()
    expect(screen.getByText('Position sizing')).toBeInTheDocument()
    expect(screen.getByText('Stop rules & managed exits')).toBeInTheDocument()
    expect(screen.getByText('Trade frequency')).toBeInTheDocument()
    expect(screen.getByText('Loss controls')).toBeInTheDocument()
    expect(screen.getByText('Correlation & symbol controls')).toBeInTheDocument()
    expect(screen.getByText('Execution safety')).toBeInTheDocument()
    expect(screen.getByText('Emergency controls')).toBeInTheDocument()
    expect(screen.getByText('Overrides (source/product)')).toBeInTheDocument()
  })

  it('persists group toggle changes via Save', async () => {
    const fetchMock = vi.fn()
    let currentPolicy = makePolicy()
    let v2Enabled = true

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
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
      if (url.includes('/api/risk-policy') && (!init || !init.method || init.method === 'GET')) {
        return {
          ok: true,
          json: async () => ({ policy: currentPolicy, source: 'db' }),
        } as unknown as Response
      }
      if (url.includes('/api/risk-policy') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        currentPolicy = body as RiskPolicy
        return { ok: true, json: async () => currentPolicy } as unknown as Response
      }
      if (url.includes('/api/risk/compiled')) {
        return { ok: true, json: async () => makeCompiledFixture() } as unknown as Response
      }
      return { ok: true, json: async () => ({}) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/settings?tab=risk']}>
        <AppThemeProvider>
          <TimeSettingsProvider>
            <SettingsPage />
          </TimeSettingsProvider>
        </AppThemeProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Trade frequency')).toBeInTheDocument()
    })

    const tradeGroup = screen.getByTestId('risk-group-trade_frequency')
    const toggle = within(tradeGroup).getByRole('checkbox')
    expect(toggle).toBeChecked()

    fireEvent.click(toggle)
    expect(toggle).not.toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('/api/risk-policy') && c[1]?.method === 'PUT')
      expect(putCall).toBeTruthy()
    })

    const putCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('/api/risk-policy') && c[1]?.method === 'PUT')
    const body = putCall?.[1]?.body ? JSON.parse(String(putCall?.[1]?.body)) : null
    expect(body.enforcement.trade_frequency).toBe(false)
  }, 15000)

  it('disables risk policy fields when enforcement is OFF', async () => {
    render(
      <MemoryRouter initialEntries={['/settings?tab=risk']}>
        <AppThemeProvider>
          <TimeSettingsProvider>
            <SettingsPage />
          </TimeSettingsProvider>
        </AppThemeProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Account-level risk')).toBeInTheDocument()
    })

    const master = screen.getByRole('checkbox', { name: /enable enforcement/i })
    fireEvent.click(master)

    const equityInput = screen.getByRole('spinbutton', { name: /manual equity/i })
    await waitFor(() => {
      expect(equityInput).toBeDisabled()
    })
  }, 15000)

  it('disables risk engine v2 settings when v2 is OFF', async () => {
    const fetchMock = vi.fn()
    let currentPolicy = makePolicy()
    let v2Enabled = false

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
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
      if (url.includes('/api/risk-policy') && (!init || !init.method || init.method === 'GET')) {
        return {
          ok: true,
          json: async () => ({ policy: currentPolicy, source: 'db' }),
        } as unknown as Response
      }
      if (url.includes('/api/risk-policy') && init?.method === 'PUT') {
        const body = init.body ? JSON.parse(String(init.body)) : null
        currentPolicy = body as RiskPolicy
        return { ok: true, json: async () => currentPolicy } as unknown as Response
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

    render(
      <MemoryRouter initialEntries={['/settings?tab=risk']}>
        <AppThemeProvider>
          <TimeSettingsProvider>
            <SettingsPage />
          </TimeSettingsProvider>
        </AppThemeProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Risk engine v2')).toBeInTheDocument()
    })

    const createBtn = screen.getByRole('button', { name: /create profile/i })
    await waitFor(() => {
      expect(createBtn).toBeDisabled()
    })

    const saveThresholds = screen.getByRole('button', { name: /save thresholds/i })
    expect(saveThresholds).toBeDisabled()
  })
})
