import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Tabs from '@mui/material/Tabs'
import Tab from '@mui/material/Tab'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import FormControlLabel from '@mui/material/FormControlLabel'
import {
  DataGrid,
  GridToolbar,
  type GridColDef,
  type GridRenderCellParams,
  type GridCellParams,
  type GridColumnVisibilityModel,
  GridLogicOperator,
} from '@mui/x-data-grid'
import { useEffect, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'

import { createManualOrder } from '../services/orders'
import { fetchMarketHistory, type CandlePoint } from '../services/marketData'
import { fetchHoldings, type Holding } from '../services/positions'
import {
  fetchHoldingsCorrelation,
  type HoldingsCorrelationResult,
} from '../services/analytics'
import {
  createIndicatorRule,
  deleteIndicatorRule,
  listIndicatorRules,
  type ActionType,
  type IndicatorCondition,
  type IndicatorRule,
  type IndicatorType,
  type OperatorType,
  type TriggerMode,
  fetchIndicatorPreview,
  type IndicatorPreview,
} from '../services/indicatorAlerts'
import {
  createStrategyTemplate,
  listStrategyTemplates,
  deleteStrategy,
  type Strategy,
} from '../services/strategies'

type HoldingIndicators = {
  rsi14?: number
  ma50Pct?: number
  ma200Pct?: number
  volatility20dPct?: number
  atr14Pct?: number
  perf1wPct?: number
  perf1mPct?: number
  perf3mPct?: number
  perf1yPct?: number
  volumeVsAvg20d?: number
}

type HoldingRow = Holding & {
  history?: CandlePoint[]
  indicators?: HoldingIndicators
  correlationCluster?: string
  correlationWeight?: number
}

type HoldingsFilterField =
  | 'symbol'
  | 'quantity'
  | 'average_price'
  | 'invested'
  | 'last_price'
  | 'current_value'
  | 'rsi14'
  | 'perf1m'
  | 'perf1y'
  | 'volatility20d'
  | 'atr14'
  | 'volumeVsAvg20d'
  | 'unrealized_pnl'
  | 'pnl_percent'
  | 'today_pnl_percent'

type HoldingsFilterOperator =
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'eq'
  | 'neq'
  | 'contains'
  | 'startsWith'
  | 'endsWith'

type HoldingsFilter = {
  id: string
  field: HoldingsFilterField
  operator: HoldingsFilterOperator
  value: string
}

type HoldingsFilterFieldConfig = {
  field: HoldingsFilterField
  label: string
  type: 'string' | 'number'
  getValue: (row: HoldingRow) => string | number | null
}

const HOLDINGS_FILTER_FIELDS: HoldingsFilterFieldConfig[] = [
  {
    field: 'symbol',
    label: 'Symbol',
    type: 'string',
    getValue: (row) => row.symbol,
  },
  {
    field: 'quantity',
    label: 'Qty',
    type: 'number',
    getValue: (row) =>
      row.quantity != null ? Number(row.quantity) : null,
  },
  {
    field: 'average_price',
    label: 'Avg Price',
    type: 'number',
    getValue: (row) =>
      row.average_price != null ? Number(row.average_price) : null,
  },
  {
    field: 'invested',
    label: 'Invested',
    type: 'number',
    getValue: (row) =>
      row.quantity != null && row.average_price != null
        ? Number(row.quantity) * Number(row.average_price)
        : null,
  },
  {
    field: 'last_price',
    label: 'Last Price',
    type: 'number',
    getValue: (row) =>
      row.last_price != null ? Number(row.last_price) : null,
  },
  {
    field: 'current_value',
    label: 'Current Value',
    type: 'number',
    getValue: (row) =>
      row.quantity != null && row.last_price != null
        ? Number(row.quantity) * Number(row.last_price)
        : null,
  },
  {
    field: 'rsi14',
    label: 'RSI(14)',
    type: 'number',
    getValue: (row) => row.indicators?.rsi14 ?? null,
  },
  {
    field: 'perf1m',
    label: '1M PnL %',
    type: 'number',
    getValue: (row) => row.indicators?.perf1mPct ?? null,
  },
  {
    field: 'perf1y',
    label: '1Y PnL %',
    type: 'number',
    getValue: (row) => row.indicators?.perf1yPct ?? null,
  },
  {
    field: 'volatility20d',
    label: 'Vol 20D %',
    type: 'number',
    getValue: (row) => row.indicators?.volatility20dPct ?? null,
  },
  {
    field: 'atr14',
    label: 'ATR(14) %',
    type: 'number',
    getValue: (row) => row.indicators?.atr14Pct ?? null,
  },
  {
    field: 'volumeVsAvg20d',
    label: 'Vol / 20D Avg',
    type: 'number',
    getValue: (row) => row.indicators?.volumeVsAvg20d ?? null,
  },
  {
    field: 'unrealized_pnl',
    label: 'Unrealized P&L',
    type: 'number',
    getValue: (row) => (row.pnl != null ? Number(row.pnl) : null),
  },
  {
    field: 'pnl_percent',
    label: 'P&L %',
    type: 'number',
    getValue: (row) =>
      row.total_pnl_percent != null
        ? Number(row.total_pnl_percent)
        : null,
  },
  {
    field: 'today_pnl_percent',
    label: "Today's P&L %",
    type: 'number',
    getValue: (row) =>
      row.today_pnl_percent != null
        ? Number(row.today_pnl_percent)
        : null,
  },
]

const NUMERIC_OPERATOR_OPTIONS: {
  value: HoldingsFilterOperator
  label: string
}[] = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '>=' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '<=' },
  { value: 'eq', label: '=' },
  { value: 'neq', label: '!=' },
]

