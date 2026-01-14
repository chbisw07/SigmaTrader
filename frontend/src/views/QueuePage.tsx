import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
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
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
  type GridRowSelectionModel,
} from '@mui/x-data-grid'

import {
  cancelOrder,
  fetchQueueOrders,
  executeOrder,
  updateOrder,
  type Order,
  type ExecutionTarget,
} from '../services/orders'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import {
  fetchBrokerCapabilities,
  fetchLtpForBroker,
  fetchMarginsForBroker,
  previewOrderForBroker,
  type BrokerCapabilities,
} from '../services/brokerRuntime'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

export function WaitingQueuePanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  const { displayTimeZone } = useTimeSettings()
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
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
  const [editExecutionTarget, setEditExecutionTarget] =
    useState<ExecutionTarget>('LIVE')
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
  const [selectionModel, setSelectionModel] = useState<GridRowSelectionModel>([])
  const [bulkCancelling, setBulkCancelling] = useState(false)
  const [bulkExecuting, setBulkExecuting] = useState(false)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('zerodha')
  const [brokerCaps, setBrokerCaps] = useState<Record<string, BrokerCapabilities>>({})

  const getCaps = (brokerName?: string | null): BrokerCapabilities | null => {
    const name = (brokerName ?? selectedBroker ?? 'zerodha').toLowerCase()
    return brokerCaps[name] ?? null
  }

  const loadQueue = async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options
    try {
      if (!silent) {
        setLoading(true)
      }
      const data = await fetchQueueOrders(undefined, selectedBroker)
      setOrders(data)
      setSelectionModel((prev) =>
        prev.filter((id) => data.some((o) => o.id === id)),
      )
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
    if (!active) return
    if (loadedOnce) return
    setLoadedOnce(true)
    void (async () => {
      try {
        const [list, caps] = await Promise.all([
          fetchBrokers(),
          fetchBrokerCapabilities(),
        ])
        setBrokers(list)
        const capsMap: Record<string, BrokerCapabilities> = {}
        for (const item of caps) {
          capsMap[item.name] = item.capabilities
        }
        setBrokerCaps(capsMap)
        if (list.length > 0 && !list.some((b) => b.name === selectedBroker)) {
          setSelectedBroker(list[0].name)
        }
      } catch {
        // Ignore; the queue can still operate with defaults.
      } finally {
        void loadQueue()
      }
    })()
  }, [active, loadedOnce, selectedBroker])

  useEffect(() => {
    if (!active || !loadedOnce) return
    void loadQueue()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker])

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void loadQueue({ silent: true })
    }, 5000)
    return () => window.clearInterval(id)
  }, [active, selectedBroker])

  useEffect(() => {
    const loadLtp = async () => {
      if (!editingOrder) return
      try {
        setLtpError(null)
        const brokerName = (editingOrder.broker_name ?? selectedBroker ?? 'zerodha')
        const caps = getCaps(brokerName)
        if (caps && !caps.supports_ltp) {
          throw new Error(`LTP not available for ${brokerName}.`)
        }
        const data = await fetchLtpForBroker(
          brokerName,
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
  }, [editingOrder, selectedBroker])

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
    setEditExecutionTarget(order.execution_target ?? 'LIVE')
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
      const brokerName = (editingOrder.broker_name ?? selectedBroker ?? 'zerodha')
      const caps = getCaps(brokerName)
      if (caps && (!caps.supports_margin_preview || !caps.supports_order_preview)) {
        throw new Error(`Funds preview is not available for ${brokerName}.`)
      }

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

      const margins = await fetchMarginsForBroker(brokerName)
      const preview = await previewOrderForBroker(brokerName, {
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
        execution_target: ExecutionTarget
        trigger_price?: number
        trigger_percent?: number
      } = {
        qty,
        price,
        side: editSide,
        order_type: editOrderType,
        product: editProduct,
        gtt: editGtt,
        execution_target: editExecutionTarget,
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
      setSuccessMessage(null)
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
      setSuccessMessage(null)
      const updated = await executeOrder(orderId)
      if (updated.gtt && updated.synthetic_gtt && updated.status === 'WAITING') {
        setOrders((prev) => prev.map((o) => (o.id === updated.id ? updated : o)))
        setSuccessMessage('Conditional order armed.')
      } else {
        setOrders((prev) => prev.filter((o) => o.id !== updated.id))
        setSuccessMessage('Order executed.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute order')
    } finally {
      setBusyExecuteId(null)
    }
  }

  const handleSelectAll = () => {
    setSelectionModel(orders.map((o) => o.id))
  }

  const handleBulkCancel = async () => {
    const ids = selectionModel.map((id) => Number(id)).filter((id) =>
      Number.isFinite(id),
    )
    if (!ids.length) return
    const ok = window.confirm(
      `Cancel ${ids.length} selected order${ids.length > 1 ? 's' : ''}?`,
    )
    if (!ok) return
    setBulkCancelling(true)
    try {
      setSuccessMessage(null)
      await Promise.all(ids.map((id) => cancelOrder(id)))
      setOrders((prev) => prev.filter((o) => !ids.includes(o.id)))
      setSelectionModel([])
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to cancel selected orders',
      )
    } finally {
      setBulkCancelling(false)
    }
  }

  const handleBulkExecute = async () => {
    const ids = selectionModel.map((id) => Number(id)).filter((id) =>
      Number.isFinite(id),
    )
    if (!ids.length) return
    const ok = window.confirm(
      `Execute ${ids.length} selected order${ids.length > 1 ? 's' : ''}? This will send them to ${selectedBroker}.`,
    )
    if (!ok) return

    setBulkExecuting(true)
    setSuccessMessage(null)
    setError(null)
    const failures: Array<{ id: number; message: string }> = []
    try {
      // Execute sequentially to avoid broker/API rate limits.
      for (const id of ids) {
        try {
          await executeOrder(id)
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Failed to execute order'
          failures.push({ id, message })
        }
      }

      // Refresh queue to reflect status changes even when the endpoint
      // returns an error after persisting a new status.
      await loadQueue({ silent: true })
      setSelectionModel([])

      if (failures.length > 0) {
        const first = failures[0]
        setError(
          `Failed to execute ${failures.length}/${ids.length} orders. First failure (order ${first.id}): ${first.message}`,
        )
      } else {
        setSuccessMessage(
          `Executed ${ids.length} order${ids.length > 1 ? 's' : ''}.`,
        )
      }
    } finally {
      setBulkExecuting(false)
    }
  }

  const columns: GridColDef[] = [
    {
      field: 'created_at',
      headerName: 'Created At',
      width: 190,
      valueFormatter: (value) =>
        typeof value === 'string'
          ? formatInDisplayTimeZone(value, displayTimeZone)
          : '',
    },
    {
      field: 'broker_name',
      headerName: 'Broker',
      width: 120,
      valueGetter: (_value, row) => {
        const order = row as Order
        return (order.broker_name ?? 'zerodha').toUpperCase()
      },
    },
    {
      field: 'origin',
      headerName: 'Source',
      width: 120,
      valueGetter: (_value, row) => {
        const order = row as Order
        const raw = String(order.origin ?? 'MANUAL').trim().toUpperCase()
        if (raw === 'TRADINGVIEW') return 'TradingView'
        return raw || 'MANUAL'
      },
    },
    {
      field: 'symbol',
      headerName: 'Symbol',
      width: 200,
    },
    {
      field: 'side',
      headerName: 'Side',
      width: 80,
    },
    {
      field: 'qty',
      headerName: 'Qty',
      width: 90,
      type: 'number',
    },
    {
      field: 'price',
      headerName: 'Price',
      width: 110,
      type: 'number',
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'trigger_price',
      headerName: 'Trigger',
      description: 'Trigger price for SL/SL-M orders and conditional (GTT) orders.',
      width: 110,
      type: 'number',
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
        if (!order.gtt) return base
        return order.synthetic_gtt ? `${base} (COND)` : `${base} (GTT)`
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
      width: 170,
      valueFormatter: (value, row) => {
        const order = row as Order
        let base = String(value ?? order.status ?? '')
        if (
          order.gtt &&
          order.synthetic_gtt &&
          base === 'WAITING' &&
          order.armed_at
        ) {
          base = 'WAITING (ARMED)'
        }
        return order.execution_target === 'PAPER' ? `${base} (PAPER)` : base
      },
    },
    {
      field: 'execution_target',
      headerName: 'Target',
      width: 110,
      valueGetter: (_value, row) => {
        const order = row as Order
        return order.execution_target ?? (order.simulated ? 'PAPER' : 'LIVE')
      },
    },
    {
      field: 'gtt',
      headerName: 'Cond',
      description:
        'Whether this order is conditional: GTT (broker-managed) or Sigma (SigmaTrader-managed).',
      width: 80,
      valueFormatter: (_value, row) => {
        const order = row as Order
        if (!order.gtt) return 'No'
        return order.synthetic_gtt ? 'Sigma' : 'GTT'
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 220,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams) => {
        const order = params.row as Order
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => openEditDialog(order)}
            >
              Edit
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="primary"
              disabled={busyExecuteId === order.id}
              onClick={() => {
                void handleExecute(order.id)
              }}
            >
              {busyExecuteId === order.id ? 'Executing…' : 'Execute'}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={busyCancelId === order.id}
              onClick={() => {
                void handleCancel(order.id)
              }}
            >
              {busyCancelId === order.id ? 'Cancelling…' : 'Cancel'}
            </Button>
          </Box>
        )
      },
    },
  ]

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          mb: embedded ? 1.5 : 2,
          flexWrap: 'wrap',
        }}
      >
        <Box>
          {!embedded && (
            <Typography variant="h4" gutterBottom>
              Waiting Queue
            </Typography>
          )}
          <Typography color="text.secondary">
            Manual review queue for orders in WAITING state. You can edit,
            execute, or cancel pending orders before they are sent to the
            broker.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            PAPER orders will execute via the simulated engine when their strategy
            execution target is set to PAPER.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {brokers.length > 0 && (
            <TextField
              select
              size="small"
              label="Broker"
              value={selectedBroker}
              onChange={(e) => setSelectedBroker(e.target.value)}
              sx={{ minWidth: 170 }}
            >
              {brokers.map((b) => (
                <MenuItem key={b.name} value={b.name}>
                  {b.label}
                </MenuItem>
              ))}
            </TextField>
          )}
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
	          <Button
	            variant="outlined"
	            size="small"
	            onClick={handleSelectAll}
	            disabled={orders.length === 0}
	          >
	            Select all
	          </Button>
	          <Button
	            variant="contained"
	            size="small"
	            onClick={() => {
	              void handleBulkExecute()
	            }}
	            disabled={
	              selectionModel.length === 0
	              || bulkExecuting
	              || bulkCancelling
	              || busyExecuteId != null
	              || busyCancelId != null
	            }
	          >
	            {bulkExecuting ? 'Executing…' : 'Execute selected'}
	          </Button>
	          <Button
	            variant="contained"
	            size="small"
	            color="error"
	            onClick={() => {
	              void handleBulkCancel()
	            }}
	            disabled={selectionModel.length === 0 || bulkCancelling || bulkExecuting}
	          >
	            {bulkCancelling ? 'Cancelling…' : 'Cancel selected'}
	          </Button>
	        </Box>
	      </Box>

      {successMessage && !error && (
        <Typography sx={{ mt: 1 }} color="success.main">
          {successMessage}
        </Typography>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading queue...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper
          sx={{
            width: '100%',
            mt: 2,
            // In tabbed mode, keep the panel height stable to avoid flicker/layout jumps.
            height: embedded ? '65vh' : undefined,
          }}
        >
          <DataGrid
            rows={orders}
            columns={columns}
            getRowId={(row) => row.id}
            {...(embedded ? {} : { autoHeight: true })}
            checkboxSelection
            rowSelectionModel={selectionModel}
            onRowSelectionModelChange={(newSelection) => {
              setSelectionModel(newSelection)
            }}
            disableRowSelectionOnClick
            density="compact"
            sx={embedded ? { height: '100%' } : undefined}
            initialState={{
              sorting: {
                sortModel: [{ field: 'created_at', sort: 'desc' }],
              },
            }}
          />
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
              <TextField
                label="Execution target"
                select
                value={editExecutionTarget}
                onChange={(e) =>
                  setEditExecutionTarget(
                    (e.target.value as ExecutionTarget) || 'LIVE',
                  )
                }
                fullWidth
                size="small"
                helperText="LIVE sends the order to the broker; PAPER routes it to the simulated engine."
              >
                <MenuItem value="LIVE">LIVE</MenuItem>
                <MenuItem value="PAPER">PAPER</MenuItem>
              </TextField>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editGtt}
                    onChange={(e) => {
                      const checked = e.target.checked
                      setEditGtt(checked)
                      if (checked && editOrderType === 'MARKET') {
                        setEditOrderType('LIMIT')
                      }
                    }}
                    size="small"
                    disabled={(() => {
                      const brokerName =
                        editingOrder?.broker_name ?? selectedBroker ?? 'zerodha'
                      const caps = getCaps(brokerName)
                      const supported = caps
                        ? caps.supports_gtt || caps.supports_conditional_orders
                        : brokerName === 'zerodha'
                      return !supported
                    })()}
                  />
                }
                label={
                  (() => {
                    const brokerName =
                      editingOrder?.broker_name ?? selectedBroker ?? 'zerodha'
                    const caps = getCaps(brokerName)
                    if (caps?.supports_gtt || brokerName === 'zerodha') {
                      return 'Place as GTT (broker-managed)'
                    }
                    return 'Place as conditional order (SigmaTrader-managed)'
                  })()
                }
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
                    disabled={(() => {
                      if (fundsLoading) return true
                      const brokerName =
                        editingOrder?.broker_name ?? selectedBroker ?? 'zerodha'
                      const caps = getCaps(brokerName)
                      return caps
                        ? !caps.supports_margin_preview || !caps.supports_order_preview
                        : brokerName !== 'zerodha'
                    })()}
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

export function QueuePage() {
  return <WaitingQueuePanel />
}
