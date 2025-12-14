import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import { fetchOrdersHistory, type Order } from '../services/orders'
import { syncZerodhaOrders } from '../services/zerodha'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'

export function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showSimulated, setShowSimulated] = useState<boolean>(true)

  const formatIst = (iso: string): string => {
    const utc = new Date(iso)
    const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
    const ist = new Date(istMs)
    return ist.toLocaleString('en-IN')
  }

  const loadOrders = async () => {
    try {
      setLoading(true)
      const data = await fetchOrdersHistory()
      setOrders(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadOrders()
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await syncZerodhaOrders()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to sync orders from Zerodha',
      )
    } finally {
      setRefreshing(false)
      await loadOrders()
    }
  }

  const columns: GridColDef[] = [
    {
      field: 'created_at',
      headerName: 'Created At',
      width: 190,
      valueFormatter: (value) =>
        typeof value === 'string' ? formatIst(value) : '',
    },
    {
      field: 'symbol',
      headerName: 'Symbol',
      flex: 1,
      minWidth: 140,
    },
    {
      field: 'side',
      headerName: 'Side',
      width: 80,
    },
    {
      field: 'qty',
      headerName: 'Qty',
      type: 'number',
      width: 90,
    },
    {
      field: 'price',
      headerName: 'Price',
      type: 'number',
      width: 110,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'trigger_price',
      headerName: 'Trigger',
      type: 'number',
      width: 110,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'order_type',
      headerName: 'Type',
      width: 110,
      valueFormatter: (value, row) => {
        const order = row as Order
        const base = String(value ?? order.order_type ?? '')
        return order.gtt ? `${base} (GTT)` : base
      },
    },
    {
      field: 'product',
      headerName: 'Product',
      width: 110,
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 130,
      renderCell: (params: GridRenderCellParams) => {
        const order = params.row as Order
        const base = String(order.status ?? '')
        const label = order.simulated ? `${base} (PAPER)` : base
        return <Typography variant="body2">{label}</Typography>
      },
    },
    {
      field: 'mode',
      headerName: 'Mode',
      width: 110,
    },
    {
      field: 'broker',
      headerName: 'Broker ID',
      flex: 1,
      minWidth: 180,
      valueGetter: (_value, row) => {
        const order = row as Order
        if (order.simulated) {
          return 'PAPER'
        }
        if (order.broker_account_id) {
          return `${order.broker_account_id} / ${order.zerodha_order_id ?? '-'}`
        }
        return order.zerodha_order_id ?? '-'
      },
    },
    {
      field: 'error_message',
      headerName: 'Error',
      flex: 2,
      minWidth: 200,
      renderCell: (params: GridRenderCellParams) => (
        <Typography variant="body2" color="error">
          {params.value ?? '-'}
        </Typography>
      ),
    },
  ]

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Orders
      </Typography>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 3,
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography color="text.secondary">
            Basic order history view. Use Refresh to sync latest status from Zerodha.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            PAPER orders are marked with simulated=true. Toggle visibility below.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={showSimulated}
              onChange={(e) => setShowSimulated(e.target.checked)}
            />
            <Typography variant="body2">Show paper (simulated) orders</Typography>
          </label>
          <Button
            size="small"
            variant="outlined"
            onClick={handleRefresh}
            disabled={loading || refreshing}
          >
            {refreshing ? 'Refreshing…' : 'Refresh from Zerodha'}
          </Button>
        </Box>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading orders...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper sx={{ width: '100%', height: '65vh' }}>
          <DataGrid
            rows={orders.filter((order) => showSimulated || !order.simulated)}
            columns={columns}
            getRowId={(row) => row.id}
            disableRowSelectionOnClick
            density="compact"
            sx={{ height: '100%' }}
          />
        </Paper>
      )}
    </Box>
  )
}
