import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import {
  DataGrid,
  type GridColDef,
} from '@mui/x-data-grid'

import { getAppLogs } from '../services/logs'
import { fetchSystemEvents, type SystemEvent } from '../services/systemEvents'

export function SystemEventsPage() {
  const [events, setEvents] = useState<SystemEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [messageFilter, setMessageFilter] = useState<string>('')

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        const data = await fetchSystemEvents()
        setEvents(data)
        setError(null)
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load system events',
        )
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  const clientLogs = getAppLogs()

  const formatIst = (iso: string): string => {
    const utc = new Date(iso)
    const istMs = utc.getTime() + 5.5 * 60 * 60 * 1000
    const ist = new Date(istMs)
    return ist.toLocaleString('en-IN')
  }

  const filteredEvents =
    messageFilter.trim() === ''
      ? events
      : events.filter((e) =>
          e.message
            ?.toLowerCase()
            .includes(messageFilter.trim().toLowerCase()),
        )

  const columns: GridColDef[] = [
    {
      field: 'created_at',
      headerName: 'Time',
      width: 190,
      valueFormatter: (value) =>
        typeof value === 'string' ? formatIst(value) : '',
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
    <Box>
      <Typography variant="h4" gutterBottom>
        System Events
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Recent backend events (alerts, orders, broker) and local client-side
        errors for this session.
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            mb: 1.5,
            gap: 2,
          }}
        >
          <Typography variant="h6">Backend events</Typography>
          <TextField
            label="Search message"
            size="small"
            variant="outlined"
            value={messageFilter}
            onChange={(e) => setMessageFilter(e.target.value)}
            sx={{ width: 280 }}
          />
        </Box>
        {loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading events…</Typography>
          </Box>
        ) : error ? (
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        ) : filteredEvents.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No backend events recorded yet.
          </Typography>
        ) : (
          <Box sx={{ width: '100%', height: 320 }}>
            <DataGrid
              rows={filteredEvents}
              columns={columns}
              getRowId={(row) => row.id}
              disableRowSelectionOnClick
              density="compact"
            />
          </Box>
        )}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Client-side events (this browser session)
        </Typography>
        {clientLogs.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No client-side events recorded in this session.
          </Typography>
        ) : (
          clientLogs.map((log) => (
            <Box
              key={log.id}
              sx={{
                mb: 1.5,
                borderLeft: 4,
                pl: 1.5,
                borderColor:
                  log.level === 'ERROR'
                    ? 'error.main'
                    : log.level === 'WARNING'
                      ? 'warning.main'
                      : 'info.main',
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {new Date(log.timestamp).toLocaleString('en-IN')} · {log.level}
              </Typography>
              <Typography variant="body2">{log.message}</Typography>
            </Box>
          ))
        )}
      </Paper>
    </Box>
  )
}
