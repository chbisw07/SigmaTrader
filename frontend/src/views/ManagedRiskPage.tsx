import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
} from '@mui/x-data-grid'

import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import type { DistanceSpec, RiskSpec } from '../services/orders'
import {
  exitManagedRiskPosition,
  fetchManagedRiskPositions,
  pauseManagedRiskPosition,
  resumeManagedRiskPosition,
  updateManagedRiskSpec,
  type ManagedRiskPosition,
} from '../services/managedRisk'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

type StatusFilter = 'ACTIVE' | 'EXITING' | 'PAUSED' | 'EXITED' | 'ALL'

const formatDistance = (value?: number | null, suffix?: string) => {
  if (value == null) return '-'
  return `${Number(value).toFixed(2)}${suffix ?? ''}`
}

const defaultDistanceSpec = (): DistanceSpec => ({
  enabled: false,
  mode: 'PCT',
  value: 0,
  atr_period: 14,
  atr_tf: '5m',
})

const buildRiskSpec = (position?: ManagedRiskPosition | null): RiskSpec => {
  const base = {
    stop_loss: defaultDistanceSpec(),
    trailing_stop: defaultDistanceSpec(),
    trailing_activation: defaultDistanceSpec(),
    exit_order_type: 'MARKET' as const,
    cooldown_ms: null as number | null,
  }
  if (!position?.risk_spec) return base
  return {
    ...base,
    ...position.risk_spec,
    stop_loss: { ...base.stop_loss, ...position.risk_spec.stop_loss },
    trailing_stop: { ...base.trailing_stop, ...position.risk_spec.trailing_stop },
    trailing_activation: {
      ...base.trailing_activation,
      ...position.risk_spec.trailing_activation,
    },
  }
}

