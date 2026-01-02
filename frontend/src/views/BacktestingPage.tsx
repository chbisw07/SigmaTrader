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

import { KeyValueJsonDialog } from '../components/KeyValueJsonDialog'
import { MarkdownLite } from '../components/MarkdownLite'
import { PriceChart, type PriceCandle, type PriceSignalMarker } from '../components/PriceChart'
import { fetchHoldings } from '../services/positions'
import { fetchGroup, listGroups, type Group, type GroupDetail } from '../services/groups'
import {
  createBacktestRun,
  deleteBacktestRuns,
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
import strategyBacktestingHelpText from '../../../docs/backtesting_strategy_help.md?raw'
import executionBacktestingHelpText from '../../../docs/backtesting_execution_help.md?raw'

type UniverseMode = 'HOLDINGS' | 'GROUP' | 'BOTH'

type BacktestTab = 'SIGNAL' | 'PORTFOLIO' | 'EXECUTION' | 'STRATEGY'

type SignalMode = 'DSL' | 'RANKING'
type RankingCadence = 'WEEKLY' | 'MONTHLY'
type PortfolioCadence = 'WEEKLY' | 'MONTHLY'
type PortfolioMethod = 'TARGET_WEIGHTS' | 'ROTATION' | 'RISK_PARITY'
type FillTiming = 'CLOSE' | 'NEXT_OPEN'
type ChargesModel = 'BPS' | 'BROKER'
type ProductType = 'CNC' | 'MIS'
type BrokerName = 'zerodha' | 'angelone'
type GateSource = 'NONE' | 'GROUP_INDEX' | 'SYMBOL'
type StrategyTimeframe = '1m' | '5m' | '15m' | '30m' | '1h' | '1d'
type StrategyDirection = 'LONG' | 'SHORT'

function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function fmtPct(value: unknown, digits = 2): string {
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(digits)}%` : '—'
}

function fmtInr(value: unknown, digits = 0): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    }).format(n)
  } catch {
    return `₹${n.toFixed(digits)}`
  }
}

function downsample<T>(values: T[], maxPoints: number): T[] {
  return downsampleKeep(values, maxPoints)
}

function downsampleKeep<T>(values: T[], maxPoints: number, keep?: (v: T) => boolean): T[] {
  if (values.length <= maxPoints) return values
  const step = Math.ceil(values.length / maxPoints)
  return values.filter((v, i) => keep?.(v) === true || i % step === 0 || i === values.length - 1)
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
  const [portfolioFillTiming, setPortfolioFillTiming] = useState<FillTiming>('CLOSE')
  const [portfolioInitialCash, setPortfolioInitialCash] = useState(100000)
  const [portfolioBudgetPct, setPortfolioBudgetPct] = useState(100)
  const [portfolioMaxTrades, setPortfolioMaxTrades] = useState(20)
  const [portfolioMinTradeValue, setPortfolioMinTradeValue] = useState(0)
  const [portfolioSlippageBps, setPortfolioSlippageBps] = useState(0)
  const [portfolioChargesBps, setPortfolioChargesBps] = useState(0)
  const [portfolioChargesModel, setPortfolioChargesModel] = useState<ChargesModel>('BROKER')
  const [portfolioChargesBroker, setPortfolioChargesBroker] = useState<BrokerName>('zerodha')
  const [portfolioProduct, setPortfolioProduct] = useState<ProductType>('CNC')
  const [portfolioIncludeDpCharges, setPortfolioIncludeDpCharges] = useState(true)
  const [portfolioGateSource, setPortfolioGateSource] = useState<GateSource>('NONE')
  const [portfolioGateDsl, setPortfolioGateDsl] = useState('RSI(14) < 30')
  const [portfolioGateGroupId, setPortfolioGateGroupId] = useState<number | ''>('')
  const [portfolioGateSymbolExchange, setPortfolioGateSymbolExchange] = useState('NSE')
  const [portfolioGateSymbol, setPortfolioGateSymbol] = useState('')
  const [portfolioGateMinCoveragePct, setPortfolioGateMinCoveragePct] = useState(90)
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
  const [executionChargesModel, setExecutionChargesModel] = useState<ChargesModel>('BROKER')
  const [executionChargesBroker, setExecutionChargesBroker] = useState<BrokerName>('zerodha')
  const [executionProduct, setExecutionProduct] = useState<ProductType>('CNC')
  const [executionIncludeDpCharges, setExecutionIncludeDpCharges] = useState(true)

  const [strategySymbolKey, setStrategySymbolKey] = useState<string>('')
  const [strategyTimeframe, setStrategyTimeframe] = useState<StrategyTimeframe>('1d')
  const [strategyEntryDsl, setStrategyEntryDsl] = useState('RSI(14) < 30')
  const [strategyExitDsl, setStrategyExitDsl] = useState('RSI(14) > 70')
  const [strategyProduct, setStrategyProduct] = useState<ProductType>('CNC')
  const [strategyDirection, setStrategyDirection] = useState<StrategyDirection>('LONG')
  const [strategyInitialCash, setStrategyInitialCash] = useState(100000)
  const [strategyPositionSizePct, setStrategyPositionSizePct] = useState(100)
  const [strategyStopLossPct, setStrategyStopLossPct] = useState(0)
  const [strategyTakeProfitPct, setStrategyTakeProfitPct] = useState(0)
  const [strategyTrailingStopPct, setStrategyTrailingStopPct] = useState(0)
  const [strategyMaxEquityDdGlobalPct, setStrategyMaxEquityDdGlobalPct] = useState(0)
  const [strategyMaxEquityDdTradePct, setStrategyMaxEquityDdTradePct] = useState(0)
  const [strategySlippageBps, setStrategySlippageBps] = useState(0)
  const [strategyChargesModel, setStrategyChargesModel] = useState<ChargesModel>('BROKER')
  const [strategyChargesBps, setStrategyChargesBps] = useState(0)
  const [strategyIncludeDpCharges, setStrategyIncludeDpCharges] = useState(true)

  const [holdingsSymbols, setHoldingsSymbols] = useState<Array<{ symbol: string; exchange: string }>>([])

  const [runs, setRuns] = useState<BacktestRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null)
  const [compareRunId, setCompareRunId] = useState<number | ''>('')
  const [compareRun, setCompareRun] = useState<BacktestRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>([])
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [detailsRun, setDetailsRun] = useState<BacktestRun | null>(null)

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

  const renderSymbolLabel = useCallback(
    (run: BacktestRun): string => {
      if (run.kind !== 'STRATEGY') return '—'
      const u = getRunUniverse(run)
      const symbols = (u.symbols as Array<Record<string, unknown>> | undefined) ?? []
      const first = symbols[0] ?? null
      if (!first) return '—'
      const exchange = String(first.exchange ?? '').trim().toUpperCase() || 'NSE'
      const symbol = String(first.symbol ?? '').trim().toUpperCase()
      return symbol ? `${exchange}:${symbol}` : '—'
    },
    [getRunUniverse],
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
        const fill = String(cfg.fill_timing ?? '')
        const budget = cfg.budget_pct != null ? `${Number(cfg.budget_pct).toFixed(0)}%` : '—'
        const maxTrades = cfg.max_trades != null ? String(cfg.max_trades) : '—'
        const chargesModel = String(cfg.charges_model ?? 'BPS')
        const dpTxt = cfg.include_dp_charges === false ? 'no-DP' : 'DP'
        const charges =
          chargesModel === 'BROKER'
            ? `charges broker (${String(cfg.charges_broker ?? '—')}/${String(cfg.product ?? 'CNC')}, ${dpTxt})`
            : `charges ${cfg.charges_bps != null ? `${Number(cfg.charges_bps).toFixed(0)}bps` : '—'}`
        const fillTxt = fill ? ` • ${fill}` : ''
        const gateSource = String(cfg.gate_source ?? 'NONE').toUpperCase()
        const gateDsl = String(cfg.gate_dsl ?? '').trim()
        const shorten = (s: string) => (s.length > 42 ? `${s.slice(0, 39)}…` : s)
        const gateTxt =
          gateSource !== 'NONE' && gateDsl
            ? ` • gate ${gateSource}: ${shorten(gateDsl)}`
            : ''
        return `${method || 'Portfolio'} • ${cadence || '—'}${fillTxt} • budget ${budget} • max ${maxTrades} • ${charges}${gateTxt}`
      }
      if (run.kind === 'STRATEGY') {
        const timeframe = String(cfg.timeframe ?? '')
        const product = String(cfg.product ?? 'CNC')
        const direction = String(cfg.direction ?? 'LONG')
        const entry = String(cfg.entry_dsl ?? '').trim()
        const exit = String(cfg.exit_dsl ?? '').trim()
        const ddGlobal = Number(cfg.max_equity_dd_global_pct ?? 0)
        const ddTrade = Number(cfg.max_equity_dd_trade_pct ?? 0)
        const shorten = (s: string) => (s.length > 48 ? `${s.slice(0, 45)}…` : s)
        const ddParts: string[] = []
        if (Number.isFinite(ddGlobal) && ddGlobal > 0) ddParts.push(`eqDD global ${ddGlobal}%`)
        if (Number.isFinite(ddTrade) && ddTrade > 0) ddParts.push(`eqDD trade ${ddTrade}%`)
        const ddTxt = ddParts.length ? ` • ${ddParts.join(' • ')}` : ''
        return `${timeframe || '—'} • ${product}/${direction} • entry: ${shorten(entry)} • exit: ${shorten(exit)}${ddTxt}`
      }
      if (run.kind === 'EXECUTION') {
        const base = cfg.base_run_id != null ? `Base #${cfg.base_run_id}` : 'Base —'
        const fill = String(cfg.fill_timing ?? '—')
        const slip = cfg.slippage_bps != null ? `${Number(cfg.slippage_bps).toFixed(0)}bps` : '—'
        const chargesModel = String(cfg.charges_model ?? 'BPS')
        const dpTxt = cfg.include_dp_charges === false ? 'no-DP' : 'DP'
        const charges =
          chargesModel === 'BROKER'
            ? `broker (${String(cfg.charges_broker ?? '—')}/${String(cfg.product ?? 'CNC')}, ${dpTxt})`
            : `${cfg.charges_bps != null ? `${Number(cfg.charges_bps).toFixed(0)}bps` : '—'}`
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

  const handleDeleteSelected = useCallback(async () => {
    const ids = selectedRunIds.slice()
    if (!ids.length) return
    setError(null)
    setRunning(true)
    try {
      const res = await deleteBacktestRuns(ids)
      const deleted = res.deleted_ids ?? []
      setSelectedRunIds((prev) => prev.filter((id) => !deleted.includes(id)))
      if (selectedRunId != null && deleted.includes(selectedRunId)) {
        setSelectedRunId(null)
      }
      if (compareRunId !== '' && typeof compareRunId === 'number' && deleted.includes(compareRunId)) {
        setCompareRunId('')
      }
      await refreshRuns()
      if ((res.forbidden_ids ?? []).length) {
        setError(`Some runs could not be deleted: ${res.forbidden_ids.join(', ')}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete runs')
    } finally {
      setRunning(false)
    }
  }, [compareRunId, refreshRuns, selectedRunId, selectedRunIds])

  useEffect(() => {
    setSelectedRunIds([])
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
      if (tab !== 'STRATEGY') return
      if (universeMode !== 'HOLDINGS' && universeMode !== 'BOTH') {
        setHoldingsSymbols([])
        return
      }
      try {
        const holdings = await fetchHoldings(brokerName)
        if (!active) return
        const symbols = holdings
          .map((h) => ({
            symbol: String(h.symbol ?? '').trim().toUpperCase(),
            exchange: String(h.exchange ?? 'NSE').trim().toUpperCase(),
          }))
          .filter((x) => x.symbol)
        setHoldingsSymbols(symbols)
      } catch {
        if (!active) return
        setHoldingsSymbols([])
      }
    })()
    return () => {
      active = false
    }
  }, [brokerName, tab, universeMode])

  useEffect(() => {
    if (tab !== 'STRATEGY') return
    if (strategyProduct === 'CNC' && strategyDirection !== 'LONG') {
      setStrategyDirection('LONG')
    }
  }, [strategyDirection, strategyProduct, tab])

  useEffect(() => {
    if (tab !== 'STRATEGY') return
    if (strategyProduct === 'MIS' && strategyTimeframe === '1d') {
      setStrategyTimeframe('1h')
    }
  }, [strategyProduct, strategyTimeframe, tab])

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

  const strategySymbolOptions = useMemo(() => {
    const symSet = new Map<string, { symbol: string; exchange: string }>()
    const add = (symbol: string, exchange: string) => {
      const s = symbol.trim().toUpperCase()
      const e = (exchange || 'NSE').trim().toUpperCase()
      if (!s) return
      symSet.set(`${e}:${s}`, { symbol: s, exchange: e })
    }
    if (universeMode === 'HOLDINGS' || universeMode === 'BOTH') {
      for (const h of holdingsSymbols) add(h.symbol, h.exchange)
    }
    if (universeMode === 'GROUP' || universeMode === 'BOTH') {
      for (const m of groupDetail?.members ?? []) add(m.symbol, m.exchange ?? 'NSE')
    }
    return Array.from(symSet.entries())
      .map(([key, val]) => ({ key, ...val }))
      .sort((a, b) => a.key.localeCompare(b.key))
  }, [groupDetail, holdingsSymbols, universeMode])

  useEffect(() => {
    if (tab !== 'STRATEGY') return
    if (!strategySymbolKey && strategySymbolOptions.length > 0) {
      setStrategySymbolKey(strategySymbolOptions[0].key)
    }
  }, [strategySymbolKey, strategySymbolOptions, tab])

  const handleRun = async () => {
    setError(null)
    setRunning(true)
    try {
      const symbols =
        kind === 'EXECUTION'
          ? []
          : kind === 'STRATEGY'
            ? strategySymbolKey
              ? [
                  {
                    symbol: strategySymbolKey.split(':', 2)[1] ?? strategySymbolKey,
                    exchange: strategySymbolKey.split(':', 2)[0] ?? 'NSE',
                  },
                ]
              : []
            : await buildUniverseSymbols()
      const title =
        kind === 'EXECUTION'
          ? `EXECUTION backtest (base #${executionBaseRunId || '?'})`
          : kind === 'STRATEGY'
            ? `STRATEGY backtest (${strategyTimeframe})`
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
        if (portfolioGateSource !== 'NONE') {
          if (!portfolioGateDsl.trim()) {
            throw new Error('Gate DSL is required when Gate is enabled.')
          }
          if (portfolioGateSource === 'SYMBOL' && !portfolioGateSymbol.trim()) {
            throw new Error('Gate symbol is required when Gate source = Symbol.')
          }
        }
      }
      if (kind === 'EXECUTION') {
        if (executionBaseRunId === '' || typeof executionBaseRunId !== 'number') {
          throw new Error('Please select a base Portfolio run for Execution backtests.')
        }
      }
      if (kind === 'STRATEGY') {
        if (!strategySymbolKey) throw new Error('Please select a symbol for Strategy backtests.')
        if (!strategyEntryDsl.trim() || !strategyExitDsl.trim()) {
          throw new Error('Both entry and exit DSL are required for Strategy backtests.')
        }
        if (strategyProduct === 'CNC' && strategyDirection !== 'LONG') {
          throw new Error('CNC does not allow short selling. Use direction LONG or switch to MIS.')
        }
        if (strategyProduct === 'MIS' && strategyTimeframe === '1d') {
          throw new Error('MIS requires an intraday timeframe (<= 1h).')
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
                    fill_timing: portfolioFillTiming,
                    initial_cash: portfolioInitialCash,
                    budget_pct: portfolioBudgetPct,
                    max_trades: portfolioMaxTrades,
                    min_trade_value: portfolioMinTradeValue,
                    slippage_bps: portfolioSlippageBps,
                    charges_bps: portfolioChargesBps,
                    charges_model: portfolioChargesModel,
                    charges_broker: portfolioChargesBroker,
                    product: portfolioProduct,
                    include_dp_charges: portfolioIncludeDpCharges,
                    gate_source: portfolioGateSource,
                    gate_dsl: portfolioGateSource === 'NONE' ? '' : portfolioGateDsl,
                    gate_symbol_exchange:
                      portfolioGateSource === 'SYMBOL' ? portfolioGateSymbolExchange : 'NSE',
                    gate_symbol: portfolioGateSource === 'SYMBOL' ? portfolioGateSymbol : '',
                    gate_group_id:
                      portfolioGateSource === 'GROUP_INDEX' && typeof portfolioGateGroupId === 'number'
                        ? portfolioGateGroupId
                        : null,
                    gate_min_coverage_pct: portfolioGateMinCoveragePct,
                    top_n: rotationTopN,
                    ranking_window: rotationWindow,
                    eligible_dsl: rotationEligibleDsl,
                    risk_window: riskWindow,
                    min_observations: riskMinObs,
                    min_weight: riskMinWeight / 100,
                    max_weight: riskMaxWeight / 100,
                  }
          : kind === 'STRATEGY'
            ? {
                timeframe: strategyTimeframe,
                start_date: startDate,
                end_date: endDate,
                entry_dsl: strategyEntryDsl,
                exit_dsl: strategyExitDsl,
                product: strategyProduct,
                direction: strategyDirection,
                initial_cash: strategyInitialCash,
                position_size_pct: strategyPositionSizePct,
                stop_loss_pct: strategyStopLossPct,
                take_profit_pct: strategyTakeProfitPct,
                trailing_stop_pct: strategyTrailingStopPct,
                max_equity_dd_global_pct: strategyMaxEquityDdGlobalPct,
                max_equity_dd_trade_pct: strategyMaxEquityDdTradePct,
                slippage_bps: strategySlippageBps,
                charges_model: strategyChargesModel,
                charges_bps: strategyChargesBps,
                charges_broker: 'zerodha',
                include_dp_charges: strategyIncludeDpCharges,
              }
          : {
              base_run_id: executionBaseRunId,
              fill_timing: executionFillTiming,
              slippage_bps: executionSlippageBps,
              charges_bps: executionChargesBps,
              charges_model: executionChargesModel,
              charges_broker: executionChargesBroker,
              product: executionProduct,
              include_dp_charges: executionIncludeDpCharges,
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
        width: 160,
        minWidth: 140,
        flex: 0,
        sortable: false,
        renderCell: (params) => renderGroupLabel(params.row as BacktestRun),
      },
      {
        field: 'symbol',
        headerName: 'Symbol',
        width: 160,
        sortable: false,
        renderCell: (params) => renderSymbolLabel(params.row as BacktestRun),
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
        minWidth: 320,
        flex: 2,
        sortable: false,
        renderCell: (params) => {
          const run = params.row as BacktestRun
          const text = renderDetails(run)
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0, width: '100%' }}>
              <Typography
                variant="body2"
                sx={{
                  flex: 1,
                  minWidth: 0,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={text}
              >
                {text}
              </Typography>
              <Button
                size="small"
                variant="outlined"
                onClick={(e) => {
                  e.stopPropagation()
                  setDetailsRun(run)
                }}
              >
                Details
              </Button>
            </Box>
          )
        },
      },
    ]
    return cols
  }, [renderDetails, renderDuration, renderGroupLabel, renderSymbolLabel])

  const runColumnVisibilityModel = useMemo(() => {
    return { symbol: tab === 'STRATEGY' }
  }, [tab])

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
          : tab === 'STRATEGY'
            ? strategyBacktestingHelpText
            : backtestingHelpText

  const runDisabled =
    running ||
    (tab === 'PORTFOLIO' && typeof groupId !== 'number') ||
    (tab === 'EXECUTION' &&
      (executionBaseRunId === '' || typeof executionBaseRunId !== 'number')) ||
    (tab === 'SIGNAL' && signalMode === 'DSL' && !signalDsl.trim()) ||
    (tab === 'STRATEGY' &&
      (!strategySymbolKey || !strategyEntryDsl.trim() || !strategyExitDsl.trim()))

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
      setExecutionChargesModel('BPS')
    },
    [executionPresets],
  )

  const strategyPresets = useMemo(
    () => [
      {
        id: 'SWING_RSI_30_70',
        label: 'Swing: RSI oversold→overbought (Long, 1d)',
        timeframe: '1d' as const,
        product: 'CNC' as const,
        direction: 'LONG' as const,
        entry_dsl: 'RSI(14) < 30',
        exit_dsl: 'RSI(14) > 70',
        stop_loss_pct: 0,
        take_profit_pct: 0,
        trailing_stop_pct: 0,
      },
      {
        id: 'SWING_TREND_MA_CROSS',
        label: 'Swing: Trend follow (MA20 cross MA50, Long, 1d)',
        timeframe: '1d' as const,
        product: 'CNC' as const,
        direction: 'LONG' as const,
        entry_dsl: 'MA(20) CROSS_ABOVE MA(50)',
        exit_dsl: 'MA(20) CROSS_BELOW MA(50)',
        stop_loss_pct: 8,
        take_profit_pct: 0,
        trailing_stop_pct: 6,
      },
      {
        id: 'INTRADAY_VWAP_RECLAIM_LONG',
        label: 'Intraday: VWAP reclaim (Long, 15m, MIS)',
        timeframe: '15m' as const,
        product: 'MIS' as const,
        direction: 'LONG' as const,
        entry_dsl: 'PRICE() CROSS_ABOVE VWAP(20) AND RSI(14) > 50',
        exit_dsl: 'PRICE() < VWAP(20) OR RSI(14) < 45',
        stop_loss_pct: 1,
        take_profit_pct: 2,
        trailing_stop_pct: 1,
      },
      {
        id: 'INTRADAY_VWAP_BREAKDOWN_SHORT',
        label: 'Intraday: VWAP breakdown (Short, 15m, MIS)',
        timeframe: '15m' as const,
        product: 'MIS' as const,
        direction: 'SHORT' as const,
        entry_dsl: 'PRICE() CROSS_BELOW VWAP(20) AND RSI(14) < 50',
        exit_dsl: 'PRICE() > VWAP(20) OR RSI(14) > 55',
        stop_loss_pct: 1,
        take_profit_pct: 2,
        trailing_stop_pct: 1,
      },
      {
        id: 'SIDEWAYS_MEAN_REVERT_LONG',
        label: 'Sideways: Mean reversion (Long, 30m, MIS)',
        timeframe: '30m' as const,
        product: 'MIS' as const,
        direction: 'LONG' as const,
        entry_dsl: 'RSI(14) < 30',
        exit_dsl: 'RSI(14) > 55',
        stop_loss_pct: 1.5,
        take_profit_pct: 2.5,
        trailing_stop_pct: 1.5,
      },
    ],
    [],
  )

  const applyStrategyPreset = useCallback((presetId: string) => {
    const p = strategyPresets.find((x) => x.id === presetId)
    if (!p) return
    setStrategyTimeframe(p.timeframe)
    setStrategyProduct(p.product)
    setStrategyDirection(p.direction)
    setStrategyEntryDsl(p.entry_dsl)
    setStrategyExitDsl(p.exit_dsl)
    setStrategyStopLossPct(p.stop_loss_pct)
    setStrategyTakeProfitPct(p.take_profit_pct)
    setStrategyTrailingStopPct(p.trailing_stop_pct)
    setStrategyMaxEquityDdGlobalPct(0)
    setStrategyMaxEquityDdTradePct(0)
    setStrategySlippageBps(0)
    setStrategyChargesModel('BROKER')
    setStrategyChargesBps(0)
  }, [strategyPresets])

  const signalSummaryRows = useMemo(() => {
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result || tab !== 'SIGNAL') return []
    const byWindow = result.by_window as Record<string, unknown> | undefined
    if (!byWindow) return []
    return Object.entries(byWindow).map(([w, v]) => {
      const row = (v ?? {}) as Record<string, unknown>
      const windowDays = Number(w)
      return {
        id: w,
        window: `${w}D`,
        windowDays,
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
    const infer = (r: Record<string, unknown>): string[] => {
      const win = Number(r.win_rate_pct)
      const avg = Number(r.avg_return_pct)
      const p10 = Number(r.p10)
      const p50 = Number(r.p50)
      const p90 = Number(r.p90)
      const count = Number(r.count)
      const windowDays = Number(r.windowDays)

      const bullets: string[] = []

      if (Number.isFinite(win) && Number.isFinite(avg) && Number.isFinite(count)) {
        const edgeWord =
          avg > 0 && win >= 50 ? 'Edge: positive bias' : avg < 0 && win < 50 ? 'Edge: negative bias' : 'Edge: mixed'
        bullets.push(`${edgeWord} (win ${win.toFixed(1)}%, avg ${fmtPct(avg, 2)}, n=${count})`)
      } else if (Number.isFinite(count)) {
        bullets.push(`Events: n=${count}`)
      }

      if (Number.isFinite(p50) && Number.isFinite(p90) && Number.isFinite(windowDays)) {
        bullets.push(
          `Typical: median ${fmtPct(p50, 2)}; upside (top 10%) ≥ ${fmtPct(p90, 2)} over ${windowDays} trading days`,
        )
      } else if (Number.isFinite(p50) && Number.isFinite(windowDays)) {
        bullets.push(`Typical: median ${fmtPct(p50, 2)} over ${windowDays} trading days`)
      }

      if (Number.isFinite(p10) && Number.isFinite(windowDays)) {
        const riskWord = p10 < 0 ? 'Risk' : 'Downside'
        bullets.push(`${riskWord}: worst 10% ≤ ${fmtPct(p10, 2)} over ${windowDays} trading days`)
      }

      return bullets.slice(0, 3)
    }

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
      {
        field: 'inference',
        headerName: 'Inference',
        flex: 1,
        minWidth: 360,
        sortable: false,
        renderCell: (params) => {
          const bullets = infer(params.row as Record<string, unknown>)
          if (!bullets.length) return '—'
          return (
            <Box sx={{ py: 0.5 }}>
              <Box
                component="ul"
                sx={{
                  pl: 2,
                  m: 0,
                  '& li': { lineHeight: 1.25 },
                }}
              >
                {bullets.map((b, idx) => (
                  <li key={idx}>
                    <Typography variant="caption" color="text.secondary">
                      {b}
                    </Typography>
                  </li>
                ))}
              </Box>
            </Box>
          )
        },
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

  const strategySeries = useMemo(() => {
    if (tab !== 'STRATEGY') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.series as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const strategyTradeMarkers = useMemo((): PriceSignalMarker[] => {
    if (tab !== 'STRATEGY') return []
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return []
    const trades = (result.trades as unknown[] | undefined) ?? []
    const countsByKey = new Map<string, number>()
    const out: PriceSignalMarker[] = []

    const push = (ts: string, kind: string, text: string) => {
      const key = `${ts}|${kind}`
      const next = (countsByKey.get(key) ?? 0) + 1
      countsByKey.set(key, next)
      out.push({ ts, kind, text: next > 1 ? `${text}${next}` : text })
    }

    for (const t of trades) {
      const row = (t ?? {}) as Record<string, unknown>
      const entryTs = String(row.entry_ts ?? '')
      const exitTs = String(row.exit_ts ?? '')
      const side = String(row.side ?? '').toUpperCase()
      if (!entryTs || !exitTs) continue
      const entryKind = side === 'SHORT' ? 'CROSSUNDER' : 'CROSSOVER'
      const exitKind = side === 'SHORT' ? 'CROSSOVER' : 'CROSSUNDER'
      push(entryTs, entryKind, 'E')
      push(exitTs, exitKind, 'X')
    }
    return out
  }, [selectedRun, tab])

  const strategyMarkerTs = useMemo(() => {
    const s = new Set<string>()
    for (const m of strategyTradeMarkers) s.add(m.ts)
    return s
  }, [strategyTradeMarkers])

  const strategyEquityCandles = useMemo((): PriceCandle[] => {
    if (tab !== 'STRATEGY') return []
    if (!strategySeries) return []
    const ts = (strategySeries.ts as unknown[] | undefined) ?? []
    const equity = (strategySeries.equity as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(ts.length, equity.length); i++) {
      const t = String(ts[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!t || !Number.isFinite(v)) continue
      candles.push({ ts: t, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return downsampleKeep(candles, 2500, (c) => strategyMarkerTs.has((c as PriceCandle).ts))
  }, [strategyMarkerTs, strategySeries, tab])

  const strategyDrawdownCandles = useMemo((): PriceCandle[] => {
    if (tab !== 'STRATEGY') return []
    if (!strategySeries) return []
    const ts = (strategySeries.ts as unknown[] | undefined) ?? []
    const dd = (strategySeries.drawdown_pct as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(ts.length, dd.length); i++) {
      const t = String(ts[i] ?? '')
      const v = Number(dd[i] ?? NaN)
      if (!t || !Number.isFinite(v)) continue
      candles.push({ ts: t, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return downsample(candles, 2500)
  }, [strategySeries, tab])

  const strategyMetrics = useMemo(() => {
    if (tab !== 'STRATEGY') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.metrics as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const strategyProfitValue = useMemo(() => {
    if (tab !== 'STRATEGY') return null
    if (!strategySeries) return null
    const equity = (strategySeries.equity as unknown[] | undefined) ?? []
    let first: number | null = null
    let last: number | null = null
    for (const v of equity) {
      const n = Number(v ?? NaN)
      if (!Number.isFinite(n)) continue
      if (first === null) first = n
      last = n
    }
    if (first === null || last === null) return null
    return last - first
  }, [strategySeries, tab])

  const strategyTradeStats = useMemo(() => {
    if (tab !== 'STRATEGY') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.trade_stats as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const strategyBaselines = useMemo(() => {
    if (tab !== 'STRATEGY') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.baselines as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const strategyBaselineOverlays = useMemo(() => {
    if (tab !== 'STRATEGY') return []
    if (!strategyBaselines || !strategySeries) return []
    const ts = (strategySeries.ts as unknown[] | undefined) ?? []
    if (!ts.length) return []

    const overlays: Array<{ name: string; color: string; points: Array<{ ts: string; value: number | null }> }> = []

    const addOverlay = (name: string, color: string, curve: unknown) => {
      const row = (curve ?? {}) as Record<string, unknown>
      const equity = (row.equity as unknown[] | undefined) ?? []
      const byTs = new Map<string, number>()
      for (let i = 0; i < Math.min(ts.length, equity.length); i++) {
        const t = String(ts[i] ?? '')
        const v = Number(equity[i] ?? NaN)
        if (!t || !Number.isFinite(v)) continue
        byTs.set(t, v)
      }
      const points = strategyEquityCandles.map((c) => ({ ts: c.ts, value: byTs.get(c.ts) ?? null }))
      overlays.push({ name, color, points })
    }

    addOverlay(
      'Buy & hold (start→end)',
      '#6b7280',
      (strategyBaselines.start_to_end as unknown) ?? null,
    )
    if (strategyBaselines.first_entry_to_end) {
      addOverlay(
        'Buy & hold (first entry→end)',
        '#9ca3af',
        strategyBaselines.first_entry_to_end,
      )
    }

    return overlays
  }, [strategyBaselines, strategyEquityCandles, strategySeries, tab])

  const strategyTradesRows = useMemo(() => {
    if (tab !== 'STRATEGY') return []
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return []
    const trades = (result.trades as unknown[] | undefined) ?? []
    return trades.map((t, idx) => {
      const row = (t ?? {}) as Record<string, unknown>
      return {
        id: idx,
        entry_ts: String(row.entry_ts ?? ''),
        exit_ts: String(row.exit_ts ?? ''),
        side: String(row.side ?? ''),
        qty: row.qty ?? null,
        pnl_pct: row.pnl_pct ?? null,
        reason: String(row.reason ?? ''),
      }
    })
  }, [selectedRun, tab])

  const strategyTradesColumns = useMemo((): GridColDef[] => {
    return [
      { field: 'entry_ts', headerName: 'Entry', width: 200 },
      { field: 'exit_ts', headerName: 'Exit', width: 200 },
      { field: 'side', headerName: 'Side', width: 110 },
      { field: 'qty', headerName: 'Qty', width: 90, type: 'number' },
      {
        field: 'pnl_pct',
        headerName: 'P&L %',
        width: 110,
        valueFormatter: (value) => fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      { field: 'reason', headerName: 'Reason', minWidth: 160, flex: 1 },
    ]
  }, [])

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

  const portfolioMeta = useMemo(() => {
    if (tab !== 'PORTFOLIO') return null
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return null
    return (result.meta as Record<string, unknown> | undefined) ?? null
  }, [selectedRun, tab])

  const portfolioActionsRows = useMemo(() => {
    if (tab !== 'PORTFOLIO') return []
    const result = selectedRun?.result as Record<string, unknown> | null | undefined
    if (!result) return []
    const actions = (result.actions as unknown[] | undefined) ?? []
    return actions.map((a, idx) => {
      const row = (a ?? {}) as Record<string, unknown>
      const trades = (row.trades as unknown[] | undefined) ?? []
      const skipped = Boolean(row.skipped)
      const charges = trades.reduce<number>(
        (acc, t) => acc + Number((t as any)?.charges ?? 0),
        0,
      )
      return {
        id: idx,
        date: String(row.date ?? ''),
        status: skipped ? 'SKIPPED' : 'OK',
        note: skipped ? String(row.skip_reason ?? '') : '',
        trades: trades.length,
        turnover_pct: row.turnover_pct ?? null,
        budget_used: row.budget_used ?? null,
        charges: Number.isFinite(charges) ? charges : null,
      }
    })
  }, [selectedRun, tab])

  const portfolioActionsColumns = useMemo((): GridColDef[] => {
    const fmtPct = (value: unknown) =>
      value == null || value === '' ? '' : `${Number(value).toFixed(1)}%`
    return [
      { field: 'date', headerName: 'Date', width: 120 },
      { field: 'status', headerName: 'Status', width: 110 },
      { field: 'note', headerName: 'Note', minWidth: 160, flex: 1 },
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
          fmtInr((value as { value?: unknown })?.value ?? value, 0),
      },
      {
        field: 'charges',
        headerName: 'Charges',
        width: 140,
        valueFormatter: (value) =>
          fmtInr((value as { value?: unknown })?.value ?? value, 0),
      },
    ]
  }, [])

  return (
    <Box>
      <Box
        sx={{
          mb: 1,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 2,
          flexWrap: 'wrap',
        }}
      >
	        <Box>
	          <Typography variant="h4" sx={{ mb: 0.5 }}>
	            Backtesting
	          </Typography>
	          <Tabs value={tab} onChange={(_e, v) => setTab(v as BacktestTab)} sx={{ mt: 0 }}>
	            <Tab value="SIGNAL" label="Signal backtest" />
	            <Tab value="PORTFOLIO" label="Portfolio backtest" />
	            <Tab value="EXECUTION" label="Execution backtest" />
	            <Tab value="STRATEGY" label="Strategy backtest" />
	          </Tabs>
	        </Box>

        <Tooltip title="Help">
          <IconButton size="small" onClick={() => setHelpOpen(true)}>
            <HelpOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      <Box
        sx={{
          mt: 1,
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
	                      <MenuItem value="CLOSE" disabled={executionProduct === 'MIS'}>
	                        Same day close
	                      </MenuItem>
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
                </Stack>

                <Stack spacing={1}>
                  <Stack direction="row" spacing={1}>
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-exec-product-label">Product</InputLabel>
                      <Select
                        labelId="bt-exec-product-label"
                        label="Product"
                        value={executionProduct}
                        onChange={(e) => {
                          const next = e.target.value as ProductType
                          setExecutionProduct(next)
                          if (next === 'MIS') setExecutionFillTiming('NEXT_OPEN')
                        }}
                      >
                        <MenuItem value="CNC">CNC (delivery)</MenuItem>
                        <MenuItem value="MIS">MIS (intraday)</MenuItem>
                      </Select>
                    </FormControl>
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-exec-charges-model-label">Charges</InputLabel>
                      <Select
                        labelId="bt-exec-charges-model-label"
                        label="Charges"
                        value={executionChargesModel}
                        onChange={(e) => setExecutionChargesModel(e.target.value as ChargesModel)}
                      >
                        <MenuItem value="BROKER">Broker estimate (India equity)</MenuItem>
                        <MenuItem value="BPS">Manual (bps)</MenuItem>
                      </Select>
                    </FormControl>
                  </Stack>

                  <Stack direction="row" spacing={1}>
                    {executionChargesModel === 'BPS' ? (
                      <TextField
                        label="Charges (bps)"
                        size="small"
                        type="number"
                        value={executionChargesBps}
                        onChange={(e) => setExecutionChargesBps(Number(e.target.value))}
                        inputProps={{ min: 0, max: 2000 }}
                        fullWidth
                      />
                    ) : (
                      <FormControl fullWidth size="small">
                        <InputLabel id="bt-exec-charges-broker-label">Broker</InputLabel>
                        <Select
                          labelId="bt-exec-charges-broker-label"
                          label="Broker"
                          value={executionChargesBroker}
                          onChange={(e) => setExecutionChargesBroker(e.target.value as BrokerName)}
                        >
                          <MenuItem value="zerodha">Zerodha</MenuItem>
                          <MenuItem value="angelone">AngelOne</MenuItem>
                        </Select>
                      </FormControl>
                    )}

	                    {executionChargesModel === 'BROKER' && executionProduct === 'CNC' && (
	                      <FormControl fullWidth size="small">
	                        <InputLabel id="bt-exec-dp-label">DP charges</InputLabel>
	                        <Select
                          labelId="bt-exec-dp-label"
                          label="DP charges"
                          value={executionIncludeDpCharges ? 'ON' : 'OFF'}
                          onChange={(e) => setExecutionIncludeDpCharges(e.target.value === 'ON')}
                        >
                          <MenuItem value="ON">Include DP (delivery sell)</MenuItem>
                          <MenuItem value="OFF">Exclude DP</MenuItem>
                        </Select>
	                      </FormControl>
	                    )}
	                  </Stack>
	                  {executionChargesModel === 'BROKER' && (
	                    <Typography variant="caption" color="text.secondary">
	                      Estimates India equity charges (brokerage + STT + exchange + SEBI + stamp duty (WB buy-side) + GST
	                      and optional DP on delivery sell). Rates are approximate.
	                    </Typography>
	                  )}
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

                <Paper variant="outlined" sx={{ p: 1 }}>
                  <Stack spacing={1}>
                    <Typography variant="caption" color="text.secondary">
                      Gate / regime filter (optional): skip rebalances unless the condition is true.
                    </Typography>
                    <Stack direction="row" spacing={1}>
                      <FormControl fullWidth size="small">
                        <InputLabel id="bt-pf-gate-source-label">Gate</InputLabel>
                        <Select
                          labelId="bt-pf-gate-source-label"
                          label="Gate"
                          value={portfolioGateSource}
                          onChange={(e) => setPortfolioGateSource(e.target.value as GateSource)}
                        >
                          <MenuItem value="NONE">(none)</MenuItem>
                          <MenuItem value="GROUP_INDEX">Group index (synthetic)</MenuItem>
                          <MenuItem value="SYMBOL">Symbol</MenuItem>
                        </Select>
                      </FormControl>
                      {portfolioGateSource === 'GROUP_INDEX' && (
                        <TextField
                          label="Min coverage (%)"
                          size="small"
                          type="number"
                          value={portfolioGateMinCoveragePct}
                          onChange={(e) => setPortfolioGateMinCoveragePct(Number(e.target.value))}
                          inputProps={{ min: 0, max: 100 }}
                          sx={{ width: 160 }}
                        />
                      )}
                    </Stack>

                    {portfolioGateSource !== 'NONE' && (
                      <>
                        <TextField
                          label="Gate DSL (indicators only, 1d)"
                          size="small"
                          multiline
                          minRows={2}
                          value={portfolioGateDsl}
                          onChange={(e) => setPortfolioGateDsl(e.target.value)}
                          placeholder="Example: MA(50) > MA(200) AND RSI(14) < 35"
                        />

                        {portfolioGateSource === 'GROUP_INDEX' && (
                          <FormControl fullWidth size="small">
                            <InputLabel id="bt-pf-gate-group-label">Gate group</InputLabel>
                            <Select
                              labelId="bt-pf-gate-group-label"
                              label="Gate group"
                              value={portfolioGateGroupId}
                              onChange={(e) => {
                                const raw = e.target.value
                                setPortfolioGateGroupId(raw === '' ? '' : Number(raw))
                              }}
                            >
                              <MenuItem value="">(use selected group)</MenuItem>
                              {groups.map((g) => (
                                <MenuItem key={g.id} value={String(g.id)}>
                                  {g.name}
                                </MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        )}

                        {portfolioGateSource === 'SYMBOL' && (
                          <Stack direction="row" spacing={1}>
                            <FormControl size="small" sx={{ minWidth: 120 }}>
                              <InputLabel id="bt-pf-gate-exch-label">Exchange</InputLabel>
                              <Select
                                labelId="bt-pf-gate-exch-label"
                                label="Exchange"
                                value={portfolioGateSymbolExchange}
                                onChange={(e) => setPortfolioGateSymbolExchange(String(e.target.value))}
                              >
                                <MenuItem value="NSE">NSE</MenuItem>
                                <MenuItem value="BSE">BSE</MenuItem>
                              </Select>
                            </FormControl>
                            <TextField
                              label="Symbol"
                              size="small"
                              value={portfolioGateSymbol}
                              onChange={(e) => setPortfolioGateSymbol(e.target.value.toUpperCase())}
                              placeholder="Example: NIFTY50 or RELIANCE"
                              fullWidth
                            />
                          </Stack>
                        )}

                        <Typography variant="caption" color="text.secondary">
                          Coverage applies only to Group index gates (dynamic availability set; default 90%).
                        </Typography>
                      </>
                    )}
                  </Stack>
                </Paper>

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
                    inputProps={{ min: 0 }}
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
                </Stack>

                <Stack spacing={1}>
                  <Stack direction="row" spacing={1}>
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-pf-fill-label">Fill timing</InputLabel>
	                      <Select
	                        labelId="bt-pf-fill-label"
	                        label="Fill timing"
	                        value={portfolioFillTiming}
	                        onChange={(e) => setPortfolioFillTiming(e.target.value as FillTiming)}
	                      >
	                        <MenuItem value="CLOSE" disabled={portfolioProduct === 'MIS'}>
	                          Same day close
	                        </MenuItem>
	                        <MenuItem value="NEXT_OPEN">Next day open</MenuItem>
	                      </Select>
	                    </FormControl>
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-pf-product-label">Product</InputLabel>
                      <Select
                        labelId="bt-pf-product-label"
                        label="Product"
                        value={portfolioProduct}
                        onChange={(e) => {
                          const next = e.target.value as ProductType
                          setPortfolioProduct(next)
                          if (next === 'MIS') setPortfolioFillTiming('NEXT_OPEN')
                        }}
                      >
                        <MenuItem value="CNC">CNC (delivery)</MenuItem>
                        <MenuItem value="MIS">MIS (intraday)</MenuItem>
                      </Select>
                    </FormControl>
                  </Stack>

                  <Stack direction="row" spacing={1}>
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-pf-charges-model-label">Charges</InputLabel>
                      <Select
                        labelId="bt-pf-charges-model-label"
                        label="Charges"
                        value={portfolioChargesModel}
                        onChange={(e) => setPortfolioChargesModel(e.target.value as ChargesModel)}
                      >
                        <MenuItem value="BROKER">Broker estimate (India equity)</MenuItem>
                        <MenuItem value="BPS">Manual (bps)</MenuItem>
                      </Select>
                    </FormControl>
                    {portfolioChargesModel === 'BPS' ? (
                      <TextField
                        label="Charges (bps)"
                        size="small"
                        type="number"
                        value={portfolioChargesBps}
                        onChange={(e) => setPortfolioChargesBps(Number(e.target.value))}
                        inputProps={{ min: 0, max: 2000 }}
                        fullWidth
                      />
                    ) : (
                      <FormControl fullWidth size="small">
                        <InputLabel id="bt-pf-charges-broker-label">Broker</InputLabel>
                        <Select
                          labelId="bt-pf-charges-broker-label"
                          label="Broker"
                          value={portfolioChargesBroker}
                          onChange={(e) => setPortfolioChargesBroker(e.target.value as BrokerName)}
                        >
                          <MenuItem value="zerodha">Zerodha</MenuItem>
                          <MenuItem value="angelone">AngelOne</MenuItem>
                        </Select>
                      </FormControl>
                    )}
                  </Stack>

	                  {portfolioChargesModel === 'BROKER' && portfolioProduct === 'CNC' && (
	                    <FormControl fullWidth size="small">
	                      <InputLabel id="bt-pf-dp-label">DP charges</InputLabel>
                      <Select
                        labelId="bt-pf-dp-label"
                        label="DP charges"
                        value={portfolioIncludeDpCharges ? 'ON' : 'OFF'}
                        onChange={(e) => setPortfolioIncludeDpCharges(e.target.value === 'ON')}
                      >
                        <MenuItem value="ON">Include DP (delivery sell)</MenuItem>
                        <MenuItem value="OFF">Exclude DP</MenuItem>
                      </Select>
	                    </FormControl>
	                  )}
	                  {portfolioChargesModel === 'BROKER' && (
	                    <Typography variant="caption" color="text.secondary">
	                      Estimates India equity charges (brokerage + STT + exchange + SEBI + stamp duty (WB buy-side) + GST
	                      and optional DP on delivery sell). Rates are approximate.
	                    </Typography>
	                  )}
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
	                      setPortfolioChargesModel('BPS')
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
	                      setPortfolioChargesModel('BROKER')
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
	                      setPortfolioChargesModel('BROKER')
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
	                      setPortfolioChargesModel('BROKER')
	                    }}
	                  >
	                    Preset: Risk parity (6M)
	                  </Button>
                </Stack>
              </Stack>
            )}

            {tab === 'STRATEGY' && (
              <Stack spacing={1.5}>
                <FormControl fullWidth size="small">
                  <InputLabel id="bt-strategy-symbol-label">Symbol</InputLabel>
                  <Select
                    labelId="bt-strategy-symbol-label"
                    label="Symbol"
                    value={strategySymbolKey}
                    onChange={(e) => setStrategySymbolKey(String(e.target.value))}
                  >
                    <MenuItem value="">(select)</MenuItem>
                    {strategySymbolOptions.map((s) => (
                      <MenuItem key={s.key} value={s.key}>
                        {s.exchange}:{s.symbol}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-strategy-timeframe-label">Timeframe</InputLabel>
                    <Select
                      labelId="bt-strategy-timeframe-label"
                      label="Timeframe"
                      value={strategyTimeframe}
                      onChange={(e) => setStrategyTimeframe(e.target.value as StrategyTimeframe)}
                    >
                      <MenuItem value="1m">1m</MenuItem>
                      <MenuItem value="5m">5m</MenuItem>
                      <MenuItem value="15m">15m</MenuItem>
                      <MenuItem value="30m">30m</MenuItem>
                      <MenuItem value="1h">1h</MenuItem>
                      <MenuItem value="1d" disabled={strategyProduct === 'MIS'}>
                        1d
                      </MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-strategy-preset-label">Preset</InputLabel>
                    <Select
                      labelId="bt-strategy-preset-label"
                      label="Preset"
                      value=""
                      onChange={(e) => applyStrategyPreset(String(e.target.value))}
                    >
                      <MenuItem value="">(choose)</MenuItem>
                      {strategyPresets.map((p) => (
                        <MenuItem key={p.id} value={p.id}>
                          {p.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>

                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-strategy-product-label">Product</InputLabel>
                    <Select
                      labelId="bt-strategy-product-label"
                      label="Product"
                      value={strategyProduct}
                      onChange={(e) => setStrategyProduct(e.target.value as ProductType)}
                    >
                      <MenuItem value="CNC">CNC (delivery)</MenuItem>
                      <MenuItem value="MIS">MIS (intraday)</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-strategy-direction-label">Direction</InputLabel>
                    <Select
                      labelId="bt-strategy-direction-label"
                      label="Direction"
                      value={strategyDirection}
                      onChange={(e) => setStrategyDirection(e.target.value as StrategyDirection)}
                      disabled={strategyProduct === 'CNC'}
                    >
                      <MenuItem value="LONG">Long</MenuItem>
                      <MenuItem value="SHORT">Short</MenuItem>
                    </Select>
                  </FormControl>
                </Stack>

                <TextField
                  label="Entry DSL (evaluate at close)"
                  size="small"
                  multiline
                  minRows={2}
                  value={strategyEntryDsl}
                  onChange={(e) => setStrategyEntryDsl(e.target.value)}
                  placeholder="Example: RSI(14) < 30"
                />
                <TextField
                  label="Exit DSL (evaluate at close)"
                  size="small"
                  multiline
                  minRows={2}
                  value={strategyExitDsl}
                  onChange={(e) => setStrategyExitDsl(e.target.value)}
                  placeholder="Example: RSI(14) > 70"
                />

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Initial cash"
                    size="small"
                    type="number"
                    value={strategyInitialCash}
                    onChange={(e) => setStrategyInitialCash(Number(e.target.value))}
                    inputProps={{ min: 0 }}
                    fullWidth
                  />
                  <TextField
                    label="Position size (%)"
                    size="small"
                    type="number"
                    value={strategyPositionSizePct}
                    onChange={(e) => setStrategyPositionSizePct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Stop loss (%)"
                    size="small"
                    type="number"
                    value={strategyStopLossPct}
                    onChange={(e) => setStrategyStopLossPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                  <TextField
                    label="Take profit (%)"
                    size="small"
                    type="number"
                    value={strategyTakeProfitPct}
                    onChange={(e) => setStrategyTakeProfitPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                  <TextField
                    label="Trailing stop (%)"
                    size="small"
                    type="number"
                    value={strategyTrailingStopPct}
                    onChange={(e) => setStrategyTrailingStopPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Max equity DD (global, %)"
                    size="small"
                    type="number"
                    value={strategyMaxEquityDdGlobalPct}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      if (!Number.isFinite(n)) return
                      setStrategyMaxEquityDdGlobalPct(Math.min(100, Math.abs(n)))
                    }}
                    inputProps={{ min: -100, max: 100 }}
                    fullWidth
                    helperText="0 disables. Enter 5 (or -5) for a 5% equity drawdown. Peak since start; triggers exit + blocks new entries."
                  />
                  <TextField
                    label="Max equity DD (per-trade, %)"
                    size="small"
                    type="number"
                    value={strategyMaxEquityDdTradePct}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      if (!Number.isFinite(n)) return
                      setStrategyMaxEquityDdTradePct(Math.min(100, Math.abs(n)))
                    }}
                    inputProps={{ min: -100, max: 100 }}
                    fullWidth
                    helperText="0 disables. Enter 5 (or -5) for a 5% equity drawdown. Peak since entry; resets on each entry."
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Slippage (bps)"
                    size="small"
                    type="number"
                    value={strategySlippageBps}
                    onChange={(e) => setStrategySlippageBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-strategy-charges-model-label">Charges</InputLabel>
                    <Select
                      labelId="bt-strategy-charges-model-label"
                      label="Charges"
                      value={strategyChargesModel}
                      onChange={(e) => setStrategyChargesModel(e.target.value as ChargesModel)}
                    >
                      <MenuItem value="BROKER">Broker estimate (India equity)</MenuItem>
                      <MenuItem value="BPS">Manual (bps)</MenuItem>
                    </Select>
                  </FormControl>
                </Stack>

                {strategyChargesModel === 'BPS' ? (
                  <TextField
                    label="Charges (bps)"
                    size="small"
                    type="number"
                    value={strategyChargesBps}
                    onChange={(e) => setStrategyChargesBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                ) : (
                  <Stack spacing={1}>
                    <FormControl fullWidth size="small" disabled>
                      <InputLabel id="bt-strategy-broker-label">Broker</InputLabel>
                      <Select labelId="bt-strategy-broker-label" label="Broker" value="zerodha">
                        <MenuItem value="zerodha">Zerodha</MenuItem>
                      </Select>
                    </FormControl>
                    {strategyProduct === 'CNC' && (
                      <FormControl fullWidth size="small">
                        <InputLabel id="bt-strategy-dp-label">DP charges</InputLabel>
                        <Select
                          labelId="bt-strategy-dp-label"
                          label="DP charges"
                          value={strategyIncludeDpCharges ? 'ON' : 'OFF'}
                          onChange={(e) => setStrategyIncludeDpCharges(e.target.value === 'ON')}
                        >
                          <MenuItem value="ON">Include DP (delivery sell)</MenuItem>
                          <MenuItem value="OFF">Exclude DP</MenuItem>
                        </Select>
                      </FormControl>
                    )}
                    <Typography variant="caption" color="text.secondary">
                      Evaluates entry/exit at close and fills at next open. CNC is long-only. MIS positions are squared off at end of day.
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Broker model estimates India equity charges (brokerage + STT + exchange + SEBI + stamp duty (WB buy-side) + GST and optional DP on
                      delivery sell). Rates are approximate.
                    </Typography>
                  </Stack>
                )}
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
              <Button
                size="small"
                color="error"
                variant="outlined"
                onClick={() => setDeleteConfirmOpen(true)}
                disabled={running || selectedRunIds.length === 0}
              >
                Delete selected
              </Button>
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
                columnVisibilityModel={runColumnVisibilityModel}
                checkboxSelection
                rowSelectionModel={selectedRunIds}
                onRowSelectionModelChange={(model) =>
                  setSelectedRunIds(
                    (model as Array<string | number>)
                      .map((x) => Number(x))
                      .filter((x) => Number.isFinite(x)),
                  )
                }
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

	                {selectedRun.status === 'FAILED' && selectedRun.error_message ? (
	                  <Typography
	                    variant="body2"
	                    color="error"
	                    sx={{ mt: 1, whiteSpace: 'pre-wrap' }}
	                  >
	                    Error: {selectedRun.error_message}
	                  </Typography>
	                ) : null}

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
                        getRowHeight={() => 'auto'}
                      />
                    </Box>
                  </Box>
                )}

                {tab === 'PORTFOLIO' &&
                  selectedRun.status === 'COMPLETED' &&
                  portfolioEquityCandles.length > 0 && (
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="subtitle2">Equity curve</Typography>
                      {portfolioMetrics ? (
                        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
                          <Chip
                            size="small"
                            label={`Total: ${Number(portfolioMetrics.total_return_pct ?? 0).toFixed(2)}%`}
                          />
                          <Chip size="small" label={`CAGR: ${Number(portfolioMetrics.cagr_pct ?? 0).toFixed(2)}%`} />
                          <Chip
                            size="small"
                            label={`Max DD: ${Number(portfolioMetrics.max_drawdown_pct ?? 0).toFixed(2)}%`}
                          />
                          <Chip
                            size="small"
                            label={`Turnover: ${Number(portfolioMetrics.turnover_pct_total ?? 0).toFixed(1)}%`}
                          />
                          {Number.isFinite(Number(portfolioMetrics.total_charges)) && (
                            <Chip
                              size="small"
                              label={`Charges: ${fmtInr(Number(portfolioMetrics.total_charges ?? 0), 0)}`}
                            />
                          )}
                          <Chip size="small" label={`Rebalances: ${Number(portfolioMetrics.rebalance_count ?? 0)}`} />
                          {Number(portfolioMetrics.rebalance_skipped_count ?? 0) > 0 && (
                            <Tooltip
                              title={
                                portfolioMeta?.gate
                                  ? `Gate blocked ${Number(portfolioMetrics.rebalance_skipped_count ?? 0)} rebalance(s).`
                                  : `Skipped ${Number(portfolioMetrics.rebalance_skipped_count ?? 0)} rebalance(s).`
                              }
                            >
                              <Chip
                                size="small"
                                color="warning"
                                label={`Skipped: ${Number(portfolioMetrics.rebalance_skipped_count ?? 0)}`}
                              />
                            </Tooltip>
                          )}
                        </Stack>
                      ) : null}

                      <Box sx={{ mt: 1 }}>
                        <PriceChart
                          candles={portfolioEquityCandles}
                          chartType="line"
                          height={260}
                          overlays={portfolioCompareOverlay}
                        />
                      </Box>

                      {runs.length > 1 ? (
                        <Box sx={{ mt: 2 }}>
                          <FormControl fullWidth size="small">
                            <InputLabel id="bt-compare-label">Compare run</InputLabel>
                            <Select
                              labelId="bt-compare-label"
                              label="Compare run"
                              value={compareRunId}
                              onChange={(e) =>
                                setCompareRunId(e.target.value === '' ? '' : Number(e.target.value))
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
                      ) : null}

                      {portfolioDrawdownCandles.length > 0 ? (
                        <Box sx={{ mt: 2 }}>
                          <Typography variant="subtitle2">Drawdown (%)</Typography>
                          <Box sx={{ mt: 1 }}>
                            <PriceChart candles={portfolioDrawdownCandles} chartType="line" height={180} />
                          </Box>
                        </Box>
                      ) : null}

                      {portfolioActionsRows.length > 0 ? (
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
                      ) : null}
                    </Box>
                  )}

                {tab === 'STRATEGY' &&
                  selectedRun.status === 'COMPLETED' &&
                  strategyEquityCandles.length > 0 && (
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="subtitle2">Equity curve</Typography>
                      {strategyMetrics ? (
                        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
                          <Chip size="small" label={`Total: ${Number(strategyMetrics.total_return_pct ?? 0).toFixed(2)}%`} />
                          <Chip size="small" label={`CAGR: ${Number(strategyMetrics.cagr_pct ?? 0).toFixed(2)}%`} />
                          <Chip size="small" label={`Max DD: ${Number(strategyMetrics.max_drawdown_pct ?? 0).toFixed(2)}%`} />
                          <Chip size="small" label={`Turnover: ${Number(strategyMetrics.turnover_pct_total ?? 0).toFixed(1)}%`} />
                          <Chip size="small" label={`Charges: ${fmtInr(Number(strategyMetrics.total_charges ?? 0), 0)}`} />
                          {strategyBaselines?.start_to_end ? (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Buy&hold: ${Number((strategyBaselines.start_to_end as any)?.total_return_pct ?? 0).toFixed(2)}%`}
                            />
                          ) : null}
                          {strategyBaselines?.first_entry_to_end ? (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`Hold from 1st entry: ${Number((strategyBaselines.first_entry_to_end as any)?.total_return_pct ?? 0).toFixed(2)}%`}
                            />
                          ) : null}
                          {strategyTradeStats ? (
                            <>
                              <Chip size="small" label={`Trades: ${Number(strategyTradeStats.count ?? 0)}`} />
                              <Chip size="small" label={`Win: ${Number(strategyTradeStats.win_rate_pct ?? 0).toFixed(1)}%`} />
                              {typeof strategyProfitValue === 'number' ? (
                                <Chip size="small" label={`Profit: ${fmtInr(strategyProfitValue, 0)}`} />
                              ) : null}
                            </>
                          ) : null}
                        </Stack>
                      ) : null}

                      <Box sx={{ mt: 1 }}>
                        <PriceChart
                          candles={strategyEquityCandles}
                          chartType="line"
                          height={260}
                          overlays={strategyBaselineOverlays}
                          markers={strategyTradeMarkers}
                          showLegend
                          baseSeriesName="Strategy equity"
                        />
                      </Box>

                      {strategyDrawdownCandles.length > 0 ? (
                        <Box sx={{ mt: 2 }}>
                          <Typography variant="subtitle2">Drawdown (%)</Typography>
                          <Box sx={{ mt: 1 }}>
                            <PriceChart candles={strategyDrawdownCandles} chartType="line" height={180} />
                          </Box>
                        </Box>
                      ) : null}

                      {strategyTradesRows.length > 0 ? (
                        <Box sx={{ mt: 2 }}>
                          <Typography variant="subtitle2">Trades</Typography>
                          <Box sx={{ height: 260, mt: 1 }}>
                            <DataGrid
                              rows={strategyTradesRows}
                              columns={strategyTradesColumns}
                              density="compact"
                              disableRowSelectionOnClick
                              pageSizeOptions={[5, 10, 25]}
                              initialState={{ pagination: { paginationModel: { pageSize: 5 } } }}
                            />
                          </Box>
                        </Box>
                      ) : null}
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

      <KeyValueJsonDialog
        open={detailsRun != null}
        onClose={() => setDetailsRun(null)}
        title={`DSL / Ranking — Run #${detailsRun?.id ?? ''}`}
        value={
          detailsRun
            ? {
                id: detailsRun.id,
                kind: detailsRun.kind,
                status: detailsRun.status,
                created_at: detailsRun.created_at,
                title: detailsRun.title,
                details: renderDetails(detailsRun),
                universe: getRunUniverse(detailsRun),
                config: getRunConfig(detailsRun),
              }
            : {}
        }
      />

      <Dialog open={deleteConfirmOpen} onClose={() => setDeleteConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Delete backtest runs</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete {selectedRunIds.length} selected run(s)? This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmOpen(false)} disabled={running}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              setDeleteConfirmOpen(false)
              void handleDeleteSelected()
            }}
            disabled={running || selectedRunIds.length === 0}
          >
            Delete
          </Button>
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
