import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EffectiveRiskSummaryPanel } from './EffectiveRiskSummaryPanel'

let clipboardWriteTextMock: ReturnType<typeof vi.fn>

function makeFixture(product: 'CNC' | 'MIS' = 'CNC') {
  return {
    context: {
      product,
      category: 'LC',
      source_bucket: 'TRADINGVIEW',
      order_type: 'MARKET',
      scenario: null,
      symbol: null,
      strategy_id: null,
    },
    inputs: {
      compiled_at: '2026-01-27T10:00:00Z',
      risk_enabled: true,
      manual_override_enabled: false,
      baseline_equity_inr: 1000000,
      drawdown_pct: 1.2,
    },
    effective: {
      allow_new_entries: true,
      blocking_reasons: [],
      drawdown_state: 'NORMAL',
      throttle_multiplier: 1.0,
      profile: { id: 1, name: `${product}_DEFAULT`, product, enabled: true, is_default: true },
      thresholds: { caution_pct: 6, defense_pct: 10, hard_stop_pct: 14 },
      allow_product: true,
      allow_short_selling: true,
      max_order_value_pct: 2.5,
      max_order_value_abs: null,
      max_quantity_per_order: null,
      order_type_policy: null,
      slippage_guard_bps: 10,
      gap_guard_pct: 1,
      capital_per_trade: 20000,
      max_positions: 6,
      max_exposure_pct: 60,
      daily_loss_pct: 1,
      hard_daily_loss_pct: 1,
      max_consecutive_losses: 3,
      risk_per_trade_pct: 0.5,
      hard_risk_pct: 0.75,
      stop_loss_mandatory: true,
      stop_reference: 'ATR',
      atr_period: 14,
      atr_mult_initial_stop: 2,
      fallback_stop_pct: 1,
      min_stop_distance_pct: 0.5,
      max_stop_distance_pct: 3,
      entry_cutoff_time: '14:55',
      force_squareoff_time: '15:15',
      max_trades_per_day: 10,
      max_trades_per_symbol_per_day: 2,
      min_bars_between_trades: 10,
      cooldown_after_loss_bars: 20,
    },
    overrides: [],
    provenance: {},
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
    expect(screen.getByText('Resolved (core)')).toBeInTheDocument()
    expect(screen.getByText('Execution Safety (per order)')).toBeInTheDocument()
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
    expect(String(fetchMock.mock.calls[1]?.[0] ?? '')).toContain('source_bucket=TRADINGVIEW')

    fireEvent.mouseDown(screen.getByLabelText('effective-risk-product'))
    fireEvent.click(screen.getByRole('option', { name: 'MIS' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(String(fetchMock.mock.calls[2]?.[0] ?? '')).toContain('product=MIS')

    expect(navigator.clipboard.writeText).toBe(clipboardWriteTextMock)

    fireEvent.click(screen.getByLabelText('copy-effective-risk-summary'))
    await waitFor(() => expect(clipboardWriteTextMock).toHaveBeenCalled())
  })
})
