import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { MarkdownLite } from '../components/MarkdownLite'
import { PriceChart, type PriceCandle } from '../components/PriceChart'
import { fetchHoldings } from '../services/positions'
import { fetchGroup, listGroups, type Group, type GroupDetail } from '../services/groups'
import {
  createBacktestRun,
  getBacktestRun,
  listBacktestRuns,
  type BacktestKind,
  type BacktestRun,
} from '../services/backtests'

import backtestingHelpText from '../../../docs/backtesting_page_help.md?raw'
import portfolioBacktestingHelpText from '../../../docs/backtesting_portfolio_help.md?raw'
import riskParityBacktestingHelpText from '../../../docs/backtesting_risk_parity_help.md?raw'
import rotationBacktestingHelpText from '../../../docs/backtesting_rotation_help.md?raw'
import signalBacktestingHelpText from '../../../docs/backtesting_signal_help.md?raw'
import executionBacktestingHelpText from '../../../docs/backtesting_execution_help.md?raw'

type UniverseMode = 'HOLDINGS' | 'GROUP' | 'BOTH'

type BacktestTab = 'SIGNAL' | 'PORTFOLIO' | 'EXECUTION'

type SignalMode = 'DSL' | 'RANKING'
type RankingCadence = 'WEEKLY' | 'MONTHLY'
type PortfolioCadence = 'WEEKLY' | 'MONTHLY'
type PortfolioMethod = 'TARGET_WEIGHTS' | 'ROTATION' | 'RISK_PARITY'
type FillTiming = 'CLOSE' | 'NEXT_OPEN'

function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function daysBetweenIsoDates(startIso: string, endIso: string): number | null {
  const a = Date.parse(startIso)
  const b = Date.parse(endIso)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null
  const days = Math.round((b - a) / (24 * 60 * 60 * 1000))
  return days >= 0 ? days : null
}

function addDays(d: Date, days: number): Date {
  const out = new Date(d)
  out.setDate(out.getDate() + days)
  return out
}

function getDatePreset(preset: '6M' | '1Y' | '2Y'): { start: string; end: string } {
  const end = new Date()
  const start =
    preset === '6M' ? addDays(end, -182) : preset === '1Y' ? addDays(end, -365) : addDays(end, -730)
  return { start: toIsoDate(start), end: toIsoDate(end) }
}

