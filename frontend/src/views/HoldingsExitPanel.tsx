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
import { useEffect, useMemo, useState } from 'react'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'

import {
  createHoldingsExitSubscription,
  deleteHoldingsExitSubscription,
  listHoldingsExitEvents,
  listHoldingsExitSubscriptions,
  pauseHoldingsExitSubscription,
  resumeHoldingsExitSubscription,
  type HoldingExitEventRead,
  type HoldingExitSubscriptionCreate,
  type HoldingExitSubscriptionRead,
} from '../services/holdingsExit'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

type StatusFilter = 'ACTIVE' | 'PAUSED' | 'ERROR' | 'COMPLETED' | 'ALL'

const safeJson = (obj: unknown): string => {
  try {
    return JSON.stringify(obj ?? {}, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

export function HoldingsExitPanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  void embedded
  const { displayTimeZone } = useTimeSettings()
  const [subs, setSubs] = useState<HoldingExitSubscriptionRead[]>([])
  const [loading, setLoading] = useState(true)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ACTIVE')
  const [busyId, setBusyId] = useState<number | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createSymbol, setCreateSymbol] = useState('')
  const [createExchange, setCreateExchange] = useState('NSE')
  const [createTriggerKind, setCreateTriggerKind] =
    useState<HoldingExitSubscriptionCreate['trigger_kind']>('TARGET_ABS_PRICE')
  const [createTriggerValue, setCreateTriggerValue] = useState('')
  const [createSizeMode, setCreateSizeMode] =
    useState<HoldingExitSubscriptionCreate['size_mode']>('PCT_OF_POSITION')
  const [createSizeValue, setCreateSizeValue] = useState('50')

  const [eventsOpen, setEventsOpen] = useState(false)
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [eventsFor, setEventsFor] = useState<HoldingExitSubscriptionRead | null>(null)
  const [events, setEvents] = useState<HoldingExitEventRead[]>([])

  const loadSubs = async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options
    try {
      if (!silent) setLoading(true)
      const data = await listHoldingsExitSubscriptions({
        status: statusFilter === 'ALL' ? undefined : statusFilter,
      })
      setSubs(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load subscriptions')
      setSubs([])
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    if (!active) return
    if (loadedOnce) return
    setLoadedOnce(true)
    void loadSubs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, loadedOnce])

  useEffect(() => {
    if (!active || !loadedOnce) return
    void loadSubs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, loadedOnce, statusFilter])

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void loadSubs({ silent: true })
    }, 5000)
    return () => window.clearInterval(id)
  }, [active, statusFilter])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadSubs()
    } finally {
      setRefreshing(false)
    }
  }

  const openEvents = async (sub: HoldingExitSubscriptionRead) => {
    setEventsFor(sub)
    setEvents([])
    setEventsError(null)
    setEventsLoading(true)
    setEventsOpen(true)
    try {
      const ev = await listHoldingsExitEvents(sub.id, 300)
      setEvents(ev)
    } catch (err) {
      setEventsError(err instanceof Error ? err.message : 'Failed to load events')
      setEvents([])
    } finally {
      setEventsLoading(false)
    }
  }

  const doPause = async (id: number) => {
    setBusyId(id)
    try {
      await pauseHoldingsExitSubscription(id)
      await loadSubs({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pause subscription')
    } finally {
      setBusyId(null)
    }
  }

  const doResume = async (id: number) => {
    setBusyId(id)
    try {
      await resumeHoldingsExitSubscription(id)
      await loadSubs({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume subscription')
    } finally {
      setBusyId(null)
    }
  }

  const doDelete = async (id: number) => {
    if (!window.confirm('Delete this holdings exit subscription?')) return
    setBusyId(id)
    try {
      await deleteHoldingsExitSubscription(id)
      await loadSubs({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete subscription')
    } finally {
      setBusyId(null)
    }
  }

  const saveCreate = async () => {
    const symbol = createSymbol.trim()
    const exchange = createExchange.trim() || 'NSE'
    const tv = Number(createTriggerValue.trim())
    const sv = Number(createSizeValue.trim())
    if (!symbol) {
      setCreateError('Symbol is required.')
      return
    }
    if (!Number.isFinite(tv) || tv <= 0) {
      setCreateError('Trigger value must be a positive number.')
      return
    }
    if (!Number.isFinite(sv) || sv <= 0) {
      setCreateError('Size value must be a positive number.')
      return
    }

    setCreating(true)
    setCreateError(null)
    try {
      await createHoldingsExitSubscription({
        broker_name: 'zerodha',
        symbol,
        exchange,
        product: 'CNC',
        trigger_kind: createTriggerKind,
        trigger_value: tv,
        price_source: 'LTP',
        size_mode: createSizeMode,
        size_value: sv,
        min_qty: 1,
        order_type: 'MARKET',
        dispatch_mode: 'MANUAL',
        execution_target: 'LIVE',
        cooldown_seconds: 300,
      })
      setCreateOpen(false)
      await loadSubs({ silent: true })
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create subscription')
    } finally {
      setCreating(false)
    }
  }

  const columns = useMemo<GridColDef<HoldingExitSubscriptionRead>[]>(() => {
    return [
      { field: 'id', headerName: 'ID', width: 90 },
      { field: 'broker_name', headerName: 'Broker', width: 110 },
      { field: 'exchange', headerName: 'Exch', width: 90 },
      { field: 'symbol', headerName: 'Symbol', width: 140 },
      {
        field: 'trigger',
        headerName: 'Trigger',
        width: 220,
        valueGetter: (_v, row) =>
          `${row.trigger_kind} ${Number(row.trigger_value).toString()}`,
      },
      {
        field: 'size',
        headerName: 'Size',
        width: 160,
        valueGetter: (_v, row) => `${row.size_mode} ${Number(row.size_value).toString()}`,
      },
      { field: 'status', headerName: 'Status', width: 160 },
      {
        field: 'pending_order_id',
        headerName: 'Pending order',
        width: 140,
        valueGetter: (_v, row) => row.pending_order_id ?? '',
      },
      {
        field: 'last_error',
        headerName: 'Last error',
        flex: 1,
        minWidth: 240,
        valueGetter: (_v, row) => row.last_error ?? '',
      },
      {
        field: 'updated_at',
        headerName: 'Updated',
        width: 170,
        valueGetter: (_v, row) => row.updated_at,
        renderCell: (params: GridRenderCellParams<HoldingExitSubscriptionRead>) => {
          const v = params.value as string
          if (!v) return <span>-</span>
          return (
            <span>
              {formatInDisplayTimeZone(v, displayTimeZone, {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          )
        },
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 280,
        sortable: false,
        filterable: false,
        renderCell: (params: GridRenderCellParams<HoldingExitSubscriptionRead>) => {
          const row = params.row
          const busy = busyId === row.id
          return (
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button size="small" onClick={() => void openEvents(row)}>
                Events
              </Button>
              {row.status === 'PAUSED' ? (
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() => void doResume(row.id)}
                >
                  Resume
                </Button>
              ) : (
                <Button
                  size="small"
                  disabled={busy || row.status === 'COMPLETED'}
                  onClick={() => void doPause(row.id)}
                >
                  Pause
                </Button>
              )}
              <Button
                size="small"
                color="error"
                disabled={busy}
                onClick={() => void doDelete(row.id)}
              >
                Delete
              </Button>
            </Box>
          )
        },
      },
    ]
  }, [busyId, displayTimeZone])

  if (!active) return null

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 1,
          gap: 2,
          flexWrap: 'wrap',
        }}
      >
        <Typography variant={embedded ? 'h6' : 'h4'}>Holdings exits</Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <TextField
            select
            size="small"
            label="Status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="ACTIVE">ACTIVE</MenuItem>
            <MenuItem value="PAUSED">PAUSED</MenuItem>
            <MenuItem value="ERROR">ERROR</MenuItem>
            <MenuItem value="COMPLETED">COMPLETED</MenuItem>
            <MenuItem value="ALL">ALL</MenuItem>
          </TextField>
          <Button variant="outlined" onClick={() => setCreateOpen(true)}>
            New subscription
          </Button>
          <Button
            variant="outlined"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
        </Box>
      </Box>

      {error && (
        <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
          <Typography color="error" variant="body2">
            {error}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Enable this feature in Settings / Risk settings / Holdings exit automation (MVP).
          </Typography>
        </Paper>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={18} />
          <Typography variant="body2">Loading holdings exits...</Typography>
        </Box>
      ) : (
        <Paper sx={{ height: 560 }}>
          <DataGrid
            rows={subs}
            getRowId={(row) => row.id}
            density="compact"
            disableRowSelectionOnClick
            columns={columns}
            sx={{ height: '100%' }}
            initialState={{
              sorting: { sortModel: [{ field: 'updated_at', sort: 'desc' }] },
            }}
          />
        </Paper>
      )}

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New holdings exit subscription (MVP)</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Creates a CNC SELL order in the Waiting Queue when the trigger is met (manual-only).
          </Typography>
          <Box sx={{ display: 'grid', gap: 1.5 }}>
            <TextField
              label="Symbol"
              value={createSymbol}
              onChange={(e) => setCreateSymbol(e.target.value)}
              placeholder="INFY or NSE:INFY"
            />
            <TextField
              label="Exchange"
              value={createExchange}
              onChange={(e) => setCreateExchange(e.target.value)}
            />
            <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
              <TextField
                select
                label="Trigger kind"
                value={createTriggerKind}
                onChange={(e) =>
                  setCreateTriggerKind(
                    e.target.value as HoldingExitSubscriptionCreate['trigger_kind'],
                  )
                }
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="TARGET_ABS_PRICE">Target abs price</MenuItem>
                <MenuItem value="TARGET_PCT_FROM_AVG_BUY">% from avg buy</MenuItem>
              </TextField>
              <TextField
                label="Trigger value"
                value={createTriggerValue}
                onChange={(e) => setCreateTriggerValue(e.target.value)}
                sx={{ minWidth: 160 }}
              />
            </Box>
            <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
              <TextField
                select
                label="Sell sizing"
                value={createSizeMode}
                onChange={(e) =>
                  setCreateSizeMode(e.target.value as HoldingExitSubscriptionCreate['size_mode'])
                }
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="PCT_OF_POSITION">% of position</MenuItem>
                <MenuItem value="ABS_QTY">Qty</MenuItem>
              </TextField>
              <TextField
                label="Size value"
                value={createSizeValue}
                onChange={(e) => setCreateSizeValue(e.target.value)}
                sx={{ minWidth: 160 }}
              />
            </Box>
            {createError && (
              <Typography variant="caption" color="error">
                {createError}
              </Typography>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} disabled={creating}>
            Cancel
          </Button>
          <Button variant="contained" onClick={() => void saveCreate()} disabled={creating}>
            {creating ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={eventsOpen} onClose={() => setEventsOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>
          Events{eventsFor ? ` — ${eventsFor.exchange}:${eventsFor.symbol}` : ''}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {eventsLoading && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <CircularProgress size={18} />
              <Typography variant="body2">Loading events...</Typography>
            </Box>
          )}
          {eventsError && (
            <Typography variant="body2" color="error" sx={{ mb: 1 }}>
              {eventsError}
            </Typography>
          )}
          {!eventsLoading && !eventsError && events.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No events found.
            </Typography>
          )}
          {events.map((e) => (
            <Paper key={e.id} variant="outlined" sx={{ p: 1.25, mb: 1 }}>
              <Typography variant="subtitle2">
                {e.event_type} —{' '}
                {formatInDisplayTimeZone(e.event_ts, displayTimeZone, {
                  year: 'numeric',
                  month: '2-digit',
                  day: '2-digit',
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, mt: 1 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    details
                  </Typography>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{safeJson(e.details)}</pre>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    price_snapshot
                  </Typography>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {safeJson(e.price_snapshot ?? {})}
                  </pre>
                </Box>
              </Box>
            </Paper>
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEventsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
