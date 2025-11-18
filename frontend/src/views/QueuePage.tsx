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
import {
  fetchZerodhaMargins,
  fetchZerodhaLtp,
  previewZerodhaOrder,
} from '../services/zerodha'

export function QueuePage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyCancelId, setBusyCancelId] = useState<number | null>(null)
  const [busyExecuteId, setBusyExecuteId] = useState<number | null>(null)
  const [editingOrder, setEditingOrder] = useState<Order | null>(null)
  const [editQty, setEditQty] = useState<string>('')
  const [editSide, setEditSide] = useState<'BUY' | 'SELL'>('BUY')
  const [editPrice, setEditPrice] = useState<string>('')
  const [editOrderType, setEditOrderType] = useState<
    'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  >('MARKET')
  const [editProduct, setEditProduct] = useState<string>('MIS')
  const [editGtt, setEditGtt] = useState<boolean>(false)
  const [savingEdit, setSavingEdit] = useState(false)
  const [fundsAvailable, setFundsAvailable] = useState<number | null>(null)
  const [fundsRequired, setFundsRequired] = useState<number | null>(null)
  const [fundsCurrency, setFundsCurrency] = useState<string | null>(null)
  const [fundsLoading, setFundsLoading] = useState(false)
  const [fundsError, setFundsError] = useState<string | null>(null)
  const [editTriggerPrice, setEditTriggerPrice] = useState<string>('')
  const [editTriggerPercent, setEditTriggerPercent] = useState<string>('')
  const [triggerMode, setTriggerMode] = useState<'PRICE' | 'PERCENT'>('PRICE')
  const [ltp, setLtp] = useState<number | null>(null)
  const [ltpError, setLtpError] = useState<string | null>(null)

  const formatIst = (iso: string): string => {
    const utc = new Date(iso)
    const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
    const ist = new Date(istMs)
    return ist.toLocaleString('en-IN')
  }

  const loadQueue = async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options
    try {
      if (!silent) {
        setLoading(true)
      }
      const data = await fetchQueueOrders()
      setOrders(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load queue')
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    void loadQueue()
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => {
      void loadQueue({ silent: true })
    }, 5000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    const loadLtp = async () => {
      if (!editingOrder) return
      try {
        setLtpError(null)
        const data = await fetchZerodhaLtp(
          editingOrder.symbol,
          editingOrder.exchange ?? 'NSE',
        )
        setLtp(data.ltp)
      } catch (err) {
        setLtp(null)
        setLtpError(
          err instanceof Error ? err.message : 'Failed to fetch LTP.',
        )
      }
    }
    if (editingOrder && (editingOrder.order_type === 'SL' || editingOrder.order_type === 'SL-M')) {
      void loadLtp()
    }
  }, [editingOrder])

  useEffect(() => {
    if (!editingOrder || ltp == null) return
    if (editOrderType !== 'SL' && editOrderType !== 'SL-M') return

    if (triggerMode === 'PRICE') {
      const tp = Number(editTriggerPrice)
      if (Number.isFinite(tp) && ltp > 0) {
        const pct = ((tp - ltp) / ltp) * 100
        setEditTriggerPercent(pct.toFixed(2))
      } else {
        setEditTriggerPercent('')
      }
    } else if (triggerMode === 'PERCENT') {
      const pct = Number(editTriggerPercent)
      if (Number.isFinite(pct) && ltp > 0) {
        const tp = ltp * (1 + pct / 100)
        setEditTriggerPrice(tp.toFixed(2))
      } else {
        setEditTriggerPrice('')
      }
    }
  }, [
    editingOrder,
    ltp,
    editOrderType,
    triggerMode,
    editTriggerPrice,
    editTriggerPercent,
  ])

  const openEditDialog = (order: Order) => {
    setEditingOrder(order)
    setEditQty(String(order.qty))
    setEditSide(order.side === 'SELL' ? 'SELL' : 'BUY')
    setEditPrice(order.price != null ? String(order.price) : '')
    if (order.order_type === 'LIMIT' || order.order_type === 'SL' || order.order_type === 'SL-M') {
      setEditOrderType(order.order_type as 'LIMIT' | 'SL' | 'SL-M')
    } else {
      setEditOrderType('MARKET')
    }
    setEditTriggerPrice(
      order.trigger_price != null ? String(order.trigger_price) : '',
    )
    setEditTriggerPercent(
      order.trigger_percent != null ? String(order.trigger_percent) : '',
    )
    setEditProduct(order.product)
    setEditGtt(order.gtt)
    setFundsAvailable(null)
    setFundsRequired(null)
    setFundsCurrency(null)
    setFundsError(null)
    setTriggerMode('PRICE')
    setLtp(null)
    setLtpError(null)
    setError(null)
  }

  const closeEditDialog = () => {
    setEditingOrder(null)
    setSavingEdit(false)
  }

  const refreshFundsPreview = async () => {
    if (!editingOrder) return
    setFundsLoading(true)
    setFundsError(null)
    try {
      const qty = Number(editQty)
      if (!Number.isFinite(qty) || qty <= 0) {
        throw new Error('Enter a positive quantity to preview funds.')
      }

      const price =
        editOrderType === 'MARKET' || editPrice.trim() === ''
          ? null
          : Number(editPrice)
      if (price != null && (!Number.isFinite(price) || price < 0)) {
        throw new Error('Enter a non-negative price to preview funds.')
      }

      let triggerPrice: number | null = null
      if (editOrderType === 'SL' || editOrderType === 'SL-M') {
        if (editTriggerPrice.trim() === '') {
          throw new Error('Enter a trigger price for SL / SL-M orders.')
        }
        const tp = Number(editTriggerPrice)
        if (!Number.isFinite(tp) || tp <= 0) {
          throw new Error('Trigger price must be a positive number.')
        }
        triggerPrice = tp
      }

      const margins = await fetchZerodhaMargins()
      const preview = await previewZerodhaOrder({
        symbol: editingOrder.symbol,
        exchange: editingOrder.exchange ?? 'NSE',
        side: editSide,
        qty,
        product: editProduct,
        order_type: editOrderType,
        price,
        trigger_price: triggerPrice,
      })

      setFundsAvailable(margins.available)
      setFundsRequired(preview.required)
      setFundsCurrency(preview.currency ?? '₹')
    } catch (err) {
      setFundsError(
        err instanceof Error
          ? err.message
          : 'Failed to fetch funds preview.',
      )
      setFundsAvailable(null)
      setFundsRequired(null)
      setFundsCurrency(null)
    } finally {
      setFundsLoading(false)
    }
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

      let triggerPrice: number | undefined
      let triggerPercent: number | undefined
      if (editOrderType === 'SL' || editOrderType === 'SL-M') {
        if (editTriggerPrice.trim() === '') {
          throw new Error('Trigger price is required for SL / SL-M orders')
        }
        const tp = Number(editTriggerPrice)
        if (!Number.isFinite(tp) || tp <= 0) {
          throw new Error('Trigger price must be a positive number')
        }
        triggerPrice = tp
        if (editTriggerPercent.trim() !== '') {
          const tpc = Number(editTriggerPercent)
          if (!Number.isFinite(tpc)) {
            throw new Error('Trigger % must be a valid number')
          }
          triggerPercent = tpc
        }
      }

      const payload: {
        qty: number
        price: number | null
        side: 'BUY' | 'SELL'
        order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
        product: string
        gtt: boolean
        trigger_price?: number
        trigger_percent?: number
      } = {
        qty,
        price,
        side: editSide,
        order_type: editOrderType,
        product: editProduct,
        gtt: editGtt,
      }
      if (triggerPrice !== undefined) {
        payload.trigger_price = triggerPrice
      }
      if (triggerPercent !== undefined) {
        payload.trigger_percent = triggerPercent
      }

      const updated = await updateOrder(editingOrder.id, payload)

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
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          mb: 2,
          flexWrap: 'wrap',
        }}
      >
        <Box>
          <Typography variant="h4" gutterBottom>
            Waiting Queue
          </Typography>
          <Typography color="text.secondary">
            Manual review queue for orders in WAITING state. You can edit,
            execute, or cancel pending orders before they are sent to the
            broker.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          size="small"
          onClick={() => {
            void loadQueue()
          }}
          disabled={loading}
        >
          Refresh
        </Button>
      </Box>

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
                    {formatIst(order.created_at)}
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
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 2,
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {editingOrder.symbol}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Button
                    size="small"
                    variant={editSide === 'BUY' ? 'contained' : 'outlined'}
                    color="primary"
                    onClick={() => setEditSide('BUY')}
                  >
                    BUY
                  </Button>
                  <Button
                    size="small"
                    variant={editSide === 'SELL' ? 'contained' : 'outlined'}
                    color="error"
                    onClick={() => setEditSide('SELL')}
                  >
                    SELL
                  </Button>
                </Box>
              </Box>
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
                    (e.target.value as 'MARKET' | 'LIMIT' | 'SL' | 'SL-M') ||
                      'MARKET',
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
                type="number"
                value={editPrice}
                onChange={(e) => setEditPrice(e.target.value)}
                fullWidth
                size="small"
                helperText={
                  editOrderType === 'MARKET' || editOrderType === 'SL-M'
                    ? 'Leave blank for pure market orders.'
                    : 'Limit price for LIMIT / SL orders.'
                }
              />
              {(editOrderType === 'SL' || editOrderType === 'SL-M') && (
                <>
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'flex-end',
                      mb: 0.5,
                      gap: 1,
                    }}
                  >
                    <Button
                      size="small"
                      variant={triggerMode === 'PRICE' ? 'contained' : 'outlined'}
                      onClick={() => setTriggerMode('PRICE')}
                    >
                      Use price
                    </Button>
                    <Button
                      size="small"
                      variant={triggerMode === 'PERCENT' ? 'contained' : 'outlined'}
                      onClick={() => setTriggerMode('PERCENT')}
                      disabled={ltp == null}
                    >
                      Use % vs LTP
                    </Button>
                  </Box>
                  <TextField
                    label="Trigger price"
                    type="number"
                    value={editTriggerPrice}
                    onChange={(e) => setEditTriggerPrice(e.target.value)}
                    fullWidth
                    size="small"
                    disabled={triggerMode === 'PERCENT'}
                  />
                  <TextField
                    label="Trigger % vs LTP (optional)"
                    type="number"
                    value={editTriggerPercent}
                    onChange={(e) => setEditTriggerPercent(e.target.value)}
                    fullWidth
                    size="small"
                    disabled={triggerMode === 'PRICE' || ltp == null}
                    helperText={
                      ltpError
                        ? ltpError
                        : 'Percentage relative to last traded price; derived automatically when using the other field.'
                    }
                  />
                </>
              )}
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
              <Box
                sx={{
                  mt: 1,
                  p: 1.5,
                  borderRadius: 1,
                  bgcolor: 'action.hover',
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    mb: 1,
                    gap: 1,
                  }}
                >
                  <Typography variant="subtitle2">Funds &amp; charges</Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      void refreshFundsPreview()
                    }}
                    disabled={fundsLoading}
                  >
                    {fundsLoading ? 'Checking…' : 'Recalculate'}
                  </Button>
                </Box>
                {fundsError ? (
                  <Typography variant="body2" color="error">
                    {fundsError}
                  </Typography>
                ) : fundsAvailable != null && fundsRequired != null ? (
                  <Typography variant="body2">
                    Required:{' '}
                    {fundsCurrency ?? '₹'} {fundsRequired.toFixed(2)} (incl. charges)
                    <br />
                    Available:{' '}
                    {fundsCurrency ?? '₹'} {fundsAvailable.toFixed(2)}
                  </Typography>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Click Recalculate to see required vs available funds and
                    charges for this order.
                  </Typography>
                )}
              </Box>
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
