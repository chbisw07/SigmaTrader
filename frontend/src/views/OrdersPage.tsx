import Box from '@mui/material/Box'
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

export function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const data = await fetchOrdersHistory()
        if (!active) return
        setOrders(data)
        setError(null)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load orders')
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Orders
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Basic order history view. Filters and advanced status insights will be
        added in future sprints.
      </Typography>

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
              {orders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell>
                    {new Date(order.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell>{order.symbol}</TableCell>
                  <TableCell>{order.side}</TableCell>
                  <TableCell align="right">{order.qty}</TableCell>
                  <TableCell align="right">
                    {order.price ?? '-'}
                  </TableCell>
                  <TableCell>{order.product}</TableCell>
                  <TableCell>{order.status}</TableCell>
                  <TableCell>{order.mode}</TableCell>
                  <TableCell>{order.zerodha_order_id ?? '-'}</TableCell>
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
