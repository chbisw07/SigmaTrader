import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import { getAppLogs } from '../services/logs'
import { fetchSystemEvents, type SystemEvent } from '../services/systemEvents'

export function SystemEventsPage() {
  const [events, setEvents] = useState<SystemEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
        <Typography variant="h6" gutterBottom>
          Backend events
        </Typography>
        {loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading events…</Typography>
          </Box>
        ) : error ? (
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        ) : events.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No backend events recorded yet.
          </Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                    Time
                  </th>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                    Level
                  </th>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                    Category
                  </th>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                    Message
                  </th>
                  <th style={{ textAlign: 'left', padding: '4px 8px' }}>
                    Correlation ID
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td style={{ padding: '4px 8px' }}>
                      {formatIst(e.created_at)}
                    </td>
                    <td style={{ padding: '4px 8px' }}>{e.level}</td>
                    <td style={{ padding: '4px 8px' }}>{e.category}</td>
                    <td style={{ padding: '4px 8px' }}>{e.message}</td>
                    <td style={{ padding: '4px 8px' }}>
                      {e.correlation_id ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
