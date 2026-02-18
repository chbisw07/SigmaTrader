import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Divider from '@mui/material/Divider'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'

import {
  ackAiException,
  fetchAiExceptions,
  resyncExpectedLedger,
  runAiReconcile,
  type AiTmException,
} from '../services/aiTradingManager'
import { isAiAssistantEnabled } from '../config/aiFeatures'

export function ExceptionsCenterPage() {
  const [items, setItems] = useState<AiTmException[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    const run = async () => {
      if (!isAiAssistantEnabled()) return
      try {
        const rows = await fetchAiExceptions({ account_id: 'default', status_filter: 'OPEN', limit: 200 })
        if (!active) return
        setItems(rows)
      } catch (e) {
        if (!active) return
        setError(e instanceof Error ? e.message : 'Failed to load exceptions')
      }
    }
    void run()
    return () => {
      active = false
    }
  }, [])

  const handleResync = async () => {
    setBusy(true)
    setError(null)
    try {
      await resyncExpectedLedger({ account_id: 'default' })
      const rows = await fetchAiExceptions({ account_id: 'default', status_filter: 'OPEN', limit: 200 })
      setItems(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to resync expected ledger')
    } finally {
      setBusy(false)
    }
  }

  const handleReconcile = async () => {
    setBusy(true)
    setError(null)
    try {
      await runAiReconcile({ account_id: 'default' })
      const rows = await fetchAiExceptions({ account_id: 'default', status_filter: 'OPEN', limit: 200 })
      setItems(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reconcile')
    } finally {
      setBusy(false)
    }
  }

  const handleAck = async (exceptionId: string) => {
    setBusy(true)
    setError(null)
    try {
      await ackAiException({ exception_id: exceptionId })
      const rows = await fetchAiExceptions({ account_id: 'default', status_filter: 'OPEN', limit: 200 })
      setItems(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to acknowledge exception')
    } finally {
      setBusy(false)
    }
  }

  if (!isAiAssistantEnabled()) {
    return (
      <Box>
        <Typography variant="h6">Exceptions Center</Typography>
        <Typography variant="body2" color="text.secondary">
          AI assistant is disabled.
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h6">Exceptions Center</Typography>
      {error && (
        <Typography variant="body2" color="error" sx={{ pt: 1 }}>
          {error}
        </Typography>
      )}
      <Stack direction="row" spacing={1} sx={{ pt: 1 }}>
        <Button onClick={handleResync} disabled={busy} size="small" variant="outlined">
          Resync expected ledger
        </Button>
        <Button onClick={handleReconcile} disabled={busy} size="small" variant="outlined">
          Reconcile now
        </Button>
      </Stack>
      <List>
        {items.map((ex) => (
          <Box key={ex.exception_id}>
            <ListItem>
              <ListItemText
                primary={`${ex.severity} • ${ex.exception_type}`}
                secondary={`${ex.summary} (${ex.key})`}
              />
              <Button
                onClick={() => void handleAck(ex.exception_id)}
                disabled={busy}
                size="small"
                variant="text"
              >
                Ack
              </Button>
            </ListItem>
            <Divider />
          </Box>
        ))}
        {items.length === 0 && (
          <ListItem>
            <ListItemText primary="No open exceptions." />
          </ListItem>
        )}
      </List>
    </Box>
  )
}
