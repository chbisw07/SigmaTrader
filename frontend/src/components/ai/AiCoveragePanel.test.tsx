import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import { AppThemeProvider } from '../../themeContext'
import { AiCoveragePanel } from './AiCoveragePanel'

vi.mock('../../services/aiTradingManager', () => {
  return {
    fetchCoverageShadows: vi.fn(async () => [
      {
        shadow_id: 'sh1',
        account_id: 'default',
        symbol: 'SBIN',
        product: 'CNC',
        side: 'LONG',
        qty_current: 10,
        avg_price: 100,
        ltp: 105,
        pnl_abs: 50,
        pnl_pct: 5,
        source: 'BROKER_DIRECT',
        status: 'OPEN',
        managed: false,
        playbook_id: null,
        playbook_mode: null,
        playbook_horizon: null,
      },
    ]),
    syncCoverageFromLatestSnapshot: vi.fn(async () => ({ status: 'ok' })),
    attachPlaybookToShadow: vi.fn(async () => ({
      playbook_id: 'pb1',
      scope_type: 'POSITION',
      scope_key: 'sh1',
      enabled: false,
      mode: 'OBSERVE',
      horizon: 'SWING',
      review_cadence_min: 60,
      exit_policy: {},
      scale_policy: {},
      execution_style: 'LIMIT_BBO',
      allow_strategy_exits: true,
      behavior_on_strategy_exit: 'ALLOW_AS_IS',
      version: 1,
    })),
    updateManagePlaybook: vi.fn(async () => ({})),
  }
})

describe('AiCoveragePanel', () => {
  it('renders coverage rows and unmanaged badge', async () => {
    render(
      <AppThemeProvider>
        <AiCoveragePanel />
      </AppThemeProvider>,
    )

    expect(await screen.findByText('Coverage')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('SBIN')).toBeTruthy())
    expect(screen.getByText('UNMANAGED')).toBeTruthy()
  })
})

