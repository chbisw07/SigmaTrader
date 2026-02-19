import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AppThemeProvider } from '../themeContext'
import { AiTradingManagerPage } from './AiTradingManagerPage'

vi.mock('../services/aiTradingManager', () => {
  return {
    fetchAiThreads: vi.fn(async () => []),
    createAiThread: vi.fn(async () => ({ thread_id: 't2', account_id: 'default' })),
    fetchAiThread: vi.fn(async () => ({
      thread_id: 'default',
      account_id: 'default',
      messages: [
        {
          message_id: 'm1',
          role: 'assistant',
          content: '| A | B |\n|---|---|\n| 1 | 2 |',
          created_at: new Date().toISOString(),
        },
      ],
    })),
    chatAi: vi.fn(async () => ({
      assistant_message: 'ok',
      decision_id: 'd1',
      tool_calls: [],
      thread: null,
    })),
    chatAiStream: vi.fn(async ({ onEvent }: any) => {
      onEvent?.({ type: 'decision', decision_id: 'd1' })
      onEvent?.({ type: 'assistant_delta', text: 'ok' })
      onEvent?.({ type: 'done', assistant_message: 'ok', decision_id: 'd1' })
      return { assistant_message: 'ok', decision_id: 'd1' }
    }),
    uploadAiFiles: vi.fn(async () => [
      {
        file_id: 'f1',
        filename: 'pnl.csv',
        size: 12,
        mime: 'text/csv',
        created_at: new Date().toISOString(),
        summary: { kind: 'csv', columns: ['symbol', 'pnl'], row_count: 1, preview_rows: [] },
      },
    ]),
    fetchDecisionTrace: vi.fn(async () => null),
    fetchCoverageUnmanagedCount: vi.fn(async () => ({ account_id: 'default', unmanaged_open: 0, open_total: 0 })),
    fetchCoverageShadows: vi.fn(async () => []),
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
    updateManagePlaybook: vi.fn(async () => ({
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
    fetchJournalEvents: vi.fn(async () => []),
    fetchJournalForecasts: vi.fn(async () => []),
    upsertJournalForecast: vi.fn(async () => ({
      forecast_id: 'f1',
      position_shadow_id: 'sh1',
      created_at: new Date().toISOString(),
      author: 'USER',
    })),
    fetchLatestPostmortem: vi.fn(async () => {
      throw new Error('not found')
    }),
  }
})

describe('AiTradingManagerPage', () => {
  it('renders assistant markdown tables as real tables', async () => {
    render(
      <MemoryRouter initialEntries={['/ai?tab=chat']}>
        <AppThemeProvider>
          <AiTradingManagerPage />
        </AppThemeProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('AI Trading Manager')).toBeTruthy()
    // The markdown table should render as a table element.
    expect(await screen.findByRole('table')).toBeTruthy()
  })

  it('supports attaching CSV/XLSX and sends attachment refs on chat', async () => {
    render(
      <MemoryRouter initialEntries={['/ai?tab=chat']}>
        <AppThemeProvider>
          <AiTradingManagerPage />
        </AppThemeProvider>
      </MemoryRouter>,
    )

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeTruthy()

    const f = new File(['symbol,pnl\nABC,10\n'], 'pnl.csv', { type: 'text/csv' })
    fireEvent.change(fileInput, { target: { files: [f] } })

    expect(await screen.findByText(/pnl\.csv/i)).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'What columns are in the file?' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    })

    const mod = await import('../services/aiTradingManager')
    await waitFor(() => expect(mod.uploadAiFiles).toHaveBeenCalled())
    await waitFor(() => expect(mod.chatAiStream).toHaveBeenCalled())

    expect(mod.chatAiStream).toHaveBeenCalledWith(
      expect.objectContaining({
        attachments: [{ file_id: 'f1', how: 'auto' }],
      }),
    )
  })
})
