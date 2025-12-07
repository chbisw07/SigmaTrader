import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import {
  DataGrid,
  GridToolbar,
  type GridColDef,
  type GridRenderCellParams,
  type GridCellParams,
} from '@mui/x-data-grid'
import { useEffect, useState } from 'react'

import { createManualOrder } from '../services/orders'
import { fetchMarketHistory, type CandlePoint } from '../services/marketData'
import { fetchHoldings, type Holding } from '../services/positions'
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
} from '../services/indicatorAlerts'

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
      field: 'last_price',
      headerName: 'Last Price',
      type: 'number',
      width: 130,
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
      <Box
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
      </Box>

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
            rows={holdings}
            columns={columns}
            getRowId={(row) => row.symbol}
            density="compact"
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

  const [indicator, setIndicator] = useState<IndicatorType>('RSI')
  const [operator, setOperator] = useState<OperatorType>('GT')
  const [timeframe, setTimeframe] = useState<string>('1d')
  const [triggerMode, setTriggerMode] =
    useState<TriggerMode>('ONCE_PER_BAR')
  const [actionType, setActionType] =
    useState<ActionType>('ALERT_ONLY')
  const [threshold1, setThreshold1] = useState<string>('80')
  const [threshold2, setThreshold2] = useState<string>('')
  const [period, setPeriod] = useState<string>('14')
  const [actionValue, setActionValue] = useState<string>('10')

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

  const resetForm = () => {
    setIndicator('RSI')
    setOperator('GT')
    setTimeframe('1d')
    setTriggerMode('ONCE_PER_BAR')
    setActionType('ALERT_ONLY')
    setThreshold1('80')
    setThreshold2('')
    setPeriod('14')
    setActionValue('10')
    setError(null)
  }

  const handleClose = () => {
    if (saving) return
    resetForm()
    onClose()
  }

  const handleCreate = async () => {
    if (!symbol) return

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

    const actionParams: Record<string, unknown> = {}
    if (actionType === 'SELL_PERCENT') {
      const v = Number(actionValue)
      if (!Number.isFinite(v) || v <= 0) {
        setError('Percent must be a positive number.')
        return
      }
      actionParams.percent = v
    } else if (actionType === 'BUY_QUANTITY') {
      const v = Number(actionValue)
      if (!Number.isFinite(v) || v <= 0) {
        setError('Quantity must be a positive number.')
        return
      }
      actionParams.quantity = v
    }

    setSaving(true)
    try {
      const created = await createIndicatorRule({
        symbol,
        exchange: exchange ?? 'NSE',
        timeframe,
        logic: 'AND',
        conditions: [cond],
        trigger_mode: triggerMode,
        action_type: actionType,
        action_params: actionParams,
        enabled: true,
      })
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

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
      <DialogTitle>Create indicator alert</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          {symbol ?? '--'} {exchange ? ` / ${exchange}` : ''}
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              label="Timeframe"
              select
              size="small"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              sx={{ minWidth: 140 }}
            >
              <MenuItem value="1d">1D</MenuItem>
              <MenuItem value="1h">1H</MenuItem>
              <MenuItem value="15m">15m</MenuItem>
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
              <MenuItem value="RSI">RSI</MenuItem>
              <MenuItem value="MA">Moving average</MenuItem>
              <MenuItem value="VOLATILITY">Volatility</MenuItem>
              <MenuItem value="ATR">ATR</MenuItem>
              <MenuItem value="PERF_PCT">Performance %</MenuItem>
              <MenuItem value="VOLUME_RATIO">Volume vs avg</MenuItem>
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
              <MenuItem value="CROSS_ABOVE">Crosses above</MenuItem>
              <MenuItem value="CROSS_BELOW">Crosses below</MenuItem>
            </TextField>
            <TextField
              label="Threshold"
              size="small"
              value={threshold1}
              onChange={(e) => setThreshold1(e.target.value)}
              sx={{ minWidth: 140 }}
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
          {loading ? (
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
                    {rule.name || rule.conditions[0]?.indicator}{' '}
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