export function BacktestingPage() {
  const [tab, setTab] = useState<BacktestTab>('SIGNAL')
  const kind: BacktestKind = tab

  const [helpOpen, setHelpOpen] = useState(false)

  const [groups, setGroups] = useState<Group[]>([])
  const [universeMode, setUniverseMode] = useState<UniverseMode>('GROUP')
  const [brokerName, setBrokerName] = useState<'zerodha' | 'angelone'>('zerodha')
  const [groupId, setGroupId] = useState<number | ''>('')
  const [groupDetail, setGroupDetail] = useState<GroupDetail | null>(null)

  const preset = useMemo(() => getDatePreset('1Y'), [])
  const [startDate, setStartDate] = useState(preset.start)
  const [endDate, setEndDate] = useState(preset.end)

  const [signalMode, setSignalMode] = useState<SignalMode>('DSL')
  const [signalDsl, setSignalDsl] = useState('RSI(14) < 30')
  const [signalForwardWindows, setSignalForwardWindows] = useState<number[]>([1, 5, 20])
  const [rankingWindow, setRankingWindow] = useState(20)
  const [rankingTopN, setRankingTopN] = useState(10)
  const [rankingCadence, setRankingCadence] = useState<RankingCadence>('MONTHLY')

  const [portfolioMethod, setPortfolioMethod] = useState<PortfolioMethod>('TARGET_WEIGHTS')
  const [portfolioCadence, setPortfolioCadence] = useState<PortfolioCadence>('MONTHLY')
  const [portfolioInitialCash, setPortfolioInitialCash] = useState(100000)
  const [portfolioBudgetPct, setPortfolioBudgetPct] = useState(100)
  const [portfolioMaxTrades, setPortfolioMaxTrades] = useState(20)
  const [portfolioMinTradeValue, setPortfolioMinTradeValue] = useState(0)
  const [portfolioSlippageBps, setPortfolioSlippageBps] = useState(0)
  const [portfolioChargesBps, setPortfolioChargesBps] = useState(0)
  const [rotationTopN, setRotationTopN] = useState(10)
  const [rotationWindow, setRotationWindow] = useState(20)
  const [rotationEligibleDsl, setRotationEligibleDsl] = useState('MA(50) > MA(200)')
  const [riskWindow, setRiskWindow] = useState(126)
  const [riskMinObs, setRiskMinObs] = useState(60)
  const [riskMinWeight, setRiskMinWeight] = useState(0)
  const [riskMaxWeight, setRiskMaxWeight] = useState(100)

  const [executionBaseRunId, setExecutionBaseRunId] = useState<number | ''>('')
  const [executionBaseRuns, setExecutionBaseRuns] = useState<BacktestRun[]>([])
  const [executionFillTiming, setExecutionFillTiming] = useState<FillTiming>('NEXT_OPEN')
  const [executionSlippageBps, setExecutionSlippageBps] = useState(10)
  const [executionChargesBps, setExecutionChargesBps] = useState(5)

  const [runs, setRuns] = useState<BacktestRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null)
  const [compareRunId, setCompareRunId] = useState<number | ''>('')
  const [compareRun, setCompareRun] = useState<BacktestRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const getRunUniverse = useCallback((run: BacktestRun) => {
    return ((run.config as any)?.universe ?? {}) as Record<string, unknown>
  }, [])

  const getRunConfig = useCallback((run: BacktestRun) => {
    return ((run.config as any)?.config ?? {}) as Record<string, unknown>
  }, [])

  const renderGroupLabel = useCallback(
    (run: BacktestRun): string => {
      const u = getRunUniverse(run)
      const mode = String(u.mode ?? '')
      const groupId = u.group_id
      if (mode === 'GROUP' || mode === 'BOTH') {
        if (typeof groupId === 'number') {
          return groups.find((g) => g.id === groupId)?.name ?? `Group #${groupId}`
        }
        return '(select group)'
      }
      if (mode === 'HOLDINGS') {
        return `Holdings (${String(u.broker_name ?? 'zerodha')})`
      }
      return mode || '—'
    },
    [getRunUniverse, groups],
  )

  const renderDuration = useCallback(
    (run: BacktestRun): string => {
      const cfg = getRunConfig(run)
      const start = String(cfg.start_date ?? '')
      const end = String(cfg.end_date ?? '')
      if (!start || !end) return '—'
      const days = daysBetweenIsoDates(start, end)
      return days == null ? `${start} → ${end}` : `${start} → ${end} (${days}d)`
    },
    [getRunConfig],
  )

  const renderDetails = useCallback(
    (run: BacktestRun): string => {
      const cfg = getRunConfig(run)
      if (run.kind === 'SIGNAL') {
        const mode = String(cfg.mode ?? '')
        if (mode === 'DSL') {
          const dsl = String(cfg.dsl ?? '').trim()
          return dsl ? `DSL: ${dsl}` : 'DSL'
        }
        const window = Number(cfg.ranking_window ?? cfg.window ?? 0)
        const topN = Number(cfg.top_n ?? 0)
        const cadence = String(cfg.cadence ?? '')
        return `Ranking: ${window || '?'}D, Top ${topN || '?'}, ${cadence || '—'}`
      }
      if (run.kind === 'PORTFOLIO') {
        const method = String(cfg.method ?? '')
        const cadence = String(cfg.cadence ?? '')
        const budget = cfg.budget_pct != null ? `${Number(cfg.budget_pct).toFixed(0)}%` : '—'
        const maxTrades = cfg.max_trades != null ? String(cfg.max_trades) : '—'
        return `${method || 'Portfolio'} • ${cadence || '—'} • budget ${budget} • max ${maxTrades}`
      }
      if (run.kind === 'EXECUTION') {
        const base = cfg.base_run_id != null ? `Base #${cfg.base_run_id}` : 'Base —'
        const fill = String(cfg.fill_timing ?? '—')
        const slip = cfg.slippage_bps != null ? `${Number(cfg.slippage_bps).toFixed(0)}bps` : '—'
        const charges = cfg.charges_bps != null ? `${Number(cfg.charges_bps).toFixed(0)}bps` : '—'
        return `${base} • ${fill} • slip ${slip} • charges ${charges}`
      }
      return run.title ?? ''
    },
    [getRunConfig],
  )

  const refreshRuns = useCallback(async () => {
    setRunsLoading(true)
    try {
      const data = await listBacktestRuns({ kind, limit: 50 })
      setRuns(data)
    } finally {
      setRunsLoading(false)
    }
  }, [kind])

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const data = await listGroups().catch(() => [])
        if (!active) return
        setGroups(data)
      } catch {
        if (!active) return
        setGroups([])
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    void refreshRuns()
  }, [refreshRuns])

  useEffect(() => {
    if (tab !== 'EXECUTION') return
    let active = true
    void (async () => {
      try {
        const data = await listBacktestRuns({ kind: 'PORTFOLIO', limit: 100 })
        if (!active) return
        setExecutionBaseRuns(data)
      } catch {
        if (!active) return
        setExecutionBaseRuns([])
      }
    })()
    return () => {
      active = false
    }
  }, [tab])

  useEffect(() => {
    let active = true
    void (async () => {
      if (!groupId || typeof groupId !== 'number') {
        setGroupDetail(null)
        return
      }
      try {
        const detail = await fetchGroup(groupId)
        if (!active) return
        setGroupDetail(detail)
      } catch {
        if (!active) return
        setGroupDetail(null)
      }
    })()
    return () => {
      active = false
    }
  }, [groupId])

  useEffect(() => {
    let active = true
    void (async () => {
      if (selectedRunId == null) {
        setSelectedRun(null)
        return
      }
      try {
        const run = await getBacktestRun(selectedRunId)
        if (!active) return
        setSelectedRun(run)
      } catch (err) {
        if (!active) return
        setSelectedRun(null)
        setError(err instanceof Error ? err.message : 'Failed to load run')
      }
    })()
    return () => {
      active = false
    }
  }, [selectedRunId])

  useEffect(() => {
    let active = true
    void (async () => {
      if (compareRunId === '' || typeof compareRunId !== 'number') {
        setCompareRun(null)
        return
      }
      try {
        const run = await getBacktestRun(compareRunId)
        if (!active) return
        setCompareRun(run)
      } catch {
        if (!active) return
        setCompareRun(null)
      }
    })()
    return () => {
      active = false
    }
  }, [compareRunId])

  const executionBaseRun = useMemo(() => {
    if (executionBaseRunId === '' || typeof executionBaseRunId !== 'number') return null
    return executionBaseRuns.find((r) => r.id === executionBaseRunId) ?? null
  }, [executionBaseRunId, executionBaseRuns])

  const buildUniverseSymbols = useCallback(async () => {
    const symSet = new Map<string, { symbol: string; exchange: string }>()
    const add = (symbol: string, exchange: string) => {
      const s = symbol.trim().toUpperCase()
      const e = (exchange || 'NSE').trim().toUpperCase()
      if (!s) return
      symSet.set(`${e}:${s}`, { symbol: s, exchange: e })
    }

    if (universeMode === 'HOLDINGS' || universeMode === 'BOTH') {
      const holdings = await fetchHoldings(brokerName)
      for (const h of holdings) {
        add(h.symbol, h.exchange ?? 'NSE')
      }
    }
    if (universeMode === 'GROUP' || universeMode === 'BOTH') {
      if (groupDetail) {
        for (const m of groupDetail.members ?? []) {
          add(m.symbol, m.exchange ?? 'NSE')
        }
      }
    }
    return Array.from(symSet.values())
  }, [brokerName, groupDetail, universeMode])

  const handleRun = async () => {
    setError(null)
    setRunning(true)
    try {
      const symbols = kind === 'EXECUTION' ? [] : await buildUniverseSymbols()
      const title =
        kind === 'EXECUTION'
          ? `EXECUTION backtest (base #${executionBaseRunId || '?'})`
          : `${kind} backtest`
      if (kind === 'SIGNAL' && signalMode === 'DSL' && !signalDsl.trim()) {
        throw new Error('DSL is required for Signal backtest (DSL mode).')
      }
      if (kind === 'PORTFOLIO') {
        if (universeMode !== 'GROUP') {
          throw new Error('Portfolio backtests currently require Universe = Group.')
        }
        if (typeof groupId !== 'number') {
          throw new Error('Please select a portfolio group for Portfolio backtests.')
        }
      }
      if (kind === 'EXECUTION') {
        if (executionBaseRunId === '' || typeof executionBaseRunId !== 'number') {
          throw new Error('Please select a base Portfolio run for Execution backtests.')
        }
      }

      const config: Record<string, unknown> =
        kind === 'SIGNAL'
          ? {
              timeframe: '1d',
              start_date: startDate,
              end_date: endDate,
              mode: signalMode,
              dsl: signalMode === 'DSL' ? signalDsl : '',
              forward_windows: signalForwardWindows,
              ranking_metric: 'PERF_PCT',
              ranking_window: rankingWindow,
              top_n: rankingTopN,
              cadence: rankingCadence,
            }
          : kind === 'PORTFOLIO'
            ? {
                timeframe: '1d',
                start_date: startDate,
                end_date: endDate,
                method: portfolioMethod,
                cadence: portfolioCadence,
                initial_cash: portfolioInitialCash,
                budget_pct: portfolioBudgetPct,
                max_trades: portfolioMaxTrades,
                min_trade_value: portfolioMinTradeValue,
                slippage_bps: portfolioSlippageBps,
                charges_bps: portfolioChargesBps,
                top_n: rotationTopN,
                ranking_window: rotationWindow,
                eligible_dsl: rotationEligibleDsl,
                risk_window: riskWindow,
                min_observations: riskMinObs,
                min_weight: riskMinWeight / 100,
                max_weight: riskMaxWeight / 100,
              }
          : {
              base_run_id: executionBaseRunId,
              fill_timing: executionFillTiming,
              slippage_bps: executionSlippageBps,
              charges_bps: executionChargesBps,
            }

      const baseGroupId =
        kind === 'EXECUTION'
          ? (executionBaseRun?.config as any)?.universe?.group_id ?? null
          : typeof groupId === 'number'
            ? groupId
            : null

      const run = await createBacktestRun({
        kind,
        title,
        universe: {
          mode: kind === 'EXECUTION' ? 'GROUP' : universeMode,
          broker_name: brokerName,
          group_id: baseGroupId,
          symbols,
        },
        config,
      })
      setSelectedRunId(run.id)
      await refreshRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  const runColumns = useMemo((): GridColDef[] => {
    const cols: GridColDef[] = [
      { field: 'id', headerName: 'Run', width: 90 },
      { field: 'created_at', headerName: 'Created', width: 180 },
      { field: 'status', headerName: 'Status', width: 120 },
      {
        field: 'group',
        headerName: 'Group',
        minWidth: 180,
        flex: 1,
        sortable: false,
        renderCell: (params) => renderGroupLabel(params.row as BacktestRun),
      },
      {
        field: 'duration',
        headerName: 'Duration',
        width: 240,
        sortable: false,
        renderCell: (params) => renderDuration(params.row as BacktestRun),
      },
      {
        field: 'details',
        headerName: 'DSL / Ranking',
        minWidth: 260,
        flex: 2,
        sortable: false,
        renderCell: (params) => renderDetails(params.row as BacktestRun),
      },
    ]
    return cols
  }, [renderDetails, renderDuration, renderGroupLabel])

  const selectedUniverseSummary = useMemo(() => {
    if (universeMode === 'HOLDINGS') return `Holdings (${brokerName})`
    if (universeMode === 'GROUP') return groupDetail ? `Group: ${groupDetail.name}` : 'Group: (select)'
    const groupLabel = groupDetail ? groupDetail.name : '(select group)'
    return `Both: Holdings (${brokerName}) + ${groupLabel}`
  }, [brokerName, groupDetail, universeMode])

  const helpText =
    tab === 'SIGNAL'
      ? signalBacktestingHelpText
      : tab === 'PORTFOLIO'
        ? portfolioMethod === 'ROTATION'
          ? rotationBacktestingHelpText
          : portfolioMethod === 'RISK_PARITY'
            ? riskParityBacktestingHelpText
          : portfolioBacktestingHelpText
        : tab === 'EXECUTION'
          ? executionBacktestingHelpText
          : backtestingHelpText

  const runDisabled =
    running ||
    (tab === 'PORTFOLIO' && typeof groupId !== 'number') ||
    (tab === 'EXECUTION' &&
      (executionBaseRunId === '' || typeof executionBaseRunId !== 'number')) ||
    (tab === 'SIGNAL' && signalMode === 'DSL' && !signalDsl.trim())

  const signalPresets = useMemo(
    () => [
      { id: 'RSI_OVERSOLD', label: 'RSI oversold (RSI(14) < 30)', mode: 'DSL' as const, dsl: 'RSI(14) < 30' },
      { id: 'SMA_TREND', label: 'Uptrend (MA(50) > MA(200))', mode: 'DSL' as const, dsl: 'MA(50) > MA(200)' },
      {
        id: 'MEAN_REVERT',
        label: 'Oversold in uptrend (MA50>MA200 AND RSI14<35)',
        mode: 'DSL' as const,
        dsl: 'MA(50) > MA(200) AND RSI(14) < 35',
      },
      { id: 'TOP_MOM_20D', label: 'Top‑N momentum (20D, monthly)', mode: 'RANKING' as const },
      { id: 'TOP_MOM_60D', label: 'Top‑N momentum (60D, weekly)', mode: 'RANKING' as const },
    ],
    [],
  )

  const applySignalPreset = useCallback(
    (presetId: string) => {
      const p = signalPresets.find((x) => x.id === presetId)
      if (!p) return
      if (p.mode === 'DSL') {
        setSignalMode('DSL')
        setSignalDsl(p.dsl)
        return
      }
      setSignalMode('RANKING')
      if (presetId === 'TOP_MOM_60D') {
        setRankingWindow(60)
        setRankingTopN(10)
        setRankingCadence('WEEKLY')
      } else {
        setRankingWindow(20)
        setRankingTopN(10)
        setRankingCadence('MONTHLY')
      }
    },
    [signalPresets],
  )

  const executionPresets = useMemo(
    () => [
      {
        id: 'NEXT_OPEN_LIGHT',
        label: 'Next open (10 bps slippage, 5 bps charges)',
        fill_timing: 'NEXT_OPEN' as const,
        slippage_bps: 10,
        charges_bps: 5,
      },
      {
        id: 'CLOSE_LIGHT',
        label: 'Same close (10 bps slippage, 5 bps charges)',
        fill_timing: 'CLOSE' as const,
        slippage_bps: 10,
        charges_bps: 5,
      },
      {
        id: 'NEXT_OPEN_HEAVY',
        label: 'Next open (25 bps slippage, 10 bps charges)',
        fill_timing: 'NEXT_OPEN' as const,
        slippage_bps: 25,
        charges_bps: 10,
      },
    ],
    [],
  )

  const applyExecutionPreset = useCallback(
    (presetId: string) => {
      const p = executionPresets.find((x) => x.id === presetId)
      if (!p) return
      setExecutionFillTiming(p.fill_timing)
      setExecutionSlippageBps(p.slippage_bps)
      setExecutionChargesBps(p.charges_bps)
    },
    [executionPresets],
  )

  const signalSummaryRows = useMemo(() => {
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result || tab !== 'SIGNAL') return []
    const byWindow = result.by_window as Record<string, unknown> | undefined
    if (!byWindow) return []
    return Object.entries(byWindow).map(([w, v]) => {
      const row = (v ?? {}) as Record<string, unknown>
      return {
        id: w,
        window: `${w}D`,
        count: Number(row.count ?? 0),
        win_rate_pct: row.win_rate_pct ?? null,
        avg_return_pct: row.avg_return_pct ?? null,
        p10: row.p10 ?? null,
        p50: row.p50 ?? null,
        p90: row.p90 ?? null,
      }
    })
  }, [selectedRun, tab])

  const signalSummaryColumns = useMemo((): GridColDef[] => {
    const fmtPct = (value: unknown, digits: number) =>
      value == null || value === '' ? '' : `${Number(value).toFixed(digits)}%`
    return [
      { field: 'window', headerName: 'Window', width: 90 },
      { field: 'count', headerName: 'Count', width: 90 },
      {
        field: 'win_rate_pct',
        headerName: 'Win %',
        width: 110,
        valueFormatter: (value) =>
          fmtPct((value as { value?: unknown })?.value ?? value, 1),
      },
      {
        field: 'avg_return_pct',
        headerName: 'Avg %',
        width: 110,
        valueFormatter: (value) =>
          fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      {
        field: 'p10',
        headerName: 'P10',
        width: 110,
        valueFormatter: (value) =>
          fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      {
        field: 'p50',
        headerName: 'P50',
        width: 110,
        valueFormatter: (value) =>
          fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      {
        field: 'p90',
        headerName: 'P90',
        width: 110,
        valueFormatter: (value) =>
          fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
    ]
  }, [])

  const portfolioEquityCandles = useMemo((): PriceCandle[] => {
    if (tab !== 'PORTFOLIO') return []
    if (!selectedRun?.result) return []
    const result = selectedRun.result as Record<string, unknown>
    const series = result.series as Record<string, unknown> | undefined
    if (!series) return []
    const dates = (series.dates as unknown[] | undefined) ?? []
    const equity = (series.equity as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(dates.length, equity.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      candles.push({ ts, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return candles
  }, [selectedRun, tab])

  const portfolioCompareOverlay = useMemo(() => {
    if (tab !== 'PORTFOLIO') return []
    if (!compareRun?.result) return []
    const r = compareRun.result as Record<string, unknown>
    const series = r.series as Record<string, unknown> | undefined
    if (!series) return []
    const dates = (series.dates as unknown[] | undefined) ?? []
    const equity = (series.equity as unknown[] | undefined) ?? []
    const byDate = new Map<string, number>()
    for (let i = 0; i < Math.min(dates.length, equity.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      byDate.set(ts, v)
    }
    const points = portfolioEquityCandles.map((c) => ({
      ts: c.ts,
      value: byDate.get(c.ts) ?? null,
    }))
    return [
      {
        name: `Compare: run #${compareRun.id}`,
        color: '#6b7280',
        points,
      },
    ]
  }, [compareRun, portfolioEquityCandles, tab])

  const executionEquityCandles = useMemo((): PriceCandle[] => {
    if (tab !== 'EXECUTION') return []
    if (!selectedRun?.result) return []
    const result = selectedRun.result as Record<string, unknown>
    const realistic = (result.realistic as Record<string, unknown> | undefined) ?? undefined
    const series = (realistic?.series as Record<string, unknown> | undefined) ?? undefined
    if (!series) return []
    const dates = (series.dates as unknown[] | undefined) ?? []
    const equity = (series.equity as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(dates.length, equity.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      candles.push({ ts, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return candles
  }, [selectedRun, tab])

  const executionIdealOverlay = useMemo(() => {
    if (tab !== 'EXECUTION') return []
    if (!selectedRun?.result) return []
    const result = selectedRun.result as Record<string, unknown>
    const ideal = (result.ideal as Record<string, unknown> | undefined) ?? undefined
    const series = (ideal?.series as Record<string, unknown> | undefined) ?? undefined
    if (!series) return []
    const dates = (series.dates as unknown[] | undefined) ?? []
    const equity = (series.equity as unknown[] | undefined) ?? []
    const byDate = new Map<string, number>()
    for (let i = 0; i < Math.min(dates.length, equity.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      byDate.set(ts, v)
    }
    const points = executionEquityCandles.map((c) => ({
      ts: c.ts,
      value: byDate.get(c.ts) ?? null,
    }))
    return [
      {
        name: 'Ideal (CLOSE, 0 costs)',
        color: '#6b7280',
        points,
      },
    ]
  }, [executionEquityCandles, selectedRun, tab])

  const executionDelta = useMemo(() => {
    if (tab !== 'EXECUTION') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.delta as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const portfolioDrawdownCandles = useMemo((): PriceCandle[] => {
    if (tab !== 'PORTFOLIO') return []
    if (!selectedRun?.result) return []
    const result = selectedRun.result as Record<string, unknown>
    const series = result.series as Record<string, unknown> | undefined
    if (!series) return []
    const dates = (series.dates as unknown[] | undefined) ?? []
    const dd = (series.drawdown_pct as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(dates.length, dd.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(dd[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      candles.push({ ts, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return candles
  }, [selectedRun, tab])

  const portfolioMetrics = useMemo(() => {
    if (tab !== 'PORTFOLIO') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.metrics as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const portfolioActionsRows = useMemo(() => {
    if (tab !== 'PORTFOLIO') return []
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return []
    const actions = (result.actions as unknown[] | undefined) ?? []
    return actions.map((a, idx) => {
      const row = (a ?? {}) as Record<string, unknown>
      const trades = (row.trades as unknown[] | undefined) ?? []
      return {
        id: idx,
        date: String(row.date ?? ''),
        trades: trades.length,
        turnover_pct: row.turnover_pct ?? null,
        budget_used: row.budget_used ?? null,
      }
    })
  }, [selectedRun, tab])

  const portfolioActionsColumns = useMemo((): GridColDef[] => {
    const fmtPct = (value: unknown) =>
      value == null || value === '' ? '' : `${Number(value).toFixed(1)}%`
    const fmtNum0 = (value: unknown) =>
      value == null || value === '' ? '' : Number(value).toFixed(0)
    return [
      { field: 'date', headerName: 'Date', width: 120 },
      { field: 'trades', headerName: 'Trades', width: 90 },
      {
        field: 'turnover_pct',
        headerName: 'Turnover %',
        width: 120,
        valueFormatter: (value) =>
          fmtPct((value as { value?: unknown })?.value ?? value),
      },
      {
        field: 'budget_used',
        headerName: 'Budget used',
        width: 140,
        valueFormatter: (value) =>
          fmtNum0((value as { value?: unknown })?.value ?? value),
      },
    ]
  }, [])

  return (
    <Box sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="h5">Backtesting</Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Help">
          <IconButton size="small" onClick={() => setHelpOpen(true)}>
            <HelpOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      <Tabs value={tab} onChange={(_e, v) => setTab(v as BacktestTab)} sx={{ mt: 1 }}>
        <Tab value="SIGNAL" label="Signal backtest" />
        <Tab value="PORTFOLIO" label="Portfolio backtest" />
        <Tab value="EXECUTION" label="Execution backtest" />
      </Tabs>

      <Box
        sx={{
          mt: 2,
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '420px 1fr' },
          gap: 2,
          alignItems: 'start',
        }}
      >
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1">Inputs</Typography>

            {tab !== 'EXECUTION' ? (
              <>
                <FormControl fullWidth size="small">
                  <InputLabel id="bt-universe-label">Universe</InputLabel>
                  <Select
                    labelId="bt-universe-label"
                    label="Universe"
                    value={universeMode}
                    onChange={(e) => setUniverseMode(e.target.value as UniverseMode)}
                  >
                    <MenuItem value="HOLDINGS">Holdings</MenuItem>
                    <MenuItem value="GROUP">Group</MenuItem>
                    <MenuItem value="BOTH">Both</MenuItem>
                  </Select>
                </FormControl>

                {(universeMode === 'HOLDINGS' || universeMode === 'BOTH') && (
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-broker-label">Broker</InputLabel>
                    <Select
                      labelId="bt-broker-label"
                      label="Broker"
                      value={brokerName}
                      onChange={(e) =>
                        setBrokerName(e.target.value === 'angelone' ? 'angelone' : 'zerodha')
                      }
                    >
                      <MenuItem value="zerodha">Zerodha</MenuItem>
                      <MenuItem value="angelone">AngelOne</MenuItem>
                    </Select>
                  </FormControl>
                )}

                {(universeMode === 'GROUP' || universeMode === 'BOTH') && (
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-group-label">Group</InputLabel>
                    <Select
                      labelId="bt-group-label"
                      label="Group"
                      value={groupId}
                      onChange={(e) =>
                        setGroupId(e.target.value === '' ? '' : Number(e.target.value))
                      }
                    >
                      <MenuItem value="">(select)</MenuItem>
                      {groups.map((g) => (
                        <MenuItem key={g.id} value={String(g.id)}>
                          {g.name} ({g.kind})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                )}

                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Chip size="small" label={selectedUniverseSummary} />
                  {groupDetail && (universeMode === 'GROUP' || universeMode === 'BOTH') && (
                    <Chip
                      size="small"
                      variant="outlined"
                      label={`${groupDetail.members.length} symbols`}
                    />
                  )}
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Start"
                    type="date"
                    size="small"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    InputLabelProps={{ shrink: true }}
                    fullWidth
                  />
                  <TextField
                    label="End"
                    type="date"
                    size="small"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    InputLabelProps={{ shrink: true }}
                    fullWidth
                  />
                </Stack>
              </>
            ) : (
              <Stack spacing={1.5}>
                <FormControl fullWidth size="small">
                  <InputLabel id="bt-exec-base-label">Base portfolio run</InputLabel>
                  <Select
                    labelId="bt-exec-base-label"
                    label="Base portfolio run"
                    value={executionBaseRunId}
                    onChange={(e) =>
                      setExecutionBaseRunId(e.target.value === '' ? '' : Number(e.target.value))
                    }
                  >
                    <MenuItem value="">(select)</MenuItem>
                    {executionBaseRuns
                      .filter((r) => r.kind === 'PORTFOLIO' && r.status === 'COMPLETED')
                      .map((r) => {
                        const groupId = Number((r.config as any)?.universe?.group_id ?? NaN)
                        const groupName = groups.find((g) => g.id === groupId)?.name ?? `Group #${groupId}`
                        const method = String((r.config as any)?.config?.method ?? '')
                        return (
                          <MenuItem key={r.id} value={String(r.id)}>
                            #{r.id} — {groupName} — {method}
                          </MenuItem>
                        )
                      })}
                  </Select>
                </FormControl>

                {executionBaseRun && (
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                    <Chip
                      size="small"
                      label={`Base #${executionBaseRun.id} • ${String(
                        (executionBaseRun.config as any)?.config?.method ?? 'PORTFOLIO',
                      )}`}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={`Window: ${String((executionBaseRun.config as any)?.config?.start_date ?? '')} → ${String(
                        (executionBaseRun.config as any)?.config?.end_date ?? '',
                      )}`}
                    />
                  </Stack>
                )}

                <FormControl fullWidth size="small">
                  <InputLabel id="bt-exec-preset-label">Preset</InputLabel>
                  <Select
                    labelId="bt-exec-preset-label"
                    label="Preset"
                    value=""
                    onChange={(e) => applyExecutionPreset(String(e.target.value))}
                  >
                    <MenuItem value="">(choose)</MenuItem>
                    {executionPresets.map((p) => (
                      <MenuItem key={p.id} value={p.id}>
                        {p.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-exec-fill-label">Fill timing</InputLabel>
                    <Select
                      labelId="bt-exec-fill-label"
                      label="Fill timing"
                      value={executionFillTiming}
                      onChange={(e) => setExecutionFillTiming(e.target.value as FillTiming)}
                    >
                      <MenuItem value="CLOSE">Same day close</MenuItem>
                      <MenuItem value="NEXT_OPEN">Next day open</MenuItem>
                    </Select>
                  </FormControl>
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Slippage (bps)"
                    size="small"
                    type="number"
                    value={executionSlippageBps}
                    onChange={(e) => setExecutionSlippageBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                  <TextField
                    label="Charges (bps)"
                    size="small"
                    type="number"
                    value={executionChargesBps}
                    onChange={(e) => setExecutionChargesBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                </Stack>
              </Stack>
            )}

            {tab === 'SIGNAL' && (
              <Stack spacing={1.5}>
                <FormControl fullWidth size="small">
                  <InputLabel id="bt-signal-mode-label">Signal mode</InputLabel>
                  <Select
                    labelId="bt-signal-mode-label"
                    label="Signal mode"
                    value={signalMode}
                    onChange={(e) => setSignalMode(e.target.value as SignalMode)}
                  >
                    <MenuItem value="DSL">DSL condition</MenuItem>
                    <MenuItem value="RANKING">Ranking (Top‑N momentum)</MenuItem>
                  </Select>
                </FormControl>

                <FormControl fullWidth size="small">
                  <InputLabel id="bt-signal-preset-label">Preset</InputLabel>
                  <Select
                    labelId="bt-signal-preset-label"
                    label="Preset"
                    value=""
                    onChange={(e) => applySignalPreset(String(e.target.value))}
                  >
                    <MenuItem value="">(choose)</MenuItem>
                    {signalPresets.map((p) => (
                      <MenuItem key={p.id} value={p.id}>
                        {p.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                {signalMode === 'DSL' ? (
                  <TextField
                    label="DSL"
                    size="small"
                    multiline
                    minRows={3}
                    value={signalDsl}
                    onChange={(e) => setSignalDsl(e.target.value)}
                    placeholder='Example: MA(50) > MA(200) AND RSI(14) < 35'
                  />
                ) : (
                  <Stack direction="row" spacing={1}>
                    <TextField
                      label="Momentum window (days)"
                      size="small"
                      type="number"
                      value={rankingWindow}
                      onChange={(e) => setRankingWindow(Number(e.target.value))}
                      inputProps={{ min: 1, max: 400 }}
                      fullWidth
                    />
                    <TextField
                      label="Top N"
                      size="small"
                      type="number"
                      value={rankingTopN}
                      onChange={(e) => setRankingTopN(Number(e.target.value))}
                      inputProps={{ min: 1, max: 200 }}
                      fullWidth
                    />
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-ranking-cadence-label">Cadence</InputLabel>
                      <Select
                        labelId="bt-ranking-cadence-label"
                        label="Cadence"
                        value={rankingCadence}
                        onChange={(e) => setRankingCadence(e.target.value as RankingCadence)}
                      >
                        <MenuItem value="WEEKLY">Weekly</MenuItem>
                        <MenuItem value="MONTHLY">Monthly</MenuItem>
                      </Select>
                    </FormControl>
                  </Stack>
                )}

                <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                  <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                    Forward windows
                  </Typography>
                  {[1, 5, 20, 60].map((w) => {
                    const active = signalForwardWindows.includes(w)
                    return (
                      <Chip
                        key={w}
                        size="small"
                        label={`${w}D`}
                        color={active ? 'primary' : 'default'}
                        variant={active ? 'filled' : 'outlined'}
                        onClick={() => {
                          setSignalForwardWindows((prev) => {
                            const next = active ? prev.filter((x) => x !== w) : [...prev, w]
                            return next.length ? next.sort((a, b) => a - b) : [1]
                          })
                        }}
                      />
                    )
                  })}
                </Stack>
              </Stack>
            )}

            {tab === 'PORTFOLIO' && (
              <Stack spacing={1.5}>
                <FormControl fullWidth size="small">
                  <InputLabel id="bt-pf-method-label">Method</InputLabel>
                  <Select
                    labelId="bt-pf-method-label"
                    label="Method"
                    value={portfolioMethod}
                    onChange={(e) => setPortfolioMethod(e.target.value as PortfolioMethod)}
                  >
                    <MenuItem value="TARGET_WEIGHTS">Target weights</MenuItem>
                    <MenuItem value="ROTATION">Rotation (Top‑N momentum)</MenuItem>
                    <MenuItem value="RISK_PARITY">Risk parity (equal risk)</MenuItem>
                  </Select>
                </FormControl>

                {portfolioMethod === 'ROTATION' && (
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1}>
                      <TextField
                        label="Top N"
                        size="small"
                        type="number"
                        value={rotationTopN}
                        onChange={(e) => setRotationTopN(Number(e.target.value))}
                        inputProps={{ min: 1, max: 200 }}
                        fullWidth
                      />
                      <TextField
                        label="Momentum window (days)"
                        size="small"
                        type="number"
                        value={rotationWindow}
                        onChange={(e) => setRotationWindow(Number(e.target.value))}
                        inputProps={{ min: 1, max: 400 }}
                        fullWidth
                      />
                    </Stack>
                    <TextField
                      label="Eligible DSL (optional)"
                      size="small"
                      multiline
                      minRows={2}
                      value={rotationEligibleDsl}
                      onChange={(e) => setRotationEligibleDsl(e.target.value)}
                      placeholder="Example: MA(50) > MA(200) AND RSI(14) < 80"
                    />
                  </Stack>
                )}

                {portfolioMethod === 'RISK_PARITY' && (
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1}>
                      <TextField
                        label="Risk window (days)"
                        size="small"
                        type="number"
                        value={riskWindow}
                        onChange={(e) => setRiskWindow(Number(e.target.value))}
                        inputProps={{ min: 2, max: 400 }}
                        fullWidth
                      />
                      <TextField
                        label="Min observations"
                        size="small"
                        type="number"
                        value={riskMinObs}
                        onChange={(e) => setRiskMinObs(Number(e.target.value))}
                        inputProps={{ min: 2, max: 400 }}
                        fullWidth
                      />
                    </Stack>
                    <Stack direction="row" spacing={1}>
                      <TextField
                        label="Min weight (%)"
                        size="small"
                        type="number"
                        value={riskMinWeight}
                        onChange={(e) => setRiskMinWeight(Number(e.target.value))}
                        inputProps={{ min: 0, max: 100 }}
                        fullWidth
                      />
                      <TextField
                        label="Max weight (%)"
                        size="small"
                        type="number"
                        value={riskMaxWeight}
                        onChange={(e) => setRiskMaxWeight(Number(e.target.value))}
                        inputProps={{ min: 1, max: 100 }}
                        fullWidth
                      />
                    </Stack>
                  </Stack>
                )}

                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pf-cadence-label">Cadence</InputLabel>
                    <Select
                      labelId="bt-pf-cadence-label"
                      label="Cadence"
                      value={portfolioCadence}
                      onChange={(e) => setPortfolioCadence(e.target.value as PortfolioCadence)}
                    >
                      <MenuItem value="WEEKLY">Weekly</MenuItem>
                      <MenuItem value="MONTHLY">Monthly</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    label="Initial cash"
                    size="small"
                    type="number"
                    value={portfolioInitialCash}
                    onChange={(e) => setPortfolioInitialCash(Number(e.target.value))}
                    inputProps={{ min: 1 }}
                    fullWidth
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Budget (%)"
                    size="small"
                    type="number"
                    value={portfolioBudgetPct}
                    onChange={(e) => setPortfolioBudgetPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                  <TextField
                    label="Max trades"
                    size="small"
                    type="number"
                    value={portfolioMaxTrades}
                    onChange={(e) => setPortfolioMaxTrades(Number(e.target.value))}
                    inputProps={{ min: 1, max: 1000 }}
                    fullWidth
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Min trade value"
                    size="small"
                    type="number"
                    value={portfolioMinTradeValue}
                    onChange={(e) => setPortfolioMinTradeValue(Number(e.target.value))}
                    inputProps={{ min: 0 }}
                    fullWidth
                  />
                  <TextField
                    label="Slippage (bps)"
                    size="small"
                    type="number"
                    value={portfolioSlippageBps}
                    onChange={(e) => setPortfolioSlippageBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                  <TextField
                    label="Charges (bps)"
                    size="small"
                    type="number"
                    value={portfolioChargesBps}
                    onChange={(e) => setPortfolioChargesBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      setPortfolioMethod('TARGET_WEIGHTS')
                      setPortfolioCadence('MONTHLY')
                      setPortfolioBudgetPct(100)
                      setPortfolioMaxTrades(50)
                      setPortfolioMinTradeValue(0)
                      setPortfolioSlippageBps(0)
                      setPortfolioChargesBps(0)
                    }}
                  >
                    Preset: Monthly (no costs)
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      setPortfolioMethod('TARGET_WEIGHTS')
                      setPortfolioCadence('WEEKLY')
                      setPortfolioBudgetPct(10)
                      setPortfolioMaxTrades(10)
                      setPortfolioMinTradeValue(2000)
                      setPortfolioSlippageBps(10)
                      setPortfolioChargesBps(10)
                    }}
                  >
                    Preset: Weekly (tight budget)
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      setPortfolioMethod('ROTATION')
                      setRotationTopN(10)
                      setRotationWindow(20)
                      setRotationEligibleDsl('MA(50) > MA(200)')
                      setPortfolioCadence('MONTHLY')
                      setPortfolioBudgetPct(100)
                      setPortfolioMaxTrades(50)
                      setPortfolioMinTradeValue(0)
                      setPortfolioSlippageBps(10)
                      setPortfolioChargesBps(10)
                    }}
                  >
                    Preset: Rotation (Top‑10 momentum)
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      setPortfolioMethod('RISK_PARITY')
                      setRiskWindow(126)
                      setRiskMinObs(60)
                      setRiskMinWeight(0)
                      setRiskMaxWeight(30)
                      setPortfolioCadence('MONTHLY')
                      setPortfolioBudgetPct(100)
                      setPortfolioMaxTrades(50)
                      setPortfolioMinTradeValue(0)
                      setPortfolioSlippageBps(10)
                      setPortfolioChargesBps(10)
                    }}
                  >
                    Preset: Risk parity (6M)
                  </Button>
                </Stack>
              </Stack>
            )}

            <Stack direction="row" spacing={1} flexWrap="wrap">
              {tab !== 'EXECUTION' &&
                (['6M', '1Y', '2Y'] as const).map((p) => (
                  <Button
                    key={p}
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      const r = getDatePreset(p)
                      setStartDate(r.start)
                      setEndDate(r.end)
                    }}
                  >
                    {p}
                  </Button>
                ))}
              <Box sx={{ flexGrow: 1 }} />
              <Button variant="contained" onClick={() => void handleRun()} disabled={runDisabled}>
                {running ? 'Running…' : 'Run backtest'}
              </Button>
            </Stack>

            {error && (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            )}

          </Stack>
        </Paper>

        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="subtitle1">Results</Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Button size="small" variant="outlined" onClick={() => void refreshRuns()} disabled={runsLoading}>
                Refresh runs
              </Button>
            </Stack>

            <Box sx={{ height: 260 }}>
              <DataGrid
                rows={runs}
                columns={runColumns}
                getRowId={(r) => (r as BacktestRun).id}
                loading={runsLoading}
                density="compact"
                disableRowSelectionOnClick
                onRowClick={(p) => setSelectedRunId((p.row as BacktestRun).id)}
                initialState={{
                  pagination: { paginationModel: { pageSize: 5 } },
                }}
                pageSizeOptions={[5, 10, 25]}
              />
            </Box>

            <DividerBlock title="Selected run" />
            {selectedRun ? (
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
                <Typography variant="body2" color="text.secondary">
                  Run #{selectedRun.id} • {selectedRun.kind} • {selectedRun.status}
                </Typography>

                {tab === 'SIGNAL' && selectedRun.status === 'COMPLETED' && signalSummaryRows.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2">Signal summary (by forward window)</Typography>
                    <Box sx={{ height: 220, mt: 1 }}>
                      <DataGrid
                        rows={signalSummaryRows}
                        columns={signalSummaryColumns}
                        density="compact"
                        disableRowSelectionOnClick
                        hideFooter
                      />
                    </Box>
                  </Box>
                )}

                {tab === 'PORTFOLIO' && selectedRun.status === 'COMPLETED' && portfolioEquityCandles.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2">Equity curve</Typography>
                    {portfolioMetrics && (
                      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
                        <Chip
                          size="small"
                          label={`Total: ${Number(portfolioMetrics.total_return_pct ?? 0).toFixed(2)}%`}
                        />
                        <Chip
                          size="small"
                          label={`CAGR: ${Number(portfolioMetrics.cagr_pct ?? 0).toFixed(2)}%`}
                        />
                        <Chip
                          size="small"
                          label={`Max DD: ${Number(portfolioMetrics.max_drawdown_pct ?? 0).toFixed(2)}%`}
                        />
                        <Chip
                          size="small"
                          label={`Turnover: ${Number(portfolioMetrics.turnover_pct_total ?? 0).toFixed(1)}%`}
                        />
                        <Chip
                          size="small"
                          label={`Rebalances: ${Number(portfolioMetrics.rebalance_count ?? 0)}`}
                        />
                      </Stack>
                    )}
                    <Box sx={{ mt: 1 }}>
                      <PriceChart
                        candles={portfolioEquityCandles}
                        chartType="line"
                        height={260}
                        overlays={portfolioCompareOverlay}
                      />
                    </Box>
                    {runs.length > 1 && (
                      <Box sx={{ mt: 2 }}>
                        <FormControl fullWidth size="small">
                          <InputLabel id="bt-compare-label">Compare run</InputLabel>
                          <Select
                            labelId="bt-compare-label"
                            label="Compare run"
                            value={compareRunId}
                            onChange={(e) =>
                              setCompareRunId(
                                e.target.value === '' ? '' : Number(e.target.value),
                              )
                            }
                          >
                            <MenuItem value="">(none)</MenuItem>
                            {runs
                              .filter((r) => r.id !== selectedRun.id && r.status === 'COMPLETED')
                              .map((r) => (
                                <MenuItem key={r.id} value={String(r.id)}>
                                  #{r.id} — {String((r.config as any)?.config?.method ?? r.title ?? '')}
                                </MenuItem>
                              ))}
                          </Select>
                        </FormControl>
                      </Box>
                    )}
                    {portfolioDrawdownCandles.length > 0 && (
                      <Box sx={{ mt: 2 }}>
                        <Typography variant="subtitle2">Drawdown (%)</Typography>
                        <Box sx={{ mt: 1 }}>
                          <PriceChart candles={portfolioDrawdownCandles} chartType="line" height={180} />
                        </Box>
                      </Box>
                    )}
                    {portfolioActionsRows.length > 0 && (
                      <Box sx={{ mt: 2 }}>
                        <Typography variant="subtitle2">Rebalance actions</Typography>
                        <Box sx={{ height: 220, mt: 1 }}>
                          <DataGrid
                            rows={portfolioActionsRows}
                            columns={portfolioActionsColumns}
                            density="compact"
                            disableRowSelectionOnClick
                            hideFooter
                          />
                        </Box>
                      </Box>
                    )}
                  </Box>
                )}

                {tab === 'EXECUTION' && selectedRun.status === 'COMPLETED' && executionEquityCandles.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2">Equity curve (realistic vs ideal)</Typography>
                    {executionDelta && (
                      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
                        <Chip
                          size="small"
                          label={`Δ End equity: ${Number(executionDelta.end_equity_delta ?? 0).toFixed(0)}`}
                        />
                        <Chip
                          size="small"
                          label={`Δ End (%): ${Number(executionDelta.end_equity_delta_pct ?? 0).toFixed(2)}%`}
                        />
                      </Stack>
                    )}
                    <Box sx={{ mt: 1 }}>
                      <PriceChart
                        candles={executionEquityCandles}
                        chartType="line"
                        height={260}
                        overlays={executionIdealOverlay}
                      />
                    </Box>
                  </Box>
                )}

                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      const config = selectedRun.config as Record<string, unknown>
                      const runKind = (selectedRun.kind || kind) as BacktestKind
                      void (async () => {
                        setError(null)
                        setRunning(true)
                        try {
                          const universe = (config.universe ?? {}) as Record<string, unknown>
                          const run = await createBacktestRun({
                            kind: runKind,
                            title: selectedRun.title ?? `${runKind} backtest`,
                            universe: {
                              mode: (universe.mode as UniverseMode) ?? 'GROUP',
                              broker_name:
                                universe.broker_name === 'angelone' ? 'angelone' : 'zerodha',
                              group_id:
                                typeof universe.group_id === 'number' ? universe.group_id : null,
                              symbols: Array.isArray(universe.symbols)
                                ? (universe.symbols as Array<Record<string, unknown>>).map((s) => ({
                                    symbol: String(s.symbol ?? '').toUpperCase(),
                                    exchange: String(s.exchange ?? 'NSE').toUpperCase(),
                                  }))
                                : [],
                            },
                            config: (config.config ?? {}) as Record<string, unknown>,
                          })
                          setSelectedRunId(run.id)
                          await refreshRuns()
                        } catch (err) {
                          setError(err instanceof Error ? err.message : 'Failed to rerun')
                        } finally {
                          setRunning(false)
                        }
                      })()
                    }}
                  >
                    Rerun
                  </Button>
                </Stack>
              </Paper>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Select a run to view details.
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Backtesting help</DialogTitle>
        <DialogContent>
          <MarkdownLite text={helpText} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

function DividerBlock({ title }: { title: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ flex: 1, height: 1, bgcolor: 'divider' }} />
      <Typography variant="caption" color="text.secondary">
        {title}
      </Typography>
      <Box sx={{ flex: 1, height: 1, bgcolor: 'divider' }} />
    </Box>
  )
}
