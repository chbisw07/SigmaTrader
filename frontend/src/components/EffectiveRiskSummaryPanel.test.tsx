import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EffectiveRiskSummaryPanel } from './EffectiveRiskSummaryPanel'

let clipboardWriteTextMock: ReturnType<typeof vi.fn>

function makeFixture(product: 'CNC' | 'MIS' = 'CNC') {
  return {
    context: { product, category: 'LC', scenario: null, symbol: null, strategy_id: null },
    inputs: {
      compiled_at: '2026-01-27T10:00:00Z',
      risk_policy_source: 'db',
      risk_policy_enabled: true,
      risk_engine_v2_enabled: true,
      manual_equity_inr: 1000000,
      drawdown_pct: 1.2,
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
        drawdown_pct: 1.2,
        drawdown_state: 'NORMAL',
        allow_new_entries: true,
        throttle_multiplier: 1.0,
        profile: { id: 1, name: `${product}_DEFAULT`, product, enabled: true, is_default: true },
        thresholds: { caution_pct: 6, defense_pct: 10, hard_stop_pct: 14 },
        capital_per_trade: 20000,
        max_positions: 6,
        max_exposure_pct: 60,
        risk_per_trade_pct: 0.5,
        hard_risk_pct: 0.75,
        daily_loss_pct: 1,
        hard_daily_loss_pct: 1,
        max_consecutive_losses: 3,
        entry_cutoff_time: '14:55',
        force_squareoff_time: '15:15',
        max_trades_per_day: 10,
        max_trades_per_symbol_per_day: 2,
        min_bars_between_trades: 10,
        cooldown_after_loss_bars: 20,
        slippage_guard_bps: 10,
        gap_guard_pct: 1,
      },
    },
    overrides: [],
    provenance: {
      'risk_engine_v2.profile': { source: 'profile', detail: 'default profile' },
      'risk_engine_v2.thresholds': { source: 'drawdown_settings', detail: null },
      'risk_engine_v2.drawdown_state': { source: 'computed', detail: null },
    },
  }
}

describe('EffectiveRiskSummaryPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    clipboardWriteTextMock = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: clipboardWriteTextMock },
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches compiled policy and renders key sections', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => makeFixture('CNC'),
    } as unknown as Response)
    vi.stubGlobal('fetch', fetchMock)

    render(<EffectiveRiskSummaryPanel />)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })

    expect(screen.getByText('Effective Risk Summary')).toBeInTheDocument()
    expect(screen.getByText('Throttle multiplier')).toBeInTheDocument()
    expect(screen.getByText('Stops model (Risk policy)')).toBeInTheDocument()
  })

  it('refetches on context change and supports copy/export', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      const product = url.includes('product=MIS') ? 'MIS' : 'CNC'
      return { ok: true, json: async () => makeFixture(product) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<EffectiveRiskSummaryPanel />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    fireEvent.mouseDown(screen.getByLabelText('effective-risk-scenario-mode'))
    fireEvent.click(screen.getByRole('option', { name: /manual what-if/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(String(fetchMock.mock.calls[1]?.[0] ?? '')).toContain('scenario=NORMAL')

    fireEvent.mouseDown(screen.getByLabelText('effective-risk-product'))
    fireEvent.click(screen.getByRole('option', { name: 'MIS' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(String(fetchMock.mock.calls[2]?.[0] ?? '')).toContain('product=MIS')

    expect(navigator.clipboard.writeText).toBe(clipboardWriteTextMock)

    fireEvent.click(screen.getByRole('button', { name: /copy summary/i }))
    await waitFor(() => expect(clipboardWriteTextMock).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: /export json/i }))
    expect(clipboardWriteTextMock).toHaveBeenCalledWith(expect.stringContaining('"context"'))
  })
})
