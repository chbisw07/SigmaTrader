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
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import { useEffect, useState } from 'react'

import {
  cancelOrder,
  fetchQueueOrders,
  executeOrder,
  updateOrder,
  type Order,
} from '../services/orders'

export function QueuePage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyCancelId, setBusyCancelId] = useState<number | null>(null)
  const [busyExecuteId, setBusyExecuteId] = useState<number | null>(null)
  const [editingOrder, setEditingOrder] = useState<Order | null>(null)
  const [editQty, setEditQty] = useState<string>('')
  const [editPrice, setEditPrice] = useState<string>('')
  const [editOrderType, setEditOrderType] = useState<'MARKET' | 'LIMIT'>(
    'MARKET',
  )
  const [editProduct, setEditProduct] = useState<string>('MIS')
  const [editGtt, setEditGtt] = useState<boolean>(false)
  const [savingEdit, setSavingEdit] = useState(false)

  const loadQueue = async () => {
    try {
      setLoading(true)
      const data = await fetchQueueOrders()
      setOrders(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load queue')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadQueue()
  }, [])

  const openEditDialog = (order: Order) => {
    setEditingOrder(order)
    setEditQty(String(order.qty))
    setEditPrice(order.price != null ? String(order.price) : '')
    setEditOrderType(order.order_type === 'LIMIT' ? 'LIMIT' : 'MARKET')
    setEditProduct(order.product)
    setEditGtt(order.gtt)
    setError(null)
  }

  const closeEditDialog = () => {
    setEditingOrder(null)
    setSavingEdit(false)
  }

  const handleSaveEdit = async () => {
    if (!editingOrder) return
    setSavingEdit(true)
    try {
      const qty = Number(editQty)
      if (!Number.isFinite(qty) || qty <= 0) {
        throw new Error('Quantity must be a positive number')
      }

      const price =
        editOrderType === 'MARKET' || editPrice.trim() === ''
          ? null
          : Number(editPrice)
      if (price != null && (!Number.isFinite(price) || price < 0)) {
        throw new Error('Price must be a non-negative number')
      }

      const updated = await updateOrder(editingOrder.id, {
        qty,
        price,
        order_type: editOrderType,
        product: editProduct,
        gtt: editGtt,
      })

      setOrders((prev) =>
        prev.map((o) => (o.id === updated.id ? updated : o)),
      )
      closeEditDialog()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update order')
      setSavingEdit(false)
    }
  }

  const handleCancel = async (orderId: number) => {
    setBusyCancelId(orderId)
    try {
      const updated = await cancelOrder(orderId)
      setOrders((prev) =>
        prev.filter((o) => o.id !== updated.id),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel order')
    } finally {
      setBusyCancelId(null)
    }
  }

  const handleExecute = async (orderId: number) => {
    setBusyExecuteId(orderId)
    try {
      const updated = await executeOrder(orderId)
      setOrders((prev) =>
        prev.filter((o) => o.id !== updated.id),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute order')
    } finally {
      setBusyExecuteId(null)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Waiting Queue
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Manual review queue for orders in WAITING state. You can edit, execute,
        or cancel pending orders before they are sent to the broker.
      </Typography>

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">
            Loading queue...
          </Typography>
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
                  <TableCell align="right">Actions</TableCell>
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
                  <TableCell align="right">
                    <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={
                          busyExecuteId === order.id || busyCancelId === order.id
                        }
                        onClick={() => openEditDialog(order)}
                      >
                        Edit
                      </Button>
                      <Button
                        size="small"
                        variant="contained"
                        disabled={
                          busyExecuteId === order.id || busyCancelId === order.id
                        }
                        onClick={() => handleExecute(order.id)}
                      >
                        {busyExecuteId === order.id ? 'Executing…' : 'Execute'}
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        disabled={
                          busyCancelId === order.id || busyExecuteId === order.id
                        }
                        onClick={() => handleCancel(order.id)}
                      >
                        {busyCancelId === order.id ? 'Cancelling…' : 'Cancel'}
                      </Button>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
              {orders.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8}>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                    >
                      No orders in the manual queue.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      )}

      <Dialog open={editingOrder != null} onClose={closeEditDialog} fullWidth>
        <DialogTitle>Edit queue order</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {editingOrder && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {editingOrder.symbol} · {editingOrder.side}
              </Typography>
              <TextField
                label="Quantity"
                type="number"
                value={editQty}
                onChange={(e) => setEditQty(e.target.value)}
                fullWidth
                size="small"
              />
              <TextField
                label="Order type"
                select
                value={editOrderType}
                onChange={(e) =>
                  setEditOrderType(
                    (e.target.value as 'MARKET' | 'LIMIT') || 'MARKET',
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
                value={editPrice}
                onChange={(e) => setEditPrice(e.target.value)}
                fullWidth
                size="small"
                helperText="Leave blank for market orders."
              />
              <TextField
                label="Product"
                select
                value={editProduct}
                onChange={(e) => setEditProduct(e.target.value)}
                fullWidth
                size="small"
                helperText="Select MIS for intraday or CNC for delivery."
              >
                <MenuItem value="MIS">MIS (Intraday)</MenuItem>
                <MenuItem value="CNC">CNC (Delivery)</MenuItem>
              </TextField>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editGtt}
                    onChange={(e) => setEditGtt(e.target.checked)}
                    size="small"
                  />
                }
                label="Convert to GTT (preference)"
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEditDialog} disabled={savingEdit}>
            Cancel
          </Button>
          <Button
            onClick={handleSaveEdit}
            variant="contained"
            disabled={savingEdit}
          >
            {savingEdit ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
