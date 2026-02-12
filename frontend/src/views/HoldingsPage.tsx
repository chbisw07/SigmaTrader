import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import AutorenewIcon from '@mui/icons-material/Autorenew'
import Paper from '@mui/material/Paper'
import Alert from '@mui/material/Alert'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Tooltip from '@mui/material/Tooltip'
import Select from '@mui/material/Select'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import FormControlLabel from '@mui/material/FormControlLabel'
import Checkbox from '@mui/material/Checkbox'
import Switch from '@mui/material/Switch'
import Chip from '@mui/material/Chip'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Divider from '@mui/material/Divider'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
  type GridCellParams,
  type GridColumnVisibilityModel,
  type GridRowSelectionModel,
  type GridRowClassNameParams,
  useGridApiRef,
} from '@mui/x-data-grid'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { Theme } from '@mui/material/styles'

import { UniverseGrid } from '../components/UniverseGrid/UniverseGrid'
import { getPaginatedRowNumber } from '../components/UniverseGrid/getPaginatedRowNumber'
import { useSensitiveVisibility } from '../utils/sensitiveVisibility'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import IconButton from '@mui/material/IconButton'
import {
  clampQtyToMax,
  shouldClampSellToHoldingsQty,
} from '../components/Trade/tradeConstraints'
import { resolvePrimaryPriceForHolding } from '../components/Trade/tradePricing'
import { RebalanceDialog } from '../components/RebalanceDialog'
import { GoalImportDialog } from '../components/GoalImportDialog'

import { createManualOrder, type DistanceMode, type RiskSpec } from '../services/orders'
import { fetchMarketHistory, type CandlePoint } from '../services/marketData'
import { fetchMarketQuotes } from '../services/marketQuotes'
import { fetchDailyPositions, fetchHoldings, type Holding } from '../services/positions'
import { fetchAngeloneStatus } from '../services/angelone'
import { fetchMarginsForBroker } from '../services/brokerRuntime'
import {
  fetchSymbolCategories,
  upsertSymbolCategory,
  type RiskCategory,
  type SymbolRiskCategory,
} from '../services/riskEngine'
import { resolveSymbolRiskCategory } from '../utils/symbolRiskCategories'
import {
  fetchHoldingsCorrelation,
  type HoldingsCorrelationResult,
  computeRiskSizing,
  type RiskSizingResponse,
} from '../services/analytics'
import {
  bulkAddGroupMembers,
  createGroup,
  fetchGroup,
  fetchGroupDataset,
  fetchGroupDatasetValues,
  fetchGroupMemberships,
  fetchPortfolioAllocations,
  listGroupMembers,
  listGroups,
  type Group,
  type GroupDetail,
  type GroupKind,
} from '../services/groups'
import {
  fetchHoldingGoals,
  upsertHoldingGoal,
  applyHoldingGoalReviewAction,
  listHoldingGoalReviews,
  type GoalReviewAction,
  type GoalLabel,
  type GoalTargetType,
  type HoldingGoal,
  type HoldingGoalReview,
} from '../services/holdingsGoals'
import { InstrumentSearch } from '../components/InstrumentSearch'
import type { InstrumentSearchResult } from '../services/instruments'
import { createHoldingsExitSubscription } from '../services/holdingsExit'
import { SensitiveToggle } from '../components/Sensitive/SensitiveToggle'

type HoldingIndicators = {
  rsi14?: number
  sma20?: number
  sma50?: number
  sma200?: number
  ema20?: number
  ema50?: number
  ema200?: number
  macd?: number
  macdSignal?: number
  macdHist?: number
  obv?: number
  pvt?: number
  pvtSlopePct20?: number
  ma50Pct?: number
  ma200Pct?: number
  volatility20dPct?: number
  volatility6mPct?: number
  atr14Pct?: number
  perf1dPct?: number
  perf5dPct?: number
  perf1wPct?: number
  perf1mPct?: number
  perf3mPct?: number
  perf6mPct?: number
  perf1yPct?: number
  volumeVsAvg20d?: number
  sr20High?: number
  sr20Low?: number
  sr50High?: number
  sr50Low?: number
  distToSr20HighPct?: number
  distToSr20LowPct?: number
  maxPnlPct?: number
  drawdownFromPeakPct?: number
  dd6mPct?: number
  week52Low?: number
  week52High?: number
  gapPct?: number
}

type HoldingRow = Holding & {
  history?: CandlePoint[]
  indicators?: HoldingIndicators
  correlationCluster?: string
  correlationWeight?: number
  groupNames?: string[]
  groupsLabel?: string
  target_weight?: number | null
  reference_qty?: number | null
  reference_price?: number | null
}

type HoldingsViewId =
  | 'default'
  | 'goal'
  | 'performance'
  | 'indicators'
  | 'support_resistance'
  | 'risk'
  | `custom:${string}`

type GoalFilter = 'all' | 'overdue' | 'due_soon' | 'near_target' | 'missing'

type PortfolioAllocationMismatch = {
  symbol: string
  allocated: number
  holdingQty: number
  excess: number
  groups: Array<{ group_id: number; group_name: string; allocated: number }>
}

const ANALYTICS_LOOKBACK_DAYS = 730
const BRACKET_BASE_MTP_DEFAULT = 5
const BRACKET_APPRECIATION_THRESHOLD = 3
const BRACKET_MTP_MIN = 3
const BRACKET_MTP_MAX = 20
const HOLDINGS_CUSTOM_VIEWS_STORAGE_KEY = 'st_holdings_custom_views_v1'
const HOLDINGS_SELECTED_VIEW_STORAGE_KEY = 'st_holdings_view_v2'
const GOAL_LABELS: GoalLabel[] = [
  'CORE',
  'TRADE',
  'THEME',
  'HEDGE',
  'INCOME',
  'PARKING',
]
const GOAL_TARGET_TYPES: Array<{ value: GoalTargetType; label: string }> = [
  { value: 'PCT_FROM_AVG_BUY', label: '% from Avg Buy' },
  { value: 'PCT_FROM_LTP', label: '% from LTP' },
  { value: 'ABSOLUTE_PRICE', label: 'Absolute Price' },
]
const GOAL_DEFAULT_REVIEW_DAYS: Record<GoalLabel, number> = {
  CORE: 180,
  TRADE: 30,
  THEME: 90,
  HEDGE: 120,
  INCOME: 180,
  PARKING: 60,
}
const GOAL_DUE_SOON_DAYS = 7
const GOAL_NEAR_TARGET_PCT = 5

