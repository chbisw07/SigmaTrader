import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Snackbar from '@mui/material/Snackbar'
import Alert from '@mui/material/Alert'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { fetchOrdersHistory, moveOrderToWaiting, type Order } from '../services/orders'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import { syncOrdersForBroker } from '../services/brokerRuntime'
import { fetchManagedRiskPositions } from '../services/managedRisk'
import { RiskRejectedHelpLink } from '../components/RiskRejectedHelpLink'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'

export function OrdersPanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  const { displayTimeZone } = useTimeSettings()
  const navigate = useNavigate()
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showSimulated, setShowSimulated] = useState<boolean>(true)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('zerodha')
  const [managedRiskCount, setManagedRiskCount] = useState<number>(0)
  const [moveBusyId, setMoveBusyId] = useState<number | null>(null)
  const [snackbar, setSnackbar] = useState<{
    open: boolean
    message: string
    severity: 'success' | 'error' | 'info'
  }>({ open: false, message: '', severity: 'info' })

  const loadOrders = async () => {
    try {
      setLoading(true)
      const data = await fetchOrdersHistory({ brokerName: selectedBroker })
      setOrders(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  const loadManagedRiskCount = async () => {
    try {
      const data = await fetchManagedRiskPositions({
        status: 'ACTIVE,EXITING,PAUSED',
        broker_name: selectedBroker,
      })
      setManagedRiskCount(data.length)
    } catch {
      setManagedRiskCount(0)
    }
  }

  useEffect(() => {
    if (!active) return
    if (loadedOnce) return
    setLoadedOnce(true)
    void (async () => {
      try {
        const list = await fetchBrokers()
        setBrokers(list)
        if (list.length > 0 && !list.some((b) => b.name === selectedBroker)) {
          setSelectedBroker(list[0].name)
        }
      } catch {
        // Ignore broker list failures; page will still load using default.
      }
    })()
    void loadOrders()
    void loadManagedRiskCount()
  }, [active, loadedOnce, selectedBroker])

  useEffect(() => {
    if (!active || !loadedOnce) return
    void loadOrders()
    void loadManagedRiskCount()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await syncOrdersForBroker(selectedBroker)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `Failed to sync orders from ${selectedBroker}`,
      )
    } finally {
      setRefreshing(false)
      await loadOrders()
      await loadManagedRiskCount()
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
        const label =
          order.simulated || order.execution_target === 'PAPER'
            ? `${base} (PAPER)`
            : base
        if (base === 'REJECTED_RISK') {
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Typography variant="body2">{label}</Typography>
              <RiskRejectedHelpLink />
            </Box>
          )
        }
        return <Typography variant="body2">{label}</Typography>
      },
    },
    {
      field: 'mode',
      headerName: 'Mode',
      width: 110,
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
      field: 'execution_target',
      headerName: 'Target',
      width: 110,
      valueGetter: (_value, row) => {
        const order = row as Order
        return order.execution_target ?? (order.simulated ? 'PAPER' : 'LIVE')
      },
    },
    {
      field: 'broker_name',
      headerName: 'Broker',
      width: 120,
      valueGetter: (_value, row) => {
        const order = row as Order
        if (order.simulated || order.execution_target === 'PAPER') return 'PAPER'
        return (order.broker_name ?? 'zerodha').toUpperCase()
      },
    },
    {
      field: 'broker',
      headerName: 'Broker Order',
      flex: 1,
      minWidth: 180,
      valueGetter: (_value, row) => {
        const order = row as Order
        if (order.simulated) {
          return 'PAPER'
        }
        const brokerOrderId =
          order.broker_order_id ?? order.zerodha_order_id ?? '-'
        if (order.broker_account_id) {
          return `${order.broker_account_id} / ${brokerOrderId}`
        }
        return brokerOrderId
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
    {
      field: 'actions',
      headerName: 'Actions',
      width: 170,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams) => {
        const order = params.row as Order
        const status = String(order.status ?? '').toUpperCase()
        const brokerId = order.broker_order_id ?? order.zerodha_order_id ?? null
        const alreadyRequeued = (order.error_message ?? '').includes(
          'Requeued to Waiting Queue as order #',
        )
        const eligible =
          !order.simulated &&
          !brokerId &&
          !alreadyRequeued &&
          (status === 'FAILED' || status === 'REJECTED_RISK' || status === 'CANCELLED')

        if (!eligible) return null

        return (
          <Button
            size="small"
            variant="outlined"
            disabled={moveBusyId === order.id}
            onClick={() => {
              void (async () => {
                setMoveBusyId(order.id)
                try {
                  const queued = await moveOrderToWaiting(order.id)
                  setOrders((prev) => {
                    const suffix = `Requeued to Waiting Queue as order #${queued.id}.`
                    const next = prev.map((o) => {
                      if (o.id !== order.id) return o
                      const base = (o.error_message ?? '').trim()
                      const msg = base ? `${base} ${suffix}` : suffix
                      return { ...o, error_message: msg }
                    })
                    return [queued, ...next.filter((o) => o.id !== queued.id)]
                  })
                  setSnackbar({
                    open: true,
                    message: `Queued a new WAITING order (#${queued.id}).`,
                    severity: 'success',
                  })
                  navigate('/queue?tab=waiting')
                } catch (err) {
                  setSnackbar({
                    open: true,
                    message: err instanceof Error ? err.message : 'Failed to move order',
                    severity: 'error',
                  })
                } finally {
                  setMoveBusyId(null)
                }
              })()
            }}
          >
            {moveBusyId === order.id ? 'Moving…' : 'Move to queue'}
          </Button>
        )
      },
    },
  ]

  return (
    <Box>
      {!embedded && (
        <Typography variant="h4" gutterBottom>
          Orders
        </Typography>
      )}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: embedded ? 1.5 : 3,
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography color="text.secondary">
            Basic order history view. Use Refresh to sync latest status from the selected broker.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            PAPER orders are marked with simulated=true. Toggle visibility below.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {managedRiskCount > 0 && (
            <Button
              size="small"
              variant="outlined"
              onClick={() => navigate('/queue?tab=risk')}
            >
              Managed exits ({managedRiskCount})
            </Button>
          )}
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
      <Snackbar
        open={snackbar.open}
        autoHideDuration={3500}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          variant="filled"
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  )
}

export function OrdersPage() {
  return <OrdersPanel />
}
