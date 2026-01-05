import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import CloseIcon from '@mui/icons-material/Close'
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Drawer from '@mui/material/Drawer'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Alert from '@mui/material/Alert'
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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTheme } from '@mui/material/styles'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useNavigate } from 'react-router-dom'

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
import {
  createDeployment,
  listDeployments,
  type DeploymentKind,
  type DeploymentUniverse,
} from '../services/deployments'
import { useTimeSettings } from '../timeSettingsContext'
import { parseBackendDate } from '../utils/datetime'

import backtestingHelpText from '../../../docs/backtesting_page_help.md?raw'
import portfolioBacktestingHelpText from '../../../docs/backtesting_portfolio_help.md?raw'
import portfolioStrategyBacktestingHelpText from '../../../docs/backtesting_portfolio_strategy_help.md?raw'
import riskParityBacktestingHelpText from '../../../docs/backtesting_risk_parity_help.md?raw'
import rotationBacktestingHelpText from '../../../docs/backtesting_rotation_help.md?raw'
import signalBacktestingHelpText from '../../../docs/backtesting_signal_help.md?raw'
import strategyBacktestingHelpText from '../../../docs/backtesting_strategy_help.md?raw'
import executionBacktestingHelpText from '../../../docs/backtesting_execution_help.md?raw'

type UniverseMode = 'HOLDINGS' | 'GROUP' | 'BOTH'

type BacktestTab = 'SIGNAL' | 'PORTFOLIO' | 'PORTFOLIO_STRATEGY' | 'EXECUTION' | 'STRATEGY'
type DrawerBacktestTab = 'PORTFOLIO' | 'PORTFOLIO_STRATEGY' | 'STRATEGY'

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
type PortfolioStrategyAllocationMode = 'EQUAL' | 'RANKING'
type PortfolioStrategySizingMode = 'PCT_EQUITY' | 'FIXED_CASH' | 'CASH_PER_SLOT'
type PortfolioStrategyRankingMetric = 'PERF_PCT'

type DeploymentPrefill = {
  kind: DeploymentKind
  universe: DeploymentUniverse
  config: Record<string, unknown>
}

type DeployConfirmState = {
  open: boolean
  existingId: number
  existingName: string
  pending: {
    name: string
    kind: DeploymentKind
    universe: DeploymentUniverse
    config: Record<string, unknown>
  }
}

function slugifyNamePart(raw: string, maxLen = 32): string {
  const s = (raw || '').trim().toUpperCase()
  const cleaned = s.replace(/[^A-Z0-9]+/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '')
  if (!cleaned) return 'UNKNOWN'
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen) : cleaned
}

function shortUuid6(): string {
  try {
    return crypto.randomUUID().replace(/-/g, '').slice(0, 6).toUpperCase()
  } catch {
    return Math.random().toString(16).slice(2, 8).toUpperCase().padEnd(6, '0')
  }
}

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

function fmtPrice(value: unknown, digits = 2): string {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function formatYmdHmsAmPm(value: unknown, displayTimeZone: 'LOCAL' | string): string {
  const raw = typeof value === 'string' ? value.trim() : ''
  const isNaive =
    Boolean(raw) &&
    !/(z|[+-]\d{2}:?\d{2})$/i.test(raw) &&
    /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw)

  const d = parseBackendDate(
    isNaive ? raw.replace(' ', 'T') + '+05:30' : value,
  )
  if (!d) return ''

  const opts: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    ...(displayTimeZone === 'LOCAL' ? {} : { timeZone: displayTimeZone }),
  }

  const parts = new Intl.DateTimeFormat('en-US', opts).formatToParts(d)
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? ''

  const year = get('year')
  const month = get('month')
  const day = get('day')
  const hour = get('hour')
  const minute = get('minute')
  const second = get('second')
  const dayPeriod = get('dayPeriod')

  if (!year || !month || !day) return ''
  return `${year}-${month}-${day} ${hour}:${minute}:${second} ${dayPeriod}`
}

