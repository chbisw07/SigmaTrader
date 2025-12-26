import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type GridColumnVisibilityModel,
  type GridRowSelectionModel,
  type GridColDef,
} from '@mui/x-data-grid'

import { UniverseGrid } from '../components/UniverseGrid/UniverseGrid'
import {
  cleanupSystemEvents,
  fetchSystemEvents,
  type SystemEvent,
} from '../services/systemEvents'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

const SYSTEM_EVENTS_RETENTION_DAYS_KEY = 'st_system_events_retention_days_v1'

function loadRetentionDays(): number {
  try {
    const raw = window.localStorage.getItem(SYSTEM_EVENTS_RETENTION_DAYS_KEY)
    const parsed = raw != null ? Number(raw) : Number.NaN
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  } catch {
    // ignore
  }
  return 7
}

function saveRetentionDays(days: number): void {
  try {
    window.localStorage.setItem(SYSTEM_EVENTS_RETENTION_DAYS_KEY, String(days))
  } catch {
    // ignore
  }
}

export function SystemEventsPage() {
  const { displayTimeZone } = useTimeSettings()
  const [events, setEvents] = useState<SystemEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retentionDays, setRetentionDays] = useState<number>(() => loadRetentionDays())
  const [cleanupInfo, setCleanupInfo] = useState<string | null>(null)
  const [cleanupError, setCleanupError] = useState<string | null>(null)
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const hasAutoCleanedRef = useRef(false)

  const [rowSelectionModel, setRowSelectionModel] =
    useState<GridRowSelectionModel>([])
  const [columnVisibilityModel, setColumnVisibilityModel] =
    useState<GridColumnVisibilityModel>({})

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await fetchSystemEvents({ limit: 500 })
      setEvents(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load system events')
    } finally {
      setLoading(false)
    }
  }, [])

  const runCleanup = useCallback(
    async (opts?: { dryRun?: boolean }) => {
      const days = Math.max(1, Number(retentionDays || 0))
      setCleanupLoading(true)
      setCleanupInfo(null)
      setCleanupError(null)
      try {
        const res = await cleanupSystemEvents({ max_days: days, dry_run: opts?.dryRun })
        setCleanupInfo(
          `${opts?.dryRun ? 'Would delete' : 'Deleted'} ${res.deleted}; remaining ${res.remaining}.`,
        )
        if (!opts?.dryRun) await load()
      } catch (err) {
        setCleanupError(err instanceof Error ? err.message : 'Failed to cleanup events')
      } finally {
        setCleanupLoading(false)
      }
    },
    [load, retentionDays],
  )

  useEffect(() => {
    saveRetentionDays(retentionDays)
  }, [retentionDays])

  useEffect(() => {
    if (hasAutoCleanedRef.current) return
    hasAutoCleanedRef.current = true
    void (async () => {
      await runCleanup()
    })()
  }, [load, runCleanup])

  const columns: GridColDef[] = [
    {
      field: 'created_at',
      headerName: 'Time',
      width: 190,
      valueFormatter: (value) =>
        typeof value === 'string'
          ? formatInDisplayTimeZone(value, displayTimeZone)
          : '',
    },
    {
      field: 'level',
      headerName: 'Level',
      width: 90,
    },
    {
      field: 'category',
      headerName: 'Category',
      width: 120,
    },
    {
      field: 'message',
      headerName: 'Message',
      flex: 1,
      minWidth: 240,
    },
    {
      field: 'correlation_id',
      headerName: 'Correlation ID',
      flex: 1,
      minWidth: 220,
      valueFormatter: (value) => value ?? '-',
    },
  ]

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      <Typography variant="h4" gutterBottom>
        System Events
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Recent backend events (alerts, orders, broker).
      </Typography>

      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', md: 'center' }}
        sx={{ mb: 0.5 }}
      >
        <Typography variant="h6">Backend events</Typography>
        <Box sx={{ flex: 1 }} />
        <TextField
          label="Keep last (days)"
          size="small"
          type="number"
          value={retentionDays}
          onChange={(e) => setRetentionDays(Math.max(1, Number(e.target.value || 1)))}
          sx={{ width: 160 }}
        />
        <Button
          variant="outlined"
          disabled={cleanupLoading}
          onClick={() => void runCleanup()}
        >
          {cleanupLoading ? 'Cleaning…' : 'Cleanup now'}
        </Button>
        <Button variant="text" disabled={loading} onClick={() => void load()}>
          Refresh
        </Button>
      </Stack>

      {cleanupInfo ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {cleanupInfo}
        </Typography>
      ) : null}
      {cleanupError ? (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {cleanupError}
        </Typography>
      ) : null}

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading events…</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error" sx={{ mt: 1 }}>
          {error}
        </Typography>
      ) : (
        <UniverseGrid
          rows={events}
          columns={columns}
          getRowId={(row) => row.id}
          loading={loading}
          checkboxSelection={false}
          rowSelectionModel={rowSelectionModel}
          onRowSelectionModelChange={(next) => setRowSelectionModel(next)}
          density="compact"
          columnVisibilityModel={columnVisibilityModel}
          onColumnVisibilityModelChange={(next) => setColumnVisibilityModel(next)}
          disableRowSelectionOnClick
          height="70vh"
          localeText={{ noRowsLabel: 'No system events found.' }}
        />
      )}
    </Box>
  )
}