export function HoldingsPage() {
  const gridApiRef = useGridApiRef()
  const navigate = useNavigate()
  const location = useLocation()
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [universeId, setUniverseId] = useState<string>('holdings')
  const [angeloneConnected, setAngeloneConnected] = useState(false)
  const [angeloneStatusLoaded, setAngeloneStatusLoaded] = useState(false)
  const [tradeBrokerName, setTradeBrokerName] = useState<'zerodha' | 'angelone'>(
    'zerodha',
  )
  const [symbolCategoryRows, setSymbolCategoryRows] = useState<SymbolRiskCategory[]>([])
  const [symbolCategoryBusyByKey, setSymbolCategoryBusyByKey] = useState<Record<string, boolean>>({})
  const [symbolCategoryError, setSymbolCategoryError] = useState<string | null>(null)
  const [availableGroups, setAvailableGroups] = useState<Group[]>([])
  const [activeGroup, setActiveGroup] = useState<GroupDetail | null>(null)
  const [activeGroupDataset, setActiveGroupDataset] = useState<{
    columns: Array<{ key: string; label: string; type: string }>
    valuesByKey: Map<string, Record<string, unknown>>
  } | null>(null)
  const [rebalanceOpen, setRebalanceOpen] = useState(false)

  const [portfolioAllocationTotalsByKey, setPortfolioAllocationTotalsByKey] = useState<
    Record<string, number>
  >({})
  const [portfolioAllocationMismatches, setPortfolioAllocationMismatches] = useState<
    PortfolioAllocationMismatch[]
  >([])
  const [portfolioMismatchDialogOpen, setPortfolioMismatchDialogOpen] = useState(false)

  const [tradeOpen, setTradeOpen] = useState(false)
  const [tradeHolding, setTradeHolding] = useState<HoldingRow | null>(null)
  const [tradeSide, setTradeSide] = useState<'BUY' | 'SELL'>('BUY')
  const [tradeSymbol, setTradeSymbol] = useState<string>('')
  const [tradePortfolioGroupId, setTradePortfolioGroupId] = useState<number | null>(
    null,
  )
  const [tradePortfolioOptions, setTradePortfolioOptions] = useState<
    Array<{ group_id: number; group_name: string; reference_qty: number }>
  >([])
  const [tradePortfolioLoading, setTradePortfolioLoading] = useState(false)
  const [tradeQty, setTradeQty] = useState<string>('')
  const [tradeAmount, setTradeAmount] = useState<string>('')
  const [tradePctEquity, setTradePctEquity] = useState<string>('')
  const [tradeSizeMode, setTradeSizeMode] = useState<
    'QTY' | 'AMOUNT' | 'PCT_POSITION' | 'PCT_PORTFOLIO' | 'RISK'
  >('QTY')
  const [tradePrice, setTradePrice] = useState<string>('')
  const [tradeProduct, setTradeProduct] = useState<'CNC' | 'MIS'>('CNC')
  const [tradeOrderType, setTradeOrderType] = useState<
    'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  >('MARKET')
  const [tradeTriggerPrice, setTradeTriggerPrice] = useState<string>('')
  const [tradeGtt, setTradeGtt] = useState<boolean>(false)
  const [tradeExecutionMode, setTradeExecutionMode] = useState<'MANUAL' | 'AUTO'>(
    'MANUAL',
  )
  const [tradeExecutionTarget, setTradeExecutionTarget] = useState<'LIVE' | 'PAPER'>(
    'LIVE',
  )

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        setSymbolCategoryError(null)
        const rows = await fetchSymbolCategories('*')
        if (!active) return
        setSymbolCategoryRows(rows)
      } catch (err) {
        if (!active) return
        setSymbolCategoryError(err instanceof Error ? err.message : 'Failed to load symbol categories')
        setSymbolCategoryRows([])
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  const handleSetSymbolCategory = useCallback(
    async (exchangeRaw: string | null | undefined, symbolRaw: string | null | undefined, category: RiskCategory) => {
      const sym = (symbolRaw || '').trim().toUpperCase()
      const exch = (exchangeRaw || 'NSE').trim().toUpperCase() || 'NSE'
      if (!sym) return
      const key = `${exch}:${sym}`
      setSymbolCategoryBusyByKey((prev) => ({ ...prev, [key]: true }))
      try {
        const saved = await upsertSymbolCategory({
          broker_name: '*',
          exchange: '*',
          symbol: sym,
          risk_category: category,
        })
        setSymbolCategoryRows((prev) => {
          const symKey = (saved.symbol || '').trim().toUpperCase()
          const exchKey = (saved.exchange || '').trim().toUpperCase()
          const brokerKey = (saved.broker_name || '').trim().toLowerCase()
          const next = prev.filter(
            (r) =>
              (r.symbol || '').trim().toUpperCase() !== symKey
              || (r.exchange || '').trim().toUpperCase() !== exchKey
              || (r.broker_name || '').trim().toLowerCase() !== brokerKey,
          )
          return [...next, saved]
        })
        setSymbolCategoryError(null)
      } catch (err) {
        setSymbolCategoryError(err instanceof Error ? err.message : 'Failed to save symbol category')
      } finally {
        setSymbolCategoryBusyByKey((prev) => ({ ...prev, [key]: false }))
      }
    },
    [],
  )
  const [tradeBracketEnabled, setTradeBracketEnabled] = useState<boolean>(false)
  const [riskSlEnabled, setRiskSlEnabled] = useState<boolean>(false)
  const [riskSlMode, setRiskSlMode] = useState<DistanceMode>('PCT')
  const [riskSlValue, setRiskSlValue] = useState<string>('2')
  const [riskSlAtrPeriod, setRiskSlAtrPeriod] = useState<string>('14')
  const [riskSlAtrTf, setRiskSlAtrTf] = useState<string>('5m')

  const [riskTrailEnabled, setRiskTrailEnabled] = useState<boolean>(false)
  const [riskTrailMode, setRiskTrailMode] = useState<DistanceMode>('PCT')
  const [riskTrailValue, setRiskTrailValue] = useState<string>('1')
  const [riskTrailAtrPeriod, setRiskTrailAtrPeriod] = useState<string>('14')
  const [riskTrailAtrTf, setRiskTrailAtrTf] = useState<string>('5m')

  const [riskActivationEnabled, setRiskActivationEnabled] = useState<boolean>(false)
  const [riskActivationMode, setRiskActivationMode] = useState<DistanceMode>('PCT')
  const [riskActivationValue, setRiskActivationValue] = useState<string>('3')
  const [riskActivationAtrPeriod, setRiskActivationAtrPeriod] = useState<string>('14')
  const [riskActivationAtrTf, setRiskActivationAtrTf] = useState<string>('5m')
  const [tradeMtpPct, setTradeMtpPct] = useState<string>('')
  const [tradeSubmitting, setTradeSubmitting] = useState(false)
  const [tradeSubmitProgress, setTradeSubmitProgress] = useState<{
    done: number
    total: number
  } | null>(null)
  const [tradeError, setTradeError] = useState<string | null>(null)
  const [tradeRiskBudget, setTradeRiskBudget] = useState<string>('')
  const [tradeRiskBudgetMode, setTradeRiskBudgetMode] = useState<
    'ABSOLUTE' | 'PORTFOLIO_PCT'
  >('ABSOLUTE')
  const [tradeRiskCategoryDraft, setTradeRiskCategoryDraft] = useState<
    RiskCategory | ''
  >('')
  const [tradeStopPrice, setTradeStopPrice] = useState<string>('')
  const [tradeMaxLoss, setTradeMaxLoss] = useState<number | null>(null)
  const [bulkTradeHoldings, setBulkTradeHoldings] = useState<HoldingRow[]>([])
  const [highlightSymbol, setHighlightSymbol] = useState<string | null>(null)
  const highlightTimerRef = useRef<number | null>(null)
  const [rowSelectionModel, setRowSelectionModel] = useState<GridRowSelectionModel>([])
  const [bulkPriceOverrides, setBulkPriceOverrides] = useState<Record<string, string>>(
    {},
  )
  const [bulkAmountOverrides, setBulkAmountOverrides] = useState<
    Record<string, string>
  >({})
  const [bulkQtyOverrides, setBulkQtyOverrides] = useState<Record<string, string>>({})
  const [bulkPriceDialogOpen, setBulkPriceDialogOpen] = useState(false)
  const [bulkAmountDialogOpen, setBulkAmountDialogOpen] = useState(false)
  const [bulkQtyDialogOpen, setBulkQtyDialogOpen] = useState(false)
  const [bulkPctDialogOpen, setBulkPctDialogOpen] = useState(false)
  const [bulkRedistributeRemainder, setBulkRedistributeRemainder] = useState(true)
  const [bulkAmountManual, setBulkAmountManual] = useState(false)
  const [bulkAmountBudget, setBulkAmountBudget] = useState<string>('')
  const [groupCreateOpen, setGroupCreateOpen] = useState(false)
  const [groupSelectionMode, setGroupSelectionMode] = useState<'create' | 'add'>(
    'create',
  )
  const [groupCreateName, setGroupCreateName] = useState('')
  const [groupCreateKind, setGroupCreateKind] = useState<GroupKind>('WATCHLIST')
  const [groupTargetId, setGroupTargetId] = useState<string>('')
  const [groupCreateSubmitting, setGroupCreateSubmitting] = useState(false)
  const [groupCreateError, setGroupCreateError] = useState<string | null>(null)
  const [groupCreateInfo, setGroupCreateInfo] = useState<string | null>(null)

  const [chartPeriodDays, setChartPeriodDays] = useState<number>(30)

  const [viewId, setViewId] = useState<HoldingsViewId>('default')
  const { visible: showMoneyValues, toggle: toggleShowMoneyValues } = useSensitiveVisibility(
    'privacy.show_money',
    false,
  )
  const { visible: showQtyValues, toggle: toggleShowQtyValues } = useSensitiveVisibility(
    'privacy.show_qty',
    false,
  )
  const enrichmentConfig = useMemo(() => {
    const computeIndicators =
      viewId === 'indicators' ||
      viewId === 'support_resistance' ||
      viewId === 'performance' ||
      viewId === 'risk' ||
      viewId.startsWith('custom:')

    return {
      periodDays: computeIndicators ? ANALYTICS_LOOKBACK_DAYS : Math.max(chartPeriodDays, 60),
      computeIndicators,
    }
  }, [chartPeriodDays, viewId])
  const enrichmentRequestedRef = useRef<{ periodDays: number; computeIndicators: boolean }>({
    periodDays: 0,
    computeIndicators: false,
  })
  const [customViews, setCustomViews] = useState<Array<{ id: string; name: string }>>(
    [],
  )
  const [viewsDialogOpen, setViewsDialogOpen] = useState(false)
  const [newViewName, setNewViewName] = useState('')
  const [holdingGoals, setHoldingGoals] = useState<HoldingGoal[]>([])
  const [goalFilter, setGoalFilter] = useState<GoalFilter>('all')
  const [goalEditOpen, setGoalEditOpen] = useState(false)
  const [goalEditRow, setGoalEditRow] = useState<HoldingRow | null>(null)
  const [goalLabel, setGoalLabel] = useState<GoalLabel>('CORE')
  const [goalReviewDate, setGoalReviewDate] = useState<string>('')
  const [goalReviewTouched, setGoalReviewTouched] = useState(false)
  const [goalTargetType, setGoalTargetType] = useState<GoalTargetType | ''>('')
  const [goalTargetValue, setGoalTargetValue] = useState<string>('')
  const [goalNote, setGoalNote] = useState('')
  const [goalSaving, setGoalSaving] = useState(false)
  const [goalSaveError, setGoalSaveError] = useState<string | null>(null)
  // Holdings Exit Automation (MVP): optional subscription derived from goal target.
  const [goalExitSubscribe, setGoalExitSubscribe] = useState(false)
  const [goalExitSizeMode, setGoalExitSizeMode] = useState<'PCT_OF_POSITION' | 'ABS_QTY'>(
    'PCT_OF_POSITION',
  )
  const [goalExitSizeValue, setGoalExitSizeValue] = useState('50')
  const [goalExitError, setGoalExitError] = useState<string | null>(null)
  const [goalReviewActionError, setGoalReviewActionError] = useState<string | null>(
    null,
  )
  const [goalActionAnchorEl, setGoalActionAnchorEl] = useState<HTMLElement | null>(
    null,
  )
  const [goalActionRow, setGoalActionRow] = useState<HoldingRow | null>(null)
  const [goalReviewHistoryOpen, setGoalReviewHistoryOpen] = useState(false)
  const [goalReviewHistoryRow, setGoalReviewHistoryRow] = useState<HoldingRow | null>(
    null,
  )
  const [goalReviewHistory, setGoalReviewHistory] = useState<HoldingGoalReview[]>([])
  const [goalReviewHistoryError, setGoalReviewHistoryError] = useState<string | null>(
    null,
  )
  const [goalLoadError, setGoalLoadError] = useState<string | null>(null)
  const [goalImportOpen, setGoalImportOpen] = useState(false)
  const columnsFieldRef = useRef<string[]>([])
  const [columnVisibilityModel, setColumnVisibilityModel] =
    useState<GridColumnVisibilityModel>({
      maxPnlPct: false,
      drawdownFromPeakPct: false,
    })

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const rawViews = window.localStorage.getItem(HOLDINGS_CUSTOM_VIEWS_STORAGE_KEY)
      if (rawViews) {
        const parsed = JSON.parse(rawViews) as Array<{ id: string; name: string }>
        if (Array.isArray(parsed)) {
          setCustomViews(
            parsed
              .filter((v) => typeof v?.id === 'string' && typeof v?.name === 'string')
              .map((v) => ({ id: v.id, name: v.name })),
          )
        }
      }
    } catch {
      // Ignore storage errors.
    }

    try {
      const raw = window.localStorage.getItem(HOLDINGS_SELECTED_VIEW_STORAGE_KEY)
      let next: HoldingsViewId | null = raw ? (raw as HoldingsViewId) : null
      if (!next) {
        const legacy = window.localStorage.getItem('st_holdings_view_v1')
        if (legacy === 'risk' || legacy === 'default') {
          next = legacy
        }
      }
      if (next) setViewId(next)
    } catch {
      // Ignore storage errors.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false)
  const [refreshDays, setRefreshDays] = useState('0')
  const [refreshHours, setRefreshHours] = useState('0')
  const [refreshMinutes, setRefreshMinutes] = useState('5')
  const [refreshSeconds, setRefreshSeconds] = useState('0')
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [refreshConfigHydrated, setRefreshConfigHydrated] = useState(false)

  const [portfolioValue, setPortfolioValue] = useState<number | null>(null)
  const [availableFunds, setAvailableFunds] = useState<number | null>(null)
  const [availableFundsError, setAvailableFundsError] = useState<string | null>(null)
  const [availableFundsLoading, setAvailableFundsLoading] = useState(false)

  const rebalanceConfig = useMemo(() => {
    if (universeId === 'holdings') {
      return {
        show: true,
        title: 'Rebalance holdings (Zerodha)',
        targetKind: 'HOLDINGS' as const,
        groupId: null as number | null,
        brokerName: 'zerodha' as const,
        brokerLocked: true,
        scheduleSupported: false,
      }
    }
    if (universeId === 'holdings:angelone') {
      return {
        show: true,
        title: 'Rebalance holdings (AngelOne)',
        targetKind: 'HOLDINGS' as const,
        groupId: null as number | null,
        brokerName: 'angelone' as const,
        brokerLocked: true,
        scheduleSupported: false,
      }
    }
    if (universeId.startsWith('group:') && activeGroup) {
      if (activeGroup.kind === 'PORTFOLIO' || activeGroup.kind === 'HOLDINGS_VIEW') {
        return {
          show: true,
          title: `Rebalance: ${activeGroup.name}`,
          targetKind: 'GROUP' as const,
          groupId: activeGroup.id,
          brokerName: tradeBrokerName,
          brokerLocked: false,
          scheduleSupported: activeGroup.kind === 'PORTFOLIO',
        }
      }
    }
    return {
      show: false,
      title: 'Rebalance',
      targetKind: 'GROUP' as const,
      groupId: null as number | null,
      brokerName: tradeBrokerName,
      brokerLocked: false,
      scheduleSupported: false,
    }
  }, [activeGroup, tradeBrokerName, universeId])
  const loadRequestId = useRef(0)
  const refreshRequestId = useRef(0)
  const refreshingRef = useRef(false)
  const holdingsRef = useRef<HoldingRow[]>([])
  const enrichRequestId = useRef(0)
  const enrichMetaBySymbolRef = useRef<Map<string, { periodDays: number; indicators: boolean }>>(
    new Map(),
  )
  const enrichPendingBySymbolRef = useRef<
    Map<
      string,
      { history: CandlePoint[]; indicators?: HoldingIndicators; lastPrice?: number | null }
    >
  >(new Map())
  const enrichFlushTimerRef = useRef<number | null>(null)

  useEffect(() => {
    refreshingRef.current = refreshing
  }, [refreshing])

  useEffect(() => {
    holdingsRef.current = holdings
  }, [holdings])

  const flushHoldingsEnrichment = useCallback(() => {
    if (typeof window !== 'undefined' && enrichFlushTimerRef.current != null) {
      window.clearTimeout(enrichFlushTimerRef.current)
    }
    enrichFlushTimerRef.current = null
    const pending = enrichPendingBySymbolRef.current
    if (pending.size === 0) return
    const patch = new Map(pending)
    pending.clear()
    setHoldings((current) => {
      let changed = false
      const next = current.map((h) => {
        const key = (h.symbol || '').trim().toUpperCase()
        const update = patch.get(key)
        if (!update) return h
        changed = true
        const out: HoldingRow = { ...h, history: update.history }
        if (update.indicators != null) out.indicators = update.indicators
        const lastCandidate = update.lastPrice
        if (
          (out.last_price == null || !Number.isFinite(Number(out.last_price)) || Number(out.last_price) <= 0) &&
          lastCandidate != null &&
          Number.isFinite(Number(lastCandidate)) &&
          Number(lastCandidate) > 0
        ) {
          out.last_price = Number(lastCandidate)
        }
        return out
      })
      return changed ? next : current
    })
  }, [])

  const enrichHoldingsWithHistory = useCallback(
    async (
      rows: HoldingRow[],
      opts?: { periodDays?: number; computeIndicators?: boolean },
    ) => {
      const periodDays = opts?.periodDays ?? ANALYTICS_LOOKBACK_DAYS
      const computeIndicators = opts?.computeIndicators ?? true
      const requestId = (enrichRequestId.current += 1)

      for (const row of rows) {
        if (requestId !== enrichRequestId.current) return
        const symbol = (row.symbol || '').trim()
        if (!symbol) continue
        const symbolKey = symbol.toUpperCase()

        const metaPrev = enrichMetaBySymbolRef.current.get(symbolKey)
        const metaHasHistory = (metaPrev?.periodDays ?? 0) >= periodDays
        const metaHasIndicators = Boolean(metaPrev?.indicators)
        const needsIndicators = computeIndicators && !metaHasIndicators
        if (metaHasHistory && !needsIndicators) continue

        try {
          const history = await fetchMarketHistory({
            symbol: row.symbol,
            exchange: row.exchange ?? 'NSE',
            timeframe: '1d',
            periodDays,
          })
          if (requestId !== enrichRequestId.current) return

          const nextIndicators = computeIndicators
            ? computeHoldingIndicators(
                history,
                row.average_price != null ? Number(row.average_price) : undefined,
              )
            : undefined

          const lastClose =
            history.length > 0 ? Number(history[history.length - 1].close) : null
          enrichPendingBySymbolRef.current.set(symbolKey, {
            history,
            ...(nextIndicators ? { indicators: nextIndicators } : {}),
            lastPrice:
              lastClose != null && Number.isFinite(lastClose) && lastClose > 0
                ? lastClose
                : null,
          })
          enrichMetaBySymbolRef.current.set(symbolKey, {
            periodDays: metaPrev ? Math.max(metaPrev.periodDays, periodDays) : periodDays,
            indicators: Boolean(metaPrev?.indicators) || Boolean(nextIndicators),
          })

          if (typeof window !== 'undefined' && enrichFlushTimerRef.current == null) {
            enrichFlushTimerRef.current = window.setTimeout(() => {
              flushHoldingsEnrichment()
            }, 80)
          }
        } catch {
          // Ignore per-symbol failures so that one bad instrument does not
          // prevent the rest of the grid from being enriched.
        }
      }

      flushHoldingsEnrichment()
    },
    [flushHoldingsEnrichment],
  )

  const [, setCorrSummary] = useState<HoldingsCorrelationResult | null>(null)
  const [, setCorrLoading] = useState(false)
  const [corrError, setCorrError] = useState<string | null>(null)

  const refreshGroupMemberships = async (symbols: string[]) => {
    const normalized = Array.from(
      new Set(
        (symbols || []).map((s) => (s || '').trim().toUpperCase()).filter(Boolean),
      ),
    )
    if (!normalized.length) return
    try {
      const memberships = await fetchGroupMemberships(normalized)
      setHoldings((current) =>
        current.map((row) => {
          const key = (row.symbol || '').trim().toUpperCase()
          const names = memberships[key] ?? []
          return {
            ...row,
            groupNames: names,
            groupsLabel: names.length ? names.join(', ') : '',
          }
        }),
      )
    } catch {
      // Best-effort only: holdings should still render even if groups fail to load.
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const rawUniverse = params.get('universe')?.trim()
    if (rawUniverse && rawUniverse !== universeId) {
      setUniverseId(rawUniverse)
      return
    }
    if (!rawUniverse && universeId !== 'holdings') {
      setUniverseId('holdings')
    }
  }, [location.search, universeId])

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const status = await fetchAngeloneStatus()
        if (!active) return
        setAngeloneConnected(Boolean(status.connected))
      } catch {
        if (!active) return
        setAngeloneConnected(false)
      } finally {
        if (!active) return
        setAngeloneStatusLoaded(true)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!angeloneStatusLoaded) return
    if (universeId !== 'holdings:angelone') return
    if (angeloneConnected) return
    setUniverseId('holdings')
    setError(
      'AngelOne is not connected. Please reconnect from Settings → Broker settings.',
    )
    navigate('/holdings', { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [angeloneConnected, angeloneStatusLoaded, loading, universeId])

  useEffect(() => {
    if (universeId === 'holdings:angelone') {
      setTradeBrokerName('angelone')
      return
    }
    if (universeId === 'holdings') {
      setTradeBrokerName('zerodha')
      return
    }
  }, [universeId])

  useEffect(() => {
    if (tradeBrokerName === 'angelone' && angeloneStatusLoaded && !angeloneConnected) {
      setTradeBrokerName('zerodha')
    }
  }, [angeloneConnected, angeloneStatusLoaded, tradeBrokerName])

  const defaultReviewDateForLabel = useCallback((label: GoalLabel): string => {
    const days = GOAL_DEFAULT_REVIEW_DAYS[label] ?? 90
    const base = new Date()
    base.setHours(0, 0, 0, 0)
    base.setDate(base.getDate() + days)
    return base.toISOString().slice(0, 10)
  }, [])

  const refreshHoldingGoals = useCallback(
    async (brokerName: string) => {
      if (!brokerName) return
      try {
        const goals = await fetchHoldingGoals({ broker_name: brokerName })
        setHoldingGoals(goals)
        setGoalLoadError(null)
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to load goals.'
        setGoalLoadError(msg)
      }
    },
    [setHoldingGoals],
  )

  const goalViewSupported =
    universeId === 'holdings' || universeId === 'holdings:angelone'

  useEffect(() => {
    if (!goalViewSupported && viewId === 'goal') {
      setViewId('default')
    }
  }, [goalViewSupported, viewId])

  useEffect(() => {
    if (viewId !== 'goal' && goalFilter !== 'all') {
      setGoalFilter('all')
    }
  }, [goalFilter, viewId])

  const load = async () => {
    const requestId = ++loadRequestId.current
    try {
      setLoading(true)
      setError(null)
      setCorrError(null)
      // Clear any stale labels immediately; rows will repopulate once the
      // latest request completes.
      setActiveGroup(null)
      setActiveGroupDataset(null)
      const holdingsBroker = universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
      const groupsPromise = listGroups().catch(() => [] as Group[])
      const allocationsPromise = fetchPortfolioAllocations().catch(() => [])
      const goalsPromise = fetchHoldingGoals({ broker_name: holdingsBroker }).catch(
        () => [],
      )
      let rawHoldings: Holding[] = []
      try {
        rawHoldings = await fetchHoldings(holdingsBroker)
      } catch (err) {
        if (holdingsBroker === 'angelone') {
          // When switching brokers, the AngelOne session may have expired.
          // Refresh broker status once and retry holdings to avoid a confusing
          // transient error that often resolves immediately after a manual refresh.
          try {
            const status = await fetchAngeloneStatus()
            if (requestId !== loadRequestId.current) throw err
            setAngeloneConnected(Boolean(status.connected))
            if (status.connected) {
              rawHoldings = await fetchHoldings('angelone')
            } else {
              throw err
            }
          } catch {
            throw err
          }
        } else {
          throw err
        }
      }
      const [groups, allocations, goals] = await Promise.all([
        groupsPromise,
        allocationsPromise,
        goalsPromise,
      ])
      if (requestId !== loadRequestId.current) return
      setAvailableGroups(groups)
      setHoldingGoals(goals)
      setGoalLoadError(null)

      const allocationTotals: Record<string, number> = {}
      const allocationTotalsBySymbol: Record<string, number> = {}
      const allocationGroupsBySymbol: Record<
        string,
        Record<number, { group_id: number; group_name: string; allocated: number }>
      > = {}
      for (const a of allocations) {
        const sym = (a.symbol || '').trim().toUpperCase()
        const exch = (a.exchange || 'NSE').trim().toUpperCase()
        const qty =
          a.reference_qty != null && Number.isFinite(Number(a.reference_qty))
            ? Number(a.reference_qty)
            : 0
        if (!sym || !Number.isFinite(qty) || qty <= 0) continue
        const key = `${exch}:${sym}`
        allocationTotals[key] = (allocationTotals[key] ?? 0) + qty
        allocationTotalsBySymbol[sym] = (allocationTotalsBySymbol[sym] ?? 0) + qty
        const groupId = Number(a.group_id)
        if (Number.isFinite(groupId) && groupId > 0) {
          allocationGroupsBySymbol[sym] = allocationGroupsBySymbol[sym] ?? {}
          const prev = allocationGroupsBySymbol[sym][groupId]
          allocationGroupsBySymbol[sym][groupId] = prev
            ? { ...prev, allocated: prev.allocated + qty }
            : {
                group_id: groupId,
                group_name: String(a.group_name ?? ''),
                allocated: qty,
              }
        }
      }
      setPortfolioAllocationTotalsByKey(allocationTotals)

      const holdingsRows: HoldingRow[] = rawHoldings.map((h) => ({ ...h }))

      // Same-day delivery buys often appear in positions before holdings update.
      // Use an effective holdings qty for mismatch detection: holdings + positive CNC positions.
      let posDeltaBySymbol: Record<string, number> = {}
      try {
        const positions = await fetchDailyPositions({ broker_name: holdingsBroker })
        if (requestId !== loadRequestId.current) return
        posDeltaBySymbol = {}
        for (const p of positions) {
          const sym = (p.symbol || '').trim().toUpperCase()
          const product = (p.product || '').trim().toUpperCase()
          const qty = Number(p.qty ?? 0)
          if (!sym || !Number.isFinite(qty) || qty <= 0) continue
          if (product !== 'CNC' && product !== 'DELIVERY') continue
          posDeltaBySymbol[sym] = (posDeltaBySymbol[sym] ?? 0) + qty
        }
      } catch {
        posDeltaBySymbol = {}
      }

      const holdingQtyBySymbol: Record<string, number> = {}
      for (const h of holdingsRows) {
        const sym = (h.symbol || '').trim().toUpperCase()
        if (!sym) continue
        const qty = Number(h.quantity ?? 0)
        const base = Number.isFinite(qty) ? qty : 0
        holdingQtyBySymbol[sym] = (holdingQtyBySymbol[sym] ?? 0) + base
      }
      for (const [sym, delta] of Object.entries(posDeltaBySymbol)) {
        if (delta > 0) {
          holdingQtyBySymbol[sym] = (holdingQtyBySymbol[sym] ?? 0) + delta
        }
      }

      const mismatches: PortfolioAllocationMismatch[] = []
      for (const [sym, allocated] of Object.entries(allocationTotalsBySymbol)) {
        const holdingQty = holdingQtyBySymbol[sym] ?? 0
        if (allocated > holdingQty + 1e-9) {
          const groups = Object.values(allocationGroupsBySymbol[sym] ?? {}).sort(
            (a, b) => b.allocated - a.allocated,
          )
          mismatches.push({
            symbol: sym,
            allocated,
            holdingQty,
            excess: allocated - holdingQty,
            groups,
          })
        }
      }
      setPortfolioAllocationMismatches(mismatches.sort((a, b) => b.excess - a.excess))

      // Compute a simple live portfolio value estimate so that sizing
      // modes such as % of portfolio and risk-based sizing can use it.
      let total = 0
      for (const h of holdingsRows) {
        const qty =
          h.quantity != null && Number.isFinite(Number(h.quantity))
            ? Number(h.quantity)
            : 0
        const priceCandidate =
          h.last_price != null
            ? Number(h.last_price)
            : h.average_price != null
              ? Number(h.average_price)
              : 0
        if (
          Number.isFinite(qty) &&
          qty > 0 &&
          Number.isFinite(priceCandidate) &&
          priceCandidate > 0
        ) {
          total += qty * priceCandidate
        }
      }
      setPortfolioValue(total > 0 ? total : null)

      let baseRows: HoldingRow[] = holdingsRows
      if (universeId !== 'holdings') {
        if (universeId.startsWith('group:')) {
          const groupIdRaw = universeId.slice('group:'.length)
          const groupId = Number(groupIdRaw)
          if (Number.isFinite(groupId) && groupId > 0) {
            const detail = await fetchGroup(groupId)
            if (requestId !== loadRequestId.current) return
            setActiveGroup(detail)
            const bySymbol = new Map<string, HoldingRow>(
              holdingsRows.map((h) => [h.symbol, h]),
            )
            const seen = new Set<string>()
            baseRows = detail.members
              .filter((m) => {
                if (!m.symbol) return false
                if (seen.has(m.symbol)) return false
                seen.add(m.symbol)
                return true
              })
              .map((m) => {
                const held = bySymbol.get(m.symbol)
                if (held)
                  return {
                    ...held,
                    target_weight: m.target_weight ?? null,
                    reference_qty: m.reference_qty ?? null,
                    reference_price: m.reference_price ?? null,
                  }
                return {
                  symbol: m.symbol,
                  exchange: m.exchange ?? 'NSE',
                  quantity: 0,
                  average_price: 0,
                  last_price: null,
                  pnl: null,
                  last_purchase_date: null,
                  total_pnl_percent: null,
                  today_pnl_percent: null,
                  target_weight: m.target_weight ?? null,
                  reference_qty: m.reference_qty ?? null,
                  reference_price: m.reference_price ?? null,
                } as HoldingRow
              })

            // Attach dynamic import columns (if any) for this group.
            try {
              const dataset = await fetchGroupDataset(groupId)
              if (requestId !== loadRequestId.current) return
              if (dataset?.columns?.length) {
                const values = await fetchGroupDatasetValues(groupId)
                if (requestId !== loadRequestId.current) return
                const valuesByKey = new Map<string, Record<string, unknown>>()
                const valuesBySymbol = new Map<string, Record<string, unknown>>()
                const symbolMultiplicity = new Map<string, number>()
                for (const item of values) {
                  const sym = (item.symbol || '').toUpperCase()
                  const exch = (item.exchange || 'NSE').toUpperCase()
                  const k = `${exch}:${sym}`
                  valuesByKey.set(k, item.values ?? {})

                  if (sym) {
                    const nextCount = (symbolMultiplicity.get(sym) ?? 0) + 1
                    symbolMultiplicity.set(sym, nextCount)
                    if (nextCount === 1) {
                      valuesBySymbol.set(sym, item.values ?? {})
                    } else {
                      // If the dataset contains the same symbol on multiple exchanges,
                      // don't guess which one to use for exchange-mismatched rows.
                      valuesBySymbol.delete(sym)
                    }
                  }
                }
                setActiveGroupDataset({
                  columns: dataset.columns.map((c) => ({
                    key: c.key,
                    label: c.label,
                    type: c.type,
                  })),
                  valuesByKey,
                })
                baseRows = baseRows.map((row) => {
                  const exch = (row.exchange ?? 'NSE').toUpperCase()
                  const sym = (row.symbol || '').toUpperCase()
                  const key = `${exch}:${sym}`
                  const vals =
                    valuesByKey.get(key) ?? (sym ? valuesBySymbol.get(sym) : null) ?? {}
                  const next: HoldingRow & Record<string, unknown> = { ...row }
                  for (const col of dataset.columns) {
                    next[`import_${col.key}`] =
                      (vals as Record<string, unknown>)[col.key] ?? null
                  }
                  return next as HoldingRow
                })
              } else {
                setActiveGroupDataset(null)
              }
            } catch {
              // Best-effort only. If import dataset fails to load, holdings still render.
              setActiveGroupDataset(null)
            }
          }
        }
      } else {
        setActiveGroup(null)
        setActiveGroupDataset(null)
      }

      if (requestId !== loadRequestId.current) return
      setHoldings(baseRows)
      setRowSelectionModel((prev) =>
        prev.filter((id) => baseRows.some((row) => row.symbol === id)),
      )
      if (!isBulkTrade) {
        setBulkPriceOverrides({})
        setBulkAmountOverrides({})
        setBulkQtyOverrides({})
      }
      setError(null)

      // Kick off background enrichment with OHLCV history and indicators.
      enrichmentRequestedRef.current = {
        periodDays: Math.max(enrichmentRequestedRef.current.periodDays, enrichmentConfig.periodDays),
        computeIndicators:
          enrichmentRequestedRef.current.computeIndicators || enrichmentConfig.computeIndicators,
      }
      void enrichHoldingsWithHistory(baseRows, enrichmentRequestedRef.current)

      void refreshGroupMemberships(baseRows.map((row) => row.symbol).filter(Boolean))
    } catch (err) {
      if (requestId !== loadRequestId.current) return
      const msg = err instanceof Error ? err.message : String(err ?? '')
      if (
        universeId === 'holdings:angelone' &&
        msg.toLowerCase().includes('reconnect angelone')
      ) {
        setAngeloneConnected(false)
        setUniverseId('holdings')
        setError(
          'AngelOne session is invalid or expired. Please reconnect from Settings.',
        )
        navigate('/holdings', { replace: true })
        return
      }
      setError(msg || 'Failed to load holdings')
    } finally {
      if (requestId === loadRequestId.current) {
        setLoading(false)
        setHasLoadedOnce(true)
      }
    }
  }

  const refreshHoldingsInPlace = async (mode: 'auto' | 'manual' = 'auto') => {
    if (refreshingRef.current) return
    const requestId = ++refreshRequestId.current
    const holdingsBroker = universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
    if (holdingsBroker === 'angelone' && angeloneStatusLoaded && !angeloneConnected) {
      return
    }
    try {
      setRefreshing(true)
      let rawHoldings: Holding[] = []
      try {
        rawHoldings = await fetchHoldings(holdingsBroker)
      } catch (err) {
        if (holdingsBroker === 'angelone') {
          try {
            const status = await fetchAngeloneStatus()
            if (requestId !== refreshRequestId.current) throw err
            setAngeloneConnected(Boolean(status.connected))
            if (status.connected) {
              rawHoldings = await fetchHoldings('angelone')
            } else {
              throw err
            }
          } catch {
            throw err
          }
        } else {
          throw err
        }
      }

      if (requestId !== refreshRequestId.current) return

      const holdingsRows: HoldingRow[] = rawHoldings.map((h) => ({ ...h }))
      const bySymbol = new Map<string, HoldingRow>(
        holdingsRows.map((h) => [h.symbol, h]),
      )
      if (universeId.startsWith('holdings')) {
        void refreshHoldingGoals(holdingsBroker)
      }

      // Update portfolio value estimate.
      let total = 0
      const rowsForValue = universeId.startsWith('holdings')
        ? holdingsRows
        : holdingsRef.current
      for (const h of rowsForValue) {
        const next = bySymbol.get(h.symbol) ?? h
        const qty =
          next.quantity != null && Number.isFinite(Number(next.quantity))
            ? Number(next.quantity)
            : 0
        const priceCandidate =
          next.last_price != null
            ? Number(next.last_price)
            : next.average_price != null
              ? Number(next.average_price)
              : 0
        if (
          Number.isFinite(qty) &&
          qty > 0 &&
          Number.isFinite(priceCandidate) &&
          priceCandidate > 0
        ) {
          total += qty * priceCandidate
        }
      }
      setPortfolioValue(total > 0 ? total : null)

      if (universeId === 'holdings' || universeId === 'holdings:angelone') {
        // Merge refreshed broker fields into existing rows so that any
        // enriched/derived fields (history, indicators, group labels, etc.)
        // remain populated without flicker.
        setHoldings((prev) => {
          const prevBySymbol = new Map(prev.map((h) => [h.symbol, h]))
          return holdingsRows.map((fresh) => {
            const existing = prevBySymbol.get(fresh.symbol)
            return existing ? { ...existing, ...fresh } : fresh
          })
        })
        setRowSelectionModel((prev) =>
          prev.filter((id) => holdingsRows.some((row) => row.symbol === id)),
        )
        void refreshGroupMemberships(
          holdingsRows.map((row) => row.symbol).filter(Boolean),
        )
        if (mode === 'manual') {
          enrichmentRequestedRef.current = {
            periodDays: Math.max(enrichmentRequestedRef.current.periodDays, enrichmentConfig.periodDays),
            computeIndicators:
              enrichmentRequestedRef.current.computeIndicators ||
              enrichmentConfig.computeIndicators,
          }
          void enrichHoldingsWithHistory(holdingsRows, enrichmentRequestedRef.current)
        }
      } else {
        // Group/universe views: keep the row set stable and only patch values in-place.
        setHoldings((prev) =>
          prev.map((row) => {
            const next = bySymbol.get(row.symbol)
            return next ? { ...row, ...next } : row
          }),
        )
        if (mode === 'manual') {
          enrichmentRequestedRef.current = {
            periodDays: Math.max(enrichmentRequestedRef.current.periodDays, enrichmentConfig.periodDays),
            computeIndicators:
              enrichmentRequestedRef.current.computeIndicators ||
              enrichmentConfig.computeIndicators,
          }
          void enrichHoldingsWithHistory(holdingsRef.current, enrichmentRequestedRef.current)
        }
      }

      setError(null)
    } catch (err) {
      if (requestId !== refreshRequestId.current) return
      const msg = err instanceof Error ? err.message : String(err ?? '')
      setError(msg || 'Failed to refresh holdings')
    } finally {
      if (requestId === refreshRequestId.current) setRefreshing(false)
    }
  }

  useEffect(() => {
    void load()
  }, [universeId])

  useEffect(() => {
    if (!hasLoadedOnce) return
    const prev = enrichmentRequestedRef.current
    const next = {
      periodDays: Math.max(prev.periodDays, enrichmentConfig.periodDays),
      computeIndicators: prev.computeIndicators || enrichmentConfig.computeIndicators,
    }
    if (next.periodDays === prev.periodDays && next.computeIndicators === prev.computeIndicators) {
      return
    }
    enrichmentRequestedRef.current = next
    void enrichHoldingsWithHistory(holdingsRef.current, next)
  }, [
    enrichHoldingsWithHistory,
    enrichmentConfig.computeIndicators,
    enrichmentConfig.periodDays,
    hasLoadedOnce,
  ])

  // Load a lightweight correlation summary so that each holding can be
  // tagged with its high-level correlation cluster and approximate
  // portfolio weight. This runs independently of the main holdings
  // fetch and is best-effort only.
  useEffect(() => {
    let active = true
    const loadCorrelation = async () => {
      try {
        if (loading) return
        setCorrLoading(true)
        setCorrError(null)
        const brokerName = universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
        if (brokerName === 'angelone' && angeloneStatusLoaded && !angeloneConnected) {
          setCorrSummary(null)
          return
        }
        const res = await fetchHoldingsCorrelation({ windowDays: 90, brokerName })
        if (!active) return
        setCorrSummary(res)
        const bySymbol: Record<string, { cluster?: string; weight?: number | null }> =
          {}
        res.symbol_stats.forEach((s) => {
          bySymbol[s.symbol] = {
            cluster: s.cluster ?? undefined,
            weight: s.weight_fraction,
          }
        })
        setHoldings((current) =>
          current.map((h) => {
            const info = bySymbol[h.symbol]
            if (!info) return h
            return {
              ...h,
              correlationCluster: info.cluster,
              correlationWeight: info.weight ?? undefined,
            }
          }),
        )
      } catch (err) {
        if (!active) return
        setCorrError(
          err instanceof Error
            ? err.message
            : 'Failed to load holdings correlation clusters.',
        )
      } finally {
        if (active) setCorrLoading(false)
      }
    }

    void loadCorrelation()

    return () => {
      active = false
    }
  }, [angeloneConnected, angeloneStatusLoaded, universeId])

  useEffect(() => {
    const isGroupUniverse = universeId.startsWith('group:')
    // When switching group universes, `activeGroup` is cleared while the new
    // group loads. Avoid applying defaults during that transient "unknown kind"
    // state because it can lock in the wrong visibility for this universe.
    if (isGroupUniverse && activeGroup?.kind == null) return

    const basketLike =
      activeGroup?.kind === 'MODEL_PORTFOLIO' || activeGroup?.kind === 'PORTFOLIO'
    const desired = basketLike
    const keys = [
      'reference_qty',
      'reference_price',
      'pnlSinceCreation',
      'pnlSinceCreationPct',
    ] as const
    setColumnVisibilityModel((prev) => {
      let changed = false
      const next: GridColumnVisibilityModel = { ...prev }
      for (const key of keys) {
        // Only apply defaults when a field hasn't been explicitly configured
        // for this universe yet.
        if (next[key] !== undefined) continue
        next[key] = desired
        changed = true
      }
      return changed ? next : prev
    })
  }, [activeGroup?.kind, universeId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem('st_holdings_refresh_config_v1')
      if (!raw) return
      const parsed = JSON.parse(raw) as {
        enabled?: boolean
        days?: string
        hours?: string
        minutes?: string
        seconds?: string
      }
      if (parsed.enabled != null) {
        setAutoRefreshEnabled(parsed.enabled)
      }
      if (parsed.days != null) setRefreshDays(parsed.days)
      if (parsed.hours != null) setRefreshHours(parsed.hours)
      if (parsed.minutes != null) setRefreshMinutes(parsed.minutes)
      if (parsed.seconds != null) setRefreshSeconds(parsed.seconds)
    } catch {
      // Ignore malformed config.
    } finally {
      // Avoid writing defaults back to storage during the same initial mount
      // commit (React StrictMode runs mount/unmount cycles in dev).
      setRefreshConfigHydrated(true)
    }
  }, [])

  useEffect(() => {
    if (!refreshConfigHydrated) return
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(
        'st_holdings_refresh_config_v1',
        JSON.stringify({
          enabled: autoRefreshEnabled,
          days: refreshDays,
          hours: refreshHours,
          minutes: refreshMinutes,
          seconds: refreshSeconds,
        }),
      )
    } catch {
      // Ignore persistence errors.
    }
  }, [
    refreshConfigHydrated,
    autoRefreshEnabled,
    refreshDays,
    refreshHours,
    refreshMinutes,
    refreshSeconds,
  ])

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return
    }

    const days = Number(refreshDays) || 0
    const hours = Number(refreshHours) || 0
    const minutes = Number(refreshMinutes) || 0
    const seconds = Number(refreshSeconds) || 0

    const totalSeconds = days * 24 * 60 * 60 + hours * 60 * 60 + minutes * 60 + seconds

    if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
      setRefreshError('Auto-refresh interval must be greater than zero.')
      return
    }

    const minSeconds = 30
    if (totalSeconds < minSeconds) {
      setRefreshError(`Minimum auto-refresh interval is ${minSeconds} seconds.`)
      return
    }

    setRefreshError(null)
    const intervalMs = totalSeconds * 1000

    const id = window.setInterval(() => {
      if (!hasLoadedOnce) return
      void refreshHoldingsInPlace('auto')
    }, intervalMs)

    return () => {
      window.clearInterval(id)
    }
  }, [
    autoRefreshEnabled,
    refreshDays,
    refreshHours,
    refreshMinutes,
    refreshSeconds,
    hasLoadedOnce,
    universeId,
    angeloneConnected,
    angeloneStatusLoaded,
  ])

  const holdingsSummary = useMemo(() => {
    const activeRows = holdings.filter((row) => {
      const symbol = (row.symbol || '').trim()
      if (!symbol) return false
      const qty = row.quantity != null ? Number(row.quantity) : 0
      return Number.isFinite(qty) && qty > 0
    })

    let invested = 0
    let currentValue = 0
    let todayComparablePrevValue = 0
    let todayComparableCurrentValue = 0

    let overallWinner = 0
    let overallLoser = 0
    let overallComparable = 0

    let todayWinner = 0
    let todayLoser = 0
    let todayComparable = 0

    for (const row of activeRows) {
      const qty = row.quantity != null ? Number(row.quantity) : 0
      const avgPrice = row.average_price != null ? Number(row.average_price) : 0
      const lastPrice = row.last_price != null ? Number(row.last_price) : 0

      const investedValue =
        Number.isFinite(qty) && qty > 0 && Number.isFinite(avgPrice) && avgPrice > 0
          ? qty * avgPrice
          : 0
      const current =
        Number.isFinite(qty) && qty > 0 && Number.isFinite(lastPrice) && lastPrice > 0
          ? qty * lastPrice
          : investedValue

      invested += investedValue
      currentValue += current

      const totalPnlPct =
        row.total_pnl_percent != null ? Number(row.total_pnl_percent) : null
      if (totalPnlPct != null && Number.isFinite(totalPnlPct)) {
        overallComparable += 1
        if (totalPnlPct > 0) overallWinner += 1
        else if (totalPnlPct < 0) overallLoser += 1
      }

      const todayPnlPct =
        row.today_pnl_percent != null ? Number(row.today_pnl_percent) : null
      if (todayPnlPct != null && Number.isFinite(todayPnlPct)) {
        todayComparable += 1
        if (todayPnlPct > 0) todayWinner += 1
        else if (todayPnlPct < 0) todayLoser += 1

        if (Number.isFinite(current) && current > 0) {
          // Prefer computing the portfolio-level "today" return using value
          // deltas (prev-close value vs current value), rather than a weighted
          // average of per-holding % returns (which can skew when weights shift).
          const denom = 1 + todayPnlPct / 100
          if (Number.isFinite(denom) && denom > 0) {
            const prevValue = current / denom
            if (Number.isFinite(prevValue) && prevValue > 0) {
              todayComparablePrevValue += prevValue
              todayComparableCurrentValue += current
            }
          }
        }
      }
    }

    const totalPnlPct =
      invested > 0 ? ((currentValue - invested) / invested) * 100 : null
    const todayPnlPct =
      todayComparablePrevValue > 0
        ? ((todayComparableCurrentValue - todayComparablePrevValue) /
            todayComparablePrevValue) *
          100
        : null

    const overallWinRate =
      overallComparable > 0 ? (overallWinner / overallComparable) * 100 : null
    const todayWinRate =
      todayComparable > 0 ? (todayWinner / todayComparable) * 100 : null

    return {
      count: activeRows.length,
      invested,
      currentValue,
      totalPnlPct,
      todayPnlPct,
      overallWinner,
      overallLoser,
      overallComparable,
      todayWinner,
      todayLoser,
      todayComparable,
      overallWinRate,
      todayWinRate,
    }
  }, [holdings])

  const formatInrCompact = useCallback((value: number | null) => {
    if (!showMoneyValues) return '₹••••'
    if (value == null || !Number.isFinite(value)) return '—'
    const abs = Math.abs(value)
    if (abs >= 1e7) return `₹${(value / 1e7).toFixed(2)}Cr`
    if (abs >= 1e5) return `₹${(value / 1e5).toFixed(2)}L`
    if (abs >= 1e3) return `₹${(value / 1e3).toFixed(1)}K`
    return value.toLocaleString('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    })
  }, [showMoneyValues])

  const formatPct = useCallback((value: number | null, digits = 2) => {
    if (value == null || !Number.isFinite(value)) return '—'
    return `${value.toFixed(digits)}%`
  }, [])

  useEffect(() => {
    let active = true
    const loadFunds = async () => {
      const holdingsBroker = universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
      if (!universeId.startsWith('holdings')) {
        setAvailableFunds(null)
        setAvailableFundsError(null)
        setAvailableFundsLoading(false)
        return
      }
      if (holdingsBroker !== 'zerodha') {
        setAvailableFunds(null)
        setAvailableFundsError(null)
        setAvailableFundsLoading(false)
        return
      }

      try {
        setAvailableFundsLoading(true)
        setAvailableFundsError(null)
        const margins = await fetchMarginsForBroker('zerodha')
        if (!active) return
        setAvailableFunds(
          margins.available != null && Number.isFinite(Number(margins.available))
            ? Number(margins.available)
            : null,
        )
      } catch (err) {
        if (!active) return
        setAvailableFunds(null)
        setAvailableFundsError(
          err instanceof Error ? err.message : 'Failed to load available funds.',
        )
      } finally {
        if (active) setAvailableFundsLoading(false)
      }
    }

    void loadFunds()
    return () => {
      active = false
    }
  }, [universeId])

  const totalActiveAlerts = holdings.reduce((acc, h) => {
    const found = h as HoldingRow & { _activeAlertCount?: number }
    return acc + (found._activeAlertCount ?? 0)
  }, 0)

  const isBulkTrade = bulkTradeHoldings.length > 0

  const tradeSymbolCategoryKey = useMemo(() => {
    if (!tradeHolding || isBulkTrade) return null
    const sym = (tradeHolding.symbol || '').trim().toUpperCase()
    const exch = (tradeHolding.exchange || 'NSE').trim().toUpperCase() || 'NSE'
    if (!sym) return null
    return `${exch}:${sym}`
  }, [tradeHolding, isBulkTrade])

  const tradeSymbolCategoryResolved = useMemo(() => {
    if (!tradeHolding || isBulkTrade) return null
    const sym = (tradeHolding.symbol || '').trim().toUpperCase()
    const exch = (tradeHolding.exchange || 'NSE').trim().toUpperCase() || 'NSE'
    if (!sym) return null
    return resolveSymbolRiskCategory(symbolCategoryRows, {
      broker_name: tradeBrokerName,
      exchange: exch,
      symbol: sym,
    })
  }, [symbolCategoryRows, tradeHolding, tradeBrokerName, isBulkTrade])

  const tradeSymbolCategoryBusy =
    tradeSymbolCategoryKey != null
      ? Boolean(symbolCategoryBusyByKey[tradeSymbolCategoryKey])
      : false

  const clampSellToHoldingsQty = shouldClampSellToHoldingsQty({
    side: tradeSide,
    product: tradeProduct,
  })
  const clampSellToHoldingsQtyEffective =
    clampSellToHoldingsQty && universeId.startsWith('holdings')

  useEffect(() => {
    if (!isBulkTrade) return
    if (tradeSizeMode !== 'PCT_PORTFOLIO') return
    setTradeSizeMode('QTY')
  }, [isBulkTrade, tradeSizeMode])

  const getDisplayPrice = useCallback((holding: HoldingRow): number | null => {
    if (holding.last_price != null && Number.isFinite(Number(holding.last_price))) {
      const v = Number(holding.last_price)
      return v > 0 ? v : null
    }
    if (
      holding.average_price != null &&
      Number.isFinite(Number(holding.average_price))
    ) {
      const v = Number(holding.average_price)
      return v > 0 ? v : null
    }
    return null
  }, [])

  const normalizeSymbolExchange = useCallback((
    symbol: string,
    exchange?: string | null,
  ): { symbol: string; exchange: string } => {
    const rawSymbol = (symbol || '').trim().toUpperCase()
    let rawExchange = (exchange || '').trim().toUpperCase()
    if (rawSymbol.includes(':')) {
      const [prefix, rest] = rawSymbol.split(':', 2)
      if (prefix && rest && (prefix === 'NSE' || prefix === 'BSE')) {
        rawExchange = prefix
        return { symbol: rest.trim().toUpperCase(), exchange: rawExchange || 'NSE' }
      }
    }
    if (rawExchange.startsWith('NSE')) {
      rawExchange = 'NSE'
    } else if (rawExchange.startsWith('BSE')) {
      rawExchange = 'BSE'
    }
    return { symbol: rawSymbol, exchange: rawExchange || 'NSE' }
  }, [])

  const goalMaps = useMemo(() => {
    const map = new Map<string, HoldingGoal>()
    const symbolCounts = new Map<string, number>()
    const symbolMap = new Map<string, HoldingGoal>()
    for (const goal of holdingGoals) {
      const { symbol: sym, exchange: exch } = normalizeSymbolExchange(
        goal.symbol,
        goal.exchange,
      )
      const broker = (goal.broker_name || 'zerodha').toLowerCase()
      if (!sym) continue
      map.set(`${broker}:${exch}:${sym}`, goal)
      const symbolKey = `${broker}:${sym}`
      symbolCounts.set(symbolKey, (symbolCounts.get(symbolKey) ?? 0) + 1)
      if (!symbolMap.has(symbolKey)) {
        symbolMap.set(symbolKey, goal)
      }
    }
    for (const [symbolKey, count] of symbolCounts.entries()) {
      if (count > 1) {
        symbolMap.delete(symbolKey)
      }
    }
    return { byKey: map, bySymbol: symbolMap }
  }, [holdingGoals, normalizeSymbolExchange])

  const getGoalForRow = useCallback(
    (row: HoldingRow, brokerName: string): HoldingGoal | null => {
      const { symbol, exchange } = normalizeSymbolExchange(row.symbol, row.exchange)
      if (!symbol) return null
      const broker = brokerName.toLowerCase()
      return (
        goalMaps.byKey.get(`${broker}:${exchange}:${symbol}`) ??
        goalMaps.bySymbol.get(`${broker}:${symbol}`) ??
        null
      )
    },
    [goalMaps, normalizeSymbolExchange],
  )

  const getGoalDaysRemaining = useCallback((goal: HoldingGoal | null): number | null => {
    if (!goal?.review_date) return null
    const review = new Date(goal.review_date)
    if (Number.isNaN(review.getTime())) return null
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    review.setHours(0, 0, 0, 0)
    const diffMs = review.getTime() - today.getTime()
    return Math.round(diffMs / (1000 * 60 * 60 * 24))
  }, [])

  const getGoalTarget = useCallback((
    row: HoldingRow,
    goal: HoldingGoal | null,
  ): { targetPrice: number | null; awayPct: number | null; label: string } => {
    if (!goal?.target_type || goal.target_value == null) {
      return { targetPrice: null, awayPct: null, label: '—' }
    }
    const ltp = getDisplayPrice(row)
    const avg = row.average_price != null ? Number(row.average_price) : null
    const targetValue = Number(goal.target_value)
    let targetPrice: number | null = null
    let label = '—'
    if (goal.target_type === 'ABSOLUTE_PRICE') {
      targetPrice = Number.isFinite(targetValue) ? targetValue : null
      label = targetPrice != null ? `₹${targetPrice.toFixed(2)}` : '—'
    } else if (goal.target_type === 'PCT_FROM_AVG_BUY') {
      if (avg != null && Number.isFinite(avg) && avg > 0) {
        targetPrice = avg * (1 + targetValue / 100)
      }
      const pctLabel = Number.isFinite(targetValue) ? `${targetValue.toFixed(2)}%` : '—'
      label =
        targetPrice != null ? `${pctLabel} (₹${targetPrice.toFixed(2)})` : pctLabel
    } else if (goal.target_type === 'PCT_FROM_LTP') {
      if (ltp != null && Number.isFinite(ltp) && ltp > 0) {
        targetPrice = ltp * (1 + targetValue / 100)
      }
      const pctLabel = Number.isFinite(targetValue) ? `${targetValue.toFixed(2)}%` : '—'
      label =
        targetPrice != null ? `${pctLabel} (₹${targetPrice.toFixed(2)})` : pctLabel
    }

    let awayPct: number | null = null
    if (ltp != null && targetPrice != null && targetPrice > 0) {
      awayPct = ((ltp - targetPrice) / targetPrice) * 100
    }
    return { targetPrice, awayPct, label }
  }, [getDisplayPrice])

  const getGoalStatus = (
    goal: HoldingGoal | null,
    daysRemaining: number | null,
  ): { label: string; color: 'default' | 'success' | 'warning' | 'error' } => {
    if (!goal || daysRemaining == null) {
      return { label: 'No review date', color: 'default' }
    }
    if (daysRemaining < 0) {
      return { label: 'Review overdue', color: 'error' }
    }
    if (daysRemaining <= GOAL_DUE_SOON_DAYS) {
      return { label: 'Review due', color: 'warning' }
    }
    return { label: 'On track', color: 'success' }
  }

  const goalTargetPreview = useMemo(() => {
    if (!goalEditRow || goalTargetType === '' || goalTargetValue.trim() === '') {
      return null
    }
    const value = Number(goalTargetValue)
    if (!Number.isFinite(value)) return null
    const previewGoal: HoldingGoal = {
      id: -1,
      user_id: -1,
      broker_name: 'preview',
      symbol: goalEditRow.symbol,
      exchange: goalEditRow.exchange ?? 'NSE',
      label: goalLabel,
      review_date: goalReviewDate || defaultReviewDateForLabel(goalLabel),
      target_type: goalTargetType,
      target_value: value,
      note: goalNote,
      created_at: '',
      updated_at: '',
    }
    return getGoalTarget(goalEditRow, previewGoal)
  }, [
    defaultReviewDateForLabel,
    getGoalTarget,
    goalEditRow,
    goalLabel,
    goalNote,
    goalReviewDate,
    goalTargetType,
    goalTargetValue,
  ])

  const goalBrokerName =
    universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'

  const goalActionMenuOpen = Boolean(goalActionAnchorEl)

  const filteredRows: HoldingRow[] = useMemo(() => {
    if (viewId !== 'goal' || !goalViewSupported) {
      return holdings
    }
    return holdings.filter((row) => {
      const goal = getGoalForRow(row, goalBrokerName)
      const days = getGoalDaysRemaining(goal)
      const { awayPct } = getGoalTarget(row, goal)
      switch (goalFilter) {
        case 'missing':
          return !goal
        case 'overdue':
          return goal != null && days != null && days < 0
        case 'due_soon':
          return (
            goal != null &&
            days != null &&
            days >= 0 &&
            days <= GOAL_DUE_SOON_DAYS
          )
        case 'near_target':
          return (
            goal != null &&
            awayPct != null &&
            days != null &&
            days >= 0 &&
            Math.abs(awayPct) <= GOAL_NEAR_TARGET_PCT
          )
        default:
          return true
      }
    })
  }, [
    getGoalForRow,
    getGoalTarget,
    goalBrokerName,
    goalFilter,
    goalViewSupported,
    holdings,
    viewId,
  ])

  const missingGoalRows = useMemo(() => {
    if (!goalViewSupported) return []
    return holdings.filter(
      (row) => getGoalForRow(row, goalBrokerName) == null,
    )
  }, [getGoalForRow, goalBrokerName, goalViewSupported, holdings])

  const missingGoalCount = missingGoalRows.length

  const goalReminderSummary = useMemo(() => {
    if (!goalViewSupported) {
      return { overdue: 0, dueSoon: 0, nearTarget: 0, missing: 0 }
    }
    let overdue = 0
    let dueSoon = 0
    let nearTarget = 0
    for (const row of holdings) {
      const goal = getGoalForRow(row, goalBrokerName)
      if (!goal) continue
      const days = getGoalDaysRemaining(goal)
      if (days == null) continue
      if (days < 0) {
        overdue += 1
        continue
      }
      if (days <= GOAL_DUE_SOON_DAYS) {
        dueSoon += 1
      }
      const { awayPct } = getGoalTarget(row, goal)
      if (awayPct != null && Math.abs(awayPct) <= GOAL_NEAR_TARGET_PCT) {
        nearTarget += 1
      }
    }
    return {
      overdue,
      dueSoon,
      nearTarget,
      missing: missingGoalCount,
    }
  }, [
    getGoalDaysRemaining,
    getGoalForRow,
    getGoalTarget,
    goalBrokerName,
    goalViewSupported,
    holdings,
    missingGoalCount,
  ])

  const holdingsSymbolsForImport = useMemo(() => {
    return holdings
      .map((row) => {
        const { symbol, exchange } = normalizeSymbolExchange(
          row.symbol,
          row.exchange,
        )
        if (!symbol) return null
        return `${exchange}:${symbol}`
      })
      .filter((item): item is string => Boolean(item))
  }, [holdings, normalizeSymbolExchange])

  const getPerHoldingPriceForSizing = (holding: HoldingRow): number | null => {
    const override = bulkPriceOverrides[holding.symbol]
    if (isBulkTrade && override != null && override.trim() !== '') {
      const v = Number(override)
      if (Number.isFinite(v) && v > 0) return v
    }
    return getDisplayPrice(holding)
  }

  const computeUsedTotalFromAmountOverrides = (
    overrides: Record<string, string>,
  ): number => {
    let total = 0
    for (const h of bulkTradeHoldings) {
      const raw = overrides[h.symbol]
      const amount = raw != null && String(raw).trim() !== '' ? Number(raw) : 0
      if (Number.isFinite(amount) && amount > 0) {
        total += amount
      }
    }
    return total
  }

  const computeAutoBulkAmountOverrides = (
    totalBudget: number,
  ): { overrides: Record<string, string>; usedTotal: number } => {
    const count = bulkTradeHoldings.length
    if (!Number.isFinite(totalBudget) || totalBudget <= 0 || count === 0) {
      return { overrides: {}, usedTotal: 0 }
    }

    const baseShare = totalBudget / count
    const prices: Record<string, number> = {}
    const firstPass: Record<string, number> = {}
    const eligible: HoldingRow[] = []
    let usedTotal = 0

    for (const h of bulkTradeHoldings) {
      const price = getPerHoldingPriceForSizing(h)
      prices[h.symbol] = price ?? 0
      if (!price || !Number.isFinite(price) || price <= 0) {
        firstPass[h.symbol] = 0
        continue
      }
      let qty = Math.floor(baseShare / price)
      if (clampSellToHoldingsQtyEffective && h.quantity != null) {
        const maxQty = Math.floor(Number(h.quantity))
        if (Number.isFinite(maxQty) && maxQty >= 0 && qty > maxQty) {
          qty = maxQty
        }
      }
      if (qty <= 0) {
        firstPass[h.symbol] = 0
        continue
      }
      const amt = qty * price
      firstPass[h.symbol] = amt
      usedTotal += amt
      eligible.push(h)
    }

    const leftover = totalBudget - usedTotal
    const finalAmounts: Record<string, number> = { ...firstPass }
    if (bulkRedistributeRemainder && leftover > 0 && eligible.length > 0) {
      const extraShare = leftover / eligible.length
      for (const h of eligible) {
        const price = prices[h.symbol]
        if (!price || !Number.isFinite(price) || price <= 0) continue
        let extraQty = Math.floor(extraShare / price)
        if (clampSellToHoldingsQtyEffective && h.quantity != null) {
          const maxQty = Math.floor(Number(h.quantity))
          if (Number.isFinite(maxQty) && maxQty >= 0) {
            const already = finalAmounts[h.symbol] ?? 0
            const alreadyQty = Math.floor(already / price)
            const remaining = maxQty - alreadyQty
            extraQty = remaining > 0 ? Math.min(extraQty, remaining) : 0
          }
        }
        if (extraQty <= 0) continue
        finalAmounts[h.symbol] += extraQty * price
      }
    }

    const overrides: Record<string, string> = {}
    usedTotal = 0
    for (const h of bulkTradeHoldings) {
      const amt = finalAmounts[h.symbol] ?? 0
      const normalized = Number.isFinite(amt) && amt > 0 ? amt : 0
      overrides[h.symbol] = normalized.toFixed(2)
      usedTotal += normalized
    }

    return { overrides, usedTotal }
  }

  useEffect(() => {
    if (!isBulkTrade) return
    if (tradeSizeMode !== 'AMOUNT') return
    if (bulkAmountManual) return
    const budgetRaw = Number(bulkAmountBudget)
    if (!Number.isFinite(budgetRaw) || budgetRaw <= 0) return
    const { overrides, usedTotal } = computeAutoBulkAmountOverrides(budgetRaw)
    setBulkAmountOverrides(overrides)
    setTradeAmount(
      usedTotal > 0 && Number.isFinite(usedTotal) ? usedTotal.toFixed(2) : '',
    )
  }, [bulkRedistributeRemainder, tradeSide])

  const formatPriceForHolding = (holding: HoldingRow): string => {
    const override = bulkPriceOverrides[holding.symbol]
    if (isBulkTrade && override != null && override.trim() !== '') {
      return override.trim()
    }
    const base = getDisplayPrice(holding)
    if (base == null || !Number.isFinite(base) || base <= 0) return '-'
    return base.toFixed(2)
  }

  const bulkPriceSummary = isBulkTrade
    ? bulkTradeHoldings.map((h) => formatPriceForHolding(h)).join(', ')
    : ''

  const openAlertDialogForHolding = useCallback((holding: HoldingRow) => {
    const symbol = (holding.symbol || '').trim()
    if (!symbol) return
    const exchange =
      (holding.exchange ?? 'NSE').toString().trim().toUpperCase() || 'NSE'
    const params = new URLSearchParams({
      create_v3: '1',
      target_kind: 'SYMBOL',
      target_ref: symbol.toUpperCase(),
      exchange,
    })
    navigate(`/alerts?${params.toString()}`)
  }, [navigate])

  const openGoalEditor = useCallback(
    (holding: HoldingRow) => {
      const brokerName =
        universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
      const goal = getGoalForRow(holding, brokerName)
      const nextLabel = goal?.label ?? 'CORE'
      setGoalEditRow(holding)
      setGoalLabel(nextLabel)
      setGoalReviewTouched(Boolean(goal?.review_date))
      setGoalReviewDate(
        goal?.review_date ?? defaultReviewDateForLabel(nextLabel),
      )
      setGoalTargetType(goal?.target_type ?? '')
      setGoalTargetValue(
        goal?.target_value != null ? String(goal.target_value) : '',
      )
      setGoalNote(goal?.note ?? '')
      setGoalSaveError(null)
      setGoalExitSubscribe(false)
      setGoalExitSizeMode('PCT_OF_POSITION')
      setGoalExitSizeValue('50')
      setGoalExitError(null)
      setGoalEditOpen(true)
    },
    [defaultReviewDateForLabel, getGoalForRow, universeId],
  )

  const applyGoalReviewAction = useCallback(
    async (holding: HoldingRow, action: GoalReviewAction, days?: number) => {
      const brokerName =
        universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
      const goal = getGoalForRow(holding, brokerName)
      if (!goal?.review_date) {
        openGoalEditor(holding)
        return
      }
      try {
        const { goal: updated } = await applyHoldingGoalReviewAction({
          symbol: holding.symbol,
          exchange: holding.exchange ?? 'NSE',
          broker_name: brokerName,
          action,
          days: days ?? null,
        })
        setHoldingGoals((prev) => {
          const next = prev.filter((g) => g.id !== updated.id)
          return [...next, updated]
        })
        setGoalReviewActionError(null)
      } catch (err) {
        setGoalReviewActionError(
          err instanceof Error ? err.message : 'Failed to update review status.',
        )
      }
    },
    [getGoalForRow, openGoalEditor, universeId],
  )

  const openGoalActionMenu = useCallback(
    (event: MouseEvent<HTMLElement>, holding: HoldingRow) => {
      setGoalActionAnchorEl(event.currentTarget)
      setGoalActionRow(holding)
    },
    [],
  )

  const closeGoalActionMenu = useCallback(() => {
    setGoalActionAnchorEl(null)
    setGoalActionRow(null)
  }, [])

  const openGoalReviewHistory = useCallback(
    async (holding: HoldingRow) => {
      const brokerName =
        universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
      setGoalReviewHistoryError(null)
      setGoalReviewHistory([])
      setGoalReviewHistoryRow(holding)
      setGoalReviewHistoryOpen(true)
      try {
        const history = await listHoldingGoalReviews({
          symbol: holding.symbol,
          exchange: holding.exchange ?? 'NSE',
          broker_name: brokerName,
        })
        setGoalReviewHistory(history)
      } catch (err) {
        setGoalReviewHistoryError(
          err instanceof Error ? err.message : 'Failed to load review history.',
        )
      }
    },
    [universeId],
  )

  const handleGoalMenuAction = useCallback(
    (action: GoalReviewAction, days?: number) => {
      if (!goalActionRow) return
      void applyGoalReviewAction(goalActionRow, action, days)
      closeGoalActionMenu()
    },
    [applyGoalReviewAction, closeGoalActionMenu, goalActionRow],
  )

  const handleGoalMenuHistory = useCallback(() => {
    if (!goalActionRow) return
    void openGoalReviewHistory(goalActionRow)
    closeGoalActionMenu()
  }, [closeGoalActionMenu, goalActionRow, openGoalReviewHistory])

  const saveGoal = useCallback(async () => {
    if (!goalEditRow) return
    const brokerName =
      universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'
    const reviewDate =
      goalReviewDate.trim() !== ''
        ? goalReviewDate.trim()
        : defaultReviewDateForLabel(goalLabel)
    const targetType = goalTargetType ? goalTargetType : null
    const targetValueRaw = goalTargetValue.trim()
    const targetValue =
      targetType && targetValueRaw !== '' ? Number(targetValueRaw) : null

    if (targetType && (targetValue == null || !Number.isFinite(targetValue))) {
      setGoalSaveError('Target value is required for the selected target type.')
      return
    }
    if (!targetType && targetValueRaw !== '') {
      setGoalSaveError('Select a target type to use a target value.')
      return
    }

    setGoalSaving(true)
    setGoalSaveError(null)
    try {
      const payload = {
        symbol: goalEditRow.symbol,
        exchange: goalEditRow.exchange ?? 'NSE',
        broker_name: brokerName,
        label: goalLabel,
        review_date: reviewDate,
        target_type: targetType,
        target_value: targetValue,
        note: goalNote.trim() || null,
      }
      const updated = await upsertHoldingGoal(payload)
      setHoldingGoals((prev) => {
        const next = prev.filter((g) => g.id !== updated.id)
        return [...next, updated]
      })

      // Best-effort: create a holdings-exit subscription derived from the goal
      // target (MVP supports only ABSOLUTE_PRICE and PCT_FROM_AVG_BUY).
      if (goalExitSubscribe) {
        setGoalExitError(null)
        const targetType2 = goalTargetType ? goalTargetType : null
        if (!targetType2) {
          throw new Error('Holdings exit subscription requires a goal target type.')
        }
        if (targetType2 === 'PCT_FROM_LTP') {
          throw new Error('Holdings exit does not support % from LTP (MVP).')
        }
        const tv2 = targetValue
        if (tv2 == null || !Number.isFinite(tv2) || tv2 <= 0) {
          throw new Error('Holdings exit subscription requires a positive target value.')
        }
        const sizeV = Number(goalExitSizeValue.trim())
        if (!Number.isFinite(sizeV) || sizeV <= 0) {
          throw new Error('Sell size must be a positive number.')
        }
        const trigger_kind =
          targetType2 === 'ABSOLUTE_PRICE'
            ? 'TARGET_ABS_PRICE'
            : 'TARGET_PCT_FROM_AVG_BUY'
        await createHoldingsExitSubscription({
          broker_name: brokerName,
          symbol: goalEditRow.symbol,
          exchange: goalEditRow.exchange ?? 'NSE',
          product: 'CNC',
          trigger_kind,
          trigger_value: Number(tv2),
          price_source: 'LTP',
          size_mode: goalExitSizeMode,
          size_value: sizeV,
          min_qty: 1,
          order_type: 'MARKET',
          dispatch_mode: 'MANUAL',
          execution_target: 'LIVE',
          cooldown_seconds: 300,
        })
      }

      setGoalEditOpen(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to save goal.'
      if (goalExitSubscribe) {
        // Keep the dialog open so the user sees the subscription error.
        setGoalExitError(msg)
      } else {
        setGoalSaveError(msg)
      }
    } finally {
      setGoalSaving(false)
    }
  }, [
    defaultReviewDateForLabel,
    goalEditRow,
    goalLabel,
    goalNote,
    goalReviewDate,
    goalTargetType,
    goalTargetValue,
    goalExitSubscribe,
    goalExitSizeMode,
    goalExitSizeValue,
    universeId,
  ])

  function getSizingPrice(holding: HoldingRow | null): number | null {
    if (isBulkTrade && holding) {
      return getPerHoldingPriceForSizing(holding)
    }
    const fromField = tradePrice.trim() !== '' ? Number(tradePrice.trim()) : null
    if (fromField != null && Number.isFinite(fromField) && fromField > 0) {
      return fromField
    }
    if (!holding) return null
    const base =
      holding.last_price != null
        ? Number(holding.last_price)
        : holding.average_price != null
          ? Number(holding.average_price)
          : null
    return base != null && Number.isFinite(base) && base > 0 ? base : null
  }

  const getPositionValue = (
    holding: HoldingRow | null,
    price: number | null,
  ): number | null => {
    if (!holding || price == null || !Number.isFinite(price) || price <= 0) {
      return null
    }
    const qty = holding.quantity != null ? Number(holding.quantity) : 0
    if (!Number.isFinite(qty) || qty <= 0) return null
    return qty * price
  }

  const bulkSupportsPctPosition =
    !isBulkTrade ||
    bulkTradeHoldings.every((h) => {
      const price = getSizingPrice(h)
      const positionValue = getPositionValue(h, price)
      return (
        positionValue != null && Number.isFinite(positionValue) && positionValue > 0
      )
    })

  useEffect(() => {
    if (!isBulkTrade) return
    if (tradeSizeMode !== 'PCT_POSITION') return
    if (bulkSupportsPctPosition) return
    setTradeSizeMode('QTY')
  }, [isBulkTrade, tradeSizeMode, bulkSupportsPctPosition])

  const getDefaultBulkQtyForHolding = (holding: HoldingRow): number => {
    let qty = Math.floor(Number(tradeQty))
    if (!Number.isFinite(qty) || qty <= 0) qty = 1
    if (!clampSellToHoldingsQtyEffective || holding.quantity == null) return qty
    const maxQty = Math.floor(Number(holding.quantity))
    if (!Number.isFinite(maxQty) || maxQty <= 0) return 0
    return clampQtyToMax(qty, maxQty)
  }

  const computeQtyForHolding = (holding: HoldingRow): number | null => {
    const clampSellQty = (qty: number): number => {
      if (!clampSellToHoldingsQtyEffective || holding.quantity == null) return qty
      const maxQty = Math.floor(Number(holding.quantity))
      if (!Number.isFinite(maxQty) || maxQty <= 0) return 0
      return clampQtyToMax(qty, maxQty)
    }

    // Quantity-based sizing does not require a price to be available.
    // (Price is only needed for derived fields like notional / % of position.)
    if (tradeSizeMode === 'QTY' || tradeSizeMode === 'RISK') {
      const rawQty = (() => {
        if (!isBulkTrade) return Math.floor(Number(tradeQty))

        const override = bulkQtyOverrides[holding.symbol]
        if (override != null && String(override).trim() !== '') {
          return Math.floor(Number(override))
        }
        return getDefaultBulkQtyForHolding(holding)
      })()
      if (!Number.isFinite(rawQty) || rawQty <= 0) return null
      const qty = clampSellQty(rawQty)
      return qty > 0 ? qty : null
    }

    const price = getSizingPrice(holding)
    const positionValue = getPositionValue(holding, price)

    if (price == null || !Number.isFinite(price) || price <= 0) {
      return null
    }

    if (tradeSizeMode === 'AMOUNT') {
      if (isBulkTrade && bulkAmountOverrides[holding.symbol] == null) {
        return null
      }
      const rawAmountStr = isBulkTrade
        ? (bulkAmountOverrides[holding.symbol] ?? tradeAmount)
        : tradeAmount
      const rawAmount = Number(rawAmountStr)
      if (!Number.isFinite(rawAmount) || rawAmount <= 0) return null
      let qty = Math.floor(rawAmount / price)
      qty = clampSellQty(qty)
      return Number.isFinite(qty) && qty > 0 ? qty : null
    }

    if (tradeSizeMode === 'PCT_POSITION') {
      const rawPct = Number(tradePctEquity)
      if (
        !Number.isFinite(rawPct) ||
        rawPct <= 0 ||
        positionValue == null ||
        positionValue <= 0
      ) {
        return null
      }
      const amountTarget = (rawPct / 100) * positionValue
      let qty = Math.floor(amountTarget / price)
      qty = clampSellQty(qty)
      return Number.isFinite(qty) && qty > 0 ? qty : null
    }

    if (tradeSizeMode === 'PCT_PORTFOLIO') {
      const rawPct = Number(tradePctEquity)
      const total = portfolioValue
      if (!Number.isFinite(rawPct) || rawPct <= 0 || total == null || total <= 0) {
        return null
      }
      const targetNotional = (rawPct / 100) * total
      let qty = Math.floor(targetNotional / price)
      qty = clampSellQty(qty)
      return Number.isFinite(qty) && qty > 0 ? qty : null
    }

    return null
  }

  const recalcFromQty = (qtyStr: string) => {
    const holding = tradeHolding
    const price = getSizingPrice(holding)
    const positionValue = getPositionValue(holding, price)

    const rawQty = Math.floor(Number(qtyStr))
    if (
      !Number.isFinite(rawQty) ||
      rawQty <= 0 ||
      price == null ||
      !Number.isFinite(price) ||
      price <= 0
    ) {
      setTradeAmount('')
      setTradePctEquity('')
      return
    }

    let qty = rawQty
    if (clampSellToHoldingsQtyEffective && holding?.quantity != null) {
      const maxQty = Math.floor(Number(holding.quantity))
      if (Number.isFinite(maxQty) && maxQty > 0 && qty > maxQty) {
        qty = clampQtyToMax(qty, maxQty)
      }
    }

    setTradeQty(String(qty))

    const notional = qty * price
    setTradeAmount(notional.toFixed(2))
    if (positionValue != null && positionValue > 0) {
      const pct = (notional / positionValue) * 100
      setTradePctEquity(pct.toFixed(2))
    } else {
      setTradePctEquity('')
    }
  }

  const recalcFromAmount = (amountStr: string, side: 'BUY' | 'SELL') => {
    const holding = tradeHolding
    const price = getSizingPrice(holding)
    const positionValue = getPositionValue(holding, price)

    const rawAmount = Number(amountStr)
    if (
      !Number.isFinite(rawAmount) ||
      rawAmount <= 0 ||
      price == null ||
      !Number.isFinite(price) ||
      price <= 0
    ) {
      setTradeQty('')
      setTradePctEquity('')
      if (amountStr === '') {
        setTradeAmount('')
      }
      return
    }

    let qty = Math.floor(rawAmount / price)
    if (side === 'SELL' && tradeProduct === 'CNC' && holding?.quantity != null) {
      const maxQty = Math.floor(Number(holding.quantity))
      if (Number.isFinite(maxQty) && maxQty > 0 && qty > maxQty) {
        qty = clampQtyToMax(qty, maxQty)
      }
    }

    if (!Number.isFinite(qty) || qty <= 0) {
      setTradeQty('')
      setTradeAmount(amountStr)
      setTradePctEquity('')
      return
    }

    setTradeQty(String(qty))

    const normalisedAmount = qty * price
    setTradeAmount(normalisedAmount.toFixed(2))
    if (positionValue != null && positionValue > 0) {
      const pct = (normalisedAmount / positionValue) * 100
      setTradePctEquity(pct.toFixed(2))
    } else {
      setTradePctEquity('')
    }
  }

  const recalcFromPctEquity = (pctStr: string, side: 'BUY' | 'SELL') => {
    const holding = tradeHolding
    const price = getSizingPrice(holding)
    const positionValue = getPositionValue(holding, price)

    const rawPct = Number(pctStr)
    if (
      !Number.isFinite(rawPct) ||
      rawPct <= 0 ||
      price == null ||
      !Number.isFinite(price) ||
      price <= 0 ||
      positionValue == null ||
      positionValue <= 0
    ) {
      setTradeQty('')
      setTradeAmount('')
      return
    }

    const amountTarget = (rawPct / 100) * positionValue
    let qty = Math.floor(amountTarget / price)
    if (side === 'SELL' && tradeProduct === 'CNC' && holding?.quantity != null) {
      const maxQty = Math.floor(Number(holding.quantity))
      if (Number.isFinite(maxQty) && maxQty > 0 && qty > maxQty) {
        qty = clampQtyToMax(qty, maxQty)
      }
    }

    if (!Number.isFinite(qty) || qty <= 0) {
      setTradeQty('')
      setTradeAmount('')
      return
    }

    setTradeQty(String(qty))
    const normalisedAmount = qty * price
    setTradeAmount(normalisedAmount.toFixed(2))
  }

  const recalcFromPctPortfolio = (pctStr: string) => {
    const holding = tradeHolding
    const price = getSizingPrice(holding)
    const total = portfolioValue

    const rawPct = Number(pctStr)
    if (
      !Number.isFinite(rawPct) ||
      rawPct <= 0 ||
      price == null ||
      !Number.isFinite(price) ||
      price <= 0 ||
      total == null ||
      total <= 0
    ) {
      setTradeQty('')
      setTradeAmount('')
      return
    }

    const targetNotional = (rawPct / 100) * total
    let qty = Math.floor(targetNotional / price)

    if (clampSellToHoldingsQtyEffective && holding?.quantity != null) {
      const maxQty = Math.floor(Number(holding.quantity))
      if (Number.isFinite(maxQty) && maxQty > 0 && qty > maxQty) {
        qty = maxQty
      }
    }

    if (!Number.isFinite(qty) || qty <= 0) {
      setTradeQty('')
      setTradeAmount('')
      return
    }

    setTradeQty(String(qty))
    const notional = qty * price
    setTradeAmount(notional.toFixed(2))
  }

  const openBulkTradeDialog = (selected: HoldingRow[], side: 'BUY' | 'SELL') => {
    const hasHoldingsQty = selected.some(
      (h) => h.quantity != null && Number(h.quantity) > 0,
    )
    const initialProduct: 'CNC' | 'MIS' =
      side === 'SELL' && !hasHoldingsQty ? 'MIS' : 'CNC'

    setTradeHolding(selected[0] ?? null)
    setTradeSide(side)
    setTradeSymbol('')
    setTradeQty('1')
    setTradePrice('')
    setTradeTriggerPrice('')
    setTradeSizeMode('QTY')
    setTradeAmount('')
    setTradePctEquity('')
    setTradeProduct(initialProduct)
    setTradeOrderType('MARKET')
    setTradeBracketEnabled(false)
    setRiskSlEnabled(false)
    setRiskSlMode('PCT')
    setRiskSlValue('2')
    setRiskSlAtrPeriod('14')
    setRiskSlAtrTf('5m')
    setRiskTrailEnabled(false)
    setRiskTrailMode('PCT')
    setRiskTrailValue('1')
    setRiskTrailAtrPeriod('14')
    setRiskTrailAtrTf('5m')
    setRiskActivationEnabled(false)
    setRiskActivationMode('PCT')
    setRiskActivationValue('3')
    setRiskActivationAtrPeriod('14')
    setRiskActivationAtrTf('5m')
    setTradeMtpPct('')
    setTradeGtt(false)
    setTradeExecutionMode('MANUAL')
    setTradeExecutionTarget('LIVE')
    if (!universeId.startsWith('group:')) {
      setTradeBrokerName(universeId === 'holdings:angelone' ? 'angelone' : 'zerodha')
    }
    setTradePortfolioGroupId(activeGroup?.kind === 'PORTFOLIO' ? activeGroup.id : null)
    setTradePortfolioOptions([])
    setTradePortfolioLoading(false)
    setTradeError(null)
    setTradeOpen(true)
  }

  const openTradeDialog = useCallback((holding: HoldingRow, side: 'BUY' | 'SELL') => {
    setTradeHolding(holding)
    setTradeSide(side)
    setTradeSymbol(holding.symbol)
    const brokerForCategory = !universeId.startsWith('group:')
      ? universeId === 'holdings:angelone'
        ? 'angelone'
        : 'zerodha'
      : tradeBrokerName
    const resolvedCategory = resolveSymbolRiskCategory(symbolCategoryRows, {
      broker_name: brokerForCategory,
      exchange: (holding.exchange || 'NSE').trim().toUpperCase() || 'NSE',
      symbol: (holding.symbol || '').trim().toUpperCase(),
    })
    setTradeRiskCategoryDraft(resolvedCategory ?? '')
    const initialProduct: 'CNC' | 'MIS' =
      side === 'SELL' && !(holding.quantity != null && holding.quantity > 0)
        ? 'MIS'
        : 'CNC'
    let defaultQty = 1
    if (side === 'SELL' && initialProduct === 'CNC' && holding.quantity != null) {
      const maxQty = Math.floor(Number(holding.quantity))
      if (Number.isFinite(maxQty) && maxQty > 0 && defaultQty > maxQty) {
        defaultQty = maxQty
      }
    }
    setTradeQty(defaultQty > 0 ? String(defaultQty) : '')
    setTradePrice(
      holding.last_price != null ? String(holding.last_price.toFixed(2)) : '',
    )
    setTradeTriggerPrice('')
    setTradeSizeMode('QTY')
    // Seed derived fields based on a single-share (or capped) quantity.
    if (defaultQty > 0) {
      const qty = defaultQty
      const priceCandidate =
        holding.last_price != null && Number.isFinite(Number(holding.last_price)) && Number(holding.last_price) > 0
          ? Number(holding.last_price)
          : holding.average_price != null && Number.isFinite(Number(holding.average_price)) && Number(holding.average_price) > 0
            ? Number(holding.average_price)
            : null
      if (priceCandidate != null) {
        const notional = qty * priceCandidate
        setTradeAmount(notional.toFixed(2))
        const holdingQty = holding.quantity != null ? Number(holding.quantity) : 0
        const positionValue =
          Number.isFinite(holdingQty) && holdingQty > 0 ? holdingQty * priceCandidate : null
        if (positionValue != null && positionValue > 0) {
          const pct = (notional / positionValue) * 100
          setTradePctEquity(Number.isFinite(pct) ? pct.toFixed(2) : '')
        } else {
          setTradePctEquity('')
        }
      } else {
        setTradeAmount('')
        setTradePctEquity('')
      }
    } else {
      setTradeAmount('')
      setTradePctEquity('')
    }
    setTradeProduct(initialProduct)
    setTradeOrderType('MARKET')
    setTradeTriggerPrice('')
    setTradeBracketEnabled(false)
    setRiskSlEnabled(false)
    setRiskSlMode('PCT')
    setRiskSlValue('2')
    setRiskSlAtrPeriod('14')
    setRiskSlAtrTf('5m')
    setRiskTrailEnabled(false)
    setRiskTrailMode('PCT')
    setRiskTrailValue('1')
    setRiskTrailAtrPeriod('14')
    setRiskTrailAtrTf('5m')
    setRiskActivationEnabled(false)
    setRiskActivationMode('PCT')
    setRiskActivationValue('3')
    setRiskActivationAtrPeriod('14')
    setRiskActivationAtrTf('5m')
    setTradeMtpPct('')
    setTradeGtt(false)
    setTradeExecutionMode('MANUAL')
    setTradeExecutionTarget('LIVE')
    if (!universeId.startsWith('group:')) {
      setTradeBrokerName(universeId === 'holdings:angelone' ? 'angelone' : 'zerodha')
    }
    const defaultPortfolioId = activeGroup?.kind === 'PORTFOLIO' ? activeGroup.id : null
    setTradePortfolioGroupId(defaultPortfolioId)
    setTradePortfolioOptions([])
    setTradePortfolioLoading(true)
    void (async () => {
      try {
        const allocs = await fetchPortfolioAllocations({
          symbol: (holding.symbol || '').trim().toUpperCase(),
          exchange: (holding.exchange || 'NSE').trim().toUpperCase(),
        })
        const rows = allocs
          .map((a) => ({
            group_id: a.group_id,
            group_name: a.group_name,
            reference_qty:
              a.reference_qty != null && Number.isFinite(Number(a.reference_qty))
                ? Math.trunc(Number(a.reference_qty))
                : 0,
          }))
          .sort((a, b) => a.group_name.localeCompare(b.group_name))
        setTradePortfolioOptions(rows)
      } catch {
        setTradePortfolioOptions([])
      } finally {
        setTradePortfolioLoading(false)
      }
    })()
    setTradeError(null)
    setTradeOpen(true)
  }, [activeGroup?.id, activeGroup?.kind, symbolCategoryRows, tradeBrokerName, universeId])

  const openQuickTradeDialog = (inst: InstrumentSearchResult) => {
    // If the symbol already exists in the current holdings grid, reuse the
    // normal trade dialog (better defaults + consistent validations).
    const symU = (inst.symbol || '').trim().toUpperCase()
    const exchU = (inst.exchange || 'NSE').trim().toUpperCase() || 'NSE'
    if (symU) {
      const existing = holdings.find((h) => {
        const hs = (h.symbol || '').trim().toUpperCase()
        const he = (h.exchange || 'NSE').trim().toUpperCase() || 'NSE'
        return hs === symU && he === exchU
      })
      if (existing) {
        openTradeDialog(existing, 'BUY')
        return
      }
    }

    // Create a minimal "holding" stub so the existing trade flow works.
    const stub: HoldingRow = {
      symbol: inst.symbol,
      exchange: inst.exchange,
      quantity: 0,
      average_price: 0,
      last_price: null,
      pnl: null,
      last_purchase_date: null,
      total_pnl_percent: null,
      today_pnl_percent: null,
      broker_name: tradeBrokerName,
    }

    setBulkTradeHoldings([])
    setTradeHolding(stub)
    setTradeSide('BUY')
    setTradeSymbol(`${inst.exchange}:${inst.symbol}`)
    const resolvedCategory = resolveSymbolRiskCategory(symbolCategoryRows, {
      broker_name: tradeBrokerName,
      exchange: (inst.exchange || 'NSE').trim().toUpperCase() || 'NSE',
      symbol: (inst.symbol || '').trim().toUpperCase(),
    })
    setTradeRiskCategoryDraft(resolvedCategory ?? '')
    setTradeQty('1')
    setTradePrice('')
    setTradeTriggerPrice('')
    setTradeSizeMode('QTY')
    setTradeAmount('')
    setTradePctEquity('')
    setTradeProduct('CNC')
    setTradeOrderType('MARKET')
    setTradeBracketEnabled(false)
    setRiskSlEnabled(false)
    setRiskSlMode('PCT')
    setRiskSlValue('2')
    setRiskSlAtrPeriod('14')
    setRiskSlAtrTf('5m')
    setRiskTrailEnabled(false)
    setRiskTrailMode('PCT')
    setRiskTrailValue('1')
    setRiskTrailAtrPeriod('14')
    setRiskTrailAtrTf('5m')
    setRiskActivationEnabled(false)
    setRiskActivationMode('PCT')
    setRiskActivationValue('3')
    setRiskActivationAtrPeriod('14')
    setRiskActivationAtrTf('5m')
    setTradeMtpPct('')
    setTradeGtt(false)
    setTradeExecutionMode('MANUAL')
    setTradeExecutionTarget('LIVE')

    if (!universeId.startsWith('group:')) {
      setTradeBrokerName(universeId === 'holdings:angelone' ? 'angelone' : 'zerodha')
    }
    setTradePortfolioGroupId(activeGroup?.kind === 'PORTFOLIO' ? activeGroup.id : null)
    setTradePortfolioOptions([])
    setTradePortfolioLoading(false)
    setTradeError(null)
    setTradeOpen(true)
  }

  const handleQuickTradeSelect = (inst: InstrumentSearchResult) => {
    const sym = (inst.symbol || '').toUpperCase()
    if (sym) {
      const idx = filteredRows.findIndex((r) => String(r.symbol || '').toUpperCase() === sym)
      if (idx >= 0) {
        try {
          gridApiRef.current.scrollToIndexes({ rowIndex: idx })
        } catch {
          // ignore
        }
        setHighlightSymbol(sym)
        if (highlightTimerRef.current != null) window.clearTimeout(highlightTimerRef.current)
        highlightTimerRef.current = window.setTimeout(() => setHighlightSymbol(null), 2000)
      }
    }
    openQuickTradeDialog(inst)
  }

  const closeTradeDialog = () => {
    if (tradeSubmitting) return
    setBulkTradeHoldings([])
    setBulkPriceOverrides({})
    setBulkAmountOverrides({})
    setBulkQtyOverrides({})
    setBulkAmountManual(false)
    setBulkAmountBudget('')
    setTradePortfolioGroupId(null)
    setTradePortfolioOptions([])
    setTradePortfolioLoading(false)
    setTradeOpen(false)
  }

  const createGroupFromSelection = async () => {
    if (groupCreateSubmitting) return
    const name = groupCreateName.trim()
    if (!name) {
      setGroupCreateError('Group name is required.')
      return
    }
    const selected = holdings.filter((h) => rowSelectionModel.includes(h.symbol))
    if (!selected.length) {
      setGroupCreateError('Select at least one row to create a group.')
      return
    }

    setGroupCreateSubmitting(true)
    setGroupCreateError(null)
    setGroupCreateInfo(null)
    try {
      const group = await createGroup({
        name,
        kind: groupCreateKind,
        description: `Created from Holdings (${selected.length} symbols).`,
      })
      await bulkAddGroupMembers(
        group.id,
        selected.map((h) => ({
          symbol: h.symbol,
          exchange: h.exchange ?? 'NSE',
          ...(groupCreateKind === 'MODEL_PORTFOLIO' || groupCreateKind === 'PORTFOLIO'
            ? {
                reference_qty: 1,
                reference_price: getDisplayPrice(h),
              }
            : {}),
        })),
      )
      setGroupCreateOpen(false)
      setGroupCreateName('')
      setGroupCreateKind('WATCHLIST')
      setGroupTargetId('')
      void refreshGroupMemberships(selected.map((h) => h.symbol))
      navigate(`/groups?${new URLSearchParams({ group: group.name }).toString()}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create group.'
      setGroupCreateError(message)
    } finally {
      setGroupCreateSubmitting(false)
    }
  }

  const addSelectionToExistingGroup = async () => {
    if (groupCreateSubmitting) return
    const targetId = Number(groupTargetId)
    if (!Number.isFinite(targetId) || targetId <= 0) {
      setGroupCreateError('Select a target group.')
      return
    }

    const target = availableGroups.find((g) => g.id === targetId)
    if (!target) {
      setGroupCreateError('Selected group not found. Refresh and try again.')
      return
    }

    const selected = holdings.filter((h) => rowSelectionModel.includes(h.symbol))
    if (!selected.length) {
      setGroupCreateError('Select at least one row to add to a group.')
      return
    }

    setGroupCreateSubmitting(true)
    setGroupCreateError(null)
    setGroupCreateInfo(null)
    try {
      const existing = await listGroupMembers(targetId)
      const existingSet = new Set(
        existing.map((m) => `${m.symbol}::${m.exchange ?? ''}`),
      )

      const payloadAll = selected.map((h) => ({
        symbol: h.symbol,
        exchange: h.exchange ?? 'NSE',
        ...(target.kind === 'MODEL_PORTFOLIO' || target.kind === 'PORTFOLIO'
          ? {
              reference_qty:
                h.quantity != null &&
                Number.isFinite(Number(h.quantity)) &&
                Number(h.quantity) > 0
                  ? Math.floor(Number(h.quantity))
                  : 1,
              reference_price:
                h.average_price != null &&
                Number.isFinite(Number(h.average_price)) &&
                Number(h.average_price) > 0
                  ? Number(h.average_price)
                  : getDisplayPrice(h),
            }
          : {}),
      }))

      const payload = payloadAll.filter(
        (m) => !existingSet.has(`${m.symbol}::${m.exchange ?? ''}`),
      )
      const skipped = payloadAll.length - payload.length

      if (payload.length) {
        await bulkAddGroupMembers(targetId, payload)
      }

      setGroupCreateInfo(
        payload.length
          ? `Added ${payload.length} symbol(s) to "${target.name}".${skipped ? ` Skipped ${skipped} already present.` : ''}`
          : `All selected symbols are already present in "${target.name}".`,
      )
      void refreshGroupMemberships(selected.map((h) => h.symbol))
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add to group.'
      setGroupCreateError(message)
    } finally {
      setGroupCreateSubmitting(false)
    }
  }

  const handleSubmitTrade = async () => {
    const primaryHolding =
      tradeHolding ?? holdings.find((h) => h.symbol === tradeSymbol) ?? null
    const targets = isBulkTrade
      ? bulkTradeHoldings
      : primaryHolding
        ? [primaryHolding]
        : []
    if (!targets.length) {
      setTradeError('No holdings selected for trade.')
      return
    }

    // Unified risk is always active; do not block trades on missing symbol category.
    const priceNumRaw =
      tradeOrderType === 'MARKET' ||
      tradeOrderType === 'SL-M' ||
      tradePrice.trim() === ''
        ? null
        : Number(tradePrice)
    const priceNum =
      priceNumRaw != null && Number.isFinite(priceNumRaw) && priceNumRaw > 0
        ? priceNumRaw
        : null
    if (priceNum != null && (!Number.isFinite(priceNum) || priceNum < 0)) {
      setTradeError('Price must be a non-negative number.')
      return
    }

    // Validate trigger/stop-loss configuration.
    let triggerPriceNum: number | null = null
    if (tradeOrderType === 'SL' || tradeOrderType === 'SL-M') {
      const raw = Number(tradeTriggerPrice)
      if (!Number.isFinite(raw) || raw <= 0) {
        setTradeError('Trigger price must be a positive number for SL / SL-M orders.')
        return
      }
      triggerPriceNum = raw
      if (tradeOrderType === 'SL') {
        if (priceNum == null || !Number.isFinite(priceNum) || priceNum <= 0) {
          setTradeError('Limit price must be a positive number for SL orders.')
          return
        }
      }
    }

    if (tradeGtt && tradeOrderType !== 'LIMIT') {
      setTradeError(
        'GTT is currently supported only for LIMIT order type. Please switch order type to LIMIT or turn off GTT.',
      )
      return
    }

    // If bracket is enabled, validate MTP up front so that any issues
    // are surfaced before placing orders. Per-holding bracket prices are
    // computed below.
    let mtpValue: number | null = null
    if (tradeBracketEnabled) {
      const mtp = Number(tradeMtpPct)
      if (!Number.isFinite(mtp) || mtp <= 0) {
        setTradeError('Min target profit (MTP) must be a positive number.')
        return
      }
      mtpValue = mtp
    }

    // Pre-compute per-holding quantities and optional bracket prices so
    // that validation errors are reported before any orders are placed.
    const plans: {
      holding: HoldingRow
      qty: number
      price: number | null
      bracketPrice: number | null
    }[] = []
    const skippedHoldings: string[] = []

    for (const h of targets) {
      const needsPriceForSizing =
        tradeSizeMode === 'AMOUNT' ||
        tradeSizeMode === 'PCT_POSITION' ||
        tradeSizeMode === 'PCT_PORTFOLIO'

      let holdingForPlan = h
      let qty = computeQtyForHolding(holdingForPlan)

      if (
        !isBulkTrade &&
        needsPriceForSizing &&
        (qty == null || qty <= 0)
      ) {
        const sizingPrice = getSizingPrice(holdingForPlan)
        if (
          sizingPrice == null ||
          !Number.isFinite(sizingPrice) ||
          sizingPrice <= 0
        ) {
        try {
          const sym = (holdingForPlan.symbol || '').trim().toUpperCase()
          const exch =
            (holdingForPlan.exchange || 'NSE').trim().toUpperCase() || 'NSE'
          if (sym) {
            const quotes = await fetchMarketQuotes([{ symbol: sym, exchange: exch }])
            const q = quotes.find(
              (it) =>
                (it.symbol || '').trim().toUpperCase() === sym &&
                ((it.exchange || 'NSE').trim().toUpperCase() || 'NSE') === exch,
            )
            const priceCandidate = q?.ltp ?? q?.prev_close ?? null
            if (
              priceCandidate != null &&
              Number.isFinite(Number(priceCandidate)) &&
              Number(priceCandidate) > 0
            ) {
              holdingForPlan = { ...holdingForPlan, last_price: Number(priceCandidate) }
              qty = computeQtyForHolding(holdingForPlan)
              setTradeHolding((prev) => {
                if (!prev) return prev
                const psym = (prev.symbol || '').trim().toUpperCase()
                const pexch = (prev.exchange || 'NSE').trim().toUpperCase() || 'NSE'
                if (psym !== sym || pexch !== exch) return prev
                const last = prev.last_price != null ? Number(prev.last_price) : null
                if (last != null && Number.isFinite(last) && last > 0) return prev
                return { ...prev, last_price: Number(priceCandidate) }
              })
            }
          }
        } catch {
          // Ignore quote failures; we'll fall back to existing validation below.
        }
        }
      }

      if (qty == null || qty <= 0) {
        if (isBulkTrade) {
          skippedHoldings.push(h.symbol)
          continue
        }
        if (needsPriceForSizing) {
          const p = getSizingPrice(h)
          if (p == null || !Number.isFinite(p) || p <= 0) {
            setTradeError(
              `Cannot compute quantity for ${h.symbol}: price is not available yet. Try again in a moment, switch sizing to Qty, or use a LIMIT order and enter a price.`,
            )
            return
          }
        }
        setTradeError(`Could not compute a valid quantity for ${h.symbol}. Check sizing inputs.`)
        return
      }

      const perHoldingPrice =
        tradeOrderType === 'MARKET' || tradeOrderType === 'SL-M'
          ? null
          : isBulkTrade
            ? getEffectivePrimaryPriceForHolding(holdingForPlan)
            : priceNum

      if (
        (tradeOrderType === 'LIMIT' || tradeOrderType === 'SL') &&
        (perHoldingPrice == null ||
          !Number.isFinite(perHoldingPrice) ||
          perHoldingPrice <= 0)
      ) {
        if (isBulkTrade) {
          skippedHoldings.push(h.symbol)
          continue
        }
        setTradeError(`Price is required for ${tradeOrderType} orders.`)
        return
      }

      let bracketPrice: number | null = null
      if (tradeBracketEnabled && mtpValue != null) {
        const base = getEffectivePrimaryPriceForHolding(holdingForPlan)
        if (base == null || base <= 0) {
          if (isBulkTrade) {
            skippedHoldings.push(h.symbol)
            continue
          }
          setTradeError(
            `Cannot compute bracket price for ${h.symbol}: price is not available.`,
          )
          return
        }
        const m = mtpValue / 100
        if (!Number.isFinite(m) || m <= 0) {
          setTradeError('Invalid MTP value.')
          return
        }
        if (tradeSide === 'BUY') {
          bracketPrice = base * (1 + m)
        } else {
          bracketPrice = base / (1 + m)
        }
        if (!Number.isFinite(bracketPrice) || bracketPrice <= 0) {
          setTradeError(`Computed bracket price is invalid for ${h.symbol}.`)
          return
        }
        bracketPrice = Number(bracketPrice.toFixed(2))
      }

      plans.push({ holding: holdingForPlan, qty, price: perHoldingPrice, bracketPrice })
    }

    if (plans.length === 0) {
      setTradeError(
        skippedHoldings.length > 0
          ? 'No eligible holdings to place orders (all computed quantities are 0).'
          : 'No eligible holdings to place orders.',
      )
      return
    }

    if (!isBulkTrade && tradeSide === 'SELL') {
      const primary = plans[0]
      const holding = primary?.holding ?? null
      if (holding) {
        const sym = (holding.symbol || '').trim().toUpperCase()
        const exch = (holding.exchange || 'NSE').trim().toUpperCase()
        const key = `${exch}:${sym}`
        const sellQty = primary.qty
        const portfolioGroupId =
          activeGroup?.kind === 'PORTFOLIO' ? activeGroup.id : tradePortfolioGroupId

        if (portfolioGroupId != null) {
          const entry = tradePortfolioOptions.find(
            (p) => p.group_id === portfolioGroupId,
          )
          const allocatedQty = entry?.reference_qty ?? holding.reference_qty ?? 0
          if (sellQty > allocatedQty) {
            setTradeError(
              `Sell qty ${sellQty} exceeds portfolio allocation ${allocatedQty} for ${sym}. Reduce qty or sell from a different bucket.`,
            )
            return
          }
        } else if (tradePortfolioOptions.some((p) => (p.reference_qty ?? 0) > 0)) {
          const holdingQty = Number(holding.quantity ?? 0)
          const totalAllocated = Number(portfolioAllocationTotalsByKey[key] ?? 0)
          const unassigned = Math.trunc(
            (Number.isFinite(holdingQty) ? holdingQty : 0) -
              (Number.isFinite(totalAllocated) ? totalAllocated : 0),
          )
          if (sellQty > unassigned) {
            setTradeError(
              `Sell qty ${sellQty} exceeds unassigned qty ${Math.max(0, unassigned)} for ${sym}. Sell from the relevant portfolio, or reconcile allocations first.`,
            )
            return
          }
        }
      }
    }

    if (tradeExecutionMode === 'AUTO' && tradeExecutionTarget === 'LIVE') {
      const tradeBroker = tradeBrokerName === 'angelone' ? 'AngelOne' : 'Zerodha'
      const isAngelOne = tradeBrokerName === 'angelone'
      const brokerActionsPerSymbol =
        (!tradeGtt ? 1 : isAngelOne ? 0 : 1) +
        (tradeBracketEnabled ? (isAngelOne ? 0 : 1) : 0)
      const localConditionalPerSymbol =
        (tradeGtt && isAngelOne ? 1 : 0) + (tradeBracketEnabled && isAngelOne ? 1 : 0)
      const totalBrokerActions = plans.length * brokerActionsPerSymbol
      const totalConditional = plans.length * localConditionalPerSymbol
      const confirmed =
        totalBrokerActions === 0
          ? true
          : window.confirm(
              `AUTO + LIVE will send ${totalBrokerActions} order${
                totalBrokerActions === 1 ? '' : 's'
              } to ${tradeBroker} now${
                totalConditional > 0
                  ? ` and arm ${totalConditional} SigmaTrader-managed conditional order${
                      totalConditional === 1 ? '' : 's'
                    }.`
                  : '.'
              } Continue?`,
            )
      if (!confirmed) return
    }

    const sellManagedRiskUnsupported = tradeSide === 'SELL' && tradeProduct !== 'MIS'
    if (
      sellManagedRiskUnsupported &&
      (riskSlEnabled || riskTrailEnabled || riskActivationEnabled)
    ) {
      setTradeError(
        'Managed SL/trailing exits for SELL are supported only for MIS shorts.',
      )
      return
    }

    const parseFloatStrict = (raw: string, label: string): number => {
      const n = Number(raw)
      if (!Number.isFinite(n)) {
        throw new Error(`${label} must be a number.`)
      }
      return n
    }

    const parseIntStrict = (raw: string, label: string): number => {
      const n = Number(raw)
      if (!Number.isFinite(n) || !Number.isInteger(n)) {
        throw new Error(`${label} must be an integer.`)
      }
      return n
    }

    let riskSpec: RiskSpec | null = null
    try {
      if (riskSlEnabled || riskTrailEnabled || riskActivationEnabled) {
        if (!riskSlEnabled) {
          throw new Error('Stop-loss must be enabled when using trailing exits.')
        }
        const slValueNum = parseFloatStrict(riskSlValue, 'Stop-loss value')
        const trailValueNum = parseFloatStrict(riskTrailValue, 'Trailing value')
        const actValueNum = parseFloatStrict(riskActivationValue, 'Activation value')
        if (slValueNum <= 0) throw new Error('Stop-loss value must be > 0.')
        if (riskTrailEnabled && trailValueNum <= 0)
          throw new Error('Trailing value must be > 0.')
        if (riskActivationEnabled && actValueNum <= 0)
          throw new Error('Activation value must be > 0.')

        const slPeriod = parseIntStrict(riskSlAtrPeriod, 'Stop-loss ATR period')
        const trailPeriod = parseIntStrict(riskTrailAtrPeriod, 'Trailing ATR period')
        const actPeriod = parseIntStrict(
          riskActivationAtrPeriod,
          'Activation ATR period',
        )
        if (slPeriod < 2 || trailPeriod < 2 || actPeriod < 2) {
          throw new Error('ATR period must be >= 2.')
        }

        riskSpec = {
          stop_loss: {
            enabled: true,
            mode: riskSlMode,
            value: slValueNum,
            atr_period: slPeriod,
            atr_tf: riskSlAtrTf,
          },
          trailing_stop: {
            enabled: riskTrailEnabled,
            mode: riskTrailMode,
            value: trailValueNum,
            atr_period: trailPeriod,
            atr_tf: riskTrailAtrTf,
          },
          trailing_activation: {
            enabled: riskActivationEnabled,
            mode: riskActivationMode,
            value: actValueNum,
            atr_period: actPeriod,
            atr_tf: riskActivationAtrTf,
          },
          exit_order_type: 'MARKET',
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? '')
      setTradeError(message || 'Invalid managed risk configuration.')
      return
    }

    setTradeSubmitting(true)
    const totalOrders = plans.length * (tradeBracketEnabled ? 2 : 1)
    setTradeSubmitProgress({ done: 0, total: totalOrders })
    setTradeError(null)
    try {
      const failures: string[] = []
      let progressDone = 0

      for (const { holding, qty, price, bracketPrice } of plans) {
        try {
          const portfolioGroupId =
            activeGroup?.kind === 'PORTFOLIO'
              ? activeGroup.id
              : isBulkTrade
                ? null
                : tradePortfolioGroupId
          const primary = await createManualOrder({
            broker_name: tradeBrokerName,
            portfolio_group_id: portfolioGroupId,
            symbol: holding.symbol,
            exchange: holding.exchange ?? 'NSE',
            side: tradeSide,
            qty,
            price,
            trigger_price: triggerPriceNum,
            order_type: tradeOrderType,
            product: tradeProduct,
            gtt: tradeGtt,
            mode: tradeExecutionMode,
            execution_target: tradeExecutionTarget,
            risk_spec: riskSpec,
          })
          progressDone += 1
          setTradeSubmitProgress({ done: progressDone, total: totalOrders })
          if (tradeExecutionMode === 'AUTO') {
            if (
              primary.status === 'WAITING' ||
              primary.status === 'FAILED' ||
              primary.status === 'REJECTED' ||
              primary.status === 'REJECTED_RISK'
            ) {
              const isConditional =
                primary.gtt && primary.synthetic_gtt && primary.status === 'WAITING'
              if (!isConditional) {
                throw new Error(
                  primary.error_message
                    ? `${holding.symbol}: ${primary.error_message}`
                    : `${holding.symbol}: order was not accepted (${primary.status}).`,
                )
              }
            }
          }

          if (tradeBracketEnabled && bracketPrice != null) {
            const bracketSide = tradeSide === 'BUY' ? 'SELL' : 'BUY'
            const bracket = await createManualOrder({
              broker_name: tradeBrokerName,
              portfolio_group_id: portfolioGroupId,
              symbol: holding.symbol,
              exchange: holding.exchange ?? 'NSE',
              side: bracketSide,
              qty,
              price: bracketPrice,
              order_type: 'LIMIT',
              product: tradeProduct,
              gtt: true,
              mode: tradeExecutionMode,
              execution_target: tradeExecutionTarget,
            })
            progressDone += 1
            setTradeSubmitProgress({ done: progressDone, total: totalOrders })
            if (tradeExecutionMode === 'AUTO') {
              if (
                bracket.status === 'WAITING' ||
                bracket.status === 'FAILED' ||
                bracket.status === 'REJECTED' ||
                bracket.status === 'REJECTED_RISK'
              ) {
                const isConditional =
                  bracket.gtt && bracket.synthetic_gtt && bracket.status === 'WAITING'
                if (!isConditional) {
                  throw new Error(
                    bracket.error_message
                      ? `${holding.symbol}: ${bracket.error_message}`
                      : `${holding.symbol}: bracket order was not accepted (${bracket.status}).`,
                  )
                }
              }
            }
          }
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err ?? '')
          failures.push(message || `${holding.symbol}: failed to create order.`)
          if (!isBulkTrade) {
            break
          }
        }
      }

      if (failures.length > 0) {
        setTradeError(
          failures.length === plans.length
            ? `Failed to create orders: ${failures[0]}`
            : `Some orders failed (${failures.length}/${plans.length}): ${failures[0]}`,
        )
        setTradeSubmitting(false)
        setTradeSubmitProgress(null)
        return
      }

      // Close the dialog as soon as the orders are accepted so the UI
      // feels snappy; refresh holdings in the background.
      setBulkTradeHoldings([])
      setTradeOpen(false)
      setTradeSubmitting(false)
      setTradeSubmitProgress(null)
      void load()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create order'
      setTradeError(message)
      setTradeSubmitting(false)
      setTradeSubmitProgress(null)
    }
  }

  const sizingPrice = getSizingPrice(tradeHolding)
  const amountStep =
    sizingPrice != null && Number.isFinite(sizingPrice) && sizingPrice > 0
      ? sizingPrice
      : 1
  const positionNotional = getPositionValue(tradeHolding, sizingPrice)
  const pctStepPosition =
    sizingPrice != null &&
    Number.isFinite(sizingPrice) &&
    sizingPrice > 0 &&
    positionNotional != null &&
    positionNotional > 0
      ? (sizingPrice / positionNotional) * 100
      : 1
  const pctStepPortfolio =
    sizingPrice != null &&
    Number.isFinite(sizingPrice) &&
    sizingPrice > 0 &&
    portfolioValue != null &&
    portfolioValue > 0
      ? (sizingPrice / portfolioValue) * 100
      : 1

  const getEffectivePrimaryPriceForHolding = (
    holding: HoldingRow | null,
  ): number | null =>
    resolvePrimaryPriceForHolding({
      isBulkTrade,
      holding,
      tradeOrderType,
      tradePrice,
      bulkPriceOverrides,
    })

  const getEffectivePrimaryPrice = (): number | null =>
    getEffectivePrimaryPriceForHolding(tradeHolding)

  const getEffectivePctOfPositionForHolding = (holding: HoldingRow): number | null => {
    const qty = computeQtyForHolding(holding)
    if (qty == null || qty <= 0) return null
    const price = getSizingPrice(holding)
    const positionValue = getPositionValue(holding, price)
    if (
      price == null ||
      !Number.isFinite(price) ||
      price <= 0 ||
      positionValue == null ||
      positionValue <= 0
    ) {
      return null
    }
    const notional = qty * price
    const pct = (notional / positionValue) * 100
    return Number.isFinite(pct) ? Number(pct.toFixed(2)) : null
  }

  const getUniverseReferencePrice = useCallback((row: HoldingRow): number | null => {
    const v = row.reference_price
    return v != null && Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : null
  }, [])

  const getUniverseReferenceQty = useCallback((row: HoldingRow): number | null => {
    const v = row.reference_qty
    return v != null && Number.isFinite(Number(v)) && Number(v) >= 0 ? Number(v) : null
  }, [])

  const getSinceCreationPnl = (row: HoldingRow): number | null => {
    const refPrice = getUniverseReferencePrice(row)
    const refQty = getUniverseReferenceQty(row)
    const current = getDisplayPrice(row)
    if (
      refPrice == null ||
      refQty == null ||
      refQty <= 0 ||
      current == null ||
      !Number.isFinite(current) ||
      current <= 0
    ) {
      return null
    }
    const pnl = (current - refPrice) * refQty
    return Number.isFinite(pnl) ? pnl : null
  }

  const getBracketPreviewPrice = (): number | null => {
    if (!tradeBracketEnabled) return null
    const mtp = Number(tradeMtpPct)
    const base = getEffectivePrimaryPrice()
    if (!Number.isFinite(mtp) || mtp <= 0 || base == null || base <= 0) {
      return null
    }
    const m = mtp / 100
    let target: number
    if (tradeSide === 'BUY') {
      target = base * (1 + m)
    } else {
      target = base / (1 + m)
    }
    if (!Number.isFinite(target) || target <= 0) return null
    return Number(target.toFixed(2))
  }

  const formatRiskDistanceLabel = (
    mode: DistanceMode,
    valueRaw: string,
    atrPeriodRaw: string,
    atrTf: string,
  ): string => {
    const valueNum = Number(valueRaw)
    const val = Number.isFinite(valueNum) ? String(valueNum) : valueRaw
    if (mode === 'PCT') return `${val}%`
    if (mode === 'ABS') return `₹${val}`
    const p = Number(atrPeriodRaw)
    const period = Number.isFinite(p) && p > 0 ? String(p) : atrPeriodRaw
    return `${val}×ATR(${period}, ${atrTf})`
  }

  const getRiskSummaryText = (): string => {
    if (!riskSlEnabled && !riskTrailEnabled && !riskActivationEnabled) return 'Off'
    const parts: string[] = []
    if (riskSlEnabled) {
      parts.push(
        `SL ${formatRiskDistanceLabel(
          riskSlMode,
          riskSlValue,
          riskSlAtrPeriod,
          riskSlAtrTf,
        )}`,
      )
    }
    if (riskTrailEnabled) {
      parts.push(
        `Trail ${formatRiskDistanceLabel(
          riskTrailMode,
          riskTrailValue,
          riskTrailAtrPeriod,
          riskTrailAtrTf,
        )}`,
      )
    }
    if (riskActivationEnabled) {
      parts.push(
        `Act ${formatRiskDistanceLabel(
          riskActivationMode,
          riskActivationValue,
          riskActivationAtrPeriod,
          riskActivationAtrTf,
        )}`,
      )
    }
    return parts.join(' | ')
  }

  const recalcFromRisk = async () => {
    const holding = tradeHolding
    const entry =
      tradeOrderType === 'MARKET' || tradePrice.trim() === ''
        ? getSizingPrice(holding)
        : Number(tradePrice)
    const stop = Number(tradeStopPrice)

    if (
      entry == null ||
      !Number.isFinite(entry) ||
      entry <= 0 ||
      !Number.isFinite(stop) ||
      stop <= 0
    ) {
      setTradeError(
        'Please provide a valid entry price (or price field) and stop price for risk sizing.',
      )
      return
    }

    let riskBudgetAbs: number | null = null
    const budgetRaw = Number(tradeRiskBudget)
    if (!Number.isFinite(budgetRaw) || budgetRaw <= 0) {
      setTradeError('Risk budget must be a positive number.')
      return
    }

    if (tradeRiskBudgetMode === 'ABSOLUTE') {
      riskBudgetAbs = budgetRaw
    } else {
      const total = portfolioValue
      if (total == null || total <= 0) {
        setTradeError(
          'Portfolio value is not available; cannot interpret risk as % of portfolio.',
        )
        return
      }
      riskBudgetAbs = (budgetRaw / 100) * total
    }

    const maxQty =
      clampSellToHoldingsQtyEffective && holding?.quantity != null
        ? Math.floor(Number(holding.quantity))
        : null

    try {
      const res: RiskSizingResponse = await computeRiskSizing({
        entry_price: entry,
        stop_price: stop,
        risk_budget: riskBudgetAbs,
        max_qty: maxQty ?? undefined,
      })
      if (res.qty <= 0) {
        setTradeError(
          'Risk budget is too small for at least one share at this entry/stop.',
        )
        setTradeQty('')
        setTradeAmount('')
        setTradeMaxLoss(null)
        return
      }
      setTradeError(null)
      setTradeQty(String(res.qty))
      setTradeAmount(res.notional.toFixed(2))
      setTradeMaxLoss(res.max_loss)
    } catch (err) {
      setTradeError(
        err instanceof Error
          ? err.message
          : 'Failed to compute risk-based position size.',
      )
    }
  }

  const bulkTotalAmountLabel = isBulkTrade
    ? (() => {
        let total = 0
        for (const h of bulkTradeHoldings) {
          const qty = computeQtyForHolding(h)
          const price = getPerHoldingPriceForSizing(h)
          if (
            qty != null &&
            qty > 0 &&
            price != null &&
            Number.isFinite(price) &&
            price > 0
          ) {
            total += qty * price
          }
        }
        return total > 0 && Number.isFinite(total) ? total.toFixed(2) : ''
      })()
    : tradeAmount

  const bulkQtySummary =
    isBulkTrade && (tradeSizeMode === 'QTY' || tradeSizeMode === 'AMOUNT')
      ? bulkTradeHoldings
          .map((h) => {
            const qty = computeQtyForHolding(h)
            return qty != null && Number.isFinite(qty) && qty > 0 ? String(qty) : '0'
          })
          .join(', ')
      : tradeQty

  const bulkPctSummary =
    isBulkTrade && (tradeSizeMode === 'QTY' || tradeSizeMode === 'AMOUNT')
      ? bulkTradeHoldings
          .map((h) => {
            const qty = computeQtyForHolding(h) ?? 0
            if (!Number.isFinite(qty) || qty <= 0) return '0.00'
            const pct = getEffectivePctOfPositionForHolding(h)
            if (pct == null || !Number.isFinite(pct)) return '0.00'
            return pct.toFixed(2)
          })
          .join(', ')
      : tradePctEquity

  const symbolColumnMinWidth = activeGroup
    ? activeGroup.kind === 'PORTFOLIO'
      ? 220
      : 200
    : 140
  const symbolColumnFlex = activeGroup ? 1.2 : 1

  const portfolioBaselineTotalValue = useMemo(() => {
    if (activeGroup?.kind !== 'PORTFOLIO') return null
    let total = 0
    for (const row of holdings) {
      const h = row as HoldingRow
      const qty = getUniverseReferenceQty(h) ?? 0
      if (!Number.isFinite(qty) || qty <= 0) continue
      let price = getUniverseReferencePrice(h)
      if (price == null) {
        const avg = Number(h.average_price ?? 0)
        if (Number.isFinite(avg) && avg > 0) price = avg
      }
      if (price == null) {
        const ltp = Number(h.last_price ?? 0)
        if (Number.isFinite(ltp) && ltp > 0) price = ltp
      }
      if (price == null || !Number.isFinite(price) || price <= 0) continue
      total += qty * price
    }
    return total > 0 && Number.isFinite(total) ? total : null
  }, [activeGroup?.kind, holdings, getUniverseReferencePrice, getUniverseReferenceQty])

  const baseColumns: GridColDef[] = useMemo(() => [
    {
      field: 'index',
      headerName: '#',
      width: 70,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams) => getPaginatedRowNumber(params),
    },
    {
      field: 'symbol',
      headerName: 'Symbol',
      flex: symbolColumnFlex,
      minWidth: symbolColumnMinWidth,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const symbol = row.symbol || ''
        const qty = row.quantity != null ? Number(row.quantity) : 0
        const isHeld = Number.isFinite(qty) && qty > 0
        const showHoldingsChip = !universeId.startsWith('holdings') && isHeld

        return (
          <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5 }}>
            <span>{symbol}</span>
            {showHoldingsChip && (
              <Tooltip
                title={
                  showQtyValues
                    ? `In Holdings (Zerodha): qty ${Math.floor(qty)}`
                    : 'In Holdings (Zerodha): qty •••'
                }
              >
                <Chip
                  size="small"
                  variant="outlined"
                  color="success"
                  label="Holdings"
                  sx={{
                    height: 16,
                    fontSize: '0.62rem',
                    lineHeight: 1,
                    verticalAlign: 'super',
                    '& .MuiChip-label': { px: 0.5 },
                  }}
                />
              </Tooltip>
            )}
          </Box>
        )
      },
    },
    {
      field: 'risk_category',
      headerName: 'Category',
      width: 130,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const sym = (row.symbol || '').trim().toUpperCase()
        const exch = (row.exchange ?? 'NSE').toString().trim().toUpperCase() || 'NSE'
        const key = `${exch}:${sym}`
        const busy = Boolean(sym && symbolCategoryBusyByKey[key])
        const value = sym
          ? (resolveSymbolRiskCategory(symbolCategoryRows, {
              broker_name: tradeBrokerName,
              exchange: exch,
              symbol: sym,
            }) ?? '')
          : ''
        return (
          <TextField
            select
            size="small"
            value={value}
            disabled={!sym || busy}
            onChange={(e) =>
              void handleSetSymbolCategory(exch, sym, e.target.value as RiskCategory)
            }
            sx={{ minWidth: 110 }}
          >
            <MenuItem value="" disabled>
              â€”
            </MenuItem>
            <MenuItem value="LC">LC</MenuItem>
            <MenuItem value="MC">MC</MenuItem>
            <MenuItem value="SC">SC</MenuItem>
            <MenuItem value="ETF">ETF</MenuItem>
          </TextField>
        )
      },
    },
    {
      field: 'goal_label',
      headerName: 'Label',
      width: 120,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const goal = getGoalForRow(row, goalBrokerName)
        if (!goal) {
          return <Chip size="small" variant="outlined" label="No goal" />
        }
        return <Chip size="small" variant="outlined" color="primary" label={goal.label} />
      },
    },
    {
      field: 'goal_review_date',
      headerName: 'Review Date',
      width: 130,
      valueGetter: (_value, row) => {
        const goal = getGoalForRow(row as HoldingRow, goalBrokerName)
        return goal?.review_date ?? null
      },
      renderCell: (params) => <span>{params.value ?? '—'}</span>,
    },
    {
      field: 'goal_days',
      headerName: 'Days',
      type: 'number',
      width: 90,
      valueGetter: (_value, row) => {
        const goal = getGoalForRow(row as HoldingRow, goalBrokerName)
        return getGoalDaysRemaining(goal)
      },
      valueFormatter: (value) => (value != null ? String(value) : '—'),
      cellClassName: (params: GridCellParams) => {
        if (params.value == null) return ''
        const n = Number(params.value)
        if (!Number.isFinite(n)) return ''
        if (n < 0) return 'goal-overdue'
        if (n <= GOAL_DUE_SOON_DAYS) return 'goal-due-soon'
        return ''
      },
    },
    {
      field: 'goal_status',
      headerName: 'Status',
      width: 140,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const goal = getGoalForRow(row, goalBrokerName)
        const days = getGoalDaysRemaining(goal)
        const status = getGoalStatus(goal, days)
        return (
          <Chip size="small" variant="outlined" color={status.color} label={status.label} />
        )
      },
    },
    {
      field: 'goal_target',
      headerName: 'Target',
      width: 150,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const goal = getGoalForRow(row, goalBrokerName)
        const target = getGoalTarget(row, goal)
        return <span>{target.label}</span>
      },
    },
    {
      field: 'goal_away_pct',
      headerName: 'Away %',
      type: 'number',
      width: 110,
      valueGetter: (_value, row) => {
        const r = row as HoldingRow
        const goal = getGoalForRow(r, goalBrokerName)
        const target = getGoalTarget(r, goal)
        return target.awayPct
      },
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? `${Number(value).toFixed(2)}%`
          : '—',
      cellClassName: (params: GridCellParams) => {
        const row = params.row as HoldingRow
        const goal = getGoalForRow(row, goalBrokerName)
        const days = getGoalDaysRemaining(goal)
        const n = Number(params.value)
        return Number.isFinite(n) &&
          Math.abs(n) <= GOAL_NEAR_TARGET_PCT &&
          days != null &&
          days >= 0
          ? 'goal-near-target'
          : ''
      },
    },
    {
      field: 'goal_note',
      headerName: 'Note',
      flex: 1,
      minWidth: 160,
      valueGetter: (_value, row) => {
        const goal = getGoalForRow(row as HoldingRow, goalBrokerName)
        return goal?.note ?? null
      },
      renderCell: (params) => <span>{params.value ?? '—'}</span>,
    },
    {
      field: 'goal_actions',
      headerName: 'Actions',
      sortable: false,
      filterable: false,
      width: 170,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const goal = getGoalForRow(row, goalBrokerName)
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" variant="outlined" onClick={() => openGoalEditor(row)}>
              Edit
            </Button>
            <Tooltip title={goal?.review_date ? 'Review actions' : 'Set a review date'}>
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!goal?.review_date}
                  onClick={(event) => {
                    event.stopPropagation()
                    openGoalActionMenu(event, row)
                  }}
                >
                  Review
                </Button>
              </span>
            </Tooltip>
          </Box>
        )
      },
    },
    {
      field: 'groupsLabel',
      headerName: 'Groups',
      flex: 1,
      minWidth: 180,
      valueGetter: (_value, row) => (row as HoldingRow).groupsLabel ?? '',
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const names = row.groupNames ?? []
        if (!names.length) return <span>—</span>
        const visible = names.slice(0, 2)
        const remaining = names.length - visible.length

        const openGroup = (name: string) => {
          const query = new URLSearchParams({ group: name }).toString()
          navigate(`/groups?${query}`)
        }

        return (
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {visible.map((name) => (
              <Chip
                key={name}
                size="small"
                label={name}
                clickable
                onClick={() => openGroup(name)}
              />
            ))}
            {remaining > 0 && (
              <Chip
                size="small"
                label={`+${remaining}`}
                clickable
                onClick={() => openGroup(visible[0] ?? names[0])}
              />
            )}
          </Box>
        )
      },
    },
    {
      field: 'chart',
      headerName: 'Chart',
      sortable: false,
      filterable: false,
      width: 160,
      renderCell: (params) => (
        <HoldingChartCell
          history={(params.row as HoldingRow).history}
          periodDays={chartPeriodDays}
        />
      ),
    },
    {
      field: 'quantity',
      headerName: 'Qty',
      type: 'number',
      width: 100,
      renderHeader: () => (
        <SensitiveToggle
          label="Qty"
          visible={showQtyValues}
          onToggle={toggleShowQtyValues}
          ariaLabel={showQtyValues ? 'Hide quantities' : 'Show quantities'}
        />
      ),
      renderCell: (params) => {
        if (!showQtyValues) return <span>•••</span>
        const row = params.row as HoldingRow
        if (activeGroup?.kind !== 'PORTFOLIO') return <span>{row.quantity}</span>

        const holdRaw = row.quantity
        const holdQty =
          holdRaw != null && Number.isFinite(Number(holdRaw))
            ? Math.trunc(Number(holdRaw))
            : null
        const ref = row.reference_qty
        const refQty =
          ref != null && Number.isFinite(Number(ref)) ? Math.trunc(Number(ref)) : null

        if (refQty == null || holdQty == null) return <span>{row.quantity}</span>

        const bad = refQty > holdQty
        return (
          <span style={bad ? { color: '#d32f2f', fontWeight: 600 } : undefined}>
            {refQty}/{holdQty}
          </span>
        )
      },
    },
    {
      field: 'reference_qty',
      headerName: 'Ref Qty',
      type: 'number',
      width: 110,
      valueGetter: (_value, row) => (row as HoldingRow).reference_qty ?? null,
      renderHeader: () => (
        <SensitiveToggle
          label="Ref Qty"
          visible={showQtyValues}
          onToggle={toggleShowQtyValues}
          ariaLabel={showQtyValues ? 'Hide quantities' : 'Show quantities'}
        />
      ),
      renderCell: (params) => {
        if (!showQtyValues) return <span>•••</span>
        const row = params.row as HoldingRow
        const ref = row.reference_qty
        if (ref == null || !Number.isFinite(Number(ref))) return <span>—</span>
        const refQty = Math.trunc(Number(ref))
        const holdRaw = row.quantity
        const holdQty =
          holdRaw != null && Number.isFinite(Number(holdRaw))
            ? Math.trunc(Number(holdRaw))
            : null
        if (holdQty == null) return <span>{refQty}</span>
        const bad = refQty > holdQty
        return (
          <span style={bad ? { color: '#d32f2f', fontWeight: 600 } : undefined}>
            {refQty}/{holdQty}
          </span>
        )
      },
    },
    {
      field: 'average_price',
      headerName: 'Avg Price',
      type: 'number',
      width: 130,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'reference_price',
      headerName: 'Ref Price',
      type: 'number',
      width: 130,
      valueGetter: (_value, row) => (row as HoldingRow).reference_price ?? null,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const ref = row.reference_price
        if (ref == null || !Number.isFinite(Number(ref))) return <span>—</span>
        const refPrice = Number(ref)
        const holdAvgRaw = row.average_price
        const holdAvg =
          holdAvgRaw != null &&
          Number.isFinite(Number(holdAvgRaw)) &&
          Number(holdAvgRaw) > 0
            ? Number(holdAvgRaw)
            : null
        if (holdAvg == null) return <span>{refPrice.toFixed(2)}</span>
        return (
          <span>
            {refPrice.toFixed(2)}/{holdAvg.toFixed(2)}
          </span>
        )
      },
    },
    {
      field: 'last_price',
      headerName: 'Last Price',
      type: 'number',
      width: 130,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'gap_pct',
      headerName: 'Gap %',
      type: 'number',
      width: 110,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.gapPct ?? null,
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? `${Number(value).toFixed(2)}%`
          : '—',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'week52_low',
      headerName: '52W Low',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.week52Low ?? null,
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? Number(value).toFixed(2)
          : '—',
    },
    {
      field: 'week52_high',
      headerName: '52W High',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.week52High ?? null,
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? Number(value).toFixed(2)
          : '—',
    },
    {
      field: 'pnlSinceCreation',
      headerName: 'P&L (Since)',
      type: 'number',
      width: 150,
      renderHeader: () => (
        <SensitiveToggle
          label="P&L (Since)"
          visible={showMoneyValues}
          onToggle={toggleShowMoneyValues}
          ariaLabel={showMoneyValues ? 'Hide money values' : 'Show money values'}
        />
      ),
      valueGetter: (_value, row) => getSinceCreationPnl(row as HoldingRow),
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? Number(value).toFixed(2)
          : '—',
      renderCell: (params) =>
        showMoneyValues ? (
          <span>
            {params.value != null && Number.isFinite(Number(params.value))
              ? Number(params.value).toFixed(2)
              : '—'}
          </span>
        ) : (
          <span>₹••••</span>
        ),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'pnlSinceCreationPct',
      headerName: 'P&L% (Since)',
      type: 'number',
      width: 150,
      valueGetter: (_value, row) => {
        const r = row as HoldingRow
        const refPrice = getUniverseReferencePrice(r)
        const current = getDisplayPrice(r)
        if (refPrice == null || current == null || current <= 0) return null
        const pct = (current / refPrice - 1) * 100
        return Number.isFinite(pct) ? pct : null
      },
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? `${Number(value).toFixed(2)}%`
          : '—',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'invested',
      headerName: 'Invested',
      type: 'number',
      width: 140,
      renderHeader: () => (
        <SensitiveToggle
          label="Invested"
          visible={showMoneyValues}
          onToggle={toggleShowMoneyValues}
          ariaLabel={showMoneyValues ? 'Hide money values' : 'Show money values'}
        />
      ),
      valueGetter: (_value, row) => {
        const h = row as HoldingRow
        if (h.quantity == null || h.average_price == null) return null
        return Number(h.quantity) * Number(h.average_price)
      },
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
      renderCell: (params) =>
        showMoneyValues ? (
          <span>
            {params.value != null && Number.isFinite(Number(params.value))
              ? Number(params.value).toFixed(2)
              : '-'}
          </span>
        ) : (
          <span>₹••••</span>
        ),
    },
    {
      field: 'current_value',
      headerName: 'Current Value',
      type: 'number',
      width: 150,
      renderHeader: () => (
        <SensitiveToggle
          label="Current Value"
          visible={showMoneyValues}
          onToggle={toggleShowMoneyValues}
          ariaLabel={showMoneyValues ? 'Hide money values' : 'Show money values'}
        />
      ),
      valueGetter: (_value, row) => {
        const h = row as HoldingRow
        if (h.quantity == null || h.last_price == null) return null
        return Number(h.quantity) * Number(h.last_price)
      },
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
      renderCell: (params) =>
        showMoneyValues ? (
          <span>
            {params.value != null && Number.isFinite(Number(params.value))
              ? Number(params.value).toFixed(2)
              : '-'}
          </span>
        ) : (
          <span>₹••••</span>
        ),
    },
    {
      field: 'weight',
      headerName: 'Weight',
      width: activeGroup ? 140 : 110,
      filterable: false,
      valueGetter: (_value, row) => {
        const h = row as HoldingRow

        const qty = Number(h.quantity ?? 0)
        const price = getDisplayPrice(h)
        const hv =
          Number.isFinite(qty) && qty > 0 && price != null && price > 0
            ? qty * price
            : 0
        const wh =
          portfolioValue != null &&
          Number.isFinite(portfolioValue) &&
          portfolioValue > 0 &&
          hv > 0
            ? (hv / portfolioValue) * 100
            : null

        const kind = activeGroup?.kind ?? null
        const shouldSortByPortfolioWeight =
          kind === 'MODEL_PORTFOLIO' || kind === 'PORTFOLIO'
        if (!shouldSortByPortfolioWeight) return wh

        let wp = 0
        if (kind === 'PORTFOLIO') {
          const refQty = getUniverseReferenceQty(h) ?? 0
          let refPrice = getUniverseReferencePrice(h)
          if (refPrice == null) {
            const avg = Number(h.average_price ?? 0)
            if (Number.isFinite(avg) && avg > 0) refPrice = avg
          }
          if (refPrice == null) {
            const ltp = Number(h.last_price ?? 0)
            if (Number.isFinite(ltp) && ltp > 0) refPrice = ltp
          }
          const base =
            Number.isFinite(refQty) && refQty > 0 && refPrice != null && refPrice > 0
              ? refQty * refPrice
              : 0
          wp =
            portfolioBaselineTotalValue != null &&
            portfolioBaselineTotalValue > 0 &&
            base > 0
              ? (base / portfolioBaselineTotalValue) * 100
              : 0
        } else {
          const tw = Number(h.target_weight ?? 0)
          wp = Number.isFinite(tw) && tw > 0 ? tw * 100 : 0
        }
        return Number.isFinite(wp) ? wp : null
      },
      sortComparator: (v1, v2) => {
        const a = typeof v1 === 'number' ? v1 : v1 != null ? Number(v1) : null
        const b = typeof v2 === 'number' ? v2 : v2 != null ? Number(v2) : null
        const aOk = a != null && Number.isFinite(a)
        const bOk = b != null && Number.isFinite(b)
        if (!aOk && !bOk) return 0
        if (!aOk) return 1
        if (!bOk) return -1
        return a - b
      },
      renderCell: (params: GridRenderCellParams) => {
        const row = params.row as HoldingRow
        const qty = Number(row.quantity ?? 0)
        const price = getDisplayPrice(row)
        const hv =
          Number.isFinite(qty) && qty > 0 && price != null && price > 0
            ? qty * price
            : 0
        const wh =
          portfolioValue != null &&
          Number.isFinite(portfolioValue) &&
          portfolioValue > 0
            ? (hv / portfolioValue) * 100
            : null

        if (!activeGroup) {
          return <span>{wh == null ? '—' : wh.toFixed(2)}</span>
        }

        let wp = 0
        if (activeGroup.kind === 'PORTFOLIO') {
          const refQty = getUniverseReferenceQty(row) ?? 0
          let refPrice = getUniverseReferencePrice(row)
          if (refPrice == null) {
            const avg = Number(row.average_price ?? 0)
            if (Number.isFinite(avg) && avg > 0) refPrice = avg
          }
          if (refPrice == null) {
            const ltp = Number(row.last_price ?? 0)
            if (Number.isFinite(ltp) && ltp > 0) refPrice = ltp
          }
          const base =
            Number.isFinite(refQty) && refQty > 0 && refPrice != null && refPrice > 0
              ? refQty * refPrice
              : 0
          wp =
            portfolioBaselineTotalValue != null &&
            portfolioBaselineTotalValue > 0 &&
            base > 0
              ? (base / portfolioBaselineTotalValue) * 100
              : 0
        } else {
          const tw = Number(row.target_weight ?? 0)
          wp = Number.isFinite(tw) && tw > 0 ? tw * 100 : 0
        }

        const left = Number.isFinite(wp) ? wp.toFixed(2) : '0.00'
        const right = wh != null && Number.isFinite(wh) ? wh.toFixed(2) : '—'
        return <span>{`${left}/${right}`}</span>
      },
    },
    {
      field: 'indicator_rsi14',
      headerName: 'RSI(14)',
      type: 'number',
      width: 110,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.rsi14 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(1) : '-'),
    },
    {
      field: 'perf_1d_pct',
      headerName: '1D PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.perf1dPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'perf_5d_pct',
      headerName: '5D PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.perf5dPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'perf_1m_pct',
      headerName: '1M PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.perf1mPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'perf_3m_pct',
      headerName: '3M PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.perf3mPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'perf_6m_pct',
      headerName: '6M PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.perf6mPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'perf_1y_pct',
      headerName: '1Y PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.perf1yPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'sma_20',
      headerName: 'SMA(20)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sma20 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'sma_50',
      headerName: 'SMA(50)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sma50 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'sma_200',
      headerName: 'SMA(200)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sma200 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'ema_20',
      headerName: 'EMA(20)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.ema20 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'ema_50',
      headerName: 'EMA(50)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.ema50 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'ema_200',
      headerName: 'EMA(200)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.ema200 ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'macd',
      headerName: 'MACD',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.macd ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(3) : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'macd_signal',
      headerName: 'MACD Sig',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.macdSignal ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(3) : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'macd_hist',
      headerName: 'MACD Hist',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.macdHist ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(3) : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'sr_20_high',
      headerName: '20D High',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sr20High ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'sr_20_low',
      headerName: '20D Low',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sr20Low ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'sr_50_high',
      headerName: '50D High',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sr50High ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'sr_50_low',
      headerName: '50D Low',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.sr50Low ?? null,
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
    },
    {
      field: 'dist_20_high_pct',
      headerName: 'To 20D High %',
      type: 'number',
      width: 140,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.distToSr20HighPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'dist_20_low_pct',
      headerName: 'To 20D Low %',
      type: 'number',
      width: 140,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.distToSr20LowPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'obv',
      headerName: 'OBV',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.obv ?? null,
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? String(Math.trunc(Number(value)))
          : '-',
    },
    {
      field: 'pvt',
      headerName: 'PVT',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.pvt ?? null,
      valueFormatter: (value) =>
        value != null && Number.isFinite(Number(value))
          ? Number(value).toFixed(0)
          : '-',
    },
    {
      field: 'pvt_slope_pct_20',
      headerName: 'PVT 20D %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.pvtSlopePct20 ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'volatility_20d_pct',
      headerName: 'Vol 20D %',
      type: 'number',
      width: 130,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.volatility20dPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
    },
    {
      field: 'atr_14_pct',
      headerName: 'ATR(14) %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.atr14Pct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
    },
    {
      field: 'volume_vs_20d_avg',
      headerName: 'Vol / 20D Avg',
      type: 'number',
      width: 150,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.volumeVsAvg20d ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}x` : '-'),
    },
    {
      field: 'pnl',
      headerName: 'Unrealized P&L',
      type: 'number',
      width: 150,
      renderHeader: () => (
        <SensitiveToggle
          label="Unrealized P&L"
          visible={showMoneyValues}
          onToggle={toggleShowMoneyValues}
          ariaLabel={showMoneyValues ? 'Hide money values' : 'Show money values'}
        />
      ),
      valueFormatter: (value) => (value != null ? Number(value).toFixed(2) : '-'),
      renderCell: (params) =>
        showMoneyValues ? (
          <span>{params.value != null ? Number(params.value).toFixed(2) : '-'}</span>
        ) : (
          <span>₹••••</span>
        ),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'pnl_shares',
      headerName: 'PnL Shares',
      type: 'number',
      width: 120,
      renderHeader: () => (
        <SensitiveToggle
          label="PnL Shares"
          visible={showMoneyValues}
          onToggle={toggleShowMoneyValues}
          ariaLabel={showMoneyValues ? 'Hide money values' : 'Show money values'}
        />
      ),
      valueGetter: (_value, row) => {
        const r = row as HoldingRow
        const pnl = r.pnl
        const last = r.last_price
        if (pnl == null || last == null) return null
        const pnlN = Number(pnl)
        const lastN = Number(last)
        if (!Number.isFinite(pnlN) || !Number.isFinite(lastN) || lastN <= 0) {
          return null
        }
        return Math.floor(pnlN / lastN)
      },
      valueFormatter: (value) =>
        value != null ? String(Math.trunc(Number(value))) : '-',
      renderCell: (params) =>
        showMoneyValues ? (
          <span>{params.value != null ? String(Math.trunc(Number(params.value))) : '-'}</span>
        ) : (
          <span>•••</span>
        ),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'total_pnl_percent',
      headerName: 'P&L %',
      type: 'number',
      width: 110,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'maxPnlPct',
      headerName: 'Max P&L % (since entry)',
      type: 'number',
      width: 160,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.maxPnlPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'drawdownFromPeakPct',
      headerName: 'DD (6M)',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) => (row as HoldingRow).indicators?.dd6mPct ?? null,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'today_pnl_percent',
      headerName: 'Today P&L %',
      type: 'number',
      width: 130,
      valueFormatter: (value) => (value != null ? `${Number(value).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'alerts',
      headerName: 'Alerts',
      sortable: false,
      filterable: false,
      width: 120,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        return (
          <Button
            size="small"
            variant="outlined"
            onClick={() => openAlertDialogForHolding(row)}
          >
            Alert
          </Button>
        )
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      sortable: false,
      filterable: false,
      width: 160,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => openTradeDialog(row, 'BUY')}
            >
              Buy
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="error"
              onClick={() => openTradeDialog(row, 'SELL')}
            >
              Sell
            </Button>
          </Box>
        )
      },
    },
  ], [
    activeGroup,
    chartPeriodDays,
    formatInrCompact,
    formatPct,
    getDisplayPrice,
    getGoalDaysRemaining,
    getGoalForRow,
    getGoalTarget,
    goalBrokerName,
    navigate,
    openAlertDialogForHolding,
    openGoalActionMenu,
    openGoalEditor,
    openTradeDialog,
    portfolioBaselineTotalValue,
    portfolioValue,
    showMoneyValues,
    showQtyValues,
    symbolCategoryBusyByKey,
    symbolCategoryRows,
    symbolColumnFlex,
    symbolColumnMinWidth,
    toggleShowMoneyValues,
    toggleShowQtyValues,
    universeId,
  ])

  const importColumns: GridColDef[] = useMemo(() => {
    if (!activeGroupDataset?.columns?.length) return []
    return activeGroupDataset.columns.map((c) => {
      const field = `import_${c.key}`
      return {
        field,
        headerName: c.label,
        headerClassName: 'st-imported-column-header',
        type: c.type === 'number' ? 'number' : 'string',
        minWidth: 140,
        flex: 1,
        valueGetter: (_value, row) =>
          (row as unknown as Record<string, unknown>)[field] ?? null,
        valueFormatter: (value: unknown) => {
          if (value == null) return '—'
          const n = Number(value)
          return Number.isFinite(n) ? n.toFixed(2) : String(value)
        },
        cellClassName: (params: GridCellParams) => {
          const n = Number(params.value)
          return Number.isFinite(n) && n < 0 ? 'st-imported-negative' : ''
        },
      } satisfies GridColDef
    })
  }, [activeGroupDataset?.columns])

  const columns: GridColDef[] = useMemo(() => {
    if (importColumns.length === 0) return baseColumns
    const symbolIndex = baseColumns.findIndex((c) => c.field === 'symbol')
    const insertAt = symbolIndex >= 0 ? symbolIndex + 1 : 2
    return [
      ...baseColumns.slice(0, insertAt),
      ...importColumns,
      ...baseColumns.slice(insertAt),
    ]
  }, [baseColumns, importColumns])

  const columnFields = useMemo(() => columns.map((c) => String(c.field)), [columns])
  columnsFieldRef.current = columnFields

  useEffect(() => {
    if (typeof window === 'undefined') return

    if (viewId.startsWith('custom:') && !customViews.some((v) => v.id === viewId)) {
      try {
        const raw = window.localStorage.getItem(HOLDINGS_CUSTOM_VIEWS_STORAGE_KEY)
        if (raw) {
          const parsed = JSON.parse(raw) as Array<{ id: string }>
          if (Array.isArray(parsed) && parsed.some((v) => v?.id === viewId)) {
            // Storage has it; allow subsequent render to pick it up.
            return
          }
        }
      } catch {
        // Ignore parse errors.
      }

      setViewId('default')
      try {
        window.localStorage.setItem(HOLDINGS_SELECTED_VIEW_STORAGE_KEY, 'default')
      } catch {
        // Ignore persistence errors.
      }
      return
    }

    const universeKey = encodeURIComponent(universeId)
    const viewKey = encodeURIComponent(viewId)
    const visibilityKeyVersion = viewId === 'default' ? 'v3' : 'v2'
    const perUniverseKeyV2 = `st_holdings_column_visibility_${viewKey}_${universeKey}_${visibilityKeyVersion}`
    const globalKeyV2 = `st_holdings_column_visibility_${viewKey}_${visibilityKeyVersion}`

    const readModel = (key: string): GridColumnVisibilityModel | null => {
      try {
        const raw = window.localStorage.getItem(key)
        if (!raw) return null
        const parsed = JSON.parse(raw) as GridColumnVisibilityModel
        return parsed && typeof parsed === 'object' ? parsed : null
      } catch {
        return null
      }
    }

    const buildShowOnlyModel = (
      showFields: string[],
      options?: { keepImportColumns?: boolean },
    ): GridColumnVisibilityModel => {
      const show = new Set(showFields)
      const model: GridColumnVisibilityModel = {}
      const keepImportColumns = options?.keepImportColumns ?? true
      for (const field of columnsFieldRef.current) {
        if (field.startsWith('import_') && keepImportColumns) continue
        model[field] = show.has(field)
      }
      return model
    }

    const defaultModel: GridColumnVisibilityModel = buildShowOnlyModel(
      [
        'symbol',
        'risk_category',
        'chart',
        'average_price',
        'last_price',
        'invested',
        'current_value',
        'weight',
        'total_pnl_percent',
        'today_pnl_percent',
        'alerts',
        'actions',
      ],
      { keepImportColumns: false },
    )

    const presetShowFields: Record<string, string[]> = {
      goal: [
        'index',
        'symbol',
        'goal_label',
        'goal_review_date',
        'goal_days',
        'goal_status',
        'goal_target',
        'goal_away_pct',
        'goal_note',
        'goal_actions',
      ],
      performance: [
        'index',
        'symbol',
        'groupsLabel',
        'chart',
        'quantity',
        'last_price',
        'gap_pct',
        'weight',
        'perf_1d_pct',
        'perf_5d_pct',
        'perf_1m_pct',
        'perf_3m_pct',
        'perf_6m_pct',
        'perf_1y_pct',
        'volume_vs_20d_avg',
        'pnlSinceCreationPct',
      ],
      indicators: [
        'index',
        'symbol',
        'groupsLabel',
        'chart',
        'last_price',
        'indicator_rsi14',
        'sma_20',
        'sma_50',
        'sma_200',
        'ema_20',
        'ema_50',
        'ema_200',
        'macd',
        'macd_signal',
        'macd_hist',
        'atr_14_pct',
        'volatility_20d_pct',
        'volume_vs_20d_avg',
        'obv',
        'pvt',
        'pvt_slope_pct_20',
      ],
      support_resistance: [
        'index',
        'symbol',
        'groupsLabel',
        'chart',
        'last_price',
        'gap_pct',
        'sma_20',
        'sma_50',
        'sr_20_high',
        'sr_20_low',
        'sr_50_high',
        'sr_50_low',
        'dist_20_high_pct',
        'dist_20_low_pct',
        'week52_low',
        'week52_high',
        'atr_14_pct',
      ],
      risk: [
        'index',
        'symbol',
        'groupsLabel',
        'quantity',
        'average_price',
        'last_price',
        'weight',
        'maxPnlPct',
        'drawdownFromPeakPct',
        'dd6mPct',
        'volatility_20d_pct',
        'atr_14_pct',
      ],
    }

    const v2 = readModel(perUniverseKeyV2) ?? readModel(globalKeyV2)
    if (v2) {
      setColumnVisibilityModel(v2)
      return
    }

    // Backward-compatible fallback for legacy default/risk view keys.
    if (viewId === 'default' || viewId === 'risk') {
      const legacyPerUniverseKey = `st_holdings_column_visibility_${viewId}_${universeKey}_v1`
      const legacy = readModel(legacyPerUniverseKey)
      if (legacy) {
        setColumnVisibilityModel(legacy)
        return
      }

      const legacyKey =
        viewId === 'risk'
          ? 'st_holdings_column_visibility_risk_v1'
          : 'st_holdings_column_visibility_default_v1'
      const legacyGlobal = readModel(legacyKey)
      if (legacyGlobal) {
        setColumnVisibilityModel(legacyGlobal)
        return
      }
    }

    let nextModel: GridColumnVisibilityModel
    if (viewId === 'default') {
      nextModel = defaultModel
    } else if (presetShowFields[viewId]) {
      nextModel = buildShowOnlyModel(presetShowFields[viewId])
    } else {
      nextModel = defaultModel
    }

    setColumnVisibilityModel(nextModel)
    try {
      window.localStorage.setItem(globalKeyV2, JSON.stringify(nextModel))
    } catch {
      // Ignore persistence errors.
    }
  }, [customViews, universeId, viewId])

  const gridGetRowId = useCallback((row: HoldingRow) => row.symbol, [])

  const handleRowSelectionModelChange = useCallback((newSelection: GridRowSelectionModel) => {
    setRowSelectionModel(newSelection)
  }, [])

  const handleColumnVisibilityModelChange = useCallback(
    (model: GridColumnVisibilityModel) => {
      setColumnVisibilityModel(model)
      try {
        const universeKey = encodeURIComponent(universeId)
        const viewKey = encodeURIComponent(viewId)
        const visibilityKeyVersion = viewId === 'default' ? 'v3' : 'v2'
        const perUniverseKey = `st_holdings_column_visibility_${viewKey}_${universeKey}_${visibilityKeyVersion}`
        const globalKey = `st_holdings_column_visibility_${viewKey}_${visibilityKeyVersion}`
        window.localStorage.setItem(perUniverseKey, JSON.stringify(model))
        window.localStorage.setItem(globalKey, JSON.stringify(model))

        // Keep the legacy keys updated for backwards-compatible defaults
        // (these are used only as fallbacks).
        if (viewId === 'default' || viewId === 'risk') {
          const legacyKey =
            viewId === 'risk'
              ? 'st_holdings_column_visibility_risk_v1'
              : 'st_holdings_column_visibility_default_v1'
          if (universeId === 'holdings' || universeId === 'holdings:angelone') {
            window.localStorage.setItem(legacyKey, JSON.stringify(model))
          }
        }
      } catch {
        // Ignore persistence errors.
      }
    },
    [universeId, viewId],
  )

  const gridGetRowClassName = useCallback((params: GridRowClassNameParams<HoldingRow>) => {
    const id = String(params.id || '').toUpperCase()
    return highlightSymbol && id === highlightSymbol ? 'st-row-highlight' : ''
  }, [highlightSymbol])

  const gridSx = useMemo(
    () => ({
      '& .pnl-negative': {
        color: 'error.main',
      },
      '& .MuiDataGrid-row.st-row-highlight': {
        backgroundColor: (theme: Theme) =>
          theme.palette.mode === 'dark'
            ? 'rgba(255, 193, 7, 0.22)'
            : 'rgba(255, 193, 7, 0.16)',
      },
      '& .goal-overdue': {
        color: 'error.main',
        fontWeight: 600,
      },
      '& .goal-due-soon': {
        color: 'warning.main',
        fontWeight: 600,
      },
      '& .goal-near-target': {
        color: 'success.main',
        fontWeight: 600,
      },
      '& .MuiDataGrid-columnHeader.st-imported-column-header': {
        backgroundColor: (theme: Theme) =>
          theme.palette.mode === 'dark'
            ? 'rgba(144, 202, 249, 0.18)'
            : 'rgba(25, 118, 210, 0.08)',
      },
      '& .MuiDataGrid-columnHeader.st-imported-column-header .MuiDataGrid-columnHeaderTitle':
        {
          fontWeight: 600,
        },
      '& .st-imported-negative': {
        color: 'error.main',
      },
    }),
    [],
  )

  const gridInitialState = useMemo(
    () => ({
      pagination: { paginationModel: { pageSize: 100 } },
    }),
    [],
  )

  const gridLocaleText = useMemo(
    () => ({
      noRowsLabel: 'No holdings found.',
    }),
    [],
  )

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
        <Box sx={{ flex: '1 1 560px', minWidth: 320 }}>
          <Typography variant="h4" gutterBottom>
            {activeGroup ? activeGroup.name : 'Holdings'}
          </Typography>
          {activeGroup && (
            <Typography color="text.secondary" sx={{ mb: 1 }}>
              {activeGroup.description ? activeGroup.description : 'Symbols loaded from the selected group.'}
            </Typography>
          )}
          {refreshError && (
            <Typography
              variant="caption"
              color="error"
              sx={{ mb: 1, display: 'block' }}
            >
              {refreshError}
            </Typography>
          )}
          {corrError && (
            <Typography
              variant="caption"
              color="error"
              sx={{ mb: 1, display: 'block' }}
            >
              {corrError}
            </Typography>
          )}
          {goalLoadError && viewId === 'goal' && (
            <Typography
              variant="caption"
              color="error"
              sx={{ mb: 1, display: 'block' }}
            >
              {goalLoadError}
            </Typography>
          )}
          {viewId === 'goal' && goalViewSupported && goalReviewActionError && (
            <Alert severity="error" sx={{ mb: 1 }}>
              {goalReviewActionError}
            </Alert>
          )}
          {viewId === 'goal' && goalViewSupported && goalReminderSummary.overdue > 0 && (
            <Alert
              severity="error"
              sx={{ mb: 1 }}
              action={
                <Button
                  color="inherit"
                  size="small"
                  onClick={() => setGoalFilter('overdue')}
                >
                  View overdue
                </Button>
              }
            >
              {goalReminderSummary.overdue} holding
              {goalReminderSummary.overdue === 1 ? '' : 's'} overdue for review.
            </Alert>
          )}
          {viewId === 'goal' &&
            goalViewSupported &&
            goalReminderSummary.dueSoon > 0 && (
              <Alert
                severity="warning"
                sx={{ mb: 1 }}
                action={
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => setGoalFilter('due_soon')}
                  >
                    View due soon
                  </Button>
                }
              >
                {goalReminderSummary.dueSoon} holding
                {goalReminderSummary.dueSoon === 1 ? '' : 's'} due within{' '}
                {GOAL_DUE_SOON_DAYS} days.
              </Alert>
            )}
          {viewId === 'goal' &&
            goalViewSupported &&
            goalReminderSummary.nearTarget > 0 && (
              <Alert
                severity="info"
                sx={{ mb: 1 }}
                action={
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => setGoalFilter('near_target')}
                  >
                    View near target
                  </Button>
                }
              >
                {goalReminderSummary.nearTarget} holding
                {goalReminderSummary.nearTarget === 1 ? '' : 's'} within{' '}
                {GOAL_NEAR_TARGET_PCT}% of target.
              </Alert>
            )}
          {portfolioAllocationMismatches.length > 0 && (
            <Alert
              severity="warning"
              sx={{ mb: 1 }}
              action={
                <Button
                  color="inherit"
                  size="small"
                  onClick={() => setPortfolioMismatchDialogOpen(true)}
                >
                  Review
                </Button>
              }
            >
              Portfolio allocation mismatch detected for{' '}
              {portfolioAllocationMismatches.length} symbol
              {portfolioAllocationMismatches.length === 1 ? '' : 's'} (Σ portfolio ref
              qty exceeds broker holdings).
            </Alert>
          )}

          <Dialog
            open={portfolioMismatchDialogOpen}
            onClose={() => setPortfolioMismatchDialogOpen(false)}
            fullWidth
            maxWidth="md"
          >
            <DialogTitle>Portfolio allocation mismatches</DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Σ portfolio reference qty across all PORTFOLIO groups is greater than
                your broker holdings qty for these symbols. Click a portfolio chip to
                open that portfolio.
              </Typography>
              <Paper sx={{ height: 520 }}>
                <DataGrid
                  rows={portfolioAllocationMismatches}
                  getRowId={(row) => row.symbol}
                  density="compact"
                  disableRowSelectionOnClick
                  sx={{ height: '100%' }}
                  columns={[
                    { field: 'symbol', headerName: 'Symbol', width: 140 },
                    {
                      field: 'holdingQty',
                      headerName: 'Holdings',
                      width: 120,
                      type: 'number',
                      renderHeader: () => (
                        <SensitiveToggle
                          label="Holdings"
                          visible={showQtyValues}
                          onToggle={toggleShowQtyValues}
                          ariaLabel={showQtyValues ? 'Hide quantities' : 'Show quantities'}
                        />
                      ),
                      valueFormatter: (v) =>
                        showQtyValues ? Math.trunc(Number(v ?? 0)) : '•••',
                    },
                    {
                      field: 'allocated',
                      headerName: 'Allocated (Σ)',
                      width: 140,
                      type: 'number',
                      renderHeader: () => (
                        <SensitiveToggle
                          label="Allocated (Σ)"
                          visible={showQtyValues}
                          onToggle={toggleShowQtyValues}
                          ariaLabel={showQtyValues ? 'Hide quantities' : 'Show quantities'}
                        />
                      ),
                      valueFormatter: (v) =>
                        showQtyValues ? Math.trunc(Number(v ?? 0)) : '•••',
                    },
                    {
                      field: 'excess',
                      headerName: 'Excess',
                      width: 110,
                      type: 'number',
                      renderHeader: () => (
                        <SensitiveToggle
                          label="Excess"
                          visible={showQtyValues}
                          onToggle={toggleShowQtyValues}
                          ariaLabel={showQtyValues ? 'Hide quantities' : 'Show quantities'}
                        />
                      ),
                      valueFormatter: (v) =>
                        showQtyValues ? Math.trunc(Number(v ?? 0)) : '•••',
                    },
                    {
                      field: 'groups',
                      headerName: 'Portfolios',
                      flex: 1,
                      minWidth: 260,
                      sortable: false,
                      filterable: false,
                      renderCell: (
                        params: GridRenderCellParams<PortfolioAllocationMismatch>,
                      ) => {
                        const row = params.row
                        const top = row.groups.slice(0, 4)
                        const extra = row.groups.length - top.length
                        return (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {top.map((g) => (
                              <Chip
                                key={g.group_id}
                                size="small"
                                label={`${g.group_name} (${showQtyValues ? Math.trunc(g.allocated) : '•••'})`}
                                clickable
                                onClick={() =>
                                  navigate(
                                    `/groups?group=${encodeURIComponent(g.group_name)}`,
                                  )
                                }
                              />
                            ))}
                            {extra > 0 && (
                              <Chip
                                size="small"
                                variant="outlined"
                                label={`+${extra} more`}
                              />
                            )}
                          </Box>
                        )
                      },
                    },
                  ]}
                />
              </Paper>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => navigate('/groups')}>Open groups</Button>
              <Button onClick={() => setPortfolioMismatchDialogOpen(false)}>
                Close
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog
            open={goalEditOpen}
            onClose={() => setGoalEditOpen(false)}
            fullWidth
            maxWidth="sm"
          >
            <DialogTitle>
              Edit Goal{goalEditRow?.symbol ? ` — ${goalEditRow.symbol}` : ''}
            </DialogTitle>
            <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Label (required)
                </Typography>
                <RadioGroup
                  row
                  value={goalLabel}
                  onChange={(e) => {
                    const next = e.target.value as GoalLabel
                    setGoalLabel(next)
                    if (!goalReviewTouched) {
                      setGoalReviewDate(defaultReviewDateForLabel(next))
                    }
                  }}
                >
                  {GOAL_LABELS.map((label) => (
                    <FormControlLabel
                      key={label}
                      value={label}
                      control={<Radio size="small" />}
                      label={label}
                    />
                  ))}
                </RadioGroup>
              </Box>
              <TextField
                label="Review date (required)"
                type="date"
                value={goalReviewDate}
                onChange={(e) => {
                  setGoalReviewDate(e.target.value)
                  setGoalReviewTouched(true)
                }}
                helperText="This holding must be reviewed on or after this date."
                InputLabelProps={{ shrink: true }}
              />
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <TextField
                  select
                  label="Target type (optional)"
                  value={goalTargetType}
                  onChange={(e) => {
                    const next = e.target.value as GoalTargetType | ''
                    setGoalTargetType(next)
                    if (next === '') setGoalTargetValue('')
                  }}
                  sx={{ minWidth: 220 }}
                >
                  <MenuItem value="">No target</MenuItem>
                  {GOAL_TARGET_TYPES.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Target value"
                  value={goalTargetValue}
                  onChange={(e) => setGoalTargetValue(e.target.value)}
                  disabled={goalTargetType === ''}
                  placeholder={goalTargetType === 'ABSOLUTE_PRICE' ? 'Price' : '%'}
                  sx={{ minWidth: 160 }}
                />
              </Box>
              <TextField
                label="Computed target (preview)"
                value={goalTargetPreview?.label ?? '—'}
                InputProps={{ readOnly: true }}
              />

              <Box sx={{ mt: 1 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={goalExitSubscribe}
                      onChange={(e) => {
                        setGoalExitSubscribe(Boolean(e.target.checked))
                        setGoalExitError(null)
                      }}
                      disabled={goalTargetType === '' || goalTargetType === 'PCT_FROM_LTP'}
                    />
                  }
                  label="Subscribe to holdings exit automation (MVP)"
                />
                <Typography variant="caption" color="text.secondary">
                  When enabled, SigmaTrader will monitor this holding and create a CNC SELL
                  order in the Waiting Queue when the target is met. Manual-only (safe).
                </Typography>
                {goalTargetType === 'PCT_FROM_LTP' && (
                  <Typography variant="caption" color="warning.main" display="block">
                    % from LTP target is not supported for holdings exit automation (MVP).
                  </Typography>
                )}
                {goalExitSubscribe && (
                  <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mt: 1 }}>
                    <TextField
                      select
                      label="Sell sizing"
                      value={goalExitSizeMode}
                      onChange={(e) =>
                        setGoalExitSizeMode(
                          e.target.value as 'PCT_OF_POSITION' | 'ABS_QTY',
                        )
                      }
                      sx={{ minWidth: 220 }}
                    >
                      <MenuItem value="PCT_OF_POSITION">% of position</MenuItem>
                      <MenuItem value="ABS_QTY">Qty</MenuItem>
                    </TextField>
                    <TextField
                      label={goalExitSizeMode === 'ABS_QTY' ? 'Qty' : '% of position'}
                      value={goalExitSizeValue}
                      onChange={(e) => setGoalExitSizeValue(e.target.value)}
                      sx={{ minWidth: 160 }}
                    />
                  </Box>
                )}
                {goalExitError && (
                  <Typography variant="caption" color="error" display="block">
                    {goalExitError}
                  </Typography>
                )}
              </Box>

              <TextField
                label="Thesis note (optional)"
                value={goalNote}
                onChange={(e) => setGoalNote(e.target.value)}
                placeholder="One-line reason or context"
              />
              {goalSaveError && (
                <Typography variant="caption" color="error">
                  {goalSaveError}
                </Typography>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setGoalEditOpen(false)} disabled={goalSaving}>
                Cancel
              </Button>
              <Button
                variant="contained"
                onClick={saveGoal}
                disabled={goalSaving || !goalEditRow}
              >
                Save Goal
              </Button>
            </DialogActions>
          </Dialog>

          <GoalImportDialog
            open={goalImportOpen}
            brokerName={goalBrokerName}
            holdingsSymbols={holdingsSymbolsForImport}
            onClose={() => setGoalImportOpen(false)}
            onImported={() => refreshHoldingGoals(goalBrokerName)}
          />

          <Menu
            anchorEl={goalActionAnchorEl}
            open={goalActionMenuOpen}
            onClose={closeGoalActionMenu}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <MenuItem onClick={() => handleGoalMenuAction('REVIEWED')}>
              Mark reviewed
            </MenuItem>
            <MenuItem onClick={() => handleGoalMenuAction('SNOOZE', 7)}>
              Snooze 7d
            </MenuItem>
            <MenuItem onClick={() => handleGoalMenuAction('EXTEND', 30)}>
              Extend 30d
            </MenuItem>
            <MenuItem onClick={() => handleGoalMenuAction('EXTEND', 90)}>
              Extend 90d
            </MenuItem>
            <Divider />
            <MenuItem onClick={handleGoalMenuHistory}>View history</MenuItem>
          </Menu>

          <Dialog
            open={goalReviewHistoryOpen}
            onClose={() => setGoalReviewHistoryOpen(false)}
            fullWidth
            maxWidth="sm"
          >
            <DialogTitle>
              Review history{goalReviewHistoryRow ? ` — ${goalReviewHistoryRow.symbol}` : ''}
            </DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              {goalReviewHistoryError && (
                <Alert severity="error" sx={{ mb: 1 }}>
                  {goalReviewHistoryError}
                </Alert>
              )}
              {!goalReviewHistoryError && goalReviewHistory.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  No review actions recorded yet.
                </Typography>
              )}
              {goalReviewHistory.map((entry) => (
                <Box key={entry.id} sx={{ mb: 1.5 }}>
                  <Typography variant="subtitle2">
                    {entry.action.replace('_', ' ')} — {entry.created_at.slice(0, 10)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {entry.previous_review_date} → {entry.new_review_date}
                  </Typography>
                  {entry.note && (
                    <Typography variant="body2" color="text.secondary">
                      {entry.note}
                    </Typography>
                  )}
                </Box>
              ))}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setGoalReviewHistoryOpen(false)}>Close</Button>
            </DialogActions>
          </Dialog>
        </Box>

        <Paper
          variant="outlined"
          sx={{
            p: 1.5,
            flex: '0 1 720px',
            minWidth: 320,
            maxWidth: 860,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              flexWrap: 'wrap',
            }}
          >
            <Typography variant="subtitle2">Holdings summary</Typography>
            <Typography variant="caption" color="text.secondary">
              {holdingsSummary.count} positions
            </Typography>
          </Box>

          <Box
            sx={{
              mt: 1,
              display: 'grid',
              gap: 1.5,
              gridTemplateColumns: {
                xs: 'repeat(2, minmax(0, 1fr))',
                md: 'repeat(4, minmax(0, 1fr))',
              },
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary">
                Funds available
              </Typography>
              <Tooltip
                title={availableFundsError ?? ''}
                disableHoverListener={!availableFundsError}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Typography variant="subtitle2" sx={{ whiteSpace: 'nowrap' }}>
                    {universeId === 'holdings:angelone'
                      ? 'N/A'
                      : availableFundsLoading
                        ? 'Loading…'
                        : formatInrCompact(availableFunds)}
                  </Typography>
                  {universeId !== 'holdings:angelone' && (
                    <IconButton
                      size="small"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                      }}
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        toggleShowMoneyValues()
                      }}
                      aria-label={showMoneyValues ? 'Hide money values' : 'Show money values'}
                    >
                      {showMoneyValues ? (
                        <VisibilityIcon fontSize="small" />
                      ) : (
                        <VisibilityOffIcon fontSize="small" />
                      )}
                    </IconButton>
                  )}
                </Box>
              </Tooltip>
            </Box>

            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary">
                Value
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="subtitle2" sx={{ whiteSpace: 'nowrap' }}>
                  {formatInrCompact(holdingsSummary.currentValue)}
                </Typography>
                <IconButton
                  size="small"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                  }}
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    toggleShowMoneyValues()
                  }}
                  aria-label={showMoneyValues ? 'Hide money values' : 'Show money values'}
                >
                  {showMoneyValues ? (
                    <VisibilityIcon fontSize="small" />
                  ) : (
                    <VisibilityOffIcon fontSize="small" />
                  )}
                </IconButton>
              </Box>
            </Box>

            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary">
                P&L (total / today)
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Typography
                  variant="subtitle2"
                  sx={{
                    color:
                      holdingsSummary.totalPnlPct != null
                        ? holdingsSummary.totalPnlPct > 0
                          ? 'success.main'
                          : holdingsSummary.totalPnlPct < 0
                            ? 'error.main'
                            : 'text.primary'
                        : 'text.primary',
                  }}
                >
                  {formatPct(holdingsSummary.totalPnlPct)}
                </Typography>
                <Typography
                  variant="subtitle2"
                  sx={{
                    color:
                      holdingsSummary.todayPnlPct != null
                        ? holdingsSummary.todayPnlPct > 0
                          ? 'success.main'
                          : holdingsSummary.todayPnlPct < 0
                            ? 'error.main'
                            : 'text.primary'
                        : 'text.primary',
                  }}
                >
                  {formatPct(holdingsSummary.todayPnlPct)}
                </Typography>
              </Box>
            </Box>

            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary">
                Win rate (total / today)
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="subtitle2">
                  {formatPct(holdingsSummary.overallWinRate, 1)}
                </Typography>
                <Typography variant="subtitle2">
                  {formatPct(holdingsSummary.todayWinRate, 1)}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                W/L: {holdingsSummary.overallWinner}/{holdingsSummary.overallLoser} · Today: {holdingsSummary.todayWinner}/{holdingsSummary.todayLoser}
              </Typography>
            </Box>
          </Box>
        </Paper>
      </Box>

      <Dialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Holdings settings</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Chart
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Chart period:
              </Typography>
              <Select
                size="small"
                value={String(chartPeriodDays)}
                onChange={(e) => setChartPeriodDays(Number(e.target.value) || 30)}
              >
                <MenuItem value="7">1W</MenuItem>
                <MenuItem value="30">1M</MenuItem>
                <MenuItem value="90">3M</MenuItem>
                <MenuItem value="180">6M</MenuItem>
                <MenuItem value="365">1Y</MenuItem>
                <MenuItem value="730">2Y</MenuItem>
              </Select>
            </Box>
          </Box>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Auto refresh
            </Typography>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.5,
                flexWrap: 'wrap',
              }}
            >
              <Typography variant="caption" color="text.secondary">
                Auto refresh every
              </Typography>
              <TextField
                label="DD"
                size="small"
                type="number"
                value={refreshDays}
                onChange={(e) => setRefreshDays(e.target.value)}
                sx={{ width: 68 }}
                inputProps={{ min: 0 }}
              />
              <TextField
                label="HH"
                size="small"
                type="number"
                value={refreshHours}
                onChange={(e) => setRefreshHours(e.target.value)}
                sx={{ width: 68 }}
                inputProps={{ min: 0, max: 23 }}
              />
              <TextField
                label="MM"
                size="small"
                type="number"
                value={refreshMinutes}
                onChange={(e) => setRefreshMinutes(e.target.value)}
                sx={{ width: 68 }}
                inputProps={{ min: 0, max: 59 }}
              />
              <TextField
                label="SS"
                size="small"
                type="number"
                value={refreshSeconds}
                onChange={(e) => setRefreshSeconds(e.target.value)}
                sx={{ width: 68 }}
                inputProps={{ min: 0, max: 59 }}
              />
              <Button
                size="small"
                variant={autoRefreshEnabled ? 'contained' : 'outlined'}
                onClick={() => setAutoRefreshEnabled((prev) => !prev)}
              >
                {autoRefreshEnabled ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
              </Button>
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  setRefreshDays('0')
                  setRefreshHours('0')
                  setRefreshMinutes('5')
                  setRefreshSeconds('0')
                }}
              >
                Reset interval
              </Button>
            </Box>
            {refreshError && (
              <Typography
                variant="caption"
                color="error"
                sx={{ mt: 1, display: 'block' }}
              >
                {refreshError}
              </Typography>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSettingsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={viewsDialogOpen}
        onClose={() => setViewsDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Holdings views</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Views save your column selection. Use the Columns menu to pick columns, then
            save.
          </Typography>

          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
            <TextField
              label="New view name"
              size="small"
              value={newViewName}
              onChange={(e) => setNewViewName(e.target.value)}
              sx={{ flex: '1 1 220px' }}
            />
            <Button
              size="small"
              variant="contained"
              onClick={() => {
                const name = newViewName.trim()
                if (!name) return
                const id = `custom:${Date.now().toString(36)}`
                const next = [...customViews, { id, name }]
                setCustomViews(next)
                setNewViewName('')
                try {
                  window.localStorage.setItem(
                    HOLDINGS_CUSTOM_VIEWS_STORAGE_KEY,
                    JSON.stringify(next),
                  )
                } catch {
                  // Ignore persistence errors.
                }
                try {
                  const universeKey = encodeURIComponent(universeId)
                  const viewKey = encodeURIComponent(id)
                  window.localStorage.setItem(
                    `st_holdings_column_visibility_${viewKey}_${universeKey}_v2`,
                    JSON.stringify(columnVisibilityModel),
                  )
                  window.localStorage.setItem(
                    `st_holdings_column_visibility_${viewKey}_v2`,
                    JSON.stringify(columnVisibilityModel),
                  )
                  window.localStorage.setItem(HOLDINGS_SELECTED_VIEW_STORAGE_KEY, id)
                } catch {
                  // Ignore persistence errors.
                }
                setViewId(id as HoldingsViewId)
                setViewsDialogOpen(false)
              }}
            >
              Save as new
            </Button>
            {viewId.startsWith('custom:') && (
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  try {
                    const universeKey = encodeURIComponent(universeId)
                    const viewKey = encodeURIComponent(viewId)
                    window.localStorage.setItem(
                      `st_holdings_column_visibility_${viewKey}_${universeKey}_v2`,
                      JSON.stringify(columnVisibilityModel),
                    )
                    window.localStorage.setItem(
                      `st_holdings_column_visibility_${viewKey}_v2`,
                      JSON.stringify(columnVisibilityModel),
                    )
                  } catch {
                    // Ignore persistence errors.
                  }
                }}
              >
                Update current
              </Button>
            )}
          </Box>

          {customViews.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Custom views
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {customViews.map((v) => (
                  <Box
                    key={v.id}
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 1,
                      p: 1,
                      border: '1px solid',
                      borderColor: 'divider',
                      borderRadius: 1,
                    }}
                  >
                    <Typography variant="body2">{v.name}</Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => {
                          setViewId(v.id as HoldingsViewId)
                          try {
                            window.localStorage.setItem(
                              HOLDINGS_SELECTED_VIEW_STORAGE_KEY,
                              v.id,
                            )
                          } catch {
                            // Ignore persistence errors.
                          }
                          setViewsDialogOpen(false)
                        }}
                      >
                        Use
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => {
                          const nextName = window.prompt('Rename view', v.name)?.trim()
                          if (!nextName) return
                          const next = customViews.map((x) =>
                            x.id === v.id ? { ...x, name: nextName } : x,
                          )
                          setCustomViews(next)
                          try {
                            window.localStorage.setItem(
                              HOLDINGS_CUSTOM_VIEWS_STORAGE_KEY,
                              JSON.stringify(next),
                            )
                          } catch {
                            // Ignore persistence errors.
                          }
                        }}
                      >
                        Rename
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        variant="outlined"
                        onClick={() => {
                          const ok = window.confirm(`Delete view "${v.name}"?`)
                          if (!ok) return
                          const next = customViews.filter((x) => x.id !== v.id)
                          setCustomViews(next)
                          try {
                            window.localStorage.setItem(
                              HOLDINGS_CUSTOM_VIEWS_STORAGE_KEY,
                              JSON.stringify(next),
                            )
                          } catch {
                            // Ignore persistence errors.
                          }
                          if (viewId === v.id) {
                            setViewId('default')
                            try {
                              window.localStorage.setItem(
                                HOLDINGS_SELECTED_VIEW_STORAGE_KEY,
                                'default',
                              )
                            } catch {
                              // Ignore persistence errors.
                            }
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewsDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <RebalanceDialog
        open={rebalanceOpen}
        onClose={() => setRebalanceOpen(false)}
        title={rebalanceConfig.title}
        targetKind={rebalanceConfig.targetKind}
        groupId={rebalanceConfig.groupId}
        brokerName={rebalanceConfig.brokerName}
        brokerLocked={rebalanceConfig.brokerLocked}
        scheduleSupported={rebalanceConfig.scheduleSupported}
      />

      <Box
        sx={{
          mb: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-start',
          flexWrap: 'wrap',
          gap: 2,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            gap: 0.5,
            flex: '1 1 auto',
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              flexWrap: 'wrap',
              justifyContent: 'flex-start',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Universe:
              </Typography>
              <Select
                size="small"
                value={universeId}
                onChange={(e) => {
                  const next = String(e.target.value || 'holdings')
                  setRowSelectionModel([])
                  setUniverseId(next)
                  if (next === 'holdings') {
                    navigate('/holdings', { replace: true })
                  } else {
                    navigate(
                      `/holdings?${new URLSearchParams({ universe: next }).toString()}`,
                      { replace: true },
                    )
                  }
                }}
                sx={{ minWidth: 240 }}
              >
                <MenuItem value="holdings">Holdings (Zerodha)</MenuItem>
                {angeloneConnected && (
                  <MenuItem value="holdings:angelone">Holdings (AngelOne)</MenuItem>
                )}
                {availableGroups.map((g) => {
                  const kindLabel =
                    g.kind === 'WATCHLIST'
                      ? 'Watchlist'
                      : g.kind === 'MODEL_PORTFOLIO'
                        ? 'Basket'
                        : g.kind === 'PORTFOLIO'
                          ? 'Portfolio'
                          : g.kind === 'HOLDINGS_VIEW'
                            ? 'Holdings view'
                            : g.kind
                  return (
                    <MenuItem key={g.id} value={`group:${g.id}`}>
                      {g.name} ({kindLabel})
                    </MenuItem>
                  )
                })}
              </Select>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary">
                View:
              </Typography>
              <Select
                size="small"
                value={viewId}
                onChange={(e) => {
                  const next = String(e.target.value || 'default') as HoldingsViewId
                  setViewId(next)
                  if (typeof window !== 'undefined') {
                    try {
                      window.localStorage.setItem(
                        HOLDINGS_SELECTED_VIEW_STORAGE_KEY,
                        next,
                      )
                    } catch {
                      // Ignore persistence errors.
                    }
                  }
                }}
                sx={{ minWidth: 160 }}
              >
                <MenuItem value="default">Default</MenuItem>
                {goalViewSupported && <MenuItem value="goal">Goal View</MenuItem>}
                <MenuItem value="performance">Performance</MenuItem>
                <MenuItem value="indicators">Indicators</MenuItem>
                <MenuItem value="support_resistance">Support/Resistance</MenuItem>
                <MenuItem value="risk">Risk</MenuItem>
                {customViews.length > 0 && <MenuItem disabled>— Custom —</MenuItem>}
                {customViews.map((v) => (
                  <MenuItem key={v.id} value={v.id as HoldingsViewId}>
                    {v.name}
                  </MenuItem>
                ))}
              </Select>
              <Button
                size="small"
                variant="outlined"
                onClick={() => setViewsDialogOpen(true)}
              >
                Views…
              </Button>
            </Box>
            {viewId === 'goal' && goalViewSupported && (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  flexWrap: 'wrap',
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  Filters:
                </Typography>
                <Chip
                  size="small"
                  label="All"
                  color={goalFilter === 'all' ? 'primary' : 'default'}
                  onClick={() => setGoalFilter('all')}
                />
                <Chip
                  size="small"
                  label="Overdue"
                  color={goalFilter === 'overdue' ? 'primary' : 'default'}
                  onClick={() => setGoalFilter('overdue')}
                />
                <Chip
                  size="small"
                  label={`Due Soon (≤${GOAL_DUE_SOON_DAYS}d)`}
                  color={goalFilter === 'due_soon' ? 'primary' : 'default'}
                  onClick={() => setGoalFilter('due_soon')}
                />
                <Chip
                  size="small"
                  label={`Near Target (±${GOAL_NEAR_TARGET_PCT}%)`}
                  color={goalFilter === 'near_target' ? 'primary' : 'default'}
                  onClick={() => setGoalFilter('near_target')}
                />
                <Chip
                  size="small"
                  label="Missing"
                  color={goalFilter === 'missing' ? 'primary' : 'default'}
                  onClick={() => setGoalFilter('missing')}
                />
                {missingGoalCount > 0 && (
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => openGoalEditor(missingGoalRows[0])}
                  >
                    Set missing goals ({missingGoalCount})
                  </Button>
                )}
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setGoalImportOpen(true)}
                >
                  Import CSV
                </Button>
              </Box>
            )}
            <Button
              size="small"
              variant="contained"
              onClick={() => {
                const selected = holdings.filter((h) =>
                  rowSelectionModel.includes(h.symbol),
                )
                if (!selected.length) return
                setBulkTradeHoldings(selected)
                setBulkPriceOverrides({})
                setBulkAmountOverrides({})
                setBulkQtyOverrides({})
                setBulkAmountManual(false)
                setBulkAmountBudget('')
                openBulkTradeDialog(selected, 'BUY')
              }}
              disabled={rowSelectionModel.length === 0}
            >
              Bulk buy
            </Button>
            <Button
              size="small"
              variant="contained"
              color="error"
              onClick={() => {
                const selected = holdings.filter((h) =>
                  rowSelectionModel.includes(h.symbol),
                )
                if (!selected.length) return
                setBulkTradeHoldings(selected)
                setBulkPriceOverrides({})
                setBulkAmountOverrides({})
                setBulkQtyOverrides({})
                setBulkAmountManual(false)
                setBulkAmountBudget('')
                openBulkTradeDialog(selected, 'SELL')
              }}
              disabled={rowSelectionModel.length === 0}
            >
              Bulk sell
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                setGroupCreateError(null)
                setGroupCreateInfo(null)
                setGroupSelectionMode('create')
                setGroupTargetId('')
                setGroupCreateOpen(true)
              }}
              disabled={rowSelectionModel.length === 0}
            >
              Group
            </Button>
            {rebalanceConfig.show && (
              <Button
                size="small"
                variant="outlined"
                startIcon={<AutorenewIcon />}
                onClick={() => setRebalanceOpen(true)}
              >
                Rebalance
              </Button>
            )}
            <Button
              size="small"
              variant="outlined"
              onClick={() => setSettingsOpen(true)}
            >
              View settings
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                if (!hasLoadedOnce) {
                  void load()
                  return
                }
                void refreshHoldingsInPlace('manual')
              }}
            >
              Refresh now
            </Button>
            <Box sx={{ flex: '1 1 240px', minWidth: 260, maxWidth: 420, ml: { xs: 0, md: 'auto' } }}>
              <InstrumentSearch
                label="Quick trade"
                brokerName={universeId === 'holdings:angelone' ? 'angelone' : 'zerodha'}
                onSelect={handleQuickTradeSelect}
              />
            </Box>
          </Box>
          {totalActiveAlerts > 0 && (
            <Typography variant="caption" color="text.secondary">
              Active alerts (approx.): {totalActiveAlerts}
            </Typography>
          )}
        </Box>
      </Box>

      {/*
      {advancedFiltersOpen && screenerMode === 'builder' && (
        <Paper
          sx={{
            mb: 1,
            p: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          {advancedFilters.map((filter, idx) => {
            const operatorOptions = getOperatorOptions(filter.field)
            const fieldCfg = getFieldConfig(filter.field)
            const rhsMode = filter.compareTo ?? 'value'
            const comparableFields = HOLDINGS_FILTER_FIELDS.filter(
              (f) => f.type === fieldCfg.type && f.field !== filter.field,
            )
            return (
              <Box
                key={filter.id}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  flexWrap: 'wrap',
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    flexWrap: 'wrap',
                    flex: 1,
                    minWidth: 0,
                  }}
                >
                  <TextField
                    label="Column"
                    select
                    size="small"
                    value={filter.field}
                    onChange={(e) => {
                      const nextField =
                        e.target.value as HoldingsFilterField
                      const nextOperatorOptions =
                        getOperatorOptions(nextField)
                      setAdvancedFilters((current) =>
                        current.map((f) =>
                          f.id === filter.id
                            ? {
                                ...f,
                                field: nextField,
                                operator:
                                  nextOperatorOptions[0]?.value ??
                                  f.operator,
                                compareField:
                                  (f.compareTo ?? 'value') === 'field'
                                    ? (HOLDINGS_FILTER_FIELDS.filter(
                                        (cfg) =>
                                          cfg.type === getFieldConfig(nextField).type
                                          && cfg.field !== nextField,
                                      )[0]?.field ?? f.compareField)
                                    : f.compareField,
                              }
                            : f,
                        ),
                      )
                    }}
                    sx={{ minWidth: 180 }}
                  >
                    {HOLDINGS_FILTER_FIELDS.map((f) => (
                      <MenuItem key={f.field} value={f.field}>
                        {f.label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Operator"
                    select
                    size="small"
                    value={filter.operator}
                    onChange={(e) => {
                      const nextOp =
                        e.target.value as HoldingsFilterOperator
                      setAdvancedFilters((current) =>
                        current.map((f) =>
                          f.id === filter.id ? { ...f, operator: nextOp } : f,
                        ),
                      )
                    }}
                    sx={{ minWidth: 140 }}
                  >
                    {operatorOptions.map((opt) => (
                      <MenuItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <FormControlLabel
                    sx={{ ml: 0 }}
                    control={
                      <Checkbox
                        size="small"
                        checked={rhsMode === 'field'}
                        disabled={comparableFields.length === 0}
                        onChange={(e) => {
                          const checked = e.target.checked
                          setAdvancedFilters((current) =>
                            current.map((f) => {
                              if (f.id !== filter.id) return f
                              if (!checked) {
                                return { ...f, compareTo: 'value' }
                              }
                              const cfg = getFieldConfig(f.field)
                              const defaultField =
                                HOLDINGS_FILTER_FIELDS.filter(
                                  (x) => x.type === cfg.type && x.field !== f.field,
                                )[0]?.field
                              return {
                                ...f,
                                compareTo: 'field',
                                compareField: defaultField ?? f.compareField,
                              }
                            }),
                          )
                        }}
                      />
                    }
                    label="Compare to column"
                  />
                  {rhsMode === 'field' ? (
                    <TextField
                      label="RHS column"
                      select
                      size="small"
                      value={filter.compareField ?? comparableFields[0]?.field ?? ''}
                      disabled={comparableFields.length === 0}
                      onChange={(e) => {
                        const nextField = e.target.value as HoldingsFilterField
                        setAdvancedFilters((current) =>
                          current.map((f) =>
                            f.id === filter.id
                              ? { ...f, compareField: nextField, compareTo: 'field' }
                              : f,
                          ),
                        )
                      }}
                      sx={{ minWidth: 180 }}
                    >
                      {comparableFields.map((f) => (
                        <MenuItem key={f.field} value={f.field}>
                          {f.label}
                        </MenuItem>
                      ))}
                    </TextField>
                  ) : (
                    <TextField
                      label="Value"
                      size="small"
                      value={filter.value}
                      onChange={(e) => {
                        const nextValue = e.target.value
                        setAdvancedFilters((current) =>
                          current.map((f) =>
                            f.id === filter.id ? { ...f, value: nextValue } : f,
                          ),
                        )
                      }}
                      sx={{ minWidth: 140 }}
                    />
                  )}
                  <Button
                    size="small"
                    onClick={() =>
                      setAdvancedFilters((current) =>
                        current.filter((f) => f.id !== filter.id),
                      )
                    }
                  >
                    Remove
                  </Button>
                </Box>
                {idx < advancedFilters.length - 1 && (
                  <Box
                    sx={{
                      width: 72,
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Chip
                      size="small"
                      variant="outlined"
                      label={
                        screenerLogicOperator === GridLogicOperator.Or
                          ? 'OR'
                          : 'AND'
                      }
                      aria-label={
                        screenerLogicOperator === GridLogicOperator.Or
                          ? 'Rows combined with OR'
                          : 'Rows combined with AND'
                      }
                      sx={{
                        fontWeight: 600,
                        letterSpacing: 0.5,
                      }}
                    />
                  </Box>
                )}
              </Box>
            )
          })}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              flexWrap: 'wrap',
            }}
          >
            <Button
              size="small"
              variant="outlined"
              onClick={() =>
                setAdvancedFilters((current) => [
                  ...current,
                  {
                    id: `f-${Date.now()}-${current.length + 1}`,
                    field: 'symbol',
                    operator: 'contains',
                    value: '',
                    compareTo: 'value',
                  },
                ])
              }
            >
              + Add condition
            </Button>
            {advancedFilters.length > 0 && (
              <Button
                size="small"
                onClick={() => setAdvancedFilters([])}
              >
                Clear all
              </Button>
            )}
            <TextField
              label="Match mode"
              select
              size="small"
              value={
                screenerLogicOperator === GridLogicOperator.Or
                  ? 'OR'
                  : 'AND'
              }
              onChange={(e) =>
                setScreenerLogicOperator(
                  e.target.value === 'OR'
                    ? GridLogicOperator.Or
                    : GridLogicOperator.And,
                )
              }
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="AND">All conditions (AND)</MenuItem>
              <MenuItem value="OR">Any condition (OR)</MenuItem>
            </TextField>
          </Box>
        </Paper>
      )}

      {advancedFiltersOpen && screenerMode === 'dsl' && (
        <Paper
          sx={{
            mb: 1,
            p: 1.5,
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
            }}
          >
            <Typography variant="subtitle2">DSL screener</Typography>
            <Tooltip title="DSL help">
              <IconButton
                size="small"
                onClick={() => setScreenerDslHelpOpen(true)}
              >
                <HelpOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          <Typography variant="caption" color="text.secondary">
            Use the same DSL as indicator alerts, e.g.
            {' '}
            <code>RSI(14, 1d) {'<'} 30 AND PERF_PCT(20, 1d) {'<'} -10</code>.
          </Typography>
          <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
            <Editor
              height="120px"
              defaultLanguage="sigma-dsl"
              value={screenerDsl}
              onChange={(value) => {
                setScreenerDsl(value ?? '')
                setScreenerDslError(null)
                setScreenerDslMatches(null)
              }}
              onMount={handleScreenerDslMount}
              options={{
                minimap: { enabled: false },
                fontSize: 12,
                lineNumbers: 'off',
                scrollBeyondLastLine: false,
              }}
            />
          </Box>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              flexWrap: 'wrap',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Button
                size="small"
                variant="outlined"
                disabled={screenerDslLoading}
                onClick={async () => {
                  const expr = screenerDsl.trim()
                  if (!expr) {
                    setScreenerDslError('DSL expression cannot be empty.')
                    setScreenerDslMatches(null)
                    return
                  }
                  try {
                    setScreenerDslLoading(true)
                    setScreenerDslError(null)
                    const res = await evaluateHoldingsScreenerDsl(expr)
                    setScreenerDslMatches(res.matches)
                    if (res.matches.length === 0) {
                      setScreenerDslError(
                        'No holdings currently match this expression.',
                      )
                    }
                  } catch (err) {
                    setScreenerDslMatches(null)
                    setScreenerDslError(
                      err instanceof Error
                        ? err.message
                        : 'Failed to evaluate screener.',
                    )
                  } finally {
                    setScreenerDslLoading(false)
                  }
                }}
              >
                {screenerDslLoading ? 'Evaluating…' : 'Apply screener'}
              </Button>
              {screenerDslMatches && !screenerDslLoading && (
                <Typography variant="caption" color="text.secondary">
                  Matches:
                  {' '}
                  {screenerDslMatches.length}
                </Typography>
              )}
            </Box>
            {screenerDslError && (
              <Typography variant="caption" color="error">
                {screenerDslError}
              </Typography>
            )}
          </Box>
        </Paper>
      )}

      <Dialog
        open={screenerDslHelpOpen}
        onClose={() => setScreenerDslHelpOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>DSL screener help</DialogTitle>
        <DialogContent dividers>
          <Typography variant="subtitle2" gutterBottom>
            Fields
          </Typography>
          <Typography variant="body2" paragraph>
            You can reference holdings fields directly:
            {' '}
            <code>PNL_PCT</code>, <code>TODAY_PNL_PCT</code>,{' '}
            <code>MAX_PNL_PCT</code>, <code>DRAWDOWN_PCT</code>,{' '}
            <code>INVESTED</code>, <code>CURRENT_VALUE</code>,{' '}
            <code>QTY</code>, <code>AVG_PRICE</code>.
            {' '}
            (<code>DRAWDOWN_FROM_PEAK_PCT</code> is accepted as an alias.)
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Indicators
          </Typography>
          <Typography variant="body2" paragraph>
            Supported indicator functions:
            {' '}
            <code>PRICE(tf?)</code>, <code>RSI(period, tf?)</code>,{' '}
            <code>MA(period, tf?)</code> / <code>SMA(period, tf?)</code>,{' '}
            <code>VOLATILITY(period, tf?)</code>, <code>ATR(period, tf?)</code>,{' '}
            <code>PERF_PCT(period, tf?)</code> / <code>MOMENTUM(period, tf?)</code>,{' '}
            <code>VOLUME_RATIO(period, tf?)</code>, <code>VWAP(period, tf?)</code>,{' '}
            <code>PVT(tf?)</code>, <code>PVT_SLOPE(period, tf?)</code>.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>Notes:</strong>
            {' '}
            <code>tf</code> is optional and defaults to <code>1d</code>. Negative numbers are supported (e.g. <code>PNL_PCT {'<'} -10</code>).
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Operators
          </Typography>
          <Typography variant="body2" paragraph>
            Comparisons:
            {' '}
            {'>'}, {'>='}, {'<'}, {'<='}, {'=='}, {'!='};
            {' '}
            cross:
            {' '}
            <code>CROSS_ABOVE</code>, <code>CROSS_BELOW</code>;
            {' '}
            boolean:
            {' '}
            <code>AND</code>, <code>OR</code>, <code>NOT</code>; use parentheses for grouping.
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Timeframes
          </Typography>
          <Typography variant="body2" paragraph>
            <code>1m</code>, <code>5m</code>, <code>15m</code>, <code>1h</code>, <code>1d</code>, <code>1mo</code>, <code>1y</code>
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Examples
          </Typography>
          <Typography variant="body2">
            Oversold:
            {' '}
            <code>RSI(14, 1d) {'<'} 30</code>
          </Typography>
          <Typography variant="body2">
            Profit + pullback:
            {' '}
            <code>PNL_PCT {'>'} 10 AND DRAWDOWN_PCT {'<'} -5</code>
          </Typography>
          <Typography variant="body2">
            Momentum / volatility filter:
            {' '}
            <code>MOMENTUM(20, 1d) {'>'} 5 AND VOLATILITY(20, 1d) {'<'} 3</code>
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setScreenerDslHelpOpen(false)}>Close</Button>
        </DialogActions>
	      </Dialog>

	      {/* Old chart-period-only box removed; merged into combined toolbar above */}
      {/* <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 1,
          mb: 1,
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Chart period:
        </Typography>
        <Select
          size="small"
          value={String(chartPeriodDays)}
          onChange={(e) => setChartPeriodDays(Number(e.target.value) || 30)}
        >
          <MenuItem value="30">1M</MenuItem>
          <MenuItem value="90">3M</MenuItem>
          <MenuItem value="180">6M</MenuItem>
          <MenuItem value="365">1Y</MenuItem>
          <MenuItem value="730">2Y</MenuItem>
        </Select>
      </Box> */}

      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
      {symbolCategoryError && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {symbolCategoryError}
        </Typography>
      )}
      {refreshing && !loading && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mb: 1, display: 'block' }}
        >
          Refreshing…
        </Typography>
      )}
      <UniverseGrid
        apiRef={gridApiRef}
        rows={filteredRows}
        columns={columns}
        getRowId={gridGetRowId}
        height="calc(100vh - 260px)"
        loading={loading || refreshing}
        checkboxSelection
        keepNonExistentRowsSelected
        rowSelectionModel={rowSelectionModel}
        onRowSelectionModelChange={handleRowSelectionModelChange}
        density="compact"
        columnVisibilityModel={columnVisibilityModel}
        onColumnVisibilityModelChange={handleColumnVisibilityModelChange}
        disableRowSelectionOnClick
        getRowClassName={gridGetRowClassName}
        sx={gridSx}
        initialState={gridInitialState}
        pageSizeOptions={[25, 50, 100]}
        localeText={gridLocaleText}
      />

      <Dialog open={tradeOpen} onClose={closeTradeDialog} fullWidth maxWidth="lg">
        <DialogTitle
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 2,
          }}
        >
          <span>
            {isBulkTrade
              ? tradeSide === 'BUY'
                ? 'Bulk buy from holdings'
                : 'Bulk sell from holdings'
              : tradeSide === 'BUY'
                ? 'Buy from holdings'
                : 'Sell from holdings'}
          </span>
          <Chip
            size="small"
            variant="outlined"
            label={`Broker: ${
              tradeBrokerName === 'angelone' ? 'AngelOne (SmartAPI)' : 'Zerodha (Kite)'
            }`}
          />
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="subtitle1">
              {isBulkTrade
                ? `${bulkTradeHoldings.length} selected holdings`
                : tradeSymbol}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button
                size="small"
                variant={tradeSide === 'BUY' ? 'contained' : 'outlined'}
                onClick={() => setTradeSide('BUY')}
              >
                BUY
              </Button>
              <Button
                size="small"
                variant={tradeSide === 'SELL' ? 'contained' : 'outlined'}
                color="error"
                onClick={() => setTradeSide('SELL')}
              >
                SELL
              </Button>
            </Box>
          </Box>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', lg: '1fr 320px' },
              gap: 2,
              alignItems: 'start',
            }}
          >
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box
                sx={{
                  display: 'flex',
                  gap: 2,
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <TextField
                  label="Destination broker"
                  select
                  size="small"
                  value={tradeBrokerName}
                  onChange={(e) => {
                    const next = e.target.value === 'angelone' ? 'angelone' : 'zerodha'
                    setTradeBrokerName(next)
                  }}
                  sx={{ minWidth: 220 }}
                  disabled={
                    universeId === 'holdings' || universeId === 'holdings:angelone'
                  }
                  helperText={
                    universeId === 'holdings' || universeId === 'holdings:angelone'
                      ? 'Broker is fixed for holdings universes.'
                      : 'Orders will be created for this broker.'
                  }
                >
                  <MenuItem value="zerodha">Zerodha (Kite)</MenuItem>
                  <MenuItem
                    value="angelone"
                    disabled={angeloneStatusLoaded && !angeloneConnected}
                  >
                    AngelOne (SmartAPI)
                  </MenuItem>
                </TextField>
                <TextField
                  label="Submit mode"
                  select
                  value={tradeExecutionMode}
                  onChange={(e) =>
                    setTradeExecutionMode(e.target.value === 'AUTO' ? 'AUTO' : 'MANUAL')
                  }
                  size="small"
                  sx={{ minWidth: 220 }}
                  helperText={
                    tradeExecutionMode === 'AUTO'
                      ? 'AUTO sends immediately; may skip the waiting queue.'
                      : 'MANUAL adds orders to the waiting queue.'
                  }
                >
                  <MenuItem value="MANUAL">Manual (review in queue)</MenuItem>
                  <MenuItem value="AUTO">Auto (send now)</MenuItem>
                </TextField>
                <FormControlLabel
                  control={
                    <Switch
                      checked={tradeExecutionTarget === 'PAPER'}
                      onChange={(e) =>
                        setTradeExecutionTarget(e.target.checked ? 'PAPER' : 'LIVE')
                      }
                    />
                  }
                  label={`Execution target: ${tradeExecutionTarget}`}
                />
              </Box>

              {!isBulkTrade && tradeHolding && activeGroup?.kind !== 'PORTFOLIO' && (
                <Box
                  sx={{
                    display: 'flex',
                    gap: 2,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                  }}
                >
                  <TextField
                    label="Allocation bucket"
                    select
                    size="small"
                    value={
                      tradePortfolioGroupId != null ? String(tradePortfolioGroupId) : ''
                    }
                    onChange={(e) => {
                      const v = e.target.value
                      setTradePortfolioGroupId(v ? Number(v) : null)
                    }}
                    sx={{ minWidth: 260 }}
                    helperText={
                      tradePortfolioOptions.length > 0
                        ? 'Choose which portfolio (or Unassigned) this trade belongs to.'
                        : tradePortfolioLoading
                          ? 'Loading portfolio allocations…'
                          : 'No portfolios contain this symbol; trade is Unassigned.'
                    }
                  >
                    <MenuItem value="">Unassigned</MenuItem>
                    {tradePortfolioOptions.map((p) => (
                      <MenuItem key={p.group_id} value={String(p.group_id)}>
                        {p.group_name} (alloc {p.reference_qty})
                      </MenuItem>
                    ))}
                  </TextField>
                  {tradePortfolioOptions.length > 0 && (
                    <Typography variant="caption" color="text.secondary">
                      Tip: for portfolio sells, it’s safer to open that portfolio
                      universe and sell there.
                    </Typography>
                  )}
                </Box>
              )}

              {!isBulkTrade && tradeHolding && activeGroup?.kind === 'PORTFOLIO' && (
                <Alert severity="info">
                  This trade is attributed to portfolio: {activeGroup.name}
                </Alert>
              )}
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                  gap: 2,
                  alignItems: 'start',
                }}
              >
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Typography variant="caption" color="text.secondary">
                    Position sizing
                  </Typography>
                  <RadioGroup
                    row
                    value={tradeSizeMode}
                    onChange={(e) => {
                      if (
                        isBulkTrade &&
                        e.target.value === 'PCT_POSITION' &&
                        !bulkSupportsPctPosition
                      ) {
                        return
                      }
                      const mode =
                        e.target.value === 'AMOUNT'
                          ? 'AMOUNT'
                          : e.target.value === 'PCT_POSITION'
                            ? 'PCT_POSITION'
                            : e.target.value === 'PCT_PORTFOLIO'
                              ? 'PCT_PORTFOLIO'
                              : e.target.value === 'RISK'
                                ? 'RISK'
                                : 'QTY'
                      setTradeSizeMode(mode)
                      if (mode === 'QTY') {
                        recalcFromQty(tradeQty)
                      } else if (mode === 'AMOUNT') {
                        recalcFromAmount(tradeAmount, tradeSide)
                      } else if (mode === 'PCT_POSITION') {
                        recalcFromPctEquity(tradePctEquity, tradeSide)
                      } else if (mode === 'PCT_PORTFOLIO') {
                        recalcFromPctPortfolio(tradePctEquity)
                      }
                    }}
                  >
                    <FormControlLabel
                      value="QTY"
                      control={<Radio size="small" />}
                      label="Qty"
                    />
                    <FormControlLabel
                      value="AMOUNT"
                      control={<Radio size="small" />}
                      label="Amount"
                    />
                    <FormControlLabel
                      value="PCT_POSITION"
                      control={<Radio size="small" />}
                      label="% of position"
                      disabled={isBulkTrade && !bulkSupportsPctPosition}
                    />
                    {!isBulkTrade && (
                      <FormControlLabel
                        value="PCT_PORTFOLIO"
                        control={<Radio size="small" />}
                        label="% of portfolio"
                      />
                    )}
                  </RadioGroup>
                  <TextField
                    label={isBulkTrade ? 'Quantity (each)' : 'Quantity'}
                    type={isBulkTrade ? 'text' : 'number'}
                    value={isBulkTrade ? bulkQtySummary : tradeQty}
                    onChange={(e) => {
                      const value = e.target.value
                      if (isBulkTrade) return
                      setTradeSizeMode('QTY')
                      setTradeQty(value)
                      recalcFromQty(value)
                    }}
                    fullWidth
                    size="small"
                    disabled={tradeSizeMode !== 'QTY'}
                    helperText={
                      isBulkTrade && tradeSizeMode === 'QTY' ? (
                        <Box
                          sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: 1,
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            Per-holding quantities. Use Manage to adjust.
                          </Typography>
                          <Button
                            size="small"
                            onClick={() => setBulkQtyDialogOpen(true)}
                          >
                            Manage
                          </Button>
                        </Box>
                      ) : undefined
                    }
                    InputProps={{
                      readOnly: isBulkTrade,
                    }}
                  />
                  {isBulkTrade && tradeSizeMode === 'QTY' && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: -1 }}
                    >
                      Default qty for new selections is {tradeQty || '—'}; update per
                      symbol via Manage.
                    </Typography>
                  )}
                  <TextField
                    label="Amount"
                    type="number"
                    value={
                      isBulkTrade && tradeSizeMode !== 'AMOUNT'
                        ? bulkTotalAmountLabel
                        : tradeAmount
                    }
                    onChange={(e) => {
                      const value = e.target.value
                      setTradeSizeMode('AMOUNT')
                      setTradeAmount(value)
                      if (isBulkTrade) {
                        setBulkAmountBudget(value)
                        setBulkAmountOverrides({})
                        setBulkAmountManual(false)
                      }
                    }}
                    onBlur={() => {
                      if (tradeSizeMode === 'AMOUNT') {
                        if (isBulkTrade) {
                          const budgetRaw =
                            bulkAmountBudget.trim() !== ''
                              ? Number(bulkAmountBudget)
                              : Number(tradeAmount)
                          if (!Number.isFinite(budgetRaw) || budgetRaw <= 0) {
                            setBulkAmountOverrides({})
                            return
                          }
                          const { overrides, usedTotal } =
                            computeAutoBulkAmountOverrides(budgetRaw)
                          setBulkAmountOverrides(overrides)
                          setBulkAmountManual(false)
                          setTradeAmount(
                            usedTotal > 0 && Number.isFinite(usedTotal)
                              ? usedTotal.toFixed(2)
                              : '',
                          )
                        } else {
                          recalcFromAmount(tradeAmount, tradeSide)
                        }
                      }
                    }}
                    fullWidth
                    size="small"
                    disabled={tradeSizeMode !== 'AMOUNT'}
                    inputProps={{ step: amountStep }}
                    helperText={
                      isBulkTrade ? (
                        <Box
                          sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: 1,
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            {tradeSizeMode === 'QTY'
                              ? 'Total notional across selected holdings.'
                              : 'Total notional based on per-holding amounts.'}
                          </Typography>
                          <Button
                            size="small"
                            onClick={() => {
                              if (isBulkTrade && tradeSizeMode === 'AMOUNT') {
                                const hasAny = bulkTradeHoldings.some((h) => {
                                  const v = bulkAmountOverrides[h.symbol]
                                  return v != null && String(v).trim() !== ''
                                })
                                if (!hasAny) {
                                  const budgetRaw =
                                    bulkAmountBudget.trim() !== ''
                                      ? Number(bulkAmountBudget)
                                      : Number(tradeAmount)
                                  if (
                                    Number.isFinite(budgetRaw) &&
                                    budgetRaw > 0 &&
                                    bulkTradeHoldings.length > 0
                                  ) {
                                    const { overrides, usedTotal } =
                                      computeAutoBulkAmountOverrides(budgetRaw)
                                    setBulkAmountOverrides(overrides)
                                    setBulkAmountManual(false)
                                    setTradeAmount(
                                      usedTotal > 0 && Number.isFinite(usedTotal)
                                        ? usedTotal.toFixed(2)
                                        : '',
                                    )
                                  }
                                }
                              }
                              setBulkAmountDialogOpen(true)
                            }}
                            disabled={tradeSizeMode !== 'AMOUNT'}
                          >
                            Manage
                          </Button>
                        </Box>
                      ) : undefined
                    }
                  />
                  {isBulkTrade && tradeSizeMode === 'AMOUNT' && (
                    <FormControlLabel
                      control={
                        <Checkbox
                          size="small"
                          checked={bulkRedistributeRemainder}
                          onChange={(e) =>
                            setBulkRedistributeRemainder(e.target.checked)
                          }
                        />
                      }
                      label="Redistribute unused budget across eligible holdings"
                    />
                  )}
                  <TextField
                    label={
                      tradeSizeMode === 'PCT_PORTFOLIO'
                        ? '% of portfolio'
                        : '% of position'
                    }
                    type={
                      isBulkTrade &&
                      (tradeSizeMode === 'QTY' || tradeSizeMode === 'AMOUNT')
                        ? 'text'
                        : 'number'
                    }
                    value={bulkPctSummary}
                    onChange={(e) => {
                      const value = e.target.value
                      // If we are already in a percent-based mode, keep it;
                      // otherwise default to % of position.
                      const nextMode =
                        tradeSizeMode === 'PCT_PORTFOLIO'
                          ? 'PCT_PORTFOLIO'
                          : 'PCT_POSITION'
                      setTradeSizeMode(nextMode)
                      setTradePctEquity(value)
                    }}
                    onBlur={() => {
                      if (tradeSizeMode === 'PCT_POSITION') {
                        recalcFromPctEquity(tradePctEquity, tradeSide)
                      } else if (tradeSizeMode === 'PCT_PORTFOLIO') {
                        recalcFromPctPortfolio(tradePctEquity)
                      }
                    }}
                    fullWidth
                    size="small"
                    disabled={
                      tradeSizeMode !== 'PCT_POSITION' &&
                      tradeSizeMode !== 'PCT_PORTFOLIO'
                    }
                    inputProps={{
                      step:
                        tradeSizeMode === 'PCT_PORTFOLIO'
                          ? pctStepPortfolio
                          : pctStepPosition,
                    }}
                    helperText={
                      isBulkTrade && tradeSizeMode === 'PCT_POSITION' ? (
                        <Box
                          sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: 1,
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            Requested % of each position. Actual values may differ.
                          </Typography>
                          <Button
                            size="small"
                            onClick={() => setBulkPctDialogOpen(true)}
                          >
                            Manage
                          </Button>
                        </Box>
                      ) : undefined
                    }
                  />
                  {tradeSizeMode === 'RISK' && (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      <Typography variant="caption" color="text.secondary">
                        Risk sizing
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        <TextField
                          label="Risk budget"
                          type="number"
                          value={tradeRiskBudget}
                          onChange={(e) => setTradeRiskBudget(e.target.value)}
                          size="small"
                          sx={{ flex: 1, minWidth: 140 }}
                        />
                        <TextField
                          label="Mode"
                          select
                          size="small"
                          value={tradeRiskBudgetMode}
                          onChange={(e) =>
                            setTradeRiskBudgetMode(
                              e.target.value === 'PORTFOLIO_PCT'
                                ? 'PORTFOLIO_PCT'
                                : 'ABSOLUTE',
                            )
                          }
                          sx={{ width: 180 }}
                        >
                          <MenuItem value="ABSOLUTE">₹ per trade</MenuItem>
                          <MenuItem value="PORTFOLIO_PCT">% of portfolio</MenuItem>
                        </TextField>
                      </Box>
                      <TextField
                        label="Stop price"
                        type="number"
                        value={tradeStopPrice}
                        onChange={(e) => setTradeStopPrice(e.target.value)}
                        size="small"
                      />
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 1,
                        }}
                      >
                        <Typography variant="body2" color="text.secondary">
                          {tradeMaxLoss != null
                            ? `Approx. max loss at stop: ₹${tradeMaxLoss.toFixed(2)}`
                            : 'Max loss will be estimated from entry, stop, and risk.'}
                        </Typography>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => void recalcFromRisk()}
                        >
                          Update from risk
                        </Button>
                      </Box>
                    </Box>
                  )}
                </Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <TextField
                    label="Order type"
                    select
                    value={tradeOrderType}
                    onChange={(e) =>
                      setTradeOrderType(
                        e.target.value as 'MARKET' | 'LIMIT' | 'SL' | 'SL-M',
                      )
                    }
                    fullWidth
                    size="small"
                  >
                    <MenuItem value="MARKET">MARKET</MenuItem>
                    <MenuItem value="LIMIT">LIMIT</MenuItem>
                    <MenuItem value="SL">SL (Stop-loss limit)</MenuItem>
                    <MenuItem value="SL-M">SL-M (Stop-loss market)</MenuItem>
                  </TextField>
                  <TextField
                    label="Price"
                    type={isBulkTrade ? 'text' : 'number'}
                    value={isBulkTrade ? bulkPriceSummary : tradePrice}
                    onChange={
                      isBulkTrade ? undefined : (e) => setTradePrice(e.target.value)
                    }
                    fullWidth
                    size="small"
                    disabled={tradeOrderType === 'MARKET' || tradeOrderType === 'SL-M'}
                    InputProps={{
                      readOnly: isBulkTrade,
                    }}
                    helperText={
                      isBulkTrade ? (
                        <Box
                          sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: 1,
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            Per-holding prices. Use Set prices to adjust.
                          </Typography>
                          <Button
                            size="small"
                            onClick={() => {
                              if (
                                tradeOrderType === 'MARKET' ||
                                tradeOrderType === 'SL-M'
                              ) {
                                return
                              }
                              setBulkPriceDialogOpen(true)
                            }}
                            disabled={
                              tradeOrderType === 'MARKET' || tradeOrderType === 'SL-M'
                            }
                          >
                            Set prices
                          </Button>
                        </Box>
                      ) : undefined
                    }
                  />
                  {(tradeOrderType === 'SL' ||
                    tradeOrderType === 'SL-M' ||
                    tradeGtt) && (
                    <TextField
                      label="Trigger price"
                      type="number"
                      value={tradeTriggerPrice}
                      onChange={(e) => setTradeTriggerPrice(e.target.value)}
                      fullWidth
                      size="small"
                      helperText={
                        tradeOrderType === 'SL' || tradeOrderType === 'SL-M'
                          ? 'Required for SL / SL-M orders.'
                          : 'Optional trigger for GTT orders; defaults to limit price when left blank.'
                      }
                    />
                  )}
                  <TextField
                    label="Product"
                    select
                    value={tradeProduct}
                    onChange={(e) =>
                      setTradeProduct(e.target.value === 'MIS' ? 'MIS' : 'CNC')
                    }
                    fullWidth
                    size="small"
                    helperText="Select MIS for intraday or CNC for delivery."
                  >
                    <MenuItem value="CNC">CNC (Delivery)</MenuItem>
                    <MenuItem value="MIS">MIS (Intraday)</MenuItem>
                  </TextField>
                  {!isBulkTrade && tradeHolding && (
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                      <TextField
                        label="Risk category"
                        select
                        value={tradeRiskCategoryDraft}
                        onChange={(e) =>
                          setTradeRiskCategoryDraft(
                            e.target.value as RiskCategory | '',
                          )
                        }
                        size="small"
                        sx={{ flex: 1, minWidth: 220 }}
                        helperText={
                          tradeSymbolCategoryResolved
                            ? `Saved: ${tradeSymbolCategoryResolved}`
                            : 'Optional (used for drawdown thresholds and risk sizing).'
                        }
                      >
                        <MenuItem value="">
                          <em>Unassigned</em>
                        </MenuItem>
                        <MenuItem value="LC">LC</MenuItem>
                        <MenuItem value="MC">MC</MenuItem>
                        <MenuItem value="SC">SC</MenuItem>
                        <MenuItem value="ETF">ETF</MenuItem>
                      </TextField>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={
                          !tradeRiskCategoryDraft ||
                          tradeSymbolCategoryBusy ||
                          tradeHolding == null
                        }
                        onClick={() => {
                          if (!tradeHolding) return
                          if (!tradeRiskCategoryDraft) return
                          setTradeError(null)
                          void handleSetSymbolCategory(
                            tradeHolding.exchange,
                            tradeHolding.symbol,
                            tradeRiskCategoryDraft as RiskCategory,
                          )
                        }}
                        sx={{ mt: 0.25, minWidth: 120 }}
                      >
                        {tradeSymbolCategoryBusy ? 'Saving…' : 'Save category'}
                      </Button>
                    </Box>
                  )}
                </Box>
              </Box>
              <Accordion variant="outlined" defaultExpanded={false} sx={{ mt: 1 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      width: '100%',
                      gap: 1,
                    }}
                  >
                    <Typography variant="body2">
                      Risk exits (SigmaTrader-managed)
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ marginLeft: 'auto' }}
                    >
                      {getRiskSummaryText()}
                    </Typography>
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  {tradeSide === 'SELL' && tradeProduct !== 'MIS' && (
                    <Typography variant="caption" color="text.secondary">
                      SELL trailing exits are supported only for MIS shorts.
                    </Typography>
                  )}
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={riskSlEnabled}
                        disabled={tradeSide === 'SELL' && tradeProduct !== 'MIS'}
                        onChange={(e) => {
                          const checked = e.target.checked
                          setRiskSlEnabled(checked)
                          if (!checked) {
                            setRiskTrailEnabled(false)
                            setRiskActivationEnabled(false)
                          }
                        }}
                      />
                    }
                    label="Stop-loss"
                  />
                  {riskSlEnabled && (
                    <>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <TextField
                          label="SL mode"
                          select
                          value={riskSlMode}
                          onChange={(e) =>
                            setRiskSlMode(e.target.value as DistanceMode)
                          }
                          size="small"
                          sx={{ flex: 1 }}
                        >
                          <MenuItem value="PCT">%</MenuItem>
                          <MenuItem value="ABS">₹</MenuItem>
                          <MenuItem value="ATR">ATR×</MenuItem>
                        </TextField>
                        <TextField
                          label="SL value"
                          type="number"
                          value={riskSlValue}
                          onChange={(e) => setRiskSlValue(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        />
                      </Box>
                      {riskSlMode === 'ATR' && (
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <TextField
                            label="ATR period"
                            type="number"
                            value={riskSlAtrPeriod}
                            onChange={(e) => setRiskSlAtrPeriod(e.target.value)}
                            size="small"
                            sx={{ flex: 1 }}
                          />
                          <TextField
                            label="ATR tf"
                            select
                            value={riskSlAtrTf}
                            onChange={(e) => setRiskSlAtrTf(e.target.value)}
                            size="small"
                            sx={{ flex: 1 }}
                          >
                            <MenuItem value="1m">1m</MenuItem>
                            <MenuItem value="5m">5m</MenuItem>
                            <MenuItem value="15m">15m</MenuItem>
                            <MenuItem value="30m">30m</MenuItem>
                            <MenuItem value="1h">1h</MenuItem>
                            <MenuItem value="1d">1d</MenuItem>
                          </TextField>
                        </Box>
                      )}
                    </>
                  )}

                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={riskTrailEnabled}
                        disabled={
                          !riskSlEnabled ||
                          (tradeSide === 'SELL' && tradeProduct !== 'MIS')
                        }
                        onChange={(e) => {
                          const checked = e.target.checked
                          setRiskTrailEnabled(checked)
                          if (checked) {
                            setRiskSlEnabled(true)
                          } else {
                            setRiskActivationEnabled(false)
                          }
                        }}
                      />
                    }
                    label="Trailing stop-loss"
                  />
                  {riskTrailEnabled && (
                    <>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <TextField
                          label="Trail mode"
                          select
                          value={riskTrailMode}
                          onChange={(e) =>
                            setRiskTrailMode(e.target.value as DistanceMode)
                          }
                          size="small"
                          sx={{ flex: 1 }}
                        >
                          <MenuItem value="PCT">%</MenuItem>
                          <MenuItem value="ABS">₹</MenuItem>
                          <MenuItem value="ATR">ATR×</MenuItem>
                        </TextField>
                        <TextField
                          label="Trail value"
                          type="number"
                          value={riskTrailValue}
                          onChange={(e) => setRiskTrailValue(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        />
                      </Box>
                      {riskTrailMode === 'ATR' && (
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <TextField
                            label="ATR period"
                            type="number"
                            value={riskTrailAtrPeriod}
                            onChange={(e) => setRiskTrailAtrPeriod(e.target.value)}
                            size="small"
                            sx={{ flex: 1 }}
                          />
                          <TextField
                            label="ATR tf"
                            select
                            value={riskTrailAtrTf}
                            onChange={(e) => setRiskTrailAtrTf(e.target.value)}
                            size="small"
                            sx={{ flex: 1 }}
                          >
                            <MenuItem value="1m">1m</MenuItem>
                            <MenuItem value="5m">5m</MenuItem>
                            <MenuItem value="15m">15m</MenuItem>
                            <MenuItem value="30m">30m</MenuItem>
                            <MenuItem value="1h">1h</MenuItem>
                            <MenuItem value="1d">1d</MenuItem>
                          </TextField>
                        </Box>
                      )}
                    </>
                  )}

                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={riskActivationEnabled}
                        disabled={
                          !riskTrailEnabled ||
                          (tradeSide === 'SELL' && tradeProduct !== 'MIS')
                        }
                        onChange={(e) => {
                          const checked = e.target.checked
                          setRiskActivationEnabled(checked)
                          if (checked) {
                            setRiskSlEnabled(true)
                            setRiskTrailEnabled(true)
                          }
                        }}
                      />
                    }
                    label="Trailing profit activation"
                  />
                  {riskActivationEnabled && (
                    <>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <TextField
                          label="Activation mode"
                          select
                          value={riskActivationMode}
                          onChange={(e) =>
                            setRiskActivationMode(e.target.value as DistanceMode)
                          }
                          size="small"
                          sx={{ flex: 1 }}
                        >
                          <MenuItem value="PCT">%</MenuItem>
                          <MenuItem value="ABS">₹</MenuItem>
                          <MenuItem value="ATR">ATR×</MenuItem>
                        </TextField>
                        <TextField
                          label="Activation value"
                          type="number"
                          value={riskActivationValue}
                          onChange={(e) => setRiskActivationValue(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        />
                      </Box>
                      {riskActivationMode === 'ATR' && (
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <TextField
                            label="ATR period"
                            type="number"
                            value={riskActivationAtrPeriod}
                            onChange={(e) => setRiskActivationAtrPeriod(e.target.value)}
                            size="small"
                            sx={{ flex: 1 }}
                          />
                          <TextField
                            label="ATR tf"
                            select
                            value={riskActivationAtrTf}
                            onChange={(e) => setRiskActivationAtrTf(e.target.value)}
                            size="small"
                            sx={{ flex: 1 }}
                          >
                            <MenuItem value="1m">1m</MenuItem>
                            <MenuItem value="5m">5m</MenuItem>
                            <MenuItem value="15m">15m</MenuItem>
                            <MenuItem value="30m">30m</MenuItem>
                            <MenuItem value="1h">1h</MenuItem>
                            <MenuItem value="1d">1d</MenuItem>
                          </TextField>
                        </Box>
                      )}
                    </>
                  )}
                </AccordionDetails>
              </Accordion>
              <Box
                sx={{
                  mt: 1,
                  p: 1,
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1,
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  Bracket / follow-up conditional
                </Typography>
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={tradeBracketEnabled}
                      onChange={(e) => {
                        const checked = e.target.checked
                        setTradeBracketEnabled(checked)
                        if (checked) {
                          // When enabling for the first time, pre-fill MTP.
                          if (!tradeMtpPct) {
                            let defaultMtp = BRACKET_BASE_MTP_DEFAULT
                            if (
                              tradeSide === 'SELL' &&
                              tradeHolding?.today_pnl_percent != null
                            ) {
                              const today = Number(tradeHolding.today_pnl_percent)
                              if (Number.isFinite(today) && today > 0) {
                                // Only mirror today's appreciation when it is
                                // meaningfully above noise; clamp to a
                                // reasonable swing range so re-entry levels
                                // stay realistic.
                                if (today >= BRACKET_APPRECIATION_THRESHOLD) {
                                  const clamped = Math.max(
                                    BRACKET_MTP_MIN,
                                    Math.min(today, BRACKET_MTP_MAX),
                                  )
                                  defaultMtp = Number(clamped.toFixed(2))
                                }
                              }
                            }
                            setTradeMtpPct(String(defaultMtp))
                          }
                        }
                      }}
                    />
                  }
                  label={(() => {
                    const isAngelOne = tradeBrokerName === 'angelone'
                    const suffix = isAngelOne ? 'conditional' : 'GTT'
                    return tradeSide === 'BUY'
                      ? `Add profit-target SELL ${suffix}`
                      : `Add re-entry BUY ${suffix}`
                  })()}
                />
                {tradeBracketEnabled && (
                  <>
                    <TextField
                      label="Min target profit (MTP) %"
                      type="number"
                      value={tradeMtpPct}
                      onChange={(e) => setTradeMtpPct(e.target.value)}
                      size="small"
                      fullWidth
                    />
                    <Typography variant="caption" color="text.secondary">
                      {(() => {
                        const p = getBracketPreviewPrice()
                        if (p == null) {
                          return 'Follow-up order price will be shown here when price and MTP are valid.'
                        }
                        const base = getEffectivePrimaryPrice()
                        const sideLabel = (() => {
                          const isAngelOne = tradeBrokerName === 'angelone'
                          const suffix = isAngelOne ? 'conditional' : 'GTT'
                          return tradeSide === 'BUY'
                            ? `SELL ${suffix} target`
                            : `BUY ${suffix} re-entry`
                        })()
                        if (base != null && base > 0) {
                          const eff = (p / base - 1) * 100
                          return `${sideLabel}: ₹${p.toFixed(2)} (≈ ${eff.toFixed(2)}% from primary price).`
                        }
                        return `${sideLabel}: ₹${p.toFixed(2)}.`
                      })()}
                    </Typography>
                  </>
                )}
              </Box>
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={tradeGtt}
                    onChange={(e) => {
                      setTradeGtt(e.target.checked)
                    }}
                  />
                }
                label={
                  tradeBrokerName === 'angelone'
                    ? 'Conditional order (SigmaTrader-managed)'
                    : 'GTT (good-till-triggered) order'
                }
              />
              {tradeError && (
                <Typography variant="body2" color="error">
                  {tradeError}
                </Typography>
              )}
            </Box>
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                borderRadius: 2,
                position: { lg: 'sticky', xs: 'static' },
                top: 8,
                alignSelf: 'start',
              }}
            >
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Summary
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                <Typography variant="body2">
                  {isBulkTrade
                    ? `${bulkTradeHoldings.length} holdings`
                    : `Symbol: ${tradeSymbol}`}
                </Typography>
                <Typography variant="body2">
                  {tradeSide} • {tradeProduct}
                </Typography>
                <Typography variant="body2">
                  {tradeBrokerName === 'angelone' ? 'AngelOne' : 'Zerodha'} •{' '}
                  {tradeExecutionMode} • {tradeExecutionTarget}
                </Typography>
                <Divider sx={{ my: 0.5 }} />
                <Typography variant="body2">Order: {tradeOrderType}</Typography>
                <Typography variant="body2">
                  Notional: {bulkTotalAmountLabel ? `₹${bulkTotalAmountLabel}` : '-'}
                </Typography>
                <Typography variant="body2">
                  Risk exits: {getRiskSummaryText()}
                </Typography>
                {tradeBracketEnabled && (
                  <Typography variant="body2">
                    {(() => {
                      const p = getBracketPreviewPrice()
                      const label = tradeMtpPct ? `${tradeMtpPct}%` : 'On'
                      return p == null
                        ? `Bracket: ${label}`
                        : `Bracket: ${label} • ₹${p.toFixed(2)}`
                    })()}
                  </Typography>
                )}
                {tradeGtt && (
                  <Typography variant="body2">
                    Conditional: {tradeBrokerName === 'angelone' ? 'Sigma' : 'GTT'}
                  </Typography>
                )}
              </Box>
            </Paper>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeTradeDialog} disabled={tradeSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmitTrade}
            disabled={tradeSubmitting}
            variant="contained"
          >
            {tradeSubmitting
              ? tradeSubmitProgress
                ? `Submitting… (${tradeSubmitProgress.done}/${tradeSubmitProgress.total})`
                : 'Submitting…'
              : isBulkTrade
                ? 'Create orders'
                : 'Create order'}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={groupCreateOpen}
        onClose={() => {
          if (groupCreateSubmitting) return
          setGroupCreateOpen(false)
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Group selected symbols</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Create a new group from the selected holdings or add them to an existing
            group.
          </Typography>
          <Tabs
            value={groupSelectionMode}
            onChange={(_e, value) => {
              if (groupCreateSubmitting) return
              setGroupSelectionMode(value as 'create' | 'add')
              setGroupCreateError(null)
              setGroupCreateInfo(null)
            }}
            sx={{ mb: 2 }}
          >
            <Tab value="create" label="Create new" />
            <Tab value="add" label="Add to existing" />
          </Tabs>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {groupSelectionMode === 'create' ? (
              <>
                <TextField
                  label="Group name"
                  value={groupCreateName}
                  onChange={(e) => setGroupCreateName(e.target.value)}
                  size="small"
                  autoFocus
                  fullWidth
                />
                <TextField
                  label="Kind"
                  select
                  value={groupCreateKind}
                  onChange={(e) => setGroupCreateKind(e.target.value as GroupKind)}
                  size="small"
                  fullWidth
                >
                  <MenuItem value="WATCHLIST">Watchlist</MenuItem>
                  <MenuItem value="MODEL_PORTFOLIO">Basket</MenuItem>
                  <MenuItem value="PORTFOLIO">Portfolio</MenuItem>
                  <MenuItem value="HOLDINGS_VIEW">Holdings view</MenuItem>
                </TextField>
                {(groupCreateKind === 'MODEL_PORTFOLIO' ||
                  groupCreateKind === 'PORTFOLIO') && (
                  <Typography variant="caption" color="text.secondary">
                    For portfolio/basket groups, new members will be added with
                    reference qty and reference price from current holdings.
                  </Typography>
                )}
              </>
            ) : (
              <>
                <TextField
                  label="Target group"
                  select
                  value={groupTargetId}
                  onChange={(e) => setGroupTargetId(String(e.target.value))}
                  size="small"
                  fullWidth
                >
                  <MenuItem value="">Select a group…</MenuItem>
                  {availableGroups
                    .filter((g) => g.kind !== 'HOLDINGS_VIEW')
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map((g) => (
                      <MenuItem key={g.id} value={String(g.id)}>
                        {g.name} (
                        {g.kind === 'MODEL_PORTFOLIO'
                          ? 'Basket'
                          : g.kind === 'PORTFOLIO'
                            ? 'Portfolio'
                            : 'Watchlist'}
                        )
                      </MenuItem>
                    ))}
                </TextField>
                <Typography variant="caption" color="text.secondary">
                  Existing members are skipped automatically to avoid errors.
                </Typography>
              </>
            )}
            {groupCreateError && (
              <Typography variant="body2" color="error">
                {groupCreateError}
              </Typography>
            )}
            {groupCreateInfo && (
              <Typography variant="body2" color="success.main">
                {groupCreateInfo}
              </Typography>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setGroupCreateOpen(false)}
            disabled={groupCreateSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={() =>
              void (groupSelectionMode === 'create'
                ? createGroupFromSelection()
                : addSelectionToExistingGroup())
            }
            disabled={groupCreateSubmitting}
            variant="contained"
          >
            {groupCreateSubmitting
              ? groupSelectionMode === 'create'
                ? 'Creating…'
                : 'Adding…'
              : groupSelectionMode === 'create'
                ? 'Create group'
                : 'Add to group'}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={bulkPriceDialogOpen}
        onClose={() => setBulkPriceDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Set prices for selected holdings</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {bulkTradeHoldings.map((h) => {
              const ltp = getDisplayPrice(h)
              const baseLabel =
                ltp != null && Number.isFinite(ltp) && ltp > 0 ? ltp.toFixed(2) : '-'
              const overrideRaw = bulkPriceOverrides[h.symbol]
              const override =
                overrideRaw != null && overrideRaw !== ''
                  ? overrideRaw
                  : baseLabel !== '-'
                    ? baseLabel
                    : ''
              return (
                <Box
                  key={h.symbol}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    flexWrap: 'wrap',
                  }}
                >
                  <Typography sx={{ minWidth: 100 }}>{h.symbol}</Typography>
                  <TextField
                    label="Current"
                    value={baseLabel}
                    size="small"
                    sx={{ width: 120 }}
                    InputProps={{ readOnly: true }}
                  />
                  <TextField
                    label="Price"
                    type="number"
                    size="small"
                    value={override}
                    onChange={(e) =>
                      setBulkPriceOverrides((prev) => ({
                        ...prev,
                        [h.symbol]: e.target.value,
                      }))
                    }
                    sx={{ width: 140 }}
                  />
                </Box>
              )
            })}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkPriceDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={bulkQtyDialogOpen}
        onClose={() => setBulkQtyDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Manage per-holding quantities</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                flexWrap: 'wrap',
                justifyContent: 'space-between',
              }}
            >
              <Typography variant="body2" color="text.secondary">
                Set quantities per symbol. Use 0 to skip a symbol.
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField
                  label="Default qty"
                  type="number"
                  size="small"
                  value={tradeQty}
                  onChange={(e) => {
                    const v = e.target.value
                    setTradeQty(v)
                  }}
                  sx={{ width: 140 }}
                  inputProps={{ min: 0, step: 1 }}
                />
                <Button
                  size="small"
                  onClick={() => {
                    const defaultQty = Math.floor(Number(tradeQty))
                    const base =
                      Number.isFinite(defaultQty) && defaultQty > 0 ? defaultQty : 1
                    const next: Record<string, string> = {}
                    for (const h of bulkTradeHoldings) {
                      let qty = base
                      if (clampSellToHoldingsQtyEffective && h.quantity != null) {
                        const maxQty = Math.floor(Number(h.quantity))
                        if (Number.isFinite(maxQty)) {
                          qty = maxQty <= 0 ? 0 : Math.min(qty, maxQty)
                        }
                      }
                      next[h.symbol] = String(qty)
                    }
                    setBulkQtyOverrides(next)
                  }}
                >
                  Apply to all
                </Button>
              </Box>
            </Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
              {bulkTradeHoldings.map((h) => {
                const stored = bulkQtyOverrides[h.symbol]
                const fallback = String(getDefaultBulkQtyForHolding(h))
                const displayValue = stored != null ? stored : fallback
                return (
                  <Box
                    key={h.symbol}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      flexWrap: 'wrap',
                    }}
                  >
                    <Typography sx={{ minWidth: 100 }}>{h.symbol}</Typography>
                    <TextField
                      label="Qty"
                      type="number"
                      size="small"
                      value={displayValue}
                      onChange={(e) => {
                        const value = e.target.value
                        setBulkQtyOverrides((prev) => ({
                          ...prev,
                          [h.symbol]: value,
                        }))
                      }}
                      onBlur={(e) => {
                        const rawText = e.target.value
                        const raw = Number(rawText)
                        let nextQty: number
                        if (rawText.trim() === '') {
                          nextQty = getDefaultBulkQtyForHolding(h)
                        } else if (!Number.isFinite(raw)) {
                          nextQty = getDefaultBulkQtyForHolding(h)
                        } else {
                          nextQty = Math.floor(raw)
                          if (!Number.isFinite(nextQty) || nextQty < 0) nextQty = 0
                          if (clampSellToHoldingsQtyEffective && h.quantity != null) {
                            const maxQty = Math.floor(Number(h.quantity))
                            if (Number.isFinite(maxQty)) {
                              nextQty = maxQty <= 0 ? 0 : Math.min(nextQty, maxQty)
                            }
                          }
                        }
                        setBulkQtyOverrides((prev) => ({
                          ...prev,
                          [h.symbol]: String(nextQty),
                        }))
                      }}
                      sx={{ width: 140 }}
                      inputProps={{ min: 0, step: 1 }}
                    />
                  </Box>
                )
              })}
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkQtyDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={bulkAmountDialogOpen}
        onClose={() => setBulkAmountDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Manage per-holding amounts</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {bulkTradeHoldings.map((h) => {
              const stored = bulkAmountOverrides[h.symbol]
              const effectiveAmount = stored == null ? '0.00' : stored
              return (
                <Box
                  key={h.symbol}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    flexWrap: 'wrap',
                  }}
                >
                  <Typography sx={{ minWidth: 100 }}>{h.symbol}</Typography>
                  <TextField
                    label="Amount"
                    type="number"
                    size="small"
                    value={effectiveAmount}
                    onChange={(e) => {
                      const value = e.target.value
                      setBulkAmountManual(true)
                      setBulkAmountOverrides((prev) => ({
                        ...prev,
                        [h.symbol]: value,
                      }))
                    }}
                    onBlur={(e) => {
                      const raw = Number(e.target.value)
                      const price = getPerHoldingPriceForSizing(h)
                      if (
                        !price ||
                        !Number.isFinite(price) ||
                        price <= 0 ||
                        !Number.isFinite(raw) ||
                        raw <= 0
                      ) {
                        setBulkAmountOverrides((prev) => {
                          const next = { ...prev, [h.symbol]: '0.00' }
                          const used = computeUsedTotalFromAmountOverrides(next)
                          setTradeAmount(
                            used > 0 && Number.isFinite(used) ? used.toFixed(2) : '',
                          )
                          return next
                        })
                        return
                      }
                      const qty = Math.floor(raw / price)
                      const normalised = qty > 0 ? qty * price : 0
                      setBulkAmountOverrides((prev) => {
                        const nextValue =
                          normalised > 0 && Number.isFinite(normalised)
                            ? normalised.toFixed(2)
                            : '0.00'
                        const next = { ...prev, [h.symbol]: nextValue }
                        const used = computeUsedTotalFromAmountOverrides(next)
                        setTradeAmount(
                          used > 0 && Number.isFinite(used) ? used.toFixed(2) : '',
                        )
                        return next
                      })
                    }}
                    sx={{ width: 160 }}
                  />
                </Box>
              )
            })}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkAmountDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={bulkPctDialogOpen}
        onClose={() => setBulkPctDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>% of position per holding</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            These values show the approximate % of each position that will be traded
            based on your current sizing inputs.
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {bulkTradeHoldings.map((h) => {
              const pct = getEffectivePctOfPositionForHolding(h)
              return (
                <Box
                  key={h.symbol}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    flexWrap: 'wrap',
                  }}
                >
                  <Typography sx={{ minWidth: 120 }}>{h.symbol}</Typography>
                  <TextField
                    label="% of position"
                    size="small"
                    value={pct != null && Number.isFinite(pct) ? pct.toFixed(2) : '-'}
                    InputProps={{ readOnly: true }}
                    sx={{ width: 140 }}
                  />
                </Box>
              )
            })}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkPctDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

/*
Legacy per-symbol indicator-rule alerts (pre v3) removed in Phase 1 cutover.
Kept temporarily for reference; guarded from compilation.

type IndicatorAlertDialogProps = {
  open: boolean
  onClose: () => void
  symbol: string | null
  exchange: string | null
  universeId: string
  universeLabel: string
  selectedSymbols: string[]
  symbolExchanges: Record<string, string>
}

function IndicatorAlertDialog({
  open,
  onClose,
  symbol,
  exchange,
  universeId,
  universeLabel,
  selectedSymbols,
  symbolExchanges,
}: IndicatorAlertDialogProps) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rules, setRules] = useState<IndicatorRule[]>([])
  const [error, setError] = useState<string | null>(null)

  const [indicator, setIndicator] = useState<IndicatorType>('PRICE')
  const [operator, setOperator] = useState<OperatorType>('CROSS_ABOVE')
  const [timeframe, setTimeframe] = useState<string>('1d')
  const [triggerMode, setTriggerMode] =
    useState<TriggerMode>('ONCE_PER_BAR')
  const [actionType, setActionType] =
    useState<ActionType>('ALERT_ONLY')
  const [threshold1, setThreshold1] = useState<string>('80')
  const [threshold2, setThreshold2] = useState<string>('')
  const [period, setPeriod] = useState<string>('14')
  const [actionValue, setActionValue] = useState<string>('10')

  const [preview, setPreview] = useState<IndicatorPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const [templates, setTemplates] = useState<Strategy[]>([])
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(
    null,
  )
  const [savingTemplate, setSavingTemplate] = useState(false)

  type AlertRuleMode = 'metric' | 'simple' | 'dsl'
  type MetricField =
    | 'TODAY_PNL_PCT'
    | 'PNL_PCT'
    | 'MAX_PNL_PCT'
    | 'DRAWDOWN_PCT'
    | 'INVESTED'
    | 'CURRENT_VALUE'
    | 'QTY'
    | 'AVG_PRICE'

  type MetricOperator = 'GT' | 'GTE' | 'LT' | 'LTE' | 'EQ' | 'NEQ'

  const METRIC_FIELD_OPTIONS: { value: MetricField; label: string }[] = [
    { value: 'TODAY_PNL_PCT', label: 'Today PnL %' },
    { value: 'PNL_PCT', label: 'PnL % (total)' },
    { value: 'MAX_PNL_PCT', label: 'Max PnL % (since buy)' },
    { value: 'DRAWDOWN_PCT', label: 'Drawdown from peak %' },
    { value: 'INVESTED', label: 'Invested (₹)' },
    { value: 'CURRENT_VALUE', label: 'Current value (₹)' },
    { value: 'QTY', label: 'Quantity' },
    { value: 'AVG_PRICE', label: 'Avg price' },
  ]

  const METRIC_OPERATOR_OPTIONS: { value: MetricOperator; label: string }[] = [
    { value: 'GT', label: '>' },
    { value: 'GTE', label: '>=' },
    { value: 'LT', label: '<' },
    { value: 'LTE', label: '<=' },
    { value: 'EQ', label: '==' },
    { value: 'NEQ', label: '!=' },
  ]

  const [mode, setMode] = useState<AlertRuleMode>('metric')
  const [dslExpression, setDslExpression] = useState<string>('')
  const [dslHelpOpen, setDslHelpOpen] = useState(false)
  const [applyScope, setApplyScope] = useState<
    'symbol' | 'selected' | 'universe' | 'holdings'
  >('symbol')

  const [metricField, setMetricField] =
    useState<MetricField>('TODAY_PNL_PCT')
  const [metricOperator, setMetricOperator] =
    useState<MetricOperator>('GT')
  const [metricValue, setMetricValue] = useState<string>('5')

  const metricDsl = (): string => {
    const op =
      metricOperator === 'GT'
        ? '>'
        : metricOperator === 'GTE'
          ? '>='
          : metricOperator === 'LT'
            ? '<'
            : metricOperator === 'LTE'
              ? '<='
              : metricOperator === 'EQ'
                ? '=='
                : '!='
    const valueNum = Number(metricValue || '0')
    const safeValue = Number.isFinite(valueNum) ? valueNum : 0
    return `${metricField} ${op} ${safeValue}`
  }

  const selectedTemplate = selectedStrategyId
    ? templates.find((t) => t.id === selectedStrategyId) ?? null
    : null

  const handleDeleteStrategyTemplate = async () => {
    if (!selectedTemplate) return
    const ok = window.confirm(
      `Delete strategy "${selectedTemplate.name}"? This cannot be undone.`,
    )
    if (!ok) return
    try {
      await deleteStrategy(selectedTemplate.id)
      setTemplates((prev) => prev.filter((t) => t.id !== selectedTemplate.id))
      setSelectedStrategyId(null)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to delete strategy',
      )
    }
  }

  const handleDslEditorMount: OnMount = (editor, monaco) => {
    ensureSigmaDsl(monaco)

    const model = editor.getModel()
    if (model) {
      monaco.editor.setModelLanguage(model, SIGMA_DSL_LANGUAGE_ID)
    }

    configureSigmaDslEditor(editor)
  }

  const buildSimpleDsl = (): string => {
    const timeframeLabel = timeframe
    const periodNum = Number(period) || (indicator === 'RSI' ? 14 : 20)
    const indicatorPart =
      indicator === 'PRICE'
        ? `PRICE(${timeframeLabel})`
        : `${indicator}(${periodNum}, ${timeframeLabel})`

    const operatorLabel =
      operator === 'GT'
        ? '>'
        : operator === 'LT'
          ? '<'
          : operator === 'CROSS_ABOVE'
            ? 'CROSS_ABOVE'
            : operator === 'CROSS_BELOW'
              ? 'CROSS_BELOW'
              : operator === 'BETWEEN'
                ? 'BETWEEN'
                : operator === 'OUTSIDE'
                  ? 'OUTSIDE'
                  : operator === 'MOVE_UP_PCT'
                    ? 'MOVE_UP_PCT'
                    : 'MOVE_DOWN_PCT'

    const t1 = Number(threshold1 || '0')
    let dsl = `${indicatorPart} ${operatorLabel} ${t1}`
    if (operator === 'BETWEEN' || operator === 'OUTSIDE') {
      const t2 = Number(threshold2 || '0')
      dsl = `${indicatorPart} ${operatorLabel} ${t1} ${t2}`
    }
    return dsl
  }

  useEffect(() => {
    if (!open || !symbol) {
      return
    }
    let active = true
    const loadRules = async () => {
      try {
        setLoading(true)
        const data = await listIndicatorRules(symbol)
        if (!active) return
        setRules(data)
        setError(null)
      } catch (err) {
        if (!active) return
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load indicator alerts',
        )
      } finally {
        if (active) setLoading(false)
      }
    }
    void loadRules()
    return () => {
      active = false
    }
  }, [open, symbol])

  useEffect(() => {
    if (!open || !symbol) {
      return
    }
    let active = true
    const loadTemplates = async () => {
      try {
        const data = await listStrategyTemplates(symbol)
        if (!active) return
        setTemplates(data)
      } catch {
        if (!active) return
        // Templates are a convenience; we silently ignore failures here.
        setTemplates([])
      }
    }
    void loadTemplates()
    return () => {
      active = false
    }
  }, [open, symbol])

  useEffect(() => {
    if (!selectedStrategyId) return
    const tpl = templates.find((t) => t.id === selectedStrategyId)
    if (tpl?.dsl_expression) {
      // When a template with a DSL expression is selected, switch the
      // dialog into DSL mode and load the strategy expression so that
      // the alert actually follows the strategy logic instead of the
      // simple builder defaults.
      setMode('dsl')
      setDslExpression(tpl.dsl_expression)
    }
  }, [selectedStrategyId, templates])

  useEffect(() => {
    if (!open || !symbol) {
      return
    }
    let active = true

    const loadPreview = async () => {
      try {
        setPreviewLoading(true)
        setPreviewError(null)

        const numericPeriod = Number(period) || undefined
        const params: {
          period?: number
          window?: number
        } = {}

        if (indicator === 'RSI' || indicator === 'MA' || indicator === 'ATR') {
          if (numericPeriod != null) params.period = numericPeriod
        } else if (
          indicator === 'VOLATILITY' ||
          indicator === 'PERF_PCT' ||
          indicator === 'VOLUME_RATIO' ||
          indicator === 'PVT_SLOPE'
        ) {
          if (numericPeriod != null) params.window = numericPeriod
        }

        const data = await fetchIndicatorPreview({
          symbol,
          exchange: exchange ?? 'NSE',
          timeframe,
          indicator,
          ...params,
        })
        if (!active) return
        setPreview(data)
      } catch (err) {
        if (!active) return
        setPreview(null)
        setPreviewError(
          err instanceof Error ? err.message : 'Failed to load indicator value',
        )
      } finally {
        if (active) setPreviewLoading(false)
      }
    }

    void loadPreview()

    return () => {
      active = false
    }
  }, [open, symbol, exchange, timeframe, indicator, period, mode])

  const resetForm = () => {
    setIndicator('PRICE')
    setOperator('CROSS_ABOVE')
    setTimeframe('1m')
    setTriggerMode('ONCE_PER_BAR')
    setActionType('ALERT_ONLY')
    setThreshold1('')
    setThreshold2('')
    setPeriod('14')
    setActionValue('10')
    setError(null)
    setSelectedStrategyId(null)
    setMode('metric')
    setDslExpression('')
    setApplyScope('symbol')
    setMetricField('TODAY_PNL_PCT')
    setMetricOperator('GT')
    setMetricValue('5')
  }

  const handleClose = () => {
    if (saving) return
    resetForm()
    onClose()
  }

  const handleCreate = async () => {
    if (applyScope === 'symbol' && !symbol) return

    const buildActionParams = (): Record<string, unknown> => {
      const actionParams: Record<string, unknown> = {}
      if (actionType === 'SELL_PERCENT') {
        const v = Number(actionValue)
        if (!Number.isFinite(v) || v <= 0) {
          throw new Error('Percent must be a positive number.')
        }
        actionParams.percent = v
      } else if (actionType === 'BUY_QUANTITY') {
        const v = Number(actionValue)
        if (!Number.isFinite(v) || v <= 0) {
          throw new Error('Quantity must be a positive number.')
        }
        actionParams.quantity = v
      }
      return actionParams
    }

    const actionParams: Record<string, unknown> = {}
    try {
      Object.assign(actionParams, buildActionParams())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid action settings.')
      return
    }

    let conditions: IndicatorCondition[] = []
    let dslExprToSend: string | undefined

    if (mode !== 'simple') {
      const expr =
        mode === 'metric' ? metricDsl().trim() : dslExpression.trim()
      if (!expr) {
        setError('Expression cannot be empty.')
        return
      }
      dslExprToSend = expr
      // Provide a minimal placeholder condition; evaluation for DSL-backed
      // rules uses expression_json instead of conditions_json.
      conditions = [
        {
          indicator: 'PRICE',
          operator: 'GT',
          threshold_1: 0,
          params: {},
        },
      ]
    } else {
      const t1 = Number(threshold1)
      if (!Number.isFinite(t1)) {
        setError('Primary threshold must be a number.')
        return
      }

      let t2: number | null = null
      if (operator === 'BETWEEN' || operator === 'OUTSIDE') {
        if (!threshold2.trim()) {
          setError('Second threshold is required for range operators.')
          return
        }
        t2 = Number(threshold2)
        if (!Number.isFinite(t2)) {
          setError('Second threshold must be a number.')
          return
        }
      }

      const periodNum =
        Number(period) || (indicator === 'RSI' ? 14 : 20)

      const cond: IndicatorCondition = {
        indicator,
        operator,
        threshold_1: t1,
        threshold_2: t2,
        params: {},
      }

      if (indicator === 'RSI' || indicator === 'MA' || indicator === 'ATR') {
        cond.params = { period: periodNum }
      } else if (
        indicator === 'VOLATILITY' ||
        indicator === 'PERF_PCT' ||
        indicator === 'VOLUME_RATIO'
      ) {
        cond.params = { window: periodNum }
      }

      conditions = [cond]
    }

    const payloadBase = {
      strategy_id: selectedStrategyId ?? undefined,
      timeframe,
      logic: 'AND' as const,
      conditions,
      dsl_expression: dslExprToSend,
      trigger_mode: triggerMode,
      action_type: actionType,
      action_params: actionParams,
      enabled: true,
    }

    setSaving(true)
    try {
      if (applyScope === 'selected') {
        const targets = selectedSymbols
          .map((s) => s.trim())
          .filter(Boolean)
        if (targets.length === 0) {
          setError('No rows are selected.')
          return
        }
        for (const sym of targets) {
          await createIndicatorRule({
            ...payloadBase,
            symbol: sym,
            exchange: symbolExchanges[sym] ?? 'NSE',
          })
        }
      } else if (applyScope === 'holdings') {
        await createIndicatorRule({
          ...payloadBase,
          universe: 'HOLDINGS',
        })
      } else if (applyScope === 'universe') {
        if (universeId.startsWith('group:')) {
          const groupIdRaw = universeId.slice('group:'.length)
          await createIndicatorRule({
            ...payloadBase,
            target_type: 'GROUP',
            target_id: groupIdRaw,
          })
        } else {
          await createIndicatorRule({
            ...payloadBase,
            universe: 'HOLDINGS',
          })
        }
      } else {
        const created = await createIndicatorRule({
          ...payloadBase,
          symbol: symbol ?? undefined,
          exchange: exchange ?? 'NSE',
        })
        setRules((prev) => [created, ...prev])
      }
      resetForm()
      onClose()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to create indicator alert',
      )
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAsStrategy = async () => {
    if (!symbol) return

    const name = window.prompt(
      'Enter a name for this strategy template:',
      `${symbol}-indicator-alert`,
    )
    if (!name) return

    const dsl =
      mode === 'metric'
        ? metricDsl()
        : mode === 'dsl'
          ? dslExpression.trim() || buildSimpleDsl()
          : buildSimpleDsl()

    setSavingTemplate(true)
    try {
      const created = await createStrategyTemplate({
        name,
        description: `Template created from holdings alert for ${symbol}`,
        execution_mode: 'MANUAL',
        execution_target: 'LIVE',
        enabled: true,
        scope: 'GLOBAL',
        dsl_expression: dsl,
      })
      setTemplates((prev) => [...prev, created])
      setSelectedStrategyId(created.id)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to save strategy template',
      )
    } finally {
      setSavingTemplate(false)
    }
  }

  const handleDeleteRule = async (rule: IndicatorRule) => {
    try {
      await deleteIndicatorRule(rule.id)
      setRules((prev) => prev.filter((r) => r.id !== rule.id))
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to delete indicator alert',
      )
    }
  }

  const showThreshold2 = operator === 'BETWEEN' || operator === 'OUTSIDE'
  const actionValueLabel: string | null =
    actionType === 'SELL_PERCENT'
      ? 'Sell % of quantity'
      : actionType === 'BUY_QUANTITY'
        ? 'Buy quantity'
        : null

  const formatPreviewValue = (): string => {
    if (!preview || preview.value == null) return '—'
    const v = preview.value
    if (indicator === 'PRICE' || indicator === 'MA') {
      return v.toFixed(2)
    }
    if (
      indicator === 'RSI' ||
      indicator === 'PERF_PCT' ||
      indicator === 'VOLATILITY' ||
      indicator === 'ATR' ||
      indicator === 'PVT_SLOPE'
    ) {
      return v.toFixed(2)
    }
    if (indicator === 'VOLUME_RATIO') {
      return `${v.toFixed(2)}x`
    }
    return v.toFixed(2)
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
      <DialogTitle>Create alert rule</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          {symbol ?? '--'} {exchange ? ` / ${exchange}` : ''}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Apply rules to a single symbol, selected rows, or an entire universe (group).
        </Typography>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            mb: 1,
          }}
        >
          <Tabs
            value={mode}
            onChange={(_event, value) => {
              if (value === 'dsl') {
                setDslExpression((prev) =>
                  prev.trim()
                    ? prev
                    : mode === 'metric'
                      ? metricDsl()
                      : buildSimpleDsl(),
                )
              }
              setMode(value)
            }}
          >
            <Tab value="metric" label="Quick rule" />
            <Tab value="simple" label="Indicator" />
            <Tab value="dsl" label="Advanced (DSL)" />
          </Tabs>
          <Tooltip title="View DSL syntax and examples">
            <IconButton
              size="small"
              onClick={() => setDslHelpOpen(true)}
              aria-label="DSL help"
            >
              <HelpOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              label="Strategy template"
              select
              size="small"
              value={selectedStrategyId ?? ''}
              onChange={(e) => {
                const v = e.target.value
                setSelectedStrategyId(v ? Number(v) : null)
              }}
              sx={{ minWidth: 260 }}
              helperText="Optional: tag this alert with a reusable strategy template."
            >
              <MenuItem value="">None</MenuItem>
              {templates.map((tpl) => (
                <MenuItem key={tpl.id} value={tpl.id}>
                  {tpl.name}
                  {tpl.is_builtin ? ' (builtin)' : ''}
                </MenuItem>
              ))}
            </TextField>
            <Button
              size="small"
              variant="outlined"
              onClick={handleSaveAsStrategy}
              disabled={savingTemplate || !symbol}
              sx={{ alignSelf: 'flex-start', height: 40 }}
            >
              {savingTemplate ? 'Saving…' : 'Save as strategy'}
            </Button>
            {selectedTemplate && !selectedTemplate.is_builtin && (
              <Button
                size="small"
                variant="text"
                color="error"
                onClick={handleDeleteStrategyTemplate}
                sx={{ alignSelf: 'flex-start', height: 40 }}
              >
                Delete strategy
              </Button>
            )}
          </Box>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              label="Apply to"
              select
              size="small"
              value={applyScope}
              onChange={(e) =>
                setApplyScope(
                  e.target.value as
                    | 'symbol'
                    | 'selected'
                    | 'universe'
                    | 'holdings',
                )
              }
              sx={{ minWidth: 260 }}
            >
              <MenuItem value="symbol">This symbol</MenuItem>
              <MenuItem value="selected" disabled={selectedSymbols.length === 0}>
                Selected rows ({selectedSymbols.length})
              </MenuItem>
              {universeId !== 'holdings' && (
                <MenuItem value="universe">
                  Current universe ({universeLabel})
                </MenuItem>
              )}
              <MenuItem value="holdings">All holdings (Zerodha)</MenuItem>
            </TextField>
            {applyScope === 'universe' && universeId.startsWith('group:') && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ alignSelf: 'center' }}
              >
                Targets the group dynamically (members can change).
              </Typography>
            )}
          </Box>
          {mode === 'metric' ? (
            <>
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <TextField
                  label="Metric"
                  select
                  size="small"
                  value={metricField}
                  onChange={(e) =>
                    setMetricField(e.target.value as MetricField)
                  }
                  sx={{ minWidth: 220 }}
                >
                  {METRIC_FIELD_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Operator"
                  select
                  size="small"
                  value={metricOperator}
                  onChange={(e) =>
                    setMetricOperator(e.target.value as MetricOperator)
                  }
                  sx={{ minWidth: 140 }}
                >
                  {METRIC_OPERATOR_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Value"
                  size="small"
                  value={metricValue}
                  onChange={(e) => setMetricValue(e.target.value)}
                  sx={{ minWidth: 160 }}
                  helperText="Numeric threshold (e.g., 5 for 5%)."
                />
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip
                  label="Today PnL% > 5"
                  size="small"
                  onClick={() => {
                    setMetricField('TODAY_PNL_PCT')
                    setMetricOperator('GT')
                    setMetricValue('5')
                  }}
                />
                <Chip
                  label="Today PnL% < -5"
                  size="small"
                  onClick={() => {
                    setMetricField('TODAY_PNL_PCT')
                    setMetricOperator('LT')
                    setMetricValue('-5')
                  }}
                />
                <Chip
                  label="PnL% > 10"
                  size="small"
                  onClick={() => {
                    setMetricField('PNL_PCT')
                    setMetricOperator('GT')
                    setMetricValue('10')
                  }}
                />
              </Box>
              <Typography variant="body2" color="text.secondary">
                DSL preview: <code>{metricDsl()}</code>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Need indicators (RSI/MA) or multiple conditions? Use the Indicator or DSL tabs.
              </Typography>
            </>
          ) : mode === 'simple' ? (
            <>
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <TextField
                  label="Timeframe"
                  select
                  size="small"
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  sx={{ minWidth: 140 }}
                >
                  <MenuItem value="1m">1m</MenuItem>
                  <MenuItem value="5m">5m</MenuItem>
                  <MenuItem value="15m">15m</MenuItem>
                  <MenuItem value="1h">1H</MenuItem>
                  <MenuItem value="1d">1D</MenuItem>
                </TextField>
                <TextField
                  label="Indicator"
                  select
                  size="small"
                  value={indicator}
                  onChange={(e) =>
                    setIndicator(e.target.value as IndicatorType)
                  }
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="PRICE">Price (close)</MenuItem>
                  <MenuItem value="RSI">RSI</MenuItem>
                  <MenuItem value="MA">Moving average</MenuItem>
                  <MenuItem value="VOLATILITY">Volatility</MenuItem>
                  <MenuItem value="ATR">ATR</MenuItem>
                  <MenuItem value="PERF_PCT">Performance %</MenuItem>
                  <MenuItem value="VOLUME_RATIO">Volume vs avg</MenuItem>
                  <MenuItem value="PVT">PVT (cumulative)</MenuItem>
                  <MenuItem value="PVT_SLOPE">PVT slope %</MenuItem>
                </TextField>
                <TextField
                  label="Period / window"
                  size="small"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  sx={{ minWidth: 140 }}
                  helperText={
                    indicator === 'PERF_PCT'
                      ? 'Bars lookback for performance'
                      : 'Typical values: 14, 20, 50'
                  }
                />
              </Box>
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <TextField
                  label="Operator"
                  select
                  size="small"
                  value={operator}
                  onChange={(e) =>
                    setOperator(e.target.value as OperatorType)
                  }
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="GT">&gt;</MenuItem>
                  <MenuItem value="LT">&lt;</MenuItem>
                  <MenuItem value="BETWEEN">Between</MenuItem>
                  <MenuItem value="OUTSIDE">Outside</MenuItem>
                  <MenuItem value="CROSS_ABOVE">Crossing above</MenuItem>
                  <MenuItem value="CROSS_BELOW">Crossing below</MenuItem>
                  <MenuItem value="MOVE_UP_PCT">Moving up %</MenuItem>
                  <MenuItem value="MOVE_DOWN_PCT">Moving down %</MenuItem>
                </TextField>
                <TextField
                  label="Threshold"
                  size="small"
                  value={threshold1}
                  onChange={(e) => setThreshold1(e.target.value)}
                  sx={{ minWidth: 140 }}
                  helperText={
                    previewLoading
                      ? 'Loading current value…'
                      : previewError
                        ? 'Current value unavailable'
                        : `Current ${indicator === 'PRICE' ? 'price' : indicator}: ${formatPreviewValue()}`
                  }
                />
                {showThreshold2 && (
                  <TextField
                    label="Second threshold"
                    size="small"
                    value={threshold2}
                    onChange={(e) => setThreshold2(e.target.value)}
                    sx={{ minWidth: 140 }}
                  />
                )}
              </Box>
            </>
          ) : (
            <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
              <Editor
                height="140px"
                defaultLanguage="plaintext"
                value={dslExpression}
                onChange={(val) => setDslExpression(val ?? '')}
                onMount={handleDslEditorMount}
                options={{
                  minimap: { enabled: false },
                  lineNumbers: 'off',
                  wordWrap: 'on',
                  fontSize: 13,
                  automaticLayout: true,
                }}
              />
            </Box>
          )}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              label="Trigger"
              select
              size="small"
              value={triggerMode}
              onChange={(e) =>
                setTriggerMode(e.target.value as TriggerMode)
              }
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="ONCE">Only once</MenuItem>
              <MenuItem value="ONCE_PER_BAR">Once per bar</MenuItem>
              <MenuItem value="EVERY_TIME">Every time</MenuItem>
            </TextField>
            <TextField
              label="Action"
              select
              size="small"
              value={actionType}
              onChange={(e) =>
                setActionType(e.target.value as ActionType)
              }
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="ALERT_ONLY">Alert only</MenuItem>
              <MenuItem value="SELL_PERCENT">Queue SELL %</MenuItem>
              <MenuItem value="BUY_QUANTITY">Queue BUY quantity</MenuItem>
            </TextField>
            {actionValueLabel && (
              <TextField
                label={actionValueLabel}
                size="small"
                value={actionValue}
                onChange={(e) => setActionValue(e.target.value)}
                sx={{ minWidth: 180 }}
              />
            )}
          </Box>
          {error && (
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          )}
          {applyScope !== 'symbol' ? (
            <Typography variant="body2" color="text.secondary">
              Universe-wide alerts are managed from the Alerts page.
            </Typography>
          ) : loading ? (
            <Typography variant="body2" color="text.secondary">
              Loading existing alerts…
            </Typography>
          ) : rules.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No existing indicator alerts for this symbol yet.
            </Typography>
          ) : (
            <Box sx={{ mt: 1 }}>
              <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                Existing alerts
              </Typography>
              {rules.map((rule) => (
                <Box
                  key={rule.id}
                  sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    py: 0.5,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Typography variant="body2">
                    {rule.name ||
                      (rule.dsl_expression
                        ? 'DSL rule'
                        : rule.conditions[0]?.indicator)}{' '}
                    ({rule.timeframe}, {rule.trigger_mode})
                  </Typography>
                  <Button
                    size="small"
                    color="error"
                    onClick={() => handleDeleteRule(rule)}
                  >
                    Delete
                  </Button>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          onClick={handleCreate}
          variant="contained"
          disabled={saving || !symbol}
        >
          {saving ? 'Saving…' : 'Create alert'}
        </Button>
      </DialogActions>
      <Dialog
        open={dslHelpOpen}
        onClose={() => setDslHelpOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>DSL help</DialogTitle>
        <DialogContent dividers>
          <Typography variant="subtitle2" gutterBottom>
            Indicators
          </Typography>
          <Typography variant="body2" paragraph>
            Supported indicator functions:
            {' '}
            PRICE, RSI, MA / SMA, VOLATILITY, ATR, PERF_PCT / MOMENTUM,
            VOLUME_RATIO, VWAP, PVT, PVT_SLOPE.
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Fields
          </Typography>
          <Typography variant="body2" paragraph>
            You can reference holding fields in DSL:
            {' '}
            PNL_PCT, TODAY_PNL_PCT, MAX_PNL_PCT, DRAWDOWN_PCT, INVESTED,
            CURRENT_VALUE, QTY, AVG_PRICE.
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Operators
          </Typography>
          <Typography variant="body2" paragraph>
            Comparisons:
            {' '}
            {'>'}
            , {'>='}, {'<'},
            {'<='}, {'=='}, {'!='};
            {' '}
            cross:
            {' '}
            CROSS_ABOVE, CROSS_BELOW;
            {' '}
            boolean:
            {' '}
            AND, OR, NOT; use parentheses for grouping.
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Timeframes
          </Typography>
          <Typography variant="body2" paragraph>
            1m, 5m, 15m, 1h, 1d, 1mo, 1y.
          </Typography>
          <Typography variant="subtitle2" gutterBottom>
            Examples
          </Typography>
          <Typography variant="body2">
            RSI overbought:
            {' '}
            <code>(RSI(14, 1d) {'>'} 80)</code>
          </Typography>
          <Typography variant="body2">
            Bullish MA crossover:
            {' '}
            <code>(SMA(20, 1d) CROSS_ABOVE SMA(50, 1d)) AND PRICE(1d) {'>'} SMA(200, 1d)</code>
          </Typography>
          <Typography variant="body2">
            Intraday pullback:
            {' '}
            <code>PRICE(15m) {'<'} SMA(20, 15m) AND PRICE(1d) {'>'} SMA(50, 1d) AND RSI(14, 15m) {'<'} 40</code>
          </Typography>
        </DialogContent>
      </Dialog>
    </Dialog>
  )
	}

*/

type HoldingChartCellProps = {
  history?: CandlePoint[]
  periodDays: number
}

function HoldingChartCell({ history, periodDays }: HoldingChartCellProps) {
  if (!history || history.length < 2) {
    return (
      <Typography variant="caption" color="text.secondary">
        …
      </Typography>
    )
  }

  const slice =
    periodDays > 0 && history.length > periodDays ? history.slice(-periodDays) : history

  return <MiniSparkline points={slice} />
}

type MiniSparklineProps = {
  points: CandlePoint[]
}

function MiniSparkline({ points }: MiniSparklineProps) {
  const width = 100
  const height = 32

  const closes = points.map((p) => p.close)
  const min = Math.min(...closes)
  const max = Math.max(...closes)
  const span = max - min || 1
  const stepX = width / Math.max(points.length - 1, 1)

  const path = points
    .map((p, i) => {
      const x = i * stepX
      const norm = (p.close - min) / span
      const y = height - norm * (height - 4) - 2
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')

  return (
    <Box sx={{ width: '100%', height: '100%', minHeight: 24 }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="100%"
        preserveAspectRatio="none"
      >
        <path d={path} fill="none" stroke="currentColor" strokeWidth={1.2} />
      </svg>
    </Box>
  )
}

function computeSma(values: number[], period: number): number | undefined {
  if (period <= 0 || values.length < period) return undefined
  const slice = values.slice(-period)
  const sum = slice.reduce((acc, v) => acc + v, 0)
  return sum / period
}

function computeEma(values: number[], period: number): number | undefined {
  if (period <= 0 || values.length < period) return undefined
  const k = 2 / (period + 1)
  let ema = values[0]
  for (let i = 1; i < values.length; i += 1) {
    ema = values[i] * k + ema * (1 - k)
  }
  return ema
}

function computeEmaSeries(values: number[], period: number): number[] | null {
  if (period <= 0 || values.length < period) return null
  const k = 2 / (period + 1)
  const out: number[] = new Array(values.length)
  out[0] = values[0]
  for (let i = 1; i < values.length; i += 1) {
    out[i] = values[i] * k + out[i - 1] * (1 - k)
  }
  return out
}

function computeMacd(
  closes: number[],
): { macd: number; signal: number; hist: number } | null {
  const ema12 = computeEmaSeries(closes, 12)
  const ema26 = computeEmaSeries(closes, 26)
  if (!ema12 || !ema26) return null
  const macdSeries = ema12.map((v, i) => v - ema26[i])
  const signalSeries = computeEmaSeries(macdSeries, 9)
  if (!signalSeries) return null
  const macd = macdSeries[macdSeries.length - 1]
  const signal = signalSeries[signalSeries.length - 1]
  const hist = macd - signal
  if (![macd, signal, hist].every((v) => Number.isFinite(v))) return null
  return { macd, signal, hist }
}

function computeObv(closes: number[], volumes: number[]): number | undefined {
  if (closes.length < 2 || volumes.length !== closes.length) return undefined
  let obv = 0
  for (let i = 1; i < closes.length; i += 1) {
    const prev = closes[i - 1]
    const curr = closes[i]
    const vol = volumes[i] ?? 0
    if (!Number.isFinite(vol)) continue
    if (curr > prev) obv += vol
    else if (curr < prev) obv -= vol
  }
  return Number.isFinite(obv) ? obv : undefined
}

function computePvt(closes: number[], volumes: number[]): number | undefined {
  if (closes.length < 2 || volumes.length !== closes.length) return undefined
  let pvt = 0
  for (let i = 1; i < closes.length; i += 1) {
    const prev = closes[i - 1]
    const curr = closes[i]
    const vol = volumes[i] ?? 0
    if (
      !Number.isFinite(prev) ||
      prev === 0 ||
      !Number.isFinite(curr) ||
      !Number.isFinite(vol)
    )
      continue
    pvt += ((curr - prev) / prev) * vol
  }
  return Number.isFinite(pvt) ? pvt : undefined
}

function computePvtSlopePct(
  closes: number[],
  volumes: number[],
  window: number,
): number | undefined {
  if (window <= 1 || closes.length < window + 1 || volumes.length !== closes.length) {
    return undefined
  }
  const full = new Array(closes.length).fill(0)
  for (let i = 1; i < closes.length; i += 1) {
    const prev = closes[i - 1]
    const curr = closes[i]
    const vol = volumes[i] ?? 0
    const prevPvt = full[i - 1] ?? 0
    if (
      !Number.isFinite(prev) ||
      prev === 0 ||
      !Number.isFinite(curr) ||
      !Number.isFinite(vol)
    ) {
      full[i] = prevPvt
      continue
    }
    full[i] = prevPvt + ((curr - prev) / prev) * vol
  }
  const past = full[full.length - window - 1]
  const curr = full[full.length - 1]
  if (!Number.isFinite(past) || past === 0 || !Number.isFinite(curr)) return undefined
  return ((curr - past) / Math.abs(past)) * 100
}

function computeRsi(values: number[], period: number): number | undefined {
  if (period <= 0 || values.length < period + 1) return undefined
  let gains = 0
  let losses = 0
  const start = values.length - period - 1
  for (let i = start + 1; i < values.length; i += 1) {
    const delta = values[i] - values[i - 1]
    if (delta >= 0) {
      gains += delta
    } else {
      losses -= delta
    }
  }
  const avgGain = gains / period
  const avgLoss = losses / period
  if (avgLoss === 0) return 100
  const rs = avgGain / avgLoss
  return 100 - 100 / (1 + rs)
}

function computeVolatilityPct(values: number[], window: number): number | undefined {
  if (window <= 1 || values.length < window + 1) return undefined
  const rets: number[] = []
  const start = values.length - window - 1
  for (let i = start + 1; i < values.length; i += 1) {
    const prev = values[i - 1]
    const curr = values[i]
    if (prev <= 0 || curr <= 0) continue
    rets.push(Math.log(curr / prev))
  }
  if (!rets.length) return undefined
  const mean = rets.reduce((acc, r) => acc + r, 0) / rets.length
  const variance =
    rets.reduce((acc, r) => acc + (r - mean) ** 2, 0) / Math.max(rets.length - 1, 1)
  return Math.sqrt(variance) * 100
}

function computeAtrPct(
  highs: number[],
  lows: number[],
  closes: number[],
  period: number,
): number | undefined {
  if (period <= 0 || highs.length < period + 1 || closes.length < period + 1) {
    return undefined
  }
  const trs: number[] = []
  for (let i = 1; i < highs.length; i += 1) {
    const high = highs[i]
    const low = lows[i]
    const prevClose = closes[i - 1]
    const tr = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose),
    )
    trs.push(tr)
  }
  if (trs.length < period) return undefined
  const slice = trs.slice(-period)
  const atr = slice.reduce((acc, v) => acc + v, 0) / Math.max(slice.length, period)
  const lastClose = closes[closes.length - 1]
  if (lastClose === 0) return undefined
  return (atr / lastClose) * 100
}

function computePerfPct(values: number[], window: number): number | undefined {
  if (window <= 0 || values.length <= window) return undefined
  const past = values[values.length - window - 1]
  const curr = values[values.length - 1]
  if (past === 0) return undefined
  return ((curr - past) / past) * 100
}

function computeVolumeRatio(volumes: number[], window: number): number | undefined {
  if (window <= 0 || volumes.length < window + 1) return undefined
  const today = volumes[volumes.length - 1]
  const slice = volumes.slice(-window - 1, -1)
  const avg = slice.reduce((acc, v) => acc + v, 0) / slice.length
  if (avg === 0) return undefined
  return today / avg
}

function computeHoldingIndicators(
  points: CandlePoint[],
  avgPrice?: number | null,
): HoldingIndicators {
  if (points.length < 2) return {}

  const closes = points.map((p) => p.close)
  const highs = points.map((p) => p.high)
  const lows = points.map((p) => p.low)
  const volumes = points.map((p) => p.volume)
  const lastClose = closes[closes.length - 1]

  const indicators: HoldingIndicators = {}

  indicators.rsi14 = computeRsi(closes, 14)
  indicators.sma20 = computeSma(closes, 20)
  indicators.sma50 = computeSma(closes, 50)
  indicators.sma200 = computeSma(closes, 200)
  indicators.ema20 = computeEma(closes, 20)
  indicators.ema50 = computeEma(closes, 50)
  indicators.ema200 = computeEma(closes, 200)
  const macd = computeMacd(closes)
  if (macd) {
    indicators.macd = macd.macd
    indicators.macdSignal = macd.signal
    indicators.macdHist = macd.hist
  }
  indicators.obv = computeObv(closes, volumes)
  indicators.pvt = computePvt(closes, volumes)
  indicators.pvtSlopePct20 = computePvtSlopePct(closes, volumes, 20)

  const ma50 = computeSma(closes, 50)
  if (ma50 != null && ma50 !== 0) {
    indicators.ma50Pct = ((lastClose - ma50) / ma50) * 100
  }

  const ma200 = computeSma(closes, 200)
  if (ma200 != null && ma200 !== 0) {
    indicators.ma200Pct = ((lastClose - ma200) / ma200) * 100
  }

  indicators.volatility20dPct = computeVolatilityPct(closes, 20)
  indicators.volatility6mPct = computeVolatilityPct(closes, 126)
  indicators.atr14Pct = computeAtrPct(highs, lows, closes, 14)

  indicators.perf1dPct = computePerfPct(closes, 1)
  indicators.perf5dPct = computePerfPct(closes, 5)
  indicators.perf1wPct = computePerfPct(closes, 5)
  indicators.perf1mPct = computePerfPct(closes, 21)
  indicators.perf3mPct = computePerfPct(closes, 63)
  indicators.perf6mPct = computePerfPct(closes, 126)
  indicators.perf1yPct = computePerfPct(closes, 252)

  indicators.volumeVsAvg20d = computeVolumeRatio(volumes, 20)

  // Support/resistance proxies.
  const sr20 = points.length > 20 ? points.slice(-20) : points
  const sr50 = points.length > 50 ? points.slice(-50) : points
  const sr20High = sr20.map((p) => p.high).filter((v) => Number.isFinite(v))
  const sr20Low = sr20.map((p) => p.low).filter((v) => Number.isFinite(v))
  const sr50High = sr50.map((p) => p.high).filter((v) => Number.isFinite(v))
  const sr50Low = sr50.map((p) => p.low).filter((v) => Number.isFinite(v))
  if (sr20High.length) indicators.sr20High = Math.max(...sr20High)
  if (sr20Low.length) indicators.sr20Low = Math.min(...sr20Low)
  if (sr50High.length) indicators.sr50High = Math.max(...sr50High)
  if (sr50Low.length) indicators.sr50Low = Math.min(...sr50Low)
  if (
    indicators.sr20High != null &&
    indicators.sr20High > 0 &&
    Number.isFinite(lastClose) &&
    lastClose > 0
  ) {
    indicators.distToSr20HighPct = (lastClose / indicators.sr20High - 1) * 100
  }
  if (
    indicators.sr20Low != null &&
    indicators.sr20Low > 0 &&
    Number.isFinite(lastClose) &&
    lastClose > 0
  ) {
    indicators.distToSr20LowPct = (lastClose / indicators.sr20Low - 1) * 100
  }

  // 52-week high/low (approx. 252 trading days).
  const w52 = points.length > 252 ? points.slice(-252) : points
  const high52 = w52.map((p) => p.high).filter((v) => Number.isFinite(v))
  const low52 = w52.map((p) => p.low).filter((v) => Number.isFinite(v))
  if (high52.length) indicators.week52High = Math.max(...high52)
  if (low52.length) indicators.week52Low = Math.min(...low52)

  // DD (6M) = drawdown from trailing 6-month peak close (approx. 126 trading days).
  // Uses close (not high) to avoid intraday wick noise.
  const w6m = points.length > 126 ? points.slice(-126) : points
  const close6m = w6m.map((p) => p.close).filter((v) => Number.isFinite(v))
  if (close6m.length) {
    const peak = Math.max(...close6m)
    if (
      Number.isFinite(peak) &&
      peak > 0 &&
      Number.isFinite(lastClose) &&
      lastClose > 0
    ) {
      indicators.dd6mPct = (lastClose / peak - 1) * 100
    }
  }

  // Gap % = (open - yesterday_close) / yesterday_close
  if (points.length >= 2) {
    const todayOpen = points[points.length - 1]?.open
    const prevClose = points[points.length - 2]?.close
    if (
      todayOpen != null &&
      prevClose != null &&
      Number.isFinite(todayOpen) &&
      Number.isFinite(prevClose) &&
      prevClose !== 0
    ) {
      indicators.gapPct = ((todayOpen - prevClose) / prevClose) * 100
    }
  }

  // Max P&L % and drawdown from peak based on average entry price.
  if (avgPrice != null && avgPrice > 0) {
    const pnlSeries = closes.map((close) => ((close - avgPrice) / avgPrice) * 100)
    const currentPnl = pnlSeries[pnlSeries.length - 1]
    const maxPnl = pnlSeries.reduce((acc, v) => (v > acc ? v : acc), pnlSeries[0])
    indicators.maxPnlPct = maxPnl
    indicators.drawdownFromPeakPct = currentPnl - maxPnl
  }

  return indicators
}