function csvEscape(value: unknown): string {
  const raw = value == null ? '' : String(value)
  if (/[",\n\r]/.test(raw)) return `"${raw.replace(/"/g, '""')}"`
  return raw
}

function downloadCsv(filename: string, rows: Array<Record<string, unknown>>): void {
  if (!rows.length) return
  const headers = Object.keys(rows[0] ?? {})
  const lines = [
    headers.map(csvEscape).join(','),
    ...rows.map((r) => headers.map((h) => csvEscape(r[h])).join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
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
  const theme = useTheme()
  const smUp = useMediaQuery(theme.breakpoints.up('sm'))
  const mdUp = useMediaQuery(theme.breakpoints.up('md'))
  const { displayTimeZone } = useTimeSettings()
  const navigate = useNavigate()
  const [tab, setTab] = useState<BacktestTab>('SIGNAL')
  const kind: BacktestKind = tab
  const drawerEnabled = tab === 'STRATEGY' || tab === 'PORTFOLIO' || tab === 'PORTFOLIO_STRATEGY'

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

  const [portfolioStrategyTimeframe, setPortfolioStrategyTimeframe] =
    useState<StrategyTimeframe>('1d')
  const [portfolioStrategyEntryDsl, setPortfolioStrategyEntryDsl] = useState('RSI(14) < 30')
  const [portfolioStrategyExitDsl, setPortfolioStrategyExitDsl] = useState('RSI(14) > 70')
  const [portfolioStrategyProduct, setPortfolioStrategyProduct] = useState<ProductType>('CNC')
  const [portfolioStrategyDirection, setPortfolioStrategyDirection] =
    useState<StrategyDirection>('LONG')
  const [portfolioStrategyInitialCash, setPortfolioStrategyInitialCash] = useState(100000)
  const [portfolioStrategyMaxOpenPositions, setPortfolioStrategyMaxOpenPositions] = useState(10)
  const [portfolioStrategyAllocationMode, setPortfolioStrategyAllocationMode] =
    useState<PortfolioStrategyAllocationMode>('EQUAL')
  const [portfolioStrategyRankingMetric, setPortfolioStrategyRankingMetric] =
    useState<PortfolioStrategyRankingMetric>('PERF_PCT')
  const [portfolioStrategyRankingWindow, setPortfolioStrategyRankingWindow] = useState(20)
  const [portfolioStrategySizingMode, setPortfolioStrategySizingMode] =
    useState<PortfolioStrategySizingMode>('CASH_PER_SLOT')
  const [portfolioStrategyPositionSizePct, setPortfolioStrategyPositionSizePct] = useState(10)
  const [portfolioStrategyFixedCashPerTrade, setPortfolioStrategyFixedCashPerTrade] =
    useState(10000)
  const [portfolioStrategyMinHoldingBars, setPortfolioStrategyMinHoldingBars] = useState(0)
  const [portfolioStrategyCooldownBars, setPortfolioStrategyCooldownBars] = useState(0)
  const [portfolioStrategyMaxSymbolAllocPct, setPortfolioStrategyMaxSymbolAllocPct] = useState(0)
  const [portfolioStrategyStopLossPct, setPortfolioStrategyStopLossPct] = useState(0)
  const [portfolioStrategyTakeProfitPct, setPortfolioStrategyTakeProfitPct] = useState(0)
  const [portfolioStrategyTrailingStopPct, setPortfolioStrategyTrailingStopPct] = useState(0)
  const [portfolioStrategyMaxEquityDdGlobalPct, setPortfolioStrategyMaxEquityDdGlobalPct] =
    useState(0)
  const [portfolioStrategyMaxEquityDdTradePct, setPortfolioStrategyMaxEquityDdTradePct] =
    useState(0)
  const [portfolioStrategySlippageBps, setPortfolioStrategySlippageBps] = useState(0)
  const [portfolioStrategyChargesModel, setPortfolioStrategyChargesModel] =
    useState<ChargesModel>('BROKER')
  const [portfolioStrategyChargesBps, setPortfolioStrategyChargesBps] = useState(0)
  const [portfolioStrategyChargesBroker, setPortfolioStrategyChargesBroker] =
    useState<BrokerName>('zerodha')
  const [portfolioStrategyIncludeDpCharges, setPortfolioStrategyIncludeDpCharges] = useState(true)

  const [holdingsSymbols, setHoldingsSymbols] = useState<Array<{ symbol: string; exchange: string }>>([])

  const [runs, setRuns] = useState<BacktestRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null)
  const [compareRunId, setCompareRunId] = useState<number | ''>('')
  const [compareRun, setCompareRun] = useState<BacktestRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deployingRunId, setDeployingRunId] = useState<number | null>(null)
  const [deployConfirm, setDeployConfirm] = useState<DeployConfirmState | null>(null)
  const [running, setRunning] = useState(false)
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>([])
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [detailsRun, setDetailsRun] = useState<BacktestRun | null>(null)

  const [pinnedRunIdsByTab, setPinnedRunIdsByTab] = useState<Record<DrawerBacktestTab, number[]>>({
    STRATEGY: [],
    PORTFOLIO: [],
    PORTFOLIO_STRATEGY: [],
  })
  const [pinnedRunsById, setPinnedRunsById] = useState<Record<number, BacktestRun>>({})
  const [pinnedRunErrorsById, setPinnedRunErrorsById] = useState<Record<number, string>>({})
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTab, setDrawerTab] = useState<'selected' | number>('selected')
  const [drawerWidth, setDrawerWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return 720
    try {
      const raw = window.localStorage.getItem('st_bt_drawer_width_v1')
      const n = raw ? Number(raw) : NaN
      return Number.isFinite(n) ? Math.max(420, Math.min(1600, n)) : 720
    } catch {
      return 720
    }
  })
  const resizingRef = useRef<{ startX: number; startWidth: number } | null>(null)
  const drawerWidthRef = useRef(drawerWidth)

  useEffect(() => {
    drawerWidthRef.current = drawerWidth
  }, [drawerWidth])

  const pinnedRunIds = useMemo(() => {
    if (tab === 'STRATEGY') return pinnedRunIdsByTab.STRATEGY
    if (tab === 'PORTFOLIO') return pinnedRunIdsByTab.PORTFOLIO
    if (tab === 'PORTFOLIO_STRATEGY') return pinnedRunIdsByTab.PORTFOLIO_STRATEGY
    return []
  }, [pinnedRunIdsByTab.PORTFOLIO, pinnedRunIdsByTab.PORTFOLIO_STRATEGY, pinnedRunIdsByTab.STRATEGY, tab])

  const allPinnedRunIds = useMemo(() => {
    const ids = new Set<number>()
    for (const id of pinnedRunIdsByTab.STRATEGY) ids.add(id)
    for (const id of pinnedRunIdsByTab.PORTFOLIO) ids.add(id)
    for (const id of pinnedRunIdsByTab.PORTFOLIO_STRATEGY) ids.add(id)
    return Array.from(ids.values())
  }, [pinnedRunIdsByTab.PORTFOLIO, pinnedRunIdsByTab.PORTFOLIO_STRATEGY, pinnedRunIdsByTab.STRATEGY])

  const pinRun = useCallback((runId: number) => {
    if (tab !== 'STRATEGY' && tab !== 'PORTFOLIO' && tab !== 'PORTFOLIO_STRATEGY') return
    setPinnedRunIdsByTab((prev) => {
      const list = prev[tab]
      return list.includes(runId) ? prev : { ...prev, [tab]: [...list, runId] }
    })
    setDrawerTab(runId)
    setDrawerOpen(true)
  }, [tab])

  const closePinnedRun = useCallback((runId: number) => {
    if (tab !== 'STRATEGY' && tab !== 'PORTFOLIO' && tab !== 'PORTFOLIO_STRATEGY') return
    setPinnedRunIdsByTab((prev) => ({ ...prev, [tab]: prev[tab].filter((x) => x !== runId) }))
    setDrawerTab((prev) => (prev === runId ? 'selected' : prev))
  }, [tab])

  const openDrawerSelected = useCallback(() => {
    setDrawerTab('selected')
    setDrawerOpen(true)
  }, [])

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    if (!mdUp) setDrawerTab('selected')
  }, [mdUp])

  useEffect(() => {
    setDrawerOpen(false)
    setDrawerTab('selected')
  }, [tab])

  useEffect(() => {
    if (!mdUp || !drawerEnabled) return
    const onMove = (e: MouseEvent) => {
      const st = resizingRef.current
      if (!st) return
      const dx = st.startX - e.clientX
      const next = Math.max(420, Math.min(1600, st.startWidth + dx))
      setDrawerWidth(next)
    }
    const onUp = () => {
      if (!resizingRef.current) return
      resizingRef.current = null
      try {
        window.localStorage.setItem('st_bt_drawer_width_v1', String(drawerWidthRef.current))
      } catch {
        // ignore
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [drawerEnabled, mdUp])

  useEffect(() => {
    setPinnedRunsById((prev) => {
      const keep = new Set(allPinnedRunIds)
      const next: Record<number, BacktestRun> = {}
      for (const [k, v] of Object.entries(prev)) {
        const id = Number(k)
        if (keep.has(id)) next[id] = v
      }
      return next
    })
    setPinnedRunErrorsById((prev) => {
      const keep = new Set(allPinnedRunIds)
      const next: Record<number, string> = {}
      for (const [k, v] of Object.entries(prev)) {
        const id = Number(k)
        if (keep.has(id)) next[id] = v
      }
      return next
    })
  }, [allPinnedRunIds])

  const appBarOffsetPx = useMemo(() => (smUp ? 64 : 56), [smUp])

  const renderDrawerDetails = useCallback(
    (run: BacktestRun) => {
      if (tab === 'PORTFOLIO') {
        return (
          <PortfolioRunDetailsCard
            run={run}
            runs={runs}
            compareRunId={compareRunId}
            setCompareRunId={setCompareRunId}
            compareRun={compareRun}
          />
        )
      }
      if (tab === 'PORTFOLIO_STRATEGY') {
        return <PortfolioStrategyRunDetailsCard run={run} displayTimeZone={displayTimeZone} />
      }
      return <StrategyRunEquityCard run={run} displayTimeZone={displayTimeZone} />
    },
    [compareRun, compareRunId, displayTimeZone, runs, tab],
  )

  const getRunUniverse = useCallback((run: BacktestRun) => {
    return ((run.config as any)?.universe ?? {}) as Record<string, unknown>
  }, [])

  const getRunConfig = useCallback((run: BacktestRun) => {
    return ((run.config as any)?.config ?? {}) as Record<string, unknown>
  }, [])

  const deploymentPrefillFromRun = useCallback(
    (run: BacktestRun): DeploymentPrefill | null => {
      if (run.kind !== 'STRATEGY' && run.kind !== 'PORTFOLIO_STRATEGY') return null

      const u = getRunUniverse(run)
      const cfg = getRunConfig(run)

      const broker = String(u.broker_name ?? 'zerodha').toLowerCase()
      const broker_name = broker === 'angelone' ? 'angelone' : 'zerodha'
      const baseCfg: Record<string, unknown> = {
        ...cfg,
        broker_name,
        execution_target: String((cfg as any).execution_target ?? 'PAPER').toUpperCase(),
        source_run_id: run.id,
      }

      if (run.kind === 'STRATEGY') {
        const symbols = (u.symbols as Array<Record<string, unknown>> | undefined) ?? []
        const first = symbols[0] ?? null
        const exchange = String(first?.exchange ?? 'NSE').trim().toUpperCase() || 'NSE'
        const symbol = String(first?.symbol ?? '').trim().toUpperCase()
        if (!symbol) return null
        return {
          kind: 'STRATEGY',
          universe: { target_kind: 'SYMBOL', symbols: [{ exchange, symbol }] },
          config: baseCfg,
        }
      }

      const group_id = (u.group_id as number | null | undefined) ?? null
      if (typeof group_id !== 'number' || !Number.isFinite(group_id)) return null
      return {
        kind: 'PORTFOLIO_STRATEGY',
        universe: { target_kind: 'GROUP', group_id },
        config: baseCfg,
      }
    },
    [getRunConfig, getRunUniverse],
  )

  const buildDeploymentNameForRun = useCallback(
    (run: BacktestRun, prefill: DeploymentPrefill): string => {
      const u = getRunUniverse(run)
      const broker = String(u.broker_name ?? 'zerodha').toLowerCase()
      const brokerPart = slugifyNamePart(broker === 'angelone' ? 'angelone' : 'zerodha', 16)
      const suffix = shortUuid6()

      if (prefill.kind === 'STRATEGY') {
        const sym0 = prefill.universe.symbols?.[0]
        const exchange = slugifyNamePart(String(sym0?.exchange ?? 'NSE'), 8)
        const symbol = slugifyNamePart(String(sym0?.symbol ?? ''), 20)
        return `DEP_SYM_${exchange}_${symbol}_${brokerPart}_run${run.id}_${suffix}`
      }

      const gid = prefill.universe.group_id
      const groupName =
        typeof gid === 'number'
          ? groups.find((g) => g.id === gid)?.name ?? `${gid}`
          : 'GROUP'
      const groupPart = slugifyNamePart(groupName, 24)
      return `DEP_GRP_${groupPart}_${brokerPart}_run${run.id}_${suffix}`
    },
    [getRunUniverse, groups],
  )

  const findExistingDeploymentForRun = useCallback(
    (
      run: BacktestRun,
      prefill: DeploymentPrefill,
      deployments: any[],
    ): { id: number; name: string } | null => {
      const cfg = prefill.config ?? {}
      const tf = String(cfg.timeframe ?? '')
      const entry = String(cfg.entry_dsl ?? '').trim()
      const exit = String(cfg.exit_dsl ?? '').trim()
      const broker = String(cfg.broker_name ?? '').toLowerCase()
      const product = String(cfg.product ?? '').toUpperCase()
      const direction = String(cfg.direction ?? '').toUpperCase()

      for (const d of deployments as any[]) {
        if (!d || d.kind !== prefill.kind) continue
        const dCfg = (d.config ?? {}) as Record<string, unknown>
        const sameRun = Number(dCfg.source_run_id ?? NaN) === run.id
        const sameTf = String(dCfg.timeframe ?? '') === tf
        const sameDsl =
          String(dCfg.entry_dsl ?? '').trim() === entry &&
          String(dCfg.exit_dsl ?? '').trim() === exit
        const sameBroker = String(dCfg.broker_name ?? '').toLowerCase() === broker
        const sameProduct = String(dCfg.product ?? '').toUpperCase() === product
        const sameDirection = String(dCfg.direction ?? '').toUpperCase() === direction

        if (prefill.kind === 'STRATEGY') {
          const sym0 = prefill.universe.symbols?.[0]
          const u0 = (d.universe?.symbols ?? [])[0] ?? null
          const sameSym =
            String(u0?.exchange ?? '').toUpperCase() ===
              String(sym0?.exchange ?? '').toUpperCase() &&
            String(u0?.symbol ?? '').toUpperCase() ===
              String(sym0?.symbol ?? '').toUpperCase()
          if (
            (sameRun ||
              (sameTf &&
                sameDsl &&
                sameBroker &&
                sameProduct &&
                sameDirection &&
                sameSym)) &&
            Number.isFinite(d.id)
          ) {
            return { id: Number(d.id), name: String(d.name ?? `Deployment #${d.id}`) }
          }
        } else {
          const sameGroup =
            Number(d.universe?.group_id ?? NaN) ===
            Number(prefill.universe.group_id ?? NaN)
          if (
            (sameRun ||
              (sameTf &&
                sameDsl &&
                sameBroker &&
                sameProduct &&
                sameDirection &&
                sameGroup)) &&
            Number.isFinite(d.id)
          ) {
            return { id: Number(d.id), name: String(d.name ?? `Deployment #${d.id}`) }
          }
        }
      }
      return null
    },
    [],
  )

  const deployNowFromRun = useCallback(
    async (run: BacktestRun, opts: { forceNew: boolean }) => {
      const forceNew = Boolean(opts?.forceNew)
      const prefill = deploymentPrefillFromRun(run)
      if (!prefill) {
        throw new Error(
          run.kind === 'PORTFOLIO_STRATEGY'
            ? 'Deploy requires a GROUP universe (select a group backtest run).'
            : 'Deploy requires a valid symbol in the run universe.',
        )
      }

      const pending = {
        name: buildDeploymentNameForRun(run, prefill),
        kind: prefill.kind,
        universe: prefill.universe,
        config: prefill.config,
      }

      if (!forceNew) {
        const deps = await listDeployments({ kind: prefill.kind })
        const existing = findExistingDeploymentForRun(run, prefill, deps as any[])
        if (existing) {
          setDeployConfirm({
            open: true,
            existingId: existing.id,
            existingName: existing.name,
            pending,
          })
          return
        }
      }

      const created = await createDeployment({
        name: pending.name,
        description: null,
        kind: pending.kind,
        enabled: false,
        universe: pending.universe,
        config: pending.config,
      })
      navigate(`/deployments/${created.id}`)
    },
    [
      buildDeploymentNameForRun,
      deploymentPrefillFromRun,
      findExistingDeploymentForRun,
      navigate,
    ],
  )

  const drawerRun = useMemo(() => {
    if (!drawerEnabled) return null
    if (drawerTab === 'selected') return selectedRun
    return pinnedRunsById[drawerTab] ?? null
  }, [drawerEnabled, drawerTab, pinnedRunsById, selectedRun])

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
      if (run.kind === 'PORTFOLIO_STRATEGY') {
        const timeframe = String(cfg.timeframe ?? '')
        const product = String(cfg.product ?? 'CNC')
        const direction = String(cfg.direction ?? 'LONG')
        const entry = String(cfg.entry_dsl ?? '').trim()
        const exit = String(cfg.exit_dsl ?? '').trim()
        const alloc = String(cfg.allocation_mode ?? '')
        const sizing = String(cfg.sizing_mode ?? '')
        const maxPos = Number(cfg.max_open_positions ?? 0)
        const shorten = (s: string) => (s.length > 42 ? `${s.slice(0, 39)}…` : s)
        const posTxt = Number.isFinite(maxPos) && maxPos > 0 ? ` • maxPos ${maxPos}` : ''
        const allocTxt = alloc ? ` • ${alloc}` : ''
        const sizingTxt = sizing ? ` • ${sizing}` : ''
        return `${timeframe || '—'} • ${product}/${direction}${posTxt}${allocTxt}${sizingTxt} • entry: ${shorten(entry)} • exit: ${shorten(exit)}`
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

  const applyRunToInputs = useCallback(
    (run: BacktestRun) => {
      const u = getRunUniverse(run)
      const cfg = getRunConfig(run)

      const mode = String(u.mode ?? '').toUpperCase()
      if (mode === 'HOLDINGS' || mode === 'GROUP' || mode === 'BOTH') {
        setUniverseMode(mode as UniverseMode)
      }

      const broker = String(u.broker_name ?? '').toLowerCase()
      setBrokerName(broker === 'angelone' ? 'angelone' : 'zerodha')

      const gid = u.group_id
      setGroupId(typeof gid === 'number' ? gid : '')

      const start = String(cfg.start_date ?? '').trim()
      const end = String(cfg.end_date ?? '').trim()
      if (start) setStartDate(start)
      if (end) setEndDate(end)

      if (run.kind === 'SIGNAL') {
        const modeCfg = String(cfg.mode ?? 'DSL').toUpperCase()
        if (modeCfg === 'RANKING') {
          setSignalMode('RANKING')
          setRankingWindow(Number(cfg.ranking_window ?? cfg.window ?? 20) || 20)
          setRankingTopN(Number(cfg.top_n ?? 10) || 10)
          const cadence = String(cfg.cadence ?? 'MONTHLY').toUpperCase()
          setRankingCadence(cadence === 'WEEKLY' ? 'WEEKLY' : 'MONTHLY')
        } else {
          setSignalMode('DSL')
          setSignalDsl(String(cfg.dsl ?? '').trim() || 'RSI(14) < 30')
        }
        if (Array.isArray(cfg.forward_windows)) {
          const ws = (cfg.forward_windows as unknown[])
            .map((x) => Number(x))
            .filter((x) => Number.isFinite(x) && x > 0)
          if (ws.length) setSignalForwardWindows(ws)
        }
        return
      }

      if (run.kind === 'PORTFOLIO') {
        const method = String(cfg.method ?? 'TARGET_WEIGHTS').toUpperCase()
        if (method === 'ROTATION' || method === 'RISK_PARITY' || method === 'TARGET_WEIGHTS') {
          setPortfolioMethod(method as PortfolioMethod)
        }
        const cadence = String(cfg.cadence ?? 'MONTHLY').toUpperCase()
        setPortfolioCadence(cadence === 'WEEKLY' ? 'WEEKLY' : 'MONTHLY')

        const fill = String(cfg.fill_timing ?? 'CLOSE').toUpperCase()
        setPortfolioFillTiming(fill === 'NEXT_OPEN' ? 'NEXT_OPEN' : 'CLOSE')

        const chargesModel = String(cfg.charges_model ?? 'BPS').toUpperCase()
        setPortfolioChargesModel(chargesModel === 'BROKER' ? 'BROKER' : 'BPS')
        setPortfolioChargesBps(Number(cfg.charges_bps ?? 0) || 0)
        setPortfolioChargesBroker(String(cfg.charges_broker ?? 'zerodha') === 'angelone' ? 'angelone' : 'zerodha')

        setPortfolioInitialCash(Number(cfg.initial_cash ?? 100000) || 100000)
        setPortfolioBudgetPct(Number(cfg.budget_pct ?? 100) || 100)
        setPortfolioMaxTrades(Number(cfg.max_trades ?? 50) || 50)
        setPortfolioMinTradeValue(Number(cfg.min_trade_value ?? 0) || 0)
        setPortfolioSlippageBps(Number(cfg.slippage_bps ?? 10) || 0)

        const product = String(cfg.product ?? 'CNC').toUpperCase()
        setPortfolioProduct(product === 'MIS' ? 'MIS' : 'CNC')
        setPortfolioIncludeDpCharges(cfg.include_dp_charges !== false)

        const gateSource = String(cfg.gate_source ?? 'NONE').toUpperCase()
        setPortfolioGateSource(
          gateSource === 'SYMBOL'
            ? 'SYMBOL'
            : gateSource === 'GROUP_INDEX'
              ? 'GROUP_INDEX'
              : 'NONE',
        )
        setPortfolioGateDsl(String(cfg.gate_dsl ?? ''))
        setPortfolioGateSymbol(String(cfg.gate_symbol ?? ''))
        setPortfolioGateSymbolExchange(String(cfg.gate_symbol_exchange ?? 'NSE') || 'NSE')
        setPortfolioGateGroupId(typeof cfg.gate_group_id === 'number' ? (cfg.gate_group_id as number) : '')
        setPortfolioGateMinCoveragePct(Number(cfg.gate_min_coverage_pct ?? 80) || 0)

        setRotationTopN(Number(cfg.top_n ?? rotationTopN) || rotationTopN)
        setRotationWindow(Number(cfg.ranking_window ?? rotationWindow) || rotationWindow)
        setRotationEligibleDsl(String(cfg.eligible_dsl ?? rotationEligibleDsl))
        setRiskWindow(Number(cfg.risk_window ?? riskWindow) || riskWindow)
        setRiskMinObs(Number(cfg.min_observations ?? riskMinObs) || riskMinObs)
        setRiskMinWeight(Math.round(Number(cfg.min_weight ?? 0) * 100))
        setRiskMaxWeight(Math.round(Number(cfg.max_weight ?? 1) * 100))
        return
      }

      if (run.kind === 'STRATEGY') {
        const symbols = (u.symbols as Array<Record<string, unknown>> | undefined) ?? []
        const first = symbols[0] ?? null
        if (first) {
          const ex = String(first.exchange ?? 'NSE').trim().toUpperCase()
          const sym = String(first.symbol ?? '').trim().toUpperCase()
          if (sym) setStrategySymbolKey(`${ex}:${sym}`)
        }

        const tf = String(cfg.timeframe ?? '').trim()
        if (tf === '1m' || tf === '5m' || tf === '15m' || tf === '30m' || tf === '1h' || tf === '1d') {
          setStrategyTimeframe(tf as StrategyTimeframe)
        }

        setStrategyEntryDsl(String(cfg.entry_dsl ?? '').trim() || 'RSI(14) < 30')
        setStrategyExitDsl(String(cfg.exit_dsl ?? '').trim() || 'RSI(14) > 70')

        const product = String(cfg.product ?? 'CNC').toUpperCase()
        setStrategyProduct(product === 'MIS' ? 'MIS' : 'CNC')

        const direction = String(cfg.direction ?? 'LONG').toUpperCase()
        setStrategyDirection(direction === 'SHORT' ? 'SHORT' : 'LONG')

        setStrategyInitialCash(Number(cfg.initial_cash ?? 100000) || 100000)
        setStrategyPositionSizePct(Number(cfg.position_size_pct ?? 100) || 100)
        setStrategyStopLossPct(Number(cfg.stop_loss_pct ?? 0) || 0)
        setStrategyTakeProfitPct(Number(cfg.take_profit_pct ?? 0) || 0)
        setStrategyTrailingStopPct(Number(cfg.trailing_stop_pct ?? 0) || 0)
        setStrategyMaxEquityDdGlobalPct(Number(cfg.max_equity_dd_global_pct ?? 0) || 0)
        setStrategyMaxEquityDdTradePct(Number(cfg.max_equity_dd_trade_pct ?? 0) || 0)
        setStrategySlippageBps(Number(cfg.slippage_bps ?? 0) || 0)

        const chargesModel = String(cfg.charges_model ?? 'BROKER').toUpperCase()
        setStrategyChargesModel(chargesModel === 'BPS' ? 'BPS' : 'BROKER')
        setStrategyChargesBps(Number(cfg.charges_bps ?? 0) || 0)
        setStrategyIncludeDpCharges(cfg.include_dp_charges !== false)
        return
      }

      if (run.kind === 'PORTFOLIO_STRATEGY') {
        const tf = String(cfg.timeframe ?? '').trim()
        if (tf === '1m' || tf === '5m' || tf === '15m' || tf === '30m' || tf === '1h' || tf === '1d') {
          setPortfolioStrategyTimeframe(tf as StrategyTimeframe)
        }
        setPortfolioStrategyEntryDsl(String(cfg.entry_dsl ?? '').trim() || 'RSI(14) < 30')
        setPortfolioStrategyExitDsl(String(cfg.exit_dsl ?? '').trim() || 'RSI(14) > 70')

        const product = String(cfg.product ?? 'CNC').toUpperCase()
        setPortfolioStrategyProduct(product === 'MIS' ? 'MIS' : 'CNC')

        const direction = String(cfg.direction ?? 'LONG').toUpperCase()
        setPortfolioStrategyDirection(direction === 'SHORT' ? 'SHORT' : 'LONG')

        setPortfolioStrategyInitialCash(Number(cfg.initial_cash ?? 100000) || 100000)
        setPortfolioStrategyMaxOpenPositions(Number(cfg.max_open_positions ?? 10) || 10)

        const alloc = String(cfg.allocation_mode ?? 'EQUAL').toUpperCase()
        setPortfolioStrategyAllocationMode(alloc === 'RANKING' ? 'RANKING' : 'EQUAL')
        const rMetric = String(cfg.ranking_metric ?? 'PERF_PCT').toUpperCase()
        setPortfolioStrategyRankingMetric(rMetric === 'PERF_PCT' ? 'PERF_PCT' : 'PERF_PCT')
        setPortfolioStrategyRankingWindow(Number(cfg.ranking_window ?? 20) || 20)

        const sizing = String(cfg.sizing_mode ?? 'CASH_PER_SLOT').toUpperCase()
        setPortfolioStrategySizingMode(
          sizing === 'PCT_EQUITY'
            ? 'PCT_EQUITY'
            : sizing === 'FIXED_CASH'
              ? 'FIXED_CASH'
              : 'CASH_PER_SLOT',
        )
        setPortfolioStrategyPositionSizePct(Number(cfg.position_size_pct ?? 10) || 10)
        setPortfolioStrategyFixedCashPerTrade(Number(cfg.fixed_cash_per_trade ?? 10000) || 0)

        setPortfolioStrategyMinHoldingBars(Number(cfg.min_holding_bars ?? 0) || 0)
        setPortfolioStrategyCooldownBars(Number(cfg.cooldown_bars ?? 0) || 0)
        setPortfolioStrategyMaxSymbolAllocPct(Number(cfg.max_symbol_alloc_pct ?? 0) || 0)

        setPortfolioStrategyStopLossPct(Number(cfg.stop_loss_pct ?? 0) || 0)
        setPortfolioStrategyTakeProfitPct(Number(cfg.take_profit_pct ?? 0) || 0)
        setPortfolioStrategyTrailingStopPct(Number(cfg.trailing_stop_pct ?? 0) || 0)

        setPortfolioStrategyMaxEquityDdGlobalPct(Number(cfg.max_equity_dd_global_pct ?? 0) || 0)
        setPortfolioStrategyMaxEquityDdTradePct(Number(cfg.max_equity_dd_trade_pct ?? 0) || 0)

        setPortfolioStrategySlippageBps(Number(cfg.slippage_bps ?? 0) || 0)
        const chargesModel = String(cfg.charges_model ?? 'BROKER').toUpperCase()
        setPortfolioStrategyChargesModel(chargesModel === 'BPS' ? 'BPS' : 'BROKER')
        setPortfolioStrategyChargesBps(Number(cfg.charges_bps ?? 0) || 0)
        setPortfolioStrategyChargesBroker(
          String(cfg.charges_broker ?? 'zerodha') === 'angelone' ? 'angelone' : 'zerodha',
        )
        setPortfolioStrategyIncludeDpCharges(cfg.include_dp_charges !== false)
        return
      }

      if (run.kind === 'EXECUTION') {
        const base = cfg.base_run_id
        setExecutionBaseRunId(typeof base === 'number' ? base : '')
        const fill = String(cfg.fill_timing ?? 'NEXT_OPEN').toUpperCase()
        setExecutionFillTiming(fill === 'CLOSE' ? 'CLOSE' : 'NEXT_OPEN')
        setExecutionSlippageBps(Number(cfg.slippage_bps ?? 10) || 0)
        const chargesModel = String(cfg.charges_model ?? 'BPS').toUpperCase()
        setExecutionChargesModel(chargesModel === 'BROKER' ? 'BROKER' : 'BPS')
        setExecutionChargesBps(Number(cfg.charges_bps ?? 0) || 0)
        setExecutionChargesBroker(String(cfg.charges_broker ?? 'zerodha') === 'angelone' ? 'angelone' : 'zerodha')
        const product = String(cfg.product ?? 'CNC').toUpperCase()
        setExecutionProduct(product === 'MIS' ? 'MIS' : 'CNC')
        setExecutionIncludeDpCharges(cfg.include_dp_charges !== false)
      }
    },
    [
      getRunConfig,
      getRunUniverse,
      riskMaxWeight,
      riskMinObs,
      riskWindow,
      rotationEligibleDsl,
      rotationTopN,
      rotationWindow,
    ],
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
      const missing = allPinnedRunIds.filter((id) => pinnedRunsById[id] == null)
      if (!missing.length) return
      for (const id of missing) {
        try {
          const run = await getBacktestRun(id)
          if (!active) return
          setPinnedRunsById((prev) => ({ ...prev, [id]: run }))
          setPinnedRunErrorsById((prev) => {
            const next = { ...prev }
            delete next[id]
            return next
          })
        } catch (err) {
          if (!active) return
          setPinnedRunErrorsById((prev) => ({
            ...prev,
            [id]: err instanceof Error ? err.message : 'Failed to load run',
          }))
        }
      }
    })()
    return () => {
      active = false
    }
  }, [allPinnedRunIds, pinnedRunsById])

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
    if (tab !== 'PORTFOLIO_STRATEGY') return
    if (portfolioStrategyProduct === 'CNC' && portfolioStrategyDirection !== 'LONG') {
      setPortfolioStrategyDirection('LONG')
    }
  }, [portfolioStrategyDirection, portfolioStrategyProduct, tab])

  useEffect(() => {
    if (tab !== 'PORTFOLIO_STRATEGY') return
    if (portfolioStrategyProduct === 'MIS' && portfolioStrategyTimeframe === '1d') {
      setPortfolioStrategyTimeframe('1h')
    }
  }, [portfolioStrategyProduct, portfolioStrategyTimeframe, tab])

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
            : kind === 'PORTFOLIO_STRATEGY'
              ? `Portfolio strategy backtest (${portfolioStrategyTimeframe})`
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
      if (kind === 'PORTFOLIO_STRATEGY') {
        if (universeMode !== 'GROUP') {
          throw new Error('Portfolio strategy backtests currently require Universe = Group.')
        }
        if (typeof groupId !== 'number') {
          throw new Error('Please select a portfolio group for Portfolio strategy backtests.')
        }
        if (!portfolioStrategyEntryDsl.trim() || !portfolioStrategyExitDsl.trim()) {
          throw new Error('Both entry and exit DSL are required for Portfolio strategy backtests.')
        }
        if (portfolioStrategyProduct === 'CNC' && portfolioStrategyDirection !== 'LONG') {
          throw new Error('CNC does not allow short selling. Use direction LONG or switch to MIS.')
        }
        if (portfolioStrategyProduct === 'MIS' && portfolioStrategyTimeframe === '1d') {
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
          : kind === 'PORTFOLIO_STRATEGY'
            ? {
                timeframe: portfolioStrategyTimeframe,
                start_date: startDate,
                end_date: endDate,
                entry_dsl: portfolioStrategyEntryDsl,
                exit_dsl: portfolioStrategyExitDsl,
                product: portfolioStrategyProduct,
                direction: portfolioStrategyDirection,
                initial_cash: portfolioStrategyInitialCash,
                max_open_positions: portfolioStrategyMaxOpenPositions,
                allocation_mode: portfolioStrategyAllocationMode,
                ranking_metric: portfolioStrategyRankingMetric,
                ranking_window: portfolioStrategyRankingWindow,
                sizing_mode: portfolioStrategySizingMode,
                position_size_pct: portfolioStrategyPositionSizePct,
                fixed_cash_per_trade: portfolioStrategyFixedCashPerTrade,
                min_holding_bars: portfolioStrategyMinHoldingBars,
                cooldown_bars: portfolioStrategyCooldownBars,
                max_symbol_alloc_pct: portfolioStrategyMaxSymbolAllocPct,
                stop_loss_pct: portfolioStrategyStopLossPct,
                take_profit_pct: portfolioStrategyTakeProfitPct,
                trailing_stop_pct: portfolioStrategyTrailingStopPct,
                max_equity_dd_global_pct: portfolioStrategyMaxEquityDdGlobalPct,
                max_equity_dd_trade_pct: portfolioStrategyMaxEquityDdTradePct,
                slippage_bps: portfolioStrategySlippageBps,
                charges_model: portfolioStrategyChargesModel,
                charges_bps: portfolioStrategyChargesBps,
                charges_broker: portfolioStrategyChargesBroker,
                include_dp_charges: portfolioStrategyIncludeDpCharges,
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
      {
        field: 'id',
        headerName: 'Run',
        width: 90,
        renderCell: (params) => {
          const run = params.row as BacktestRun
          return (
            <Button
              size="small"
              variant="text"
              onClick={(e) => {
                e.stopPropagation()
                setSelectedRunId(run.id)
                applyRunToInputs(run)
                if (drawerEnabled) openDrawerSelected()
              }}
            >
              {run.id}
            </Button>
          )
        },
      },
      {
        field: 'created_at',
        headerName: 'Created',
        width: 210,
        valueFormatter: (value) =>
          formatYmdHmsAmPm((value as { value?: unknown })?.value ?? value, displayTimeZone),
      },
      { field: 'status', headerName: 'Status', width: 120 },
      {
        field: 'group',
        headerName: 'Group',
        width: 140,
        minWidth: 120,
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
        width: 120,
        minWidth: 120,
        flex: 0,
        sortable: false,
        renderCell: (params) => {
          const run = params.row as BacktestRun
          const text = renderDetails(run)
          return (
            <Tooltip title={text}>
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
            </Tooltip>
          )
        },
      },
    ]
    if (tab === 'STRATEGY' || tab === 'PORTFOLIO_STRATEGY') {
      cols.push({
        field: 'deploy',
        headerName: '',
        width: 130,
        sortable: false,
        filterable: false,
        renderCell: (params) => {
          const run = params.row as BacktestRun
          const disabled =
            run.status !== 'COMPLETED' ||
            running ||
            deployingRunId === run.id
          return (
            <Tooltip title="Create a deployment (STOPPED) from this run">
              <span>
                <Button
                  size="small"
                  variant="contained"
                  startIcon={<RocketLaunchIcon />}
                  disabled={disabled}
                  onClick={(e) => {
                    e.stopPropagation()
                    void (async () => {
                      setError(null)
                      setDeployingRunId(run.id)
                      try {
                        await deployNowFromRun(run, { forceNew: false })
                      } catch (err) {
                        setError(err instanceof Error ? err.message : 'Failed to deploy')
                      } finally {
                        setDeployingRunId(null)
                      }
                    })()
                  }}
                >
                  Deploy
                </Button>
              </span>
            </Tooltip>
          )
        },
      })
    }
    return cols
  }, [
    applyRunToInputs,
    deployNowFromRun,
    deployingRunId,
    displayTimeZone,
    openDrawerSelected,
    renderDetails,
    renderDuration,
    renderGroupLabel,
    renderSymbolLabel,
    running,
    tab,
  ])

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
        : tab === 'PORTFOLIO_STRATEGY'
          ? portfolioStrategyBacktestingHelpText
        : tab === 'EXECUTION'
          ? executionBacktestingHelpText
          : tab === 'STRATEGY'
            ? strategyBacktestingHelpText
            : backtestingHelpText

  const runDisabled =
    running ||
    (tab === 'PORTFOLIO' && typeof groupId !== 'number') ||
    (tab === 'PORTFOLIO_STRATEGY' &&
      (universeMode !== 'GROUP' ||
        typeof groupId !== 'number' ||
        !portfolioStrategyEntryDsl.trim() ||
        !portfolioStrategyExitDsl.trim())) ||
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

  return (
    <Box
      sx={{
        pr: drawerEnabled && drawerOpen && mdUp ? `${drawerWidth}px` : 0,
        transition: theme.transitions.create('padding-right', {
          duration: theme.transitions.duration.shortest,
        }),
      }}
    >
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
	            <Tab value="PORTFOLIO_STRATEGY" label="Portfolio strategy backtest" />
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

            {tab === 'PORTFOLIO_STRATEGY' && (
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pfs-timeframe-label">Timeframe</InputLabel>
                    <Select
                      labelId="bt-pfs-timeframe-label"
                      label="Timeframe"
                      value={portfolioStrategyTimeframe}
                      onChange={(e) =>
                        setPortfolioStrategyTimeframe(e.target.value as StrategyTimeframe)
                      }
                    >
                      <MenuItem value="1m">1m</MenuItem>
                      <MenuItem value="5m">5m</MenuItem>
                      <MenuItem value="15m">15m</MenuItem>
                      <MenuItem value="30m">30m</MenuItem>
                      <MenuItem value="1h">1h</MenuItem>
                      <MenuItem value="1d" disabled={portfolioStrategyProduct === 'MIS'}>
                        1d
                      </MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pfs-product-label">Product</InputLabel>
                    <Select
                      labelId="bt-pfs-product-label"
                      label="Product"
                      value={portfolioStrategyProduct}
                      onChange={(e) => setPortfolioStrategyProduct(e.target.value as ProductType)}
                    >
                      <MenuItem value="CNC">CNC (delivery)</MenuItem>
                      <MenuItem value="MIS">MIS (intraday)</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pfs-direction-label">Direction</InputLabel>
                    <Select
                      labelId="bt-pfs-direction-label"
                      label="Direction"
                      value={portfolioStrategyDirection}
                      onChange={(e) =>
                        setPortfolioStrategyDirection(e.target.value as StrategyDirection)
                      }
                      disabled={portfolioStrategyProduct === 'CNC'}
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
                  value={portfolioStrategyEntryDsl}
                  onChange={(e) => setPortfolioStrategyEntryDsl(e.target.value)}
                  placeholder="Example: RSI(14) < 30"
                />

                <TextField
                  label="Exit DSL (evaluate at close)"
                  size="small"
                  multiline
                  minRows={2}
                  value={portfolioStrategyExitDsl}
                  onChange={(e) => setPortfolioStrategyExitDsl(e.target.value)}
                  placeholder="Example: RSI(14) > 70"
                />

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Initial cash"
                    size="small"
                    type="number"
                    value={portfolioStrategyInitialCash}
                    onChange={(e) => setPortfolioStrategyInitialCash(Number(e.target.value))}
                    inputProps={{ min: 0 }}
                    fullWidth
                  />
                  <TextField
                    label="Max open positions"
                    size="small"
                    type="number"
                    value={portfolioStrategyMaxOpenPositions}
                    onChange={(e) =>
                      setPortfolioStrategyMaxOpenPositions(Number(e.target.value))
                    }
                    inputProps={{ min: 1, max: 200 }}
                    fullWidth
                  />
                </Stack>

                <DividerBlock title="Allocation & sizing" />

                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pfs-alloc-label">Allocation</InputLabel>
                    <Select
                      labelId="bt-pfs-alloc-label"
                      label="Allocation"
                      value={portfolioStrategyAllocationMode}
                      onChange={(e) =>
                        setPortfolioStrategyAllocationMode(
                          e.target.value as PortfolioStrategyAllocationMode,
                        )
                      }
                    >
                      <MenuItem value="EQUAL">Equal weight</MenuItem>
                      <MenuItem value="RANKING">Ranking-based</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl
                    fullWidth
                    size="small"
                    disabled={portfolioStrategyAllocationMode !== 'RANKING'}
                  >
                    <InputLabel id="bt-pfs-rank-metric-label">Ranking</InputLabel>
                    <Select
                      labelId="bt-pfs-rank-metric-label"
                      label="Ranking"
                      value={portfolioStrategyRankingMetric}
                      onChange={(e) =>
                        setPortfolioStrategyRankingMetric(
                          e.target.value as PortfolioStrategyRankingMetric,
                        )
                      }
                    >
                      <MenuItem value="PERF_PCT">PERF_PCT (momentum)</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    label="Rank window (bars)"
                    size="small"
                    type="number"
                    value={portfolioStrategyRankingWindow}
                    onChange={(e) => setPortfolioStrategyRankingWindow(Number(e.target.value))}
                    inputProps={{ min: 1, max: 1000 }}
                    fullWidth
                    disabled={portfolioStrategyAllocationMode !== 'RANKING'}
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pfs-sizing-label">Position sizing</InputLabel>
                    <Select
                      labelId="bt-pfs-sizing-label"
                      label="Position sizing"
                      value={portfolioStrategySizingMode}
                      onChange={(e) =>
                        setPortfolioStrategySizingMode(
                          e.target.value as PortfolioStrategySizingMode,
                        )
                      }
                    >
                      <MenuItem value="CASH_PER_SLOT">Use cash per slot (max positions)</MenuItem>
                      <MenuItem value="PCT_EQUITY">% of current equity</MenuItem>
                      <MenuItem value="FIXED_CASH">Fixed cash per trade</MenuItem>
                    </Select>
                  </FormControl>
                  {portfolioStrategySizingMode === 'PCT_EQUITY' ? (
                    <TextField
                      label="Position size (%)"
                      size="small"
                      type="number"
                      value={portfolioStrategyPositionSizePct}
                      onChange={(e) =>
                        setPortfolioStrategyPositionSizePct(Number(e.target.value))
                      }
                      inputProps={{ min: 0, max: 100 }}
                      fullWidth
                    />
                  ) : portfolioStrategySizingMode === 'FIXED_CASH' ? (
                    <TextField
                      label="Cash per trade"
                      size="small"
                      type="number"
                      value={portfolioStrategyFixedCashPerTrade}
                      onChange={(e) =>
                        setPortfolioStrategyFixedCashPerTrade(Number(e.target.value))
                      }
                      inputProps={{ min: 0 }}
                      fullWidth
                    />
                  ) : (
                    <TextField
                      label="Cash per trade"
                      size="small"
                      value="Auto"
                      disabled
                      fullWidth
                      helperText="Uses all available cash split by remaining slots."
                    />
                  )}
                </Stack>

                <DividerBlock title="Constraints & risk" />

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Min holding (bars)"
                    size="small"
                    type="number"
                    value={portfolioStrategyMinHoldingBars}
                    onChange={(e) => setPortfolioStrategyMinHoldingBars(Number(e.target.value))}
                    inputProps={{ min: 0, max: 1000 }}
                    fullWidth
                  />
                  <TextField
                    label="Cooldown (bars)"
                    size="small"
                    type="number"
                    value={portfolioStrategyCooldownBars}
                    onChange={(e) => setPortfolioStrategyCooldownBars(Number(e.target.value))}
                    inputProps={{ min: 0, max: 1000 }}
                    fullWidth
                  />
                  <TextField
                    label="Max alloc/symbol (%)"
                    size="small"
                    type="number"
                    value={portfolioStrategyMaxSymbolAllocPct}
                    onChange={(e) =>
                      setPortfolioStrategyMaxSymbolAllocPct(Number(e.target.value))
                    }
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                    helperText="0 disables"
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Stop loss (%)"
                    size="small"
                    type="number"
                    value={portfolioStrategyStopLossPct}
                    onChange={(e) => setPortfolioStrategyStopLossPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                  <TextField
                    label="Take profit (%)"
                    size="small"
                    type="number"
                    value={portfolioStrategyTakeProfitPct}
                    onChange={(e) => setPortfolioStrategyTakeProfitPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                  <TextField
                    label="Trailing stop (%)"
                    size="small"
                    type="number"
                    value={portfolioStrategyTrailingStopPct}
                    onChange={(e) => setPortfolioStrategyTrailingStopPct(Number(e.target.value))}
                    inputProps={{ min: 0, max: 100 }}
                    fullWidth
                  />
                </Stack>

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Max equity DD (global, %)"
                    size="small"
                    type="number"
                    value={portfolioStrategyMaxEquityDdGlobalPct}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      if (!Number.isFinite(n)) return
                      setPortfolioStrategyMaxEquityDdGlobalPct(Math.min(100, Math.abs(n)))
                    }}
                    inputProps={{ min: -100, max: 100 }}
                    fullWidth
                    helperText="0 disables. Peak since start; triggers exits + blocks new entries."
                  />
                  <TextField
                    label="Max equity DD (per-trade, %)"
                    size="small"
                    type="number"
                    value={portfolioStrategyMaxEquityDdTradePct}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      if (!Number.isFinite(n)) return
                      setPortfolioStrategyMaxEquityDdTradePct(Math.min(100, Math.abs(n)))
                    }}
                    inputProps={{ min: -100, max: 100 }}
                    fullWidth
                    helperText="0 disables. Peak since entry; resets on each entry."
                  />
                </Stack>

                <DividerBlock title="Costs" />

                <Stack direction="row" spacing={1}>
                  <TextField
                    label="Slippage (bps)"
                    size="small"
                    type="number"
                    value={portfolioStrategySlippageBps}
                    onChange={(e) => setPortfolioStrategySlippageBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                  <FormControl fullWidth size="small">
                    <InputLabel id="bt-pfs-charges-model-label">Charges</InputLabel>
                    <Select
                      labelId="bt-pfs-charges-model-label"
                      label="Charges"
                      value={portfolioStrategyChargesModel}
                      onChange={(e) =>
                        setPortfolioStrategyChargesModel(e.target.value as ChargesModel)
                      }
                    >
                      <MenuItem value="BROKER">Broker estimate (India equity)</MenuItem>
                      <MenuItem value="BPS">Manual (bps)</MenuItem>
                    </Select>
                  </FormControl>
                </Stack>

                {portfolioStrategyChargesModel === 'BPS' ? (
                  <TextField
                    label="Charges (bps)"
                    size="small"
                    type="number"
                    value={portfolioStrategyChargesBps}
                    onChange={(e) => setPortfolioStrategyChargesBps(Number(e.target.value))}
                    inputProps={{ min: 0, max: 2000 }}
                    fullWidth
                  />
                ) : (
                  <Stack spacing={1}>
                    <FormControl fullWidth size="small">
                      <InputLabel id="bt-pfs-broker-label">Broker</InputLabel>
                      <Select
                        labelId="bt-pfs-broker-label"
                        label="Broker"
                        value={portfolioStrategyChargesBroker}
                        onChange={(e) =>
                          setPortfolioStrategyChargesBroker(
                            e.target.value === 'angelone' ? 'angelone' : 'zerodha',
                          )
                        }
                      >
                        <MenuItem value="zerodha">Zerodha</MenuItem>
                        <MenuItem value="angelone">AngelOne</MenuItem>
                      </Select>
                    </FormControl>
                    {portfolioStrategyProduct === 'CNC' && (
                      <FormControl fullWidth size="small">
                        <InputLabel id="bt-pfs-dp-label">DP charges</InputLabel>
                        <Select
                          labelId="bt-pfs-dp-label"
                          label="DP charges"
                          value={portfolioStrategyIncludeDpCharges ? 'ON' : 'OFF'}
                          onChange={(e) =>
                            setPortfolioStrategyIncludeDpCharges(e.target.value === 'ON')
                          }
                        >
                          <MenuItem value="ON">Include DP (delivery sell)</MenuItem>
                          <MenuItem value="OFF">Exclude DP</MenuItem>
                        </Select>
                      </FormControl>
                    )}
                    <Typography variant="caption" color="text.secondary">
                      Evaluates signals at close and fills at next open. CNC is long-only. MIS
                      positions are squared off at end of day.
                    </Typography>
                  </Stack>
                )}
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

            <Box sx={{ height: drawerEnabled ? 'calc(100vh - 320px)' : 260, minHeight: 260 }}>
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
                onRowClick={(p, event) => {
                  const run = p.row as BacktestRun
                  setSelectedRunId(run.id)
                  applyRunToInputs(run)
                  const e = event as unknown as { ctrlKey?: boolean; metaKey?: boolean }
                  const ctrl = Boolean(e?.ctrlKey || e?.metaKey)
                  if (ctrl && drawerEnabled) {
                    pinRun(run.id)
                  }
                }}
                initialState={{
                  pagination: { paginationModel: { pageSize: 25 } },
                }}
                pageSizeOptions={[5, 10, 25, 50]}
              />
            </Box>

            {!drawerEnabled ? (
              <>
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
              </>
            ) : null}
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

      <Drawer
        anchor="right"
        variant={mdUp ? 'persistent' : 'temporary'}
        open={drawerEnabled && drawerOpen}
        onClose={closeDrawer}
        ModalProps={{ keepMounted: true }}
        sx={{
          '& .MuiDrawer-paper': {
            width: mdUp ? drawerWidth : '100%',
            maxWidth: '100vw',
            mt: `${appBarOffsetPx}px`,
            height: `calc(100% - ${appBarOffsetPx}px)`,
          },
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: 1.25,
            py: 1,
            borderBottom: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 0 }} noWrap>
            {drawerTab === 'selected'
              ? selectedRunId != null
                ? `Run details — #${selectedRunId}`
                : 'Run details'
              : `Run details — #${drawerTab}`}
          </Typography>
          {drawerRun && (drawerRun.kind === 'STRATEGY' || drawerRun.kind === 'PORTFOLIO_STRATEGY') ? (
            <Tooltip title="Create a deployment (STOPPED) from this run">
              <Button
                size="small"
                variant="contained"
                startIcon={<RocketLaunchIcon />}
                disabled={deployingRunId === drawerRun.id}
                onClick={() => {
                  void (async () => {
                    setError(null)
                    setDeployingRunId(drawerRun.id)
                    try {
                      await deployNowFromRun(drawerRun, { forceNew: false })
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to deploy')
                    } finally {
                      setDeployingRunId(null)
                    }
                  })()
                }}
              >
                Deploy
              </Button>
            </Tooltip>
          ) : null}
          <IconButton onClick={closeDrawer} size="small" aria-label="Close">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        {mdUp ? (
          <Box
            onMouseDown={(e) => {
              resizingRef.current = { startX: e.clientX, startWidth: drawerWidthRef.current }
              e.preventDefault()
              e.stopPropagation()
            }}
            sx={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: 6,
              cursor: 'col-resize',
              zIndex: 2,
            }}
          />
        ) : null}

        <Box sx={{ px: 1.25 }}>
          <Tabs
            value={drawerTab}
            onChange={(_e, v) => setDrawerTab(v as 'selected' | number)}
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab
              value="selected"
              label="Selected"
            />
            {pinnedRunIds.map((id) => (
              <Tab
                key={id}
                value={id}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <span>Run #{id}</span>
                    <IconButton
                      size="small"
                      onClick={(ev) => {
                        ev.stopPropagation()
                        closePinnedRun(id)
                      }}
                      aria-label={`Close run ${id}`}
                    >
                      <CloseIcon fontSize="inherit" />
                    </IconButton>
                  </Box>
                }
              />
            ))}
          </Tabs>
        </Box>

        <Box sx={{ px: 1.25, pb: 2, overflow: 'auto' }}>
          {drawerTab === 'selected' ? (
            selectedRun ? (
              selectedRun.kind !== tab ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  Selected run is {selectedRun.kind}; switch to the {selectedRun.kind.toLowerCase()} tab to view details.
                </Typography>
              ) : (
                renderDrawerDetails(selectedRun)
              )
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                {selectedRunId != null ? 'Loading run…' : 'Click a run to load details.'}
              </Typography>
            )
          ) : pinnedRunErrorsById[drawerTab] ? (
            <Typography variant="body2" color="error" sx={{ mt: 2 }}>
              {pinnedRunErrorsById[drawerTab]}
            </Typography>
          ) : pinnedRunsById[drawerTab] ? (
            pinnedRunsById[drawerTab].kind !== tab ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                This pinned run is {pinnedRunsById[drawerTab].kind}; switch tabs to view.
              </Typography>
            ) : (
              renderDrawerDetails(pinnedRunsById[drawerTab])
            )
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Loading run…
            </Typography>
          )}
        </Box>
      </Drawer>

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

      <Dialog
        open={deployConfirm?.open === true}
        onClose={() => setDeployConfirm(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Deployment already exists</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This strategy already has a deployment. Creating another deployment for the same strategy can lead to
            duplicate trades and potential losses.
          </Alert>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Existing deployment: <b>{deployConfirm?.existingName ?? ''}</b> (#{deployConfirm?.existingId ?? ''})
          </Typography>
          <Typography variant="body2" color="text.secondary">
            If you still want to create a new deployment entry, click “Create new anyway (unsafe)”.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              const id = deployConfirm?.existingId
              setDeployConfirm(null)
              if (typeof id === 'number') navigate(`/deployments/${id}`)
            }}
          >
            Open existing
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const pending = deployConfirm?.pending
              setDeployConfirm(null)
              if (!pending) return
              void (async () => {
                setError(null)
                try {
                  const created = await createDeployment({
                    name: pending.name,
                    description: null,
                    kind: pending.kind,
                    enabled: false,
                    universe: pending.universe,
                    config: pending.config,
                  })
                  navigate(`/deployments/${created.id}`)
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to create deployment')
                }
              })()
            }}
          >
            Create new anyway (unsafe)
          </Button>
          <Button onClick={() => setDeployConfirm(null)}>Cancel</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

