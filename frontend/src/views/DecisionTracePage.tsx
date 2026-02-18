import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'

import { fetchDecisionTrace, type DecisionTrace } from '../services/aiTradingManager'
import { isAiAssistantEnabled } from '../config/aiFeatures'

export function DecisionTracePage() {
  const { decisionId } = useParams()
  const [trace, setTrace] = useState<DecisionTrace | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const run = async () => {
      if (!decisionId || !isAiAssistantEnabled()) return
      try {
        const t = await fetchDecisionTrace(decisionId)
        if (!active) return
        setTrace(t)
      } catch (e) {
        if (!active) return
        setError(e instanceof Error ? e.message : 'Failed to load DecisionTrace')
      }
    }
    void run()
    return () => {
      active = false
    }
  }, [decisionId])

  if (!isAiAssistantEnabled()) {
    return (
      <Box>
        <Typography variant="h6">Decision Trace</Typography>
        <Typography variant="body2" color="text.secondary">
          AI assistant is disabled.
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h6">Decision Trace</Typography>
      {!decisionId && (
        <Typography variant="body2" color="text.secondary">
          Missing decision id.
        </Typography>
      )}
      {error && (
        <Typography variant="body2" color="error" sx={{ pt: 1 }}>
          {error}
        </Typography>
      )}
      {trace && (
        <Stack spacing={1} sx={{ pt: 1 }}>
          <Typography variant="body2">Decision: {trace.decision_id}</Typography>
          <Typography variant="body2">Correlation: {trace.correlation_id}</Typography>
          <Typography variant="body2">Created: {trace.created_at}</Typography>
          <Divider />
          <Typography variant="subtitle2">User message</Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {trace.user_message}
          </Typography>
          <Divider />
          <Typography variant="subtitle2">Outcome</Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
            {JSON.stringify(trace.final_outcome ?? {}, null, 2)}
          </Typography>
        </Stack>
      )}
    </Box>
  )
}