const STRING_OPERATOR_OPTIONS: {
  value: HoldingsFilterOperator
  label: string
}[] = [
  { value: 'contains', label: 'contains' },
  { value: 'eq', label: 'equals' },
  { value: 'startsWith', label: 'starts with' },
  { value: 'endsWith', label: 'ends with' },
]

function getFieldConfig(
  field: HoldingsFilterField,
): HoldingsFilterFieldConfig {
  const cfg =
    HOLDINGS_FILTER_FIELDS.find((f) => f.field === field) ??
    HOLDINGS_FILTER_FIELDS[0]
  return cfg
}

function getOperatorOptions(
  field: HoldingsFilterField,
): { value: HoldingsFilterOperator; label: string }[] {
  const cfg = getFieldConfig(field)
  return cfg.type === 'string'
    ? STRING_OPERATOR_OPTIONS
    : NUMERIC_OPERATOR_OPTIONS
}

const ANALYTICS_LOOKBACK_DAYS = 730

export function HoldingsPage() {
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [tradeOpen, setTradeOpen] = useState(false)
  const [tradeSide, setTradeSide] = useState<'BUY' | 'SELL'>('BUY')
  const [tradeSymbol, setTradeSymbol] = useState<string>('')
  const [tradeQty, setTradeQty] = useState<string>('')
  const [tradePrice, setTradePrice] = useState<string>('')
  const [tradeProduct, setTradeProduct] = useState<'CNC' | 'MIS'>('CNC')
  const [tradeOrderType, setTradeOrderType] = useState<
    'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  >('MARKET')
  const [tradeSubmitting, setTradeSubmitting] = useState(false)
  const [tradeError, setTradeError] = useState<string | null>(null)

  const [chartPeriodDays, setChartPeriodDays] = useState<number>(30)

  const [alertOpen, setAlertOpen] = useState(false)
  const [alertSymbol, setAlertSymbol] = useState<string | null>(null)
  const [alertExchange, setAlertExchange] = useState<string | null>(null)

  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(false)
  const [advancedFilters, setAdvancedFilters] = useState<HoldingsFilter[]>([])

  const [columnVisibilityModel, setColumnVisibilityModel] =
    useState<GridColumnVisibilityModel>({})

  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false)
  const [refreshDays, setRefreshDays] = useState('0')
  const [refreshHours, setRefreshHours] = useState('0')
  const [refreshMinutes, setRefreshMinutes] = useState('5')
  const [refreshSeconds, setRefreshSeconds] = useState('0')
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const [, setCorrSummary] =
    useState<HoldingsCorrelationResult | null>(null)
  const [, setCorrLoading] = useState(false)
  const [corrError, setCorrError] = useState<string | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const raw = await fetchHoldings()
      const baseRows: HoldingRow[] = raw.map((h) => ({ ...h }))
      setHoldings(baseRows)
      setError(null)

      // Kick off background enrichment with OHLCV history and indicators.
      void enrichHoldingsWithHistory(baseRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load holdings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  // Load a lightweight correlation summary so that each holding can be
  // tagged with its high-level correlation cluster and approximate
  // portfolio weight. This runs independently of the main holdings
  // fetch and is best-effort only.
  useEffect(() => {
    let active = true
    const loadCorrelation = async () => {
      try {
        setCorrLoading(true)
        setCorrError(null)
        const res = await fetchHoldingsCorrelation({ windowDays: 90 })
        if (!active) return
        setCorrSummary(res)
        const bySymbol: Record<
          string,
          { cluster?: string; weight?: number | null }
        > = {}
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
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(
        'st_holdings_column_visibility_v1',
      )
      if (raw) {
        const parsed = JSON.parse(raw) as GridColumnVisibilityModel
        setColumnVisibilityModel(parsed)
      }
    } catch {
      // Ignore JSON/Storage errors and fall back to defaults.
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(
        'st_holdings_refresh_config_v1',
      )
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
    }
  }, [])

  useEffect(() => {
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

    const totalSeconds =
      days * 24 * 60 * 60 + hours * 60 * 60 + minutes * 60 + seconds

    if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
      setRefreshError('Auto-refresh interval must be greater than zero.')
      return
    }

    const minSeconds = 30
    if (totalSeconds < minSeconds) {
      setRefreshError(
        `Minimum auto-refresh interval is ${minSeconds} seconds.`,
      )
      return
    }

    setRefreshError(null)
    const intervalMs = totalSeconds * 1000

    const id = window.setInterval(() => {
      void load()
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
  ])

  const filteredRows =
    advancedFilters.length === 0
      ? holdings
      : applyAdvancedFilters(holdings, advancedFilters)

  const totalActiveAlerts = holdings.reduce((acc, h) => {
    const found = h as HoldingRow & { _activeAlertCount?: number }
    return acc + (found._activeAlertCount ?? 0)
  }, 0)

  const enrichHoldingsWithHistory = async (rows: HoldingRow[]) => {
    for (const row of rows) {
      try {
        const history = await fetchMarketHistory({
          symbol: row.symbol,
          exchange: row.exchange ?? 'NSE',
          timeframe: '1d',
          periodDays: ANALYTICS_LOOKBACK_DAYS,
        })
        const indicators = computeHoldingIndicators(history)
        setHoldings((current) =>
          current.map((h) =>
            h.symbol === row.symbol ? { ...h, history, indicators } : h,
          ),
        )
      } catch {
        // Ignore per-symbol failures so that one bad instrument does not
        // prevent the rest of the grid from being enriched.
      }
    }
  }

  const openAlertDialogForHolding = (holding: HoldingRow) => {
    setAlertSymbol(holding.symbol)
    setAlertExchange(holding.exchange ?? 'NSE')
    setAlertOpen(true)
  }

  const openTradeDialog = (holding: HoldingRow, side: 'BUY' | 'SELL') => {
    setTradeSide(side)
    setTradeSymbol(holding.symbol)
    setTradeQty(
      side === 'SELL' && holding.quantity != null
        ? String(holding.quantity)
        : '',
    )
    setTradePrice(
      holding.last_price != null ? String(holding.last_price.toFixed(2)) : '',
    )
    setTradeProduct('CNC')
    setTradeOrderType('MARKET')
    setTradeError(null)
    setTradeOpen(true)
  }

  const closeTradeDialog = () => {
    if (tradeSubmitting) return
    setTradeOpen(false)
  }

  const handleSubmitTrade = async () => {
    const qtyNum = Number(tradeQty)
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) {
      setTradeError('Quantity must be a positive number.')
      return
    }
    const priceNum =
      tradeOrderType === 'MARKET' || tradePrice.trim() === ''
        ? null
        : Number(tradePrice)
    if (priceNum != null && (!Number.isFinite(priceNum) || priceNum < 0)) {
      setTradeError('Price must be a non-negative number.')
      return
    }

    setTradeSubmitting(true)
    setTradeError(null)
    try {
      await createManualOrder({
        symbol: tradeSymbol,
        exchange: holdings.find((h) => h.symbol === tradeSymbol)?.exchange ?? 'NSE',
        side: tradeSide,
        qty: qtyNum,
        price: priceNum,
        order_type: tradeOrderType,
        product: tradeProduct,
        gtt: false,
      })
      setTradeOpen(false)
      await load()
    } catch (err) {
      setTradeError(
        err instanceof Error ? err.message : 'Failed to create order',
      )
    } finally {
      setTradeSubmitting(false)
    }
  }

  const columns: GridColDef[] = [
    {
      field: 'index',
      headerName: '#',
      width: 70,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams) =>
        params.api.getRowIndexRelativeToVisibleRows(params.id) + 1,
    },
    {
      field: 'symbol',
      headerName: 'Symbol',
      flex: 1,
      minWidth: 140,
    },
    {
      field: 'correlation_cluster',
      headerName: 'Cluster',
      sortable: false,
      filterable: false,
      width: 100,
      renderCell: (params) => {
        const row = params.row as HoldingRow
        const label = row.correlationCluster ?? '—'
        const weight = row.correlationWeight
        const tooltip =
          weight != null
            ? `Approx. portfolio weight in this holding: ${(weight * 100).toFixed(1)}%`
            : undefined
        return (
          <Tooltip title={tooltip ?? ''}>
            <span>{label}</span>
          </Tooltip>
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
    },
    {
      field: 'average_price',
      headerName: 'Avg Price',
      type: 'number',
      width: 130,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'last_price',
      headerName: 'Last Price',
      type: 'number',
      width: 130,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'invested',
      headerName: 'Invested',
      type: 'number',
      width: 140,
      valueGetter: (_value, row) => {
        const h = row as HoldingRow
        if (h.quantity == null || h.average_price == null) return null
        return Number(h.quantity) * Number(h.average_price)
      },
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'current_value',
      headerName: 'Current Value',
      type: 'number',
      width: 150,
      valueGetter: (_value, row) => {
        const h = row as HoldingRow
        if (h.quantity == null || h.last_price == null) return null
        return Number(h.quantity) * Number(h.last_price)
      },
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'indicator_rsi14',
      headerName: 'RSI(14)',
      type: 'number',
      width: 110,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.rsi14 ?? null,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(1) : '-',
    },
    {
      field: 'perf_1m_pct',
      headerName: '1M PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.perf1mPct ?? null,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}%` : '-',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0
          ? 'pnl-negative'
          : '',
    },
    {
      field: 'perf_1y_pct',
      headerName: '1Y PnL %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.perf1yPct ?? null,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}%` : '-',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0
          ? 'pnl-negative'
          : '',
    },
    {
      field: 'volatility_20d_pct',
      headerName: 'Vol 20D %',
      type: 'number',
      width: 130,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.volatility20dPct ?? null,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}%` : '-',
    },
    {
      field: 'atr_14_pct',
      headerName: 'ATR(14) %',
      type: 'number',
      width: 120,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.atr14Pct ?? null,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}%` : '-',
    },
    {
      field: 'volume_vs_20d_avg',
      headerName: 'Vol / 20D Avg',
      type: 'number',
      width: 150,
      valueGetter: (_value, row) =>
        (row as HoldingRow).indicators?.volumeVsAvg20d ?? null,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}x` : '-',
    },
    {
      field: 'pnl',
      headerName: 'Unrealized P&L',
      type: 'number',
      width: 150,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0
          ? 'pnl-negative'
          : '',
    },
    {
      field: 'total_pnl_percent',
      headerName: 'P&L %',
      type: 'number',
      width: 110,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}%` : '-',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0
          ? 'pnl-negative'
          : '',
    },
    {
      field: 'today_pnl_percent',
      headerName: 'Today P&L %',
      type: 'number',
      width: 130,
      valueFormatter: (value) =>
        value != null ? `${Number(value).toFixed(2)}%` : '-',
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0
          ? 'pnl-negative'
          : '',
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
  ]

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Holdings
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Live holdings fetched from Zerodha, including unrealized P&amp;L when last
        price is available.
      </Typography>
      {refreshError && (
        <Typography variant="caption" color="error" sx={{ mb: 1, display: 'block' }}>
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
                onChange={(e) =>
                  setChartPeriodDays(Number(e.target.value) || 30)
                }
              >
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

      <Box
        sx={{
          mb: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
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
            variant={advancedFiltersOpen ? 'contained' : 'outlined'}
            onClick={() => {
              setAdvancedFiltersOpen((prev) => !prev)
              if (!advancedFiltersOpen && advancedFilters.length === 0) {
                setAdvancedFilters([
                  {
                    id: `f-${Date.now()}`,
                    field: 'symbol',
                    operator: 'contains',
                    value: '',
                  },
                ])
              }
            }}
            sx={{ mr: 1 }}
          >
            {advancedFiltersOpen ? 'Hide filters' : 'Advanced filters'}
          </Button>
          {advancedFiltersOpen && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ verticalAlign: 'middle' }}
            >
              All conditions are combined with AND.
            </Typography>
          )}
        </Box>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 1,
          }}
        >
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
              void load()
            }}
          >
            Refresh now
          </Button>
          {totalActiveAlerts > 0 && (
            <Typography variant="caption" color="text.secondary">
              Active alerts (approx.): {totalActiveAlerts}
            </Typography>
          )}
        </Box>
      </Box>

      {advancedFiltersOpen && (
        <Paper
          sx={{
            mb: 1,
            p: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          {advancedFilters.map((filter) => {
            const operatorOptions = getOperatorOptions(filter.field)
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
          </Box>
        </Paper>
      )}

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

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading holdings...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper sx={{ mt: 1, height: 600, width: '100%' }}>
          <DataGrid
            rows={filteredRows}
            columns={columns}
            getRowId={(row) => row.symbol}
            density="compact"
            disableMultipleColumnsFiltering={false}
            columnVisibilityModel={columnVisibilityModel}
            onColumnVisibilityModelChange={(model) => {
              setColumnVisibilityModel(model)
              try {
                window.localStorage.setItem(
                  'st_holdings_column_visibility_v1',
                  JSON.stringify(model),
                )
              } catch {
                // Ignore persistence errors.
              }
            }}
            disableRowSelectionOnClick
            sx={{
              '& .pnl-negative': {
                color: 'error.main',
              },
            }}
            slots={{ toolbar: GridToolbar }}
            slotProps={{
              toolbar: {
                showQuickFilter: true,
                quickFilterProps: { debounceMs: 300 },
              },
              filterPanel: {
                // Combine multiple filter rows using AND semantics.
                logicOperators: [GridLogicOperator.And],
              },
            }}
            initialState={{
              pagination: { paginationModel: { pageSize: 25 } },
            }}
            pageSizeOptions={[25, 50, 100]}
            localeText={{
              noRowsLabel: 'No holdings found.',
            }}
          />
        </Paper>
      )}

      <Dialog open={tradeOpen} onClose={closeTradeDialog} fullWidth maxWidth="sm">
        <DialogTitle>
          {tradeSide === 'BUY' ? 'Buy from holdings' : 'Sell from holdings'}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="subtitle1">{tradeSymbol}</Typography>
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
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Quantity"
              type="number"
              value={tradeQty}
              onChange={(e) => setTradeQty(e.target.value)}
              fullWidth
              size="small"
            />
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
            </TextField>
            <TextField
              label="Price"
              type="number"
              value={tradePrice}
              onChange={(e) => setTradePrice(e.target.value)}
              fullWidth
              size="small"
              disabled={tradeOrderType === 'MARKET'}
            />
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
            {tradeError && (
              <Typography variant="body2" color="error">
                {tradeError}
              </Typography>
            )}
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
            {tradeSubmitting ? 'Submitting…' : 'Create order'}
          </Button>
        </DialogActions>
      </Dialog>
      <IndicatorAlertDialog
        open={alertOpen}
        onClose={() => setAlertOpen(false)}
        symbol={alertSymbol}
        exchange={alertExchange}
      />
    </Box>
  )
}

type IndicatorAlertDialogProps = {
  open: boolean
  onClose: () => void
  symbol: string | null
  exchange: string | null
}

function IndicatorAlertDialog({
  open,
  onClose,
  symbol,
  exchange,
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

  const [mode, setMode] = useState<'simple' | 'dsl'>('simple')
  const [dslExpression, setDslExpression] = useState<string>('')
  const [dslHelpOpen, setDslHelpOpen] = useState(false)
  const [applyScope, setApplyScope] = useState<'symbol' | 'holdings'>('symbol')

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
    const languageId = 'sigma-dsl'
    const alreadyRegistered = monaco.languages
      .getLanguages()
      .some((lang) => lang.id === languageId)
    if (!alreadyRegistered) {
      monaco.languages.register({ id: languageId })

      const indicatorSuggestions = [
        'PRICE',
        'RSI',
        'MA',
        'VOLATILITY',
        'ATR',
        'PERF_PCT',
        'VOLUME_RATIO',
        'VWAP',
        'PVT',
        'PVT_SLOPE',
      ]
      const keywordSuggestions = [
        'AND',
        'OR',
        'NOT',
        'CROSS_ABOVE',
        'CROSS_BELOW',
      ]
      const timeframeSuggestions = [
        '1m',
        '5m',
        '15m',
        '1h',
        '1d',
        '1mo',
        '1y',
      ]

      monaco.languages.registerCompletionItemProvider(languageId, {
        provideCompletionItems(model, position) {
          const word = model.getWordUntilPosition(position)
          const range = new monaco.Range(
            position.lineNumber,
            word.startColumn,
            position.lineNumber,
            word.endColumn,
          )

          const makeItems = (
            labels: string[],
            kind: monaco.languages.CompletionItemKind,
          ) =>
            labels.map((label) => ({
              label,
              kind,
              insertText: label,
              range,
            }))

          const suggestions = [
            ...makeItems(
              indicatorSuggestions,
              monaco.languages.CompletionItemKind.Function,
            ),
            ...makeItems(
              keywordSuggestions,
              monaco.languages.CompletionItemKind.Keyword,
            ),
            ...makeItems(
              timeframeSuggestions,
              monaco.languages.CompletionItemKind.Constant,
            ),
          ]
          return { suggestions }
        },
      })
    }

    const model = editor.getModel()
    if (model) {
      monaco.editor.setModelLanguage(model, languageId)
    }
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
    if (!open || !symbol || mode !== 'simple') {
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
  }, [open, symbol, mode])

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
    setMode('simple')
    setDslExpression('')
    setApplyScope('symbol')
  }

  const handleClose = () => {
    if (saving) return
    resetForm()
    onClose()
  }

  const handleCreate = async () => {
    if (!symbol) return

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

    if (mode === 'dsl') {
      if (!dslExpression.trim()) {
        setError('DSL expression cannot be empty.')
        return
      }
      dslExprToSend = dslExpression.trim()
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

    const payload = {
      strategy_id: selectedStrategyId ?? undefined,
      symbol: applyScope === 'symbol' ? symbol : undefined,
      universe: applyScope === 'holdings' ? 'HOLDINGS' : undefined,
      exchange: applyScope === 'symbol' ? exchange ?? 'NSE' : undefined,
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
      const created = await createIndicatorRule(payload)
      setRules((prev) => [created, ...prev])
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

    // Build a simple DSL representation of the current single-condition rule.
    const dsl = buildSimpleDsl()

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
      <DialogTitle>Create indicator alert</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          {symbol ?? '--'} {exchange ? ` / ${exchange}` : ''}
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
              setMode(value)
              if (value === 'dsl') {
                setDslExpression((prev) =>
                  prev.trim() ? prev : buildSimpleDsl(),
                )
              }
            }}
          >
            <Tab value="simple" label="Simple builder" />
            <Tab value="dsl" label="DSL expression" />
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
          <RadioGroup
            row
            value={applyScope}
            onChange={(e) =>
              setApplyScope(
                e.target.value === 'holdings' ? 'holdings' : 'symbol',
              )
            }
          >
            <FormControlLabel
              value="symbol"
              control={<Radio size="small" />}
              label="Apply to this stock only"
            />
            <FormControlLabel
              value="holdings"
              control={<Radio size="small" />}
              label="Apply to all holdings"
            />
          </RadioGroup>
          {mode === 'simple' ? (
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
          {applyScope === 'holdings' ? (
            <Typography variant="body2" color="text.secondary">
              Alerts that apply to all holdings are managed from the Alerts page.
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
            PRICE, RSI, MA, VOLATILITY, ATR, PERF_PCT, VOLUME_RATIO, VWAP,
            PVT, PVT_SLOPE.
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

type HoldingChartCellProps = {
  history?: CandlePoint[]
  periodDays: number
}

function HoldingChartCell({
  history,
  periodDays,
}: HoldingChartCellProps) {
  if (!history || history.length < 2) {
    return (
      <Typography variant="caption" color="text.secondary">
        …
      </Typography>
    )
  }

  const slice =
    periodDays > 0 && history.length > periodDays
      ? history.slice(-periodDays)
      : history

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

function computeVolatilityPct(
  values: number[],
  window: number,
): number | undefined {
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
    rets.reduce((acc, r) => acc + (r - mean) ** 2, 0) /
    Math.max(rets.length - 1, 1)
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
  const atr =
    slice.reduce((acc, v) => acc + v, 0) / Math.max(slice.length, period)
  const lastClose = closes[closes.length - 1]
  if (lastClose === 0) return undefined
  return (atr / lastClose) * 100
}

function computePerfPct(
  values: number[],
  window: number,
): number | undefined {
  if (window <= 0 || values.length <= window) return undefined
  const past = values[values.length - window - 1]
  const curr = values[values.length - 1]
  if (past === 0) return undefined
  return ((curr - past) / past) * 100
}

function computeVolumeRatio(
  volumes: number[],
  window: number,
): number | undefined {
  if (window <= 0 || volumes.length < window + 1) return undefined
  const today = volumes[volumes.length - 1]
  const slice = volumes.slice(-window - 1, -1)
  const avg = slice.reduce((acc, v) => acc + v, 0) / slice.length
  if (avg === 0) return undefined
  return today / avg
}

function computeHoldingIndicators(points: CandlePoint[]): HoldingIndicators {
  if (points.length < 2) return {}

  const closes = points.map((p) => p.close)
  const highs = points.map((p) => p.high)
  const lows = points.map((p) => p.low)
  const volumes = points.map((p) => p.volume)
  const lastClose = closes[closes.length - 1]

  const indicators: HoldingIndicators = {}

  indicators.rsi14 = computeRsi(closes, 14)

  const ma50 = computeSma(closes, 50)
  if (ma50 != null && ma50 !== 0) {
    indicators.ma50Pct = ((lastClose - ma50) / ma50) * 100
  }

  const ma200 = computeSma(closes, 200)
  if (ma200 != null && ma200 !== 0) {
    indicators.ma200Pct = ((lastClose - ma200) / ma200) * 100
  }

  indicators.volatility20dPct = computeVolatilityPct(closes, 20)
  indicators.atr14Pct = computeAtrPct(highs, lows, closes, 14)

  indicators.perf1wPct = computePerfPct(closes, 5)
  indicators.perf1mPct = computePerfPct(closes, 21)
  indicators.perf3mPct = computePerfPct(closes, 63)
  indicators.perf1yPct = computePerfPct(closes, 252)

  indicators.volumeVsAvg20d = computeVolumeRatio(volumes, 20)

  return indicators
}

function applyAdvancedFilters(
  rows: HoldingRow[],
  filters: HoldingsFilter[],
): HoldingRow[] {
  if (!filters.length) return rows

  const activeFilters = filters.filter(
    (f) => String(f.value).trim().length > 0,
  )
  if (!activeFilters.length) return rows

  return rows.filter((row) =>
    activeFilters.every((filter) => {
      const fieldConfig = getFieldConfig(filter.field)
      const rawVal = fieldConfig.getValue(row)

      if (rawVal == null) {
        return false
      }

      if (fieldConfig.type === 'string') {
        const value = String(rawVal).toLowerCase()
        const needle = String(filter.value).toLowerCase()
        switch (filter.operator) {
          case 'contains':
            return value.includes(needle)
          case 'startsWith':
            return value.startsWith(needle)
          case 'endsWith':
            return value.endsWith(needle)
          case 'eq':
            return value === needle
          case 'neq':
            return value !== needle
          default:
            return true
        }
      }

      const numericVal = Number(rawVal)
      const threshold = Number(filter.value)
      if (!Number.isFinite(numericVal) || !Number.isFinite(threshold)) {
        return true
      }

      switch (filter.operator) {
        case 'gt':
          return numericVal > threshold
        case 'gte':
          return numericVal >= threshold
        case 'lt':
          return numericVal < threshold
        case 'lte':
          return numericVal <= threshold
        case 'eq':
          return numericVal === threshold
        case 'neq':
          return numericVal !== threshold
        default:
          return true
      }
    }),
  )
}