function StrategyRunEquityCard({
  run,
  displayTimeZone,
}: {
  run: BacktestRun
  displayTimeZone: 'LOCAL' | string
}) {
  const [showTrades, setShowTrades] = useState(false)
  const [viewportHeight, setViewportHeight] = useState(() =>
    typeof window === 'undefined' ? 900 : window.innerHeight,
  )
  const result = (run.result as Record<string, unknown> | null | undefined) ?? null
  const series = (result?.series as Record<string, unknown> | undefined) ?? null
  const metrics = (result?.metrics as Record<string, unknown> | undefined) ?? null
  const tradeStats = (result?.trade_stats as Record<string, unknown> | undefined) ?? null
  const baselines = (result?.baselines as Record<string, unknown> | undefined) ?? null
  const trades = (result?.trades as unknown[] | undefined) ?? []

  const tradeMarkers = useMemo((): PriceSignalMarker[] => {
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
  }, [trades])

  const markerTs = useMemo(() => {
    const s = new Set<string>()
    for (const m of tradeMarkers) s.add(m.ts)
    return s
  }, [tradeMarkers])

  const equityCandles = useMemo((): PriceCandle[] => {
    const ts = (series?.ts as unknown[] | undefined) ?? []
    const equity = (series?.equity as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(ts.length, equity.length); i++) {
      const t = String(ts[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!t || !Number.isFinite(v)) continue
      candles.push({ ts: t, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return downsampleKeep(candles, 2500, (c) => markerTs.has((c as PriceCandle).ts))
  }, [markerTs, series])

  const drawdownCandles = useMemo((): PriceCandle[] => {
    const ts = (series?.ts as unknown[] | undefined) ?? []
    const dd = (series?.drawdown_pct as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(ts.length, dd.length); i++) {
      const t = String(ts[i] ?? '')
      const v = Number(dd[i] ?? NaN)
      if (!t || !Number.isFinite(v)) continue
      candles.push({ ts: t, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return downsample(candles, 2500)
  }, [series])

  const profitValue = useMemo(() => {
    const equity = (series?.equity as unknown[] | undefined) ?? []
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
  }, [series])

  const baselineOverlays = useMemo(() => {
    const ts = (series?.ts as unknown[] | undefined) ?? []
    if (!baselines || !ts.length) return []

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
      const points = equityCandles.map((c) => ({ ts: c.ts, value: byTs.get(c.ts) ?? null }))
      overlays.push({ name, color, points })
    }

    addOverlay('Buy & hold (start→end)', '#6b7280', (baselines.start_to_end as unknown) ?? null)
    if ((baselines as any).first_entry_to_end) {
      addOverlay('Buy & hold (first entry→end)', '#9ca3af', (baselines as any).first_entry_to_end)
    }

    return overlays
  }, [baselines, equityCandles, series])

  const tradeRows = useMemo(() => {
    return trades.map((t, idx) => {
      const row = (t ?? {}) as Record<string, unknown>
      const side = String(row.side ?? '')
      const isShort = side.toUpperCase() === 'SHORT'
      const entryPrice = Number(row.entry_price ?? NaN)
      const exitPrice = Number(row.exit_price ?? NaN)
      const buyPrice = isShort ? exitPrice : entryPrice
      const sellPrice = isShort ? entryPrice : exitPrice
      return {
        id: idx,
        entry_ts: String(row.entry_ts ?? ''),
        exit_ts: String(row.exit_ts ?? ''),
        side,
        buy_price: Number.isFinite(buyPrice) ? buyPrice : null,
        sell_price: Number.isFinite(sellPrice) ? sellPrice : null,
        qty: row.qty ?? null,
        pnl_pct: row.pnl_pct ?? null,
        reason: String(row.reason ?? ''),
      }
    })
  }, [trades])

  const tradeColumns = useMemo((): GridColDef[] => {
    return [
      {
        field: 'entry_ts',
        headerName: 'Entry',
        width: 230,
        valueFormatter: (value) =>
          formatYmdHmsAmPm((value as { value?: unknown })?.value ?? value, displayTimeZone),
      },
      {
        field: 'exit_ts',
        headerName: 'Exit',
        width: 230,
        valueFormatter: (value) =>
          formatYmdHmsAmPm((value as { value?: unknown })?.value ?? value, displayTimeZone),
      },
      { field: 'side', headerName: 'Side', width: 110 },
      {
        field: 'buy_price',
        headerName: 'Buy',
        width: 120,
        type: 'number',
        valueFormatter: (value) => fmtPrice((value as { value?: unknown })?.value ?? value, 2),
      },
      {
        field: 'sell_price',
        headerName: 'Sell',
        width: 120,
        type: 'number',
        valueFormatter: (value) => fmtPrice((value as { value?: unknown })?.value ?? value, 2),
      },
      { field: 'qty', headerName: 'Qty', width: 90, type: 'number' },
      {
        field: 'pnl_pct',
        headerName: 'P&L %',
        width: 110,
        valueFormatter: (value) => fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      { field: 'reason', headerName: 'Reason', minWidth: 160, flex: 1 },
    ]
  }, [displayTimeZone])

  useEffect(() => {
    setShowTrades(false)
  }, [run.id])

  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const chartsExpanded = !showTrades || tradeRows.length === 0
  const { equityHeight, drawdownHeight } = useMemo(() => {
    if (!chartsExpanded) return { equityHeight: 260, drawdownHeight: 180 }
    const available = Math.max(520, viewportHeight - 420)
    const eq = Math.max(320, Math.round(available * 0.62))
    const dd = Math.max(220, available - eq)
    return { equityHeight: eq, drawdownHeight: dd }
  }, [chartsExpanded, viewportHeight])

  if (run.kind !== 'STRATEGY') {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        Pinned tabs are supported for Strategy runs only.
      </Typography>
    )
  }

  if (!result || run.status !== 'COMPLETED' || !equityCandles.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        No equity curve data available for this run.
      </Typography>
    )
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
        <Typography variant="subtitle2">Equity curve</Typography>
        <Box sx={{ flexGrow: 1 }} />
        {tradeRows.length > 0 ? (
          <Button
            size="small"
            variant={showTrades ? 'contained' : 'outlined'}
            onClick={() => setShowTrades((v) => !v)}
          >
            {showTrades ? 'Hide trades' : 'Show trades'}
          </Button>
        ) : null}
      </Stack>
      {metrics ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
          <Chip size="small" label={`Total: ${Number(metrics.total_return_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`CAGR: ${Number(metrics.cagr_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`Max DD: ${Number(metrics.max_drawdown_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`Turnover: ${Number(metrics.turnover_pct_total ?? 0).toFixed(1)}%`} />
          {metrics.total_turnover != null ? (
            <Chip
              size="small"
              variant="outlined"
              label={`Turnover: ${fmtInr(Number(metrics.total_turnover ?? 0), 0)}`}
            />
          ) : null}
          <Chip size="small" label={`Charges: ${fmtInr(Number(metrics.total_charges ?? 0), 0)}`} />
          {baselines?.start_to_end ? (
            <Chip
              size="small"
              variant="outlined"
              label={`Buy&hold: ${Number((baselines.start_to_end as any)?.total_return_pct ?? 0).toFixed(2)}%`}
            />
          ) : null}
          {baselines && (baselines as any).first_entry_to_end ? (
            <Chip
              size="small"
              variant="outlined"
              label={`Hold from 1st entry: ${Number(((baselines as any).first_entry_to_end as any)?.total_return_pct ?? 0).toFixed(2)}%`}
            />
          ) : null}
          {tradeStats ? (
            <>
              <Chip size="small" label={`Trades: ${Number(tradeStats.count ?? 0)}`} />
              <Chip size="small" label={`Win: ${Number(tradeStats.win_rate_pct ?? 0).toFixed(1)}%`} />
              {typeof profitValue === 'number' ? (
                <Chip size="small" label={`Profit (net): ${fmtInr(profitValue, 0)}`} />
              ) : null}
            </>
          ) : null}
        </Stack>
      ) : null}

      <Box sx={{ mt: 1 }}>
        <PriceChart
          candles={equityCandles}
          chartType="line"
          height={equityHeight}
          overlays={baselineOverlays}
          markers={tradeMarkers}
          showLegend
          baseSeriesName="Strategy equity"
        />
      </Box>

      {drawdownCandles.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Drawdown (%)</Typography>
          <Box sx={{ mt: 1 }}>
            <PriceChart candles={drawdownCandles} chartType="line" height={drawdownHeight} />
          </Box>
        </Box>
      ) : null}

      {showTrades && tradeRows.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle2">Trades</Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                const rows = tradeRows.map((r) => ({
                  entry: formatYmdHmsAmPm(r.entry_ts, displayTimeZone),
                  exit: formatYmdHmsAmPm(r.exit_ts, displayTimeZone),
                  side: r.side,
                  buy_price: r.buy_price,
                  sell_price: r.sell_price,
                  qty: r.qty,
                  pnl_pct: r.pnl_pct,
                  reason: r.reason,
                }))
                downloadCsv(`strategy_trades_run_${run.id}.csv`, rows)
              }}
            >
              Export CSV
            </Button>
          </Stack>
          <Box sx={{ height: 260, mt: 1 }}>
            <DataGrid
              rows={tradeRows}
              columns={tradeColumns}
              density="compact"
              disableRowSelectionOnClick
              pageSizeOptions={[5, 10, 25]}
              initialState={{ pagination: { paginationModel: { pageSize: 5 } } }}
            />
          </Box>
        </Box>
      ) : null}
    </Box>
  )
}

function PortfolioStrategyRunDetailsCard({
  run,
  displayTimeZone,
}: {
  run: BacktestRun
  displayTimeZone: string
}) {
  const [showTrades, setShowTrades] = useState(false)
  const [showPerSymbolStats, setShowPerSymbolStats] = useState(false)
  const [viewportHeight, setViewportHeight] = useState(() =>
    typeof window === 'undefined' ? 900 : window.innerHeight,
  )
  const result = (run.result as Record<string, unknown> | null | undefined) ?? null
  const series = (result?.series as Record<string, unknown> | undefined) ?? null
  const metrics = (result?.metrics as Record<string, unknown> | undefined) ?? null
  const meta = (result?.meta as Record<string, unknown> | undefined) ?? null

  useEffect(() => {
    setShowTrades(false)
    setShowPerSymbolStats(false)
  }, [run.id])

  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const markers = useMemo((): PriceSignalMarker[] => {
    const ms = (result?.markers as unknown[] | undefined) ?? []
    return ms
      .map((m) => {
        const row = (m ?? {}) as Record<string, unknown>
        return {
          ts: String(row.ts ?? ''),
          kind: String(row.kind ?? ''),
          text: String(row.text ?? ''),
        } as PriceSignalMarker
      })
      .filter((m) => m.ts)
  }, [result])

  const markerTs = useMemo(() => {
    const s = new Set<string>()
    for (const m of markers) s.add(m.ts)
    return s
  }, [markers])

  const equityCandles = useMemo((): PriceCandle[] => {
    const ts = (series?.ts as unknown[] | undefined) ?? []
    const equity = (series?.equity as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(ts.length, equity.length); i++) {
      const t = String(ts[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!t || !Number.isFinite(v)) continue
      candles.push({ ts: t, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return downsampleKeep(candles, 2500, (c) => markerTs.has((c as PriceCandle).ts))
  }, [markerTs, series])

  const drawdownCandles = useMemo((): PriceCandle[] => {
    const ts = (series?.ts as unknown[] | undefined) ?? []
    const dd = (series?.drawdown_pct as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(ts.length, dd.length); i++) {
      const t = String(ts[i] ?? '')
      const v = Number(dd[i] ?? NaN)
      if (!t || !Number.isFinite(v)) continue
      candles.push({ ts: t, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return downsample(candles, 2500)
  }, [series])

  const profitValue = useMemo(() => {
    const equity = (series?.equity as unknown[] | undefined) ?? []
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
  }, [series])

  const trades = useMemo(() => {
    const ts = (result?.trades as unknown[] | undefined) ?? []
    return ts.map((t) => (t ?? {}) as Record<string, unknown>)
  }, [result])

  const tradeRows = useMemo(() => {
    return trades.map((t, idx) => ({
      id: idx,
      symbol: String(t.symbol ?? ''),
      entry_ts: String(t.entry_ts ?? ''),
      exit_ts: String(t.exit_ts ?? ''),
      side: String(t.side ?? ''),
      buy_price: (() => {
        const isShort = String(t.side ?? '').toUpperCase() === 'SHORT'
        const n = Number((isShort ? t.exit_price : t.entry_price) ?? NaN)
        return Number.isFinite(n) ? n : null
      })(),
      sell_price: (() => {
        const isShort = String(t.side ?? '').toUpperCase() === 'SHORT'
        const n = Number((isShort ? t.entry_price : t.exit_price) ?? NaN)
        return Number.isFinite(n) ? n : null
      })(),
      qty: t.qty ?? null,
      pnl_pct: t.pnl_pct ?? null,
      reason: String(t.reason ?? ''),
    }))
  }, [trades])

  const tradeColumns = useMemo((): GridColDef[] => {
    return [
      { field: 'symbol', headerName: 'Symbol', width: 160 },
      {
        field: 'entry_ts',
        headerName: 'Entry',
        width: 230,
        valueFormatter: (value) =>
          formatYmdHmsAmPm((value as { value?: unknown })?.value ?? value, displayTimeZone),
      },
      {
        field: 'exit_ts',
        headerName: 'Exit',
        width: 230,
        valueFormatter: (value) =>
          formatYmdHmsAmPm((value as { value?: unknown })?.value ?? value, displayTimeZone),
      },
      { field: 'side', headerName: 'Side', width: 110 },
      {
        field: 'buy_price',
        headerName: 'Buy',
        width: 120,
        type: 'number',
        valueFormatter: (value) => fmtPrice((value as { value?: unknown })?.value ?? value, 2),
      },
      {
        field: 'sell_price',
        headerName: 'Sell',
        width: 120,
        type: 'number',
        valueFormatter: (value) => fmtPrice((value as { value?: unknown })?.value ?? value, 2),
      },
      { field: 'qty', headerName: 'Qty', width: 90, type: 'number' },
      {
        field: 'pnl_pct',
        headerName: 'P&L %',
        width: 110,
        valueFormatter: (value) => fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      { field: 'reason', headerName: 'Reason', minWidth: 160, flex: 1 },
    ]
  }, [displayTimeZone])

  const perSymbolStats = useMemo(() => {
    const rows = (result?.per_symbol_stats as unknown[] | undefined) ?? []
    return rows.map((s) => (s ?? {}) as Record<string, unknown>)
  }, [result])

  const statsRows = useMemo(() => {
    return perSymbolStats.map((s, idx) => ({
      id: idx,
      symbol: String(s.symbol ?? ''),
      trades: s.trades ?? null,
      win_rate_pct: s.win_rate_pct ?? null,
      avg_pnl_pct: s.avg_pnl_pct ?? null,
      realized_pnl: s.realized_pnl ?? null,
    }))
  }, [perSymbolStats])

  const statsColumns = useMemo((): GridColDef[] => {
    return [
      { field: 'symbol', headerName: 'Symbol', width: 160 },
      { field: 'trades', headerName: 'Trades', width: 90, type: 'number' },
      {
        field: 'win_rate_pct',
        headerName: 'Win %',
        width: 110,
        valueFormatter: (value) => fmtPct((value as { value?: unknown })?.value ?? value, 1),
      },
      {
        field: 'avg_pnl_pct',
        headerName: 'Avg P&L %',
        width: 120,
        valueFormatter: (value) => fmtPct((value as { value?: unknown })?.value ?? value, 2),
      },
      {
        field: 'realized_pnl',
        headerName: 'Realized P&L',
        minWidth: 130,
        flex: 1,
        valueFormatter: (value) => fmtInr((value as { value?: unknown })?.value ?? value, 0),
      },
    ]
  }, [])

  if (run.kind !== 'PORTFOLIO_STRATEGY') {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        This view is available for Portfolio strategy runs only.
      </Typography>
    )
  }

  if (!result || run.status !== 'COMPLETED' || !equityCandles.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        No equity curve data available for this run.
      </Typography>
    )
  }

  const chartsExpanded = !showTrades && !showPerSymbolStats
  const { equityHeight, drawdownHeight } = useMemo(() => {
    if (!chartsExpanded) return { equityHeight: 260, drawdownHeight: 180 }
    const available = Math.max(520, viewportHeight - 420)
    const eq = Math.max(320, Math.round(available * 0.62))
    const dd = Math.max(220, available - eq)
    return { equityHeight: eq, drawdownHeight: dd }
  }, [chartsExpanded, viewportHeight])

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
        <Typography variant="subtitle2">Equity curve</Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Button
          size="small"
          variant={showTrades ? 'contained' : 'outlined'}
          onClick={() => setShowTrades((v) => !v)}
        >
          {showTrades ? 'Hide trades' : 'Show trades'}
        </Button>
        <Button
          size="small"
          variant={showPerSymbolStats ? 'contained' : 'outlined'}
          onClick={() => setShowPerSymbolStats((v) => !v)}
        >
          {showPerSymbolStats ? 'Hide per-symbol stats' : 'Show per-symbol stats'}
        </Button>
      </Stack>
      {metrics ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
          <Chip size="small" label={`Total: ${Number(metrics.total_return_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`CAGR: ${Number(metrics.cagr_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`Max DD: ${Number(metrics.max_drawdown_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`Turnover: ${Number(metrics.turnover_pct_total ?? 0).toFixed(1)}%`} />
          {metrics.total_turnover != null ? (
            <Chip
              size="small"
              variant="outlined"
              label={`Turnover: ${fmtInr(Number(metrics.total_turnover ?? 0), 0)}`}
            />
          ) : null}
          <Chip size="small" label={`Charges: ${fmtInr(Number(metrics.total_charges ?? 0), 0)}`} />
          <Chip size="small" label={`Trades: ${Number(metrics.trades ?? 0)}`} />
          <Chip size="small" label={`Win: ${Number(metrics.win_rate_pct ?? 0).toFixed(1)}%`} />
          {typeof profitValue === 'number' ? (
            <Chip size="small" label={`Profit (net): ${fmtInr(profitValue, 0)}`} />
          ) : null}
          {meta ? (
            <>
              <Chip
                size="small"
                variant="outlined"
                label={`Loaded: ${Number(meta.symbols_loaded ?? 0)} / ${Number(meta.symbols_requested ?? 0)}`}
              />
              {Array.isArray(meta.symbols_missing) && (meta.symbols_missing as unknown[]).length ? (
                <Chip
                  size="small"
                  variant="outlined"
                  color="warning"
                  label={`Missing: ${(meta.symbols_missing as unknown[]).length}`}
                />
              ) : null}
            </>
          ) : null}
        </Stack>
      ) : null}

      <Box sx={{ mt: 1 }}>
        <PriceChart
          candles={equityCandles}
          chartType="line"
          height={equityHeight}
          markers={markers}
          showLegend
          baseSeriesName="Portfolio equity"
        />
      </Box>

      {drawdownCandles.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Drawdown (%)</Typography>
          <Box sx={{ mt: 1 }}>
            <PriceChart candles={drawdownCandles} chartType="line" height={drawdownHeight} />
          </Box>
        </Box>
      ) : null}

      {showTrades && tradeRows.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle2">Trades</Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                const rows = tradeRows.map((r) => ({
                  symbol: r.symbol,
                  entry: formatYmdHmsAmPm(r.entry_ts, displayTimeZone),
                  exit: formatYmdHmsAmPm(r.exit_ts, displayTimeZone),
                  side: r.side,
                  buy_price: r.buy_price,
                  sell_price: r.sell_price,
                  qty: r.qty,
                  pnl_pct: r.pnl_pct,
                  reason: r.reason,
                }))
                downloadCsv(`portfolio_strategy_trades_run_${run.id}.csv`, rows)
              }}
            >
              Export CSV
            </Button>
          </Stack>
          <Box sx={{ height: 280, mt: 1 }}>
            <DataGrid
              rows={tradeRows}
              columns={tradeColumns}
              density="compact"
              disableRowSelectionOnClick
              pageSizeOptions={[5, 10, 25]}
              initialState={{ pagination: { paginationModel: { pageSize: 5 } } }}
            />
          </Box>
        </Box>
      ) : null}

      {showPerSymbolStats && statsRows.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle2">Per-symbol stats</Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                const rows = statsRows.map((r) => ({
                  symbol: r.symbol,
                  trades: r.trades,
                  win_rate_pct: r.win_rate_pct,
                  avg_pnl_pct: r.avg_pnl_pct,
                  realized_pnl: r.realized_pnl,
                }))
                downloadCsv(`portfolio_strategy_symbols_run_${run.id}.csv`, rows)
              }}
            >
              Export CSV
            </Button>
          </Stack>
          <Box sx={{ height: 260 }}>
            <DataGrid
              rows={statsRows}
              columns={statsColumns}
              density="compact"
              disableRowSelectionOnClick
              pageSizeOptions={[10, 25, 50, 100]}
              initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            />
          </Box>
        </Box>
      ) : null}
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

