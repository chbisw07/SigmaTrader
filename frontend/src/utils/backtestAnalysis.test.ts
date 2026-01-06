import { describe, expect, it } from 'vitest'

import {
  computeClosedTradeAnalysisRows,
  computeEquityPeriodPnlRows,
  computeTradePeriodSummaryRows,
} from './backtestAnalysis'

describe('backtestAnalysis', () => {
  it('computes monthly equity pnl buckets from an equity series', () => {
    const ts = [
      '2025-01-31T15:30:00+05:30',
      '2025-02-03T15:30:00+05:30',
      '2025-02-28T15:30:00+05:30',
      '2025-03-03T15:30:00+05:30',
    ]
    const equity = [100_000, 101_000, 99_000, 102_000]

    const rows = computeEquityPeriodPnlRows(ts, equity, 'MONTH')
    expect(rows.map((r) => r.period)).toEqual(['2025-01', '2025-02', '2025-03'])
    expect(rows[0]?.pnl).toBeCloseTo(0) // first bucket is baseline
    expect(rows[1]?.end_equity).toBeCloseTo(99_000)
    expect(rows[2]?.end_equity).toBeCloseTo(102_000)
  })

  it('computes trade analysis rows with hold days and INR pnl', () => {
    const trades = [
      {
        symbol: 'NSE:ABC',
        entry_ts: '2025-02-01T15:30:00+05:30',
        exit_ts: '2025-02-10T15:30:00+05:30',
        side: 'LONG',
        entry_price: 100,
        exit_price: 110,
        qty: 10,
        pnl_pct: 10,
        reason: 'EXIT_SIGNAL',
      },
      {
        symbol: 'NSE:XYZ',
        entry_ts: '2025-02-01T15:30:00+05:30',
        exit_ts: '2025-02-10T15:30:00+05:30',
        side: 'SHORT',
        entry_price: 200,
        exit_price: 180,
        qty: 5,
        pnl_pct: 10,
        reason: 'TRAILING_STOP',
      },
    ]

    const rows = computeClosedTradeAnalysisRows(trades)
    expect(rows).toHaveLength(2)
    expect(rows[0]?.month).toBe('2025-02')
    expect(rows[0]?.pnl_inr).toBeCloseTo(100)
    expect(rows[0]?.hold_days).toBe(9)
    expect(rows[1]?.pnl_inr).toBeCloseTo(100)
  })

  it('summarizes monthly trade pnl', () => {
    const trades = computeClosedTradeAnalysisRows([
      {
        symbol: 'NSE:ABC',
        entry_ts: '2025-02-01T15:30:00+05:30',
        exit_ts: '2025-02-10T15:30:00+05:30',
        side: 'LONG',
        entry_price: 100,
        exit_price: 110,
        qty: 10,
        pnl_pct: 10,
        reason: 'EXIT_SIGNAL',
      },
      {
        symbol: 'NSE:ABC',
        entry_ts: '2025-02-11T15:30:00+05:30',
        exit_ts: '2025-02-12T15:30:00+05:30',
        side: 'LONG',
        entry_price: 100,
        exit_price: 90,
        qty: 10,
        pnl_pct: -10,
        reason: 'STOP_LOSS',
      },
    ])

    const summary = computeTradePeriodSummaryRows(trades, 'MONTH')
    expect(summary).toHaveLength(1)
    expect(summary[0]?.period).toBe('2025-02')
    expect(summary[0]?.trades).toBe(2)
    expect(summary[0]?.wins).toBe(1)
    expect(summary[0]?.losses).toBe(1)
    expect(summary[0]?.pnl_inr).toBeCloseTo(0)
  })
})