export function ManagedRiskPanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  const { displayTimeZone } = useTimeSettings()
  const [positions, setPositions] = useState<ManagedRiskPosition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ACTIVE')
  const [busyActionId, setBusyActionId] = useState<number | null>(null)
  const [editingPosition, setEditingPosition] = useState<ManagedRiskPosition | null>(
    null,
  )
  const [editSpec, setEditSpec] = useState<RiskSpec | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)

  const loadPositions = async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options
    try {
      if (!silent) setLoading(true)
      const data = await fetchManagedRiskPositions({
        status: statusFilter === 'ALL' ? undefined : statusFilter,
        broker_name: selectedBroker === 'all' ? undefined : selectedBroker,
        include_exited: statusFilter === 'ALL',
      })
      setPositions(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load managed risk')
    } finally {
      if (!silent) setLoading(false)
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
        // Ignore broker list failures; page will still load using defaults.
      } finally {
        void loadPositions()
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, loadedOnce])

  useEffect(() => {
    if (!active || !loadedOnce) return
    void loadPositions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker, statusFilter])

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void loadPositions({ silent: true })
    }, 5000)
    return () => window.clearInterval(id)
  }, [active, selectedBroker, statusFilter])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadPositions()
    } finally {
      setRefreshing(false)
    }
  }

  const handleExitNow = async (positionId: number) => {
    setBusyActionId(positionId)
    try {
      await exitManagedRiskPosition(positionId)
      await loadPositions({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to exit position')
    } finally {
      setBusyActionId(null)
    }
  }

  const handlePause = async (positionId: number) => {
    setBusyActionId(positionId)
    try {
      await pauseManagedRiskPosition(positionId)
      await loadPositions({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pause monitor')
    } finally {
      setBusyActionId(null)
    }
  }

  const handleResume = async (positionId: number) => {
    setBusyActionId(positionId)
    try {
      await resumeManagedRiskPosition(positionId)
      await loadPositions({ silent: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume monitor')
    } finally {
      setBusyActionId(null)
    }
  }

  const openEditDialog = (position: ManagedRiskPosition) => {
    setEditingPosition(position)
    setEditSpec(buildRiskSpec(position))
    setEditError(null)
  }

  const closeEditDialog = () => {
    setEditingPosition(null)
    setEditSpec(null)
    setEditError(null)
  }

  const updateDistanceSpec = (
    key: 'stop_loss' | 'trailing_stop' | 'trailing_activation',
    patch: Partial<DistanceSpec>,
  ) => {
    setEditSpec((prev) => {
      if (!prev) return prev
      const next = {
        ...prev,
        [key]: { ...prev[key], ...patch },
      }
      if (key === 'stop_loss' && patch.enabled === false) {
        next.trailing_stop = { ...next.trailing_stop, enabled: false }
        next.trailing_activation = { ...next.trailing_activation, enabled: false }
      }
      if (key === 'trailing_stop' && patch.enabled === true) {
        next.stop_loss = { ...next.stop_loss, enabled: true }
      }
      if (key === 'trailing_stop' && patch.enabled === false) {
        next.trailing_activation = { ...next.trailing_activation, enabled: false }
      }
      if (key === 'trailing_activation' && patch.enabled === true) {
        next.trailing_stop = { ...next.trailing_stop, enabled: true }
        next.stop_loss = { ...next.stop_loss, enabled: true }
      }
      return next
    })
  }

  const handleSaveEdit = async () => {
    if (!editingPosition || !editSpec) return
    setSavingEdit(true)
    try {
      await updateManagedRiskSpec(editingPosition.id, editSpec)
      closeEditDialog()
      await loadPositions({ silent: true })
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to update risk spec')
    } finally {
      setSavingEdit(false)
    }
  }

  const rows = useMemo(() => positions, [positions])

  const columns: GridColDef[] = [
    {
      field: 'updated_at',
      headerName: 'Updated',
      width: 180,
      valueFormatter: (value) =>
        typeof value === 'string'
          ? formatInDisplayTimeZone(value, displayTimeZone)
          : '',
    },
    {
      field: 'symbol',
      headerName: 'Symbol',
      minWidth: 140,
      flex: 1,
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
      field: 'entry_price',
      headerName: 'Entry',
      width: 110,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'current_stop',
      headerName: 'Stop',
      width: 110,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'trail_price',
      headerName: 'Trail',
      width: 110,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'last_ltp',
      headerName: 'LTP',
      width: 100,
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 120,
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 240,
      sortable: false,
      filterable: false,
      align: 'left',
      headerAlign: 'left',
      renderCell: (params: GridRenderCellParams) => {
        const row = params.row as ManagedRiskPosition
        const busy = busyActionId === row.id
        const isActive = row.status === 'ACTIVE'
        const isPaused = row.status === 'PAUSED'
        const isExiting = row.status === 'EXITING'
        const isExited = row.status === 'EXITED'
        return (
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', justifyContent: 'left' }}>
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={busy || isExited}
              onClick={() => void handleExitNow(row.id)}
            >
              Exit now
            </Button>
            {isActive ? (
              <Button
                size="small"
                variant="outlined"
                disabled={busy || isExiting}
                onClick={() => void handlePause(row.id)}
              >
                Pause
              </Button>
            ) : (
              <Button
                size="small"
                variant="outlined"
                disabled={busy || !isPaused}
                onClick={() => void handleResume(row.id)}
              >
                Resume
              </Button>
            )}
            <Button
              size="small"
              variant="text"
              disabled={busy || isExited || isExiting}
              onClick={() => openEditDialog(row)}
            >
              Edit
            </Button>
          </Box>
        )
      },
    },
    {
      field: 'exit_order_id',
      headerName: 'Exit Order',
      minWidth: 160,
      flex: 1,
      align: 'left',
      headerAlign: 'left',
      renderCell: (params: GridRenderCellParams) => {
        const row = params.row as ManagedRiskPosition
        if (!row.exit_order_id) {
          return (
            <Box sx={{ width: '100%', textAlign: 'left' }}>
              <Typography variant="body2">Monitoring</Typography>
            </Box>
          )
        }
        const status = row.exit_order_status ? ` / ${row.exit_order_status}` : ''
        return (
          <Box sx={{ width: '100%', textAlign: 'left' }}>
            <Typography variant="body2">
              #{row.exit_order_id}
              {status}
            </Typography>
          </Box>
        )
      },
    },
    {
      field: 'risk_spec',
      headerName: 'Risk',
      minWidth: 200,
      flex: 1,
      valueGetter: (_value, row) => {
        const data = row as ManagedRiskPosition
        const spec = data.risk_spec
        if (!spec) return '-'
        const sl = spec.stop_loss?.enabled
          ? formatDistance(spec.stop_loss.value, spec.stop_loss.mode === 'PCT' ? '%' : '')
          : '-'
        const trail = spec.trailing_stop?.enabled
          ? formatDistance(
              spec.trailing_stop.value,
              spec.trailing_stop.mode === 'PCT' ? '%' : '',
            )
          : '-'
        const act = spec.trailing_activation?.enabled
          ? formatDistance(
              spec.trailing_activation.value,
              spec.trailing_activation.mode === 'PCT' ? '%' : '',
            )
          : '-'
        return `SL ${sl} | Trail ${trail} | Act ${act}`
      },
    },
  ]

  const renderDistanceEditor = (
    label: string,
    key: 'stop_loss' | 'trailing_stop' | 'trailing_activation',
    spec: DistanceSpec,
  ) => (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
        <FormControlLabel
          control={
            <Switch
              checked={spec.enabled}
              onChange={(e) => updateDistanceSpec(key, { enabled: e.target.checked })}
            />
          }
          label={label}
        />
        <TextField
          select
          size="small"
          label="Mode"
          value={spec.mode}
          onChange={(e) => updateDistanceSpec(key, { mode: e.target.value as DistanceSpec['mode'] })}
          disabled={!spec.enabled}
          sx={{ minWidth: 120 }}
        >
          <MenuItem value="PCT">%</MenuItem>
          <MenuItem value="ABS">ABS</MenuItem>
          <MenuItem value="ATR">ATR</MenuItem>
        </TextField>
        <TextField
          size="small"
          type="number"
          label="Value"
          value={spec.value}
          onChange={(e) => updateDistanceSpec(key, { value: Number(e.target.value) })}
          disabled={!spec.enabled}
          sx={{ width: 120 }}
        />
        <TextField
          size="small"
          type="number"
          label="ATR period"
          value={spec.atr_period ?? 14}
          onChange={(e) => updateDistanceSpec(key, { atr_period: Number(e.target.value) })}
          disabled={!spec.enabled}
          sx={{ width: 140 }}
        />
        <TextField
          select
          size="small"
          label="ATR TF"
          value={spec.atr_tf ?? '5m'}
          onChange={(e) => updateDistanceSpec(key, { atr_tf: e.target.value })}
          disabled={!spec.enabled}
          sx={{ width: 120 }}
        >
          <MenuItem value="1m">1m</MenuItem>
          <MenuItem value="5m">5m</MenuItem>
          <MenuItem value="15m">15m</MenuItem>
          <MenuItem value="30m">30m</MenuItem>
          <MenuItem value="1h">1h</MenuItem>
          <MenuItem value="1d">1d</MenuItem>
        </TextField>
        <Typography variant="caption" color="text.secondary">
          Used when Mode = ATR
        </Typography>
      </Box>
    </Paper>
  )

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Managed exits
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          These positions are actively monitored by SigmaTrader. When a trigger
          hits, an automatic exit order is created and sent to the broker. Exit
          orders do not appear in the manual queue.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            select
            size="small"
            label="Status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="ACTIVE">Active</MenuItem>
            <MenuItem value="EXITING">Exit queued</MenuItem>
            <MenuItem value="PAUSED">Paused</MenuItem>
            <MenuItem value="EXITED">Exited</MenuItem>
            <MenuItem value="ALL">All</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Broker"
            value={selectedBroker}
            onChange={(e) => setSelectedBroker(e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="all">All brokers</MenuItem>
            {brokers.map((b) => (
              <MenuItem key={b.name} value={b.name}>
                {b.label ?? b.name}
              </MenuItem>
            ))}
          </TextField>
          <Button size="small" variant="outlined" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
        </Box>
      </Paper>

      <Paper sx={{ p: 2 }}>
        {loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading managed exits...</Typography>
          </Box>
        ) : error ? (
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        ) : rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No managed exits match the current filters.
          </Typography>
        ) : (
          <DataGrid
            rows={rows}
            columns={columns}
            pageSizeOptions={[10, 25, 50]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            autoHeight
            disableRowSelectionOnClick
            sx={{
              '& .MuiDataGrid-columnHeaders': { backgroundColor: 'action.hover' },
            }}
          />
        )}
      </Paper>

      <Dialog
        open={Boolean(editingPosition && editSpec)}
        onClose={closeEditDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Edit managed exit</DialogTitle>
        <DialogContent>
          {editingPosition && editSpec ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mt: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {editingPosition.symbol} | {editingPosition.side} | Qty {editingPosition.qty} |
                Entry {Number(editingPosition.entry_price).toFixed(2)}
              </Typography>
              {renderDistanceEditor('Stop loss', 'stop_loss', editSpec.stop_loss)}
              {renderDistanceEditor('Trailing stop', 'trailing_stop', editSpec.trailing_stop)}
              {renderDistanceEditor(
                'Trail activation',
                'trailing_activation',
                editSpec.trailing_activation,
              )}
              {editError && (
                <Typography variant="caption" color="error">
                  {editError}
                </Typography>
              )}
            </Box>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEditDialog} disabled={savingEdit}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleSaveEdit()}
            disabled={savingEdit || !editSpec}
          >
            {savingEdit ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
