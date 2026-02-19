import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Paper from '@mui/material/Paper'
import Alert from '@mui/material/Alert'

import {
  chatAi,
  fetchAiThread,
  fetchPortfolioDiagnostics,
  fetchDecisionTrace,
  type AiChatToolCall,
  runAiReconcile,
  type AiTmMessage,
  type DecisionTrace,
} from '../../services/aiTradingManager'
import { isAiExecutionEnabled } from '../../config/aiFeatures'

function MessageRow({ m }: { m: AiTmMessage }) {
  const label = useMemo(() => (m.role === 'user' ? 'You' : m.role === 'assistant' ? 'Assistant' : 'System'), [m.role])
  return (
    <Box sx={{ py: 1 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
        {m.decision_id ? ` • trace ${m.decision_id}` : ''}
      </Typography>
      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
        {m.content}
      </Typography>
    </Box>
  )
}

export function AssistantPanel() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<AiTmMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [contextText, setContextText] = useState<string | null>(null)
  const [lastDecisionId, setLastDecisionId] = useState<string | null>(null)
  const [lastToolCalls, setLastToolCalls] = useState<AiChatToolCall[]>([])
  const [lastTrace, setLastTrace] = useState<DecisionTrace | null>(null)

  useEffect(() => {
    let active = true
    const run = async () => {
      try {
        const thread = await fetchAiThread({ account_id: 'default' })
        if (!active) return
        setMessages(thread.messages ?? [])
      } catch (e) {
        if (!active) return
        setError(e instanceof Error ? e.message : 'Failed to load assistant thread')
      }
    }
    void run()
    return () => {
      active = false
    }
  }, [])

  const handleSend = async () => {
    const content = input.trim()
    if (!content) return
    setBusy(true)
    setError(null)
    try {
      const resp = await chatAi({ account_id: 'default', message: content, context: {} })
      setLastDecisionId(resp.decision_id)
      setLastToolCalls(resp.tool_calls ?? [])
      try {
        const tr = await fetchDecisionTrace(resp.decision_id)
        setLastTrace(tr)
      } catch {
        setLastTrace(null)
      }
      if (resp.thread?.messages) {
        setMessages(resp.thread.messages ?? [])
      } else {
        const thread = await fetchAiThread({ account_id: 'default' })
        setMessages(thread.messages ?? [])
      }
      setInput('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send message')
    } finally {
      setBusy(false)
    }
  }

  const handleReconcile = async () => {
    setBusy(true)
    setError(null)
    try {
      await runAiReconcile({ account_id: 'default' })
      const thread = await fetchAiThread({ account_id: 'default' })
      setMessages(thread.messages ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reconcile')
    } finally {
      setBusy(false)
    }
  }

  const handleContext = async () => {
    setBusy(true)
    setError(null)
    try {
      const diag = await fetchPortfolioDiagnostics({ account_id: 'default' })
      const items = diag.market_context?.items ?? []
      if (items.length === 0) {
        setContextText('No market context yet (missing candles).')
        return
      }
      const lines = items.slice(0, 8).map((it) => {
        const vol = typeof it.vol20_ann_pct === 'number' ? `${it.vol20_ann_pct.toFixed(1)}%` : '—'
        return `${it.symbol}: trend=${it.trend_regime}, vol=${it.volatility_regime} (${vol})`
      })
      setContextText(lines.join('\n'))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load context')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>
        {!isAiExecutionEnabled() && (
          <Alert severity="info" sx={{ mb: 1 }}>
            AI execution is disabled. The assistant will propose plans but won’t place orders.
          </Alert>
        )}
        {error && (
          <Typography variant="body2" color="error" sx={{ pb: 1 }}>
            {error}
          </Typography>
        )}
        {contextText && (
          <Box sx={{ pb: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Context
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
              {contextText}
            </Typography>
            <Divider sx={{ mt: 1.25 }} />
          </Box>
        )}
        {messages.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No messages yet.
          </Typography>
        ) : (
          messages.map((m) => <MessageRow key={m.message_id} m={m} />)
        )}

        {lastDecisionId && (
          <Box sx={{ pt: 1 }}>
            <Divider sx={{ my: 1.25 }} />
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', pb: 1 }}>
              <Typography variant="subtitle2" sx={{ flex: 1, minWidth: 180 }}>
                Tool calls (latest)
              </Typography>
              <Button
                size="small"
                variant="outlined"
                onClick={() => navigate(`/ai/decision-traces/${encodeURIComponent(lastDecisionId)}`)}
              >
                View trace
              </Button>
            </Stack>
            {lastTrace?.final_outcome && (lastTrace.final_outcome as any)['trade_plan'] && (
              <Paper variant="outlined" sx={{ p: 1, mb: 1 }}>
                <Typography variant="subtitle2">Trade Plan</Typography>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify((lastTrace.final_outcome as any)['trade_plan'], null, 2)}
                </Typography>
              </Paper>
            )}
            {(lastTrace?.riskgate_result || (lastTrace?.final_outcome as any)?.['riskgate']) && (
              <Paper variant="outlined" sx={{ p: 1, mb: 1 }}>
                <Typography variant="subtitle2">RiskGate</Typography>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(
                    lastTrace.riskgate_result ?? ((lastTrace?.final_outcome as any)?.['riskgate'] ?? {}),
                    null,
                    2
                  )}
                </Typography>
              </Paper>
            )}
            {lastTrace?.final_outcome && (lastTrace.final_outcome as any)['execution'] && (
              <Paper variant="outlined" sx={{ p: 1, mb: 1 }}>
                <Typography variant="subtitle2">Execution</Typography>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify((lastTrace.final_outcome as any)['execution'], null, 2)}
                </Typography>
              </Paper>
            )}
            {lastToolCalls.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No tool calls.
              </Typography>
            ) : (
              <Stack spacing={1}>
                {lastToolCalls.map((t, idx) => (
                  <Paper key={`${t.name}-${idx}`} variant="outlined" sx={{ p: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {t.name} • {t.status} • {t.duration_ms}ms
                    </Typography>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                      args: {JSON.stringify(t.arguments ?? {}, null, 2)}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', pt: 0.5 }}
                      color={t.status === 'error' || t.status === 'blocked' ? 'error' : 'text.primary'}
                    >
                      {t.result_preview}
                    </Typography>
                  </Paper>
                ))}
              </Stack>
            )}
          </Box>
        )}
      </Box>
      <Divider />
      <Box sx={{ px: 2, py: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ pb: 1 }}>
          <Button onClick={handleReconcile} disabled={busy} size="small" variant="outlined">
            Reconcile
          </Button>
          <Button onClick={handleContext} disabled={busy} size="small" variant="outlined">
            Context
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="flex-end">
          <TextField
            value={input}
            onChange={(e) => setInput(e.target.value)}
            fullWidth
            label="Message"
            size="small"
            multiline
            minRows={2}
          />
          <Button onClick={handleSend} disabled={busy || !input.trim()} variant="contained">
            Send
          </Button>
        </Stack>
      </Box>
    </Box>
  )
}
