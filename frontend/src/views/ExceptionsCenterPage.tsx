import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Divider from '@mui/material/Divider'

import { fetchAiExceptions, type AiTmException } from '../services/aiTradingManager'
import { isAiAssistantEnabled } from '../config/aiFeatures'

export function ExceptionsCenterPage() {
  const [items, setItems] = useState<AiTmException[]>([])
  const [error, setError] = useState<string | null>(null)

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
      <List>
        {items.map((ex) => (
          <Box key={ex.exception_id}>
            <ListItem>
              <ListItemText
                primary={`${ex.severity} • ${ex.exception_type}`}
                secondary={`${ex.summary} (${ex.key})`}
              />
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