function PortfolioRunDetailsCard({
  run,
  runs,
  compareRunId,
  setCompareRunId,
  compareRun,
}: {
  run: BacktestRun
  runs: BacktestRun[]
  compareRunId: number | ''
  setCompareRunId: (id: number | '') => void
  compareRun: BacktestRun | null
}) {
  const [showActions, setShowActions] = useState(false)
  const [viewportHeight, setViewportHeight] = useState(() =>
    typeof window === 'undefined' ? 900 : window.innerHeight,
  )
  const result = (run.result as Record<string, unknown> | null | undefined) ?? null
  const series = (result?.series as Record<string, unknown> | undefined) ?? null
  const metrics = (result?.metrics as Record<string, unknown> | undefined) ?? null
  const meta = (result?.meta as Record<string, unknown> | undefined) ?? null

  const equityCandles = useMemo((): PriceCandle[] => {
    const dates = (series?.dates as unknown[] | undefined) ?? []
    const equity = (series?.equity as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(dates.length, equity.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      candles.push({ ts, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return candles
  }, [series])

  const compareOverlay = useMemo(() => {
    if (!compareRun?.result || compareRun.id === run.id) return []
    const r = compareRun.result as Record<string, unknown>
    const cSeries = r.series as Record<string, unknown> | undefined
    if (!cSeries) return []
    const dates = (cSeries.dates as unknown[] | undefined) ?? []
    const equity = (cSeries.equity as unknown[] | undefined) ?? []
    const byDate = new Map<string, number>()
    for (let i = 0; i < Math.min(dates.length, equity.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(equity[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      byDate.set(ts, v)
    }
    const points = equityCandles.map((c) => ({ ts: c.ts, value: byDate.get(c.ts) ?? null }))
    return [
      {
        name: `Compare: run #${compareRun.id}`,
        color: '#6b7280',
        points,
      },
    ]
  }, [compareRun, equityCandles, run.id])

  const drawdownCandles = useMemo((): PriceCandle[] => {
    const dates = (series?.dates as unknown[] | undefined) ?? []
    const dd = (series?.drawdown_pct as unknown[] | undefined) ?? []
    const candles: PriceCandle[] = []
    for (let i = 0; i < Math.min(dates.length, dd.length); i++) {
      const ts = String(dates[i] ?? '')
      const v = Number(dd[i] ?? NaN)
      if (!ts || !Number.isFinite(v)) continue
      candles.push({ ts, open: v, high: v, low: v, close: v, volume: 0 })
    }
    return candles
  }, [series])

  const actionsRows = useMemo(() => {
    const actions = (result?.actions as unknown[] | undefined) ?? []
    return actions.map((a, idx) => {
      const row = (a ?? {}) as Record<string, unknown>
      const trades = (row.trades as unknown[] | undefined) ?? []
      const skipped = Boolean(row.skipped)
      const charges = trades.reduce<number>((acc, t) => acc + Number((t as any)?.charges ?? 0), 0)
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
  }, [result])

  const actionsColumns = useMemo((): GridColDef[] => {
    const fmtPctLocal = (value: unknown) => (value == null || value === '' ? '' : `${Number(value).toFixed(1)}%`)
    return [
      { field: 'date', headerName: 'Date', width: 120 },
      { field: 'status', headerName: 'Status', width: 110 },
      { field: 'note', headerName: 'Note', minWidth: 160, flex: 1 },
      { field: 'trades', headerName: 'Trades', width: 90 },
      {
        field: 'turnover_pct',
        headerName: 'Turnover %',
        width: 120,
        valueFormatter: (value) => fmtPctLocal((value as { value?: unknown })?.value ?? value),
      },
      {
        field: 'budget_used',
        headerName: 'Budget used',
        width: 140,
        valueFormatter: (value) => fmtInr((value as { value?: unknown })?.value ?? value, 0),
      },
      {
        field: 'charges',
        headerName: 'Charges',
        width: 140,
        valueFormatter: (value) => fmtInr((value as { value?: unknown })?.value ?? value, 0),
      },
    ]
  }, [])

  useEffect(() => {
    setShowActions(false)
  }, [run.id])

  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const chartsExpanded = !showActions || actionsRows.length === 0
  const { equityHeight, drawdownHeight } = useMemo(() => {
    if (!chartsExpanded) return { equityHeight: 260, drawdownHeight: 180 }
    const overhead = runs.length > 1 ? 520 : 470
    const available = Math.max(520, viewportHeight - overhead)
    const eq = Math.max(320, Math.round(available * 0.62))
    const dd = Math.max(220, available - eq)
    return { equityHeight: eq, drawdownHeight: dd }
  }, [actionsRows.length, chartsExpanded, runs.length, viewportHeight])

  if (run.kind !== 'PORTFOLIO') {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        Portfolio details are available for Portfolio runs only.
      </Typography>
    )
  }

  if (!result || run.status !== 'COMPLETED' || !equityCandles.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {run.status === 'FAILED' && run.error_message ? `Error: ${run.error_message}` : 'No equity curve data available for this run.'}
      </Typography>
    )
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
        <Typography variant="subtitle2">Equity curve</Typography>
        <Box sx={{ flexGrow: 1 }} />
        {actionsRows.length > 0 ? (
          <Button
            size="small"
            variant={showActions ? 'contained' : 'outlined'}
            onClick={() => setShowActions((v) => !v)}
          >
            {showActions ? 'Hide actions' : 'Show actions'}
          </Button>
        ) : null}
      </Stack>
      {metrics ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
          <Chip size="small" label={`Total: ${Number(metrics.total_return_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`CAGR: ${Number(metrics.cagr_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`Max DD: ${Number(metrics.max_drawdown_pct ?? 0).toFixed(2)}%`} />
          <Chip size="small" label={`Turnover: ${Number(metrics.turnover_pct_total ?? 0).toFixed(1)}%`} />
          {Number.isFinite(Number(metrics.total_charges)) && (
            <Chip size="small" label={`Charges: ${fmtInr(Number(metrics.total_charges ?? 0), 0)}`} />
          )}
          <Chip size="small" label={`Rebalances: ${Number(metrics.rebalance_count ?? 0)}`} />
          {Number(metrics.rebalance_skipped_count ?? 0) > 0 ? (
            <Tooltip
              title={
                meta?.gate
                  ? `Gate blocked ${Number(metrics.rebalance_skipped_count ?? 0)} rebalance(s).`
                  : `Skipped ${Number(metrics.rebalance_skipped_count ?? 0)} rebalance(s).`
              }
            >
              <Chip size="small" color="warning" label={`Skipped: ${Number(metrics.rebalance_skipped_count ?? 0)}`} />
            </Tooltip>
          ) : null}
        </Stack>
      ) : null}

      <Box sx={{ mt: 1 }}>
        <PriceChart
          candles={equityCandles}
          chartType="line"
          height={equityHeight}
          overlays={compareOverlay}
        />
      </Box>

      {runs.length > 1 ? (
        <Box sx={{ mt: 2 }}>
          <FormControl fullWidth size="small">
            <InputLabel id={`bt-compare-label-${run.id}`}>Compare run</InputLabel>
            <Select
              labelId={`bt-compare-label-${run.id}`}
              label="Compare run"
              value={compareRunId}
              onChange={(e) => setCompareRunId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <MenuItem value="">(none)</MenuItem>
              {runs
                .filter((r) => r.id !== run.id && r.status === 'COMPLETED')
                .map((r) => (
                  <MenuItem key={r.id} value={String(r.id)}>
                    #{r.id} — {String((r.config as any)?.config?.method ?? r.title ?? '')}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
        </Box>
      ) : null}

      {drawdownCandles.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Drawdown (%)</Typography>
          <Box sx={{ mt: 1 }}>
            <PriceChart candles={drawdownCandles} chartType="line" height={drawdownHeight} />
          </Box>
        </Box>
      ) : null}

      {showActions && actionsRows.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Rebalance actions</Typography>
          <Box sx={{ height: 240, mt: 1 }}>
            <DataGrid
              rows={actionsRows}
              columns={actionsColumns}
              density="compact"
              disableRowSelectionOnClick
              hideFooter
            />
          </Box>
        </Box>
      ) : null}
    </Box>
  )
}
