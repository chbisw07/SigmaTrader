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
} from '@mui/x-data-grid'
import { useEffect, useState } from 'react'

import { createManualOrder } from '../services/orders'
import { fetchMarketHistory, type CandlePoint } from '../services/marketData'
import { fetchHoldings, type Holding } from '../services/positions'

export function HoldingsPage() {
  const [holdings, setHoldings] = useState<Holding[]>([])
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

  const load = async () => {
    try {
      setLoading(true)
      const data = await fetchHoldings()
      setHoldings(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load holdings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const openTradeDialog = (holding: Holding, side: 'BUY' | 'SELL') => {
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
          symbol={params.row.symbol as string}
          exchange={(params.row as Holding).exchange ?? 'NSE'}
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
        const h = row as Holding
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
        const h = row as Holding
        if (h.quantity == null || h.last_price == null) return null
        return Number(h.quantity) * Number(h.last_price)
      },
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'pnl',
      headerName: 'Unrealized P&L',
      type: 'number',
      width: 150,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
      cellClassName: (params: any) =>
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
      cellClassName: (params: any) =>
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
      cellClassName: (params: any) =>
        params.value != null && Number(params.value) < 0
          ? 'pnl-negative'
          : '',
    },
    {
      field: 'actions',
      headerName: 'Actions',
      sortable: false,
      filterable: false,
      width: 160,
      renderCell: (params) => {
        const row = params.row as Holding
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
    </Box>
  )
}

type HoldingChartCellProps = {
  symbol: string
  exchange: string
  periodDays: number
}

const historyCache = new Map<string, CandlePoint[]>()

function makeHistoryKey(
  symbol: string,
  exchange: string,
  periodDays: number,
): string {
  return `${symbol}|${exchange}|1d|${periodDays}`
}

function HoldingChartCell({
  symbol,
  exchange,
  periodDays,
}: HoldingChartCellProps) {
  const [points, setPoints] = useState<CandlePoint[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const key = makeHistoryKey(symbol, exchange, periodDays)
    const cached = historyCache.get(key)
    if (cached) {
      setPoints(cached)
      return
    }

    const load = async () => {
      try {
        const data = await fetchMarketHistory({
          symbol,
          exchange,
          timeframe: '1d',
          periodDays,
        })
        if (!active) return
        historyCache.set(key, data)
        setPoints(data)
        setError(null)
      } catch (err) {
        if (!active) return
        setError(
          err instanceof Error ? err.message : 'Failed to load history',
        )
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [symbol, exchange, periodDays])

  if (error) {
    return (
      <Typography variant="caption" color="text.secondary">
        —
      </Typography>
    )
  }

  if (!points || points.length < 2) {
    return (
      <Typography variant="caption" color="text.secondary">
        …
      </Typography>
    )
  }

  return <MiniSparkline points={points} />
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
