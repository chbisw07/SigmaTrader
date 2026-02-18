import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { fetchAiThread, postAiMessage, runAiReconcile, type AiTmMessage } from '../../services/aiTradingManager'

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
  const [messages, setMessages] = useState<AiTmMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
      const resp = await postAiMessage({ account_id: 'default', content })
      setMessages(resp.thread.messages ?? [])
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

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>
        {error && (
          <Typography variant="body2" color="error" sx={{ pb: 1 }}>
            {error}
          </Typography>
        )}
        {messages.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No messages yet.
          </Typography>
        ) : (
          messages.map((m) => <MessageRow key={m.message_id} m={m} />)
        )}
      </Box>
      <Divider />
      <Box sx={{ px: 2, py: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ pb: 1 }}>
          <Button onClick={handleReconcile} disabled={busy} size="small" variant="outlined">
            Reconcile
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

