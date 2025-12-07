import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
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
import { fetchHoldings, type Holding } from '../services/positions'

const formatIst = (iso: string | null | undefined): string => {
  if (!iso) return '-'
  const utc = new Date(iso)
  if (Number.isNaN(utc.getTime())) return '-'
  const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
  const ist = new Date(istMs)
  return ist.toLocaleString('en-IN')
}

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
        exchange: 'NSE',
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
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Live holdings fetched from Zerodha, including unrealized P&amp;L when last
        price is available.
      </Typography>

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
