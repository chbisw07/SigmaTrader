import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import { fetchOrdersHistory, type Order } from '../services/orders'
import { syncZerodhaOrders } from '../services/zerodha'

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
        <Paper>
          <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Created At</TableCell>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Side</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell>Product</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Mode</TableCell>
                  <TableCell>Broker ID</TableCell>
                  <TableCell>Error</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
              {orders
                .filter((order) => showSimulated || !order.simulated)
                .map((order) => (
                <TableRow
                  key={order.id}
                  sx={{
                    '& td': {
                      opacity: order.simulated ? 0.9 : 1,
                    },
                    backgroundColor: order.simulated ? 'action.hover' : undefined,
                  }}
                >
                  <TableCell>
                    {formatIst(order.created_at)}
                  </TableCell>
                  <TableCell>{order.symbol}</TableCell>
                  <TableCell>{order.side}</TableCell>
                  <TableCell align="right">{order.qty}</TableCell>
                  <TableCell align="right">
                    {order.price ?? '-'}
                  </TableCell>
                  <TableCell>{order.product}</TableCell>
                  <TableCell>
                    {order.status}
                    {order.simulated ? ' (PAPER)' : ''}
                  </TableCell>
                  <TableCell>{order.mode}</TableCell>
                  <TableCell>
                    {order.broker_account_id
                      ? `${order.broker_account_id} / ${order.zerodha_order_id ?? '-'}`
                      : order.zerodha_order_id ?? '-'}
                  </TableCell>
                  <TableCell>{order.error_message ?? '-'}</TableCell>
                </TableRow>
              ))}
              {orders.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10}>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                    >
                      No orders yet.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Box>
  )
}
