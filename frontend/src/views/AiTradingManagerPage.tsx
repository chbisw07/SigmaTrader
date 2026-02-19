import { useEffect, useMemo, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Accordion from '@mui/material/Accordion'
import AccordionSummary from '@mui/material/AccordionSummary'
import AccordionDetails from '@mui/material/AccordionDetails'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import Link from '@mui/material/Link'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { chatAi, fetchAiThread, fetchDecisionTrace, type AiTmMessage, type DecisionTrace } from '../services/aiTradingManager'

function MarkdownView({ text }: { text: string }) {
  const components = useMemo(
    () => ({
      table: ({ children }: any) => (
        <TableContainer component={Paper} variant="outlined" sx={{ my: 1 }}>
          <Table size="small">{children}</Table>
        </TableContainer>
      ),
      thead: ({ children }: any) => <TableHead>{children}</TableHead>,
      tbody: ({ children }: any) => <TableBody>{children}</TableBody>,
      tr: ({ children }: any) => <TableRow>{children}</TableRow>,
      th: ({ children }: any) => (
        <TableCell component="th" sx={{ fontWeight: 700 }}>
          {children}
        </TableCell>
      ),
      td: ({ children }: any) => <TableCell>{children}</TableCell>,
      a: ({ href, children }: any) => (
        <Link href={href} target="_blank" rel="noreferrer">
          {children}
        </Link>
      ),
      code: ({ inline, children }: any) =>
        inline ? (
          <Box component="code" sx={{ fontFamily: 'monospace', bgcolor: 'action.hover', px: 0.5, borderRadius: 0.5 }}>
            {children}
          </Box>
        ) : (
          <Box
            component="pre"
            sx={{
              fontFamily: 'monospace',
              bgcolor: 'action.hover',
              p: 1,
              borderRadius: 1,
              overflowX: 'auto',
            }}
          >
            <code>{children}</code>
          </Box>
        ),
    }),
    [],
  )

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components as any}>
      {text}
    </ReactMarkdown>
  )
}

function MessageBubble({
  message,
  onLoadTrace,
}: {
  message: AiTmMessage
  onLoadTrace: (decisionId: string) => Promise<DecisionTrace | null>
}) {
  const isUser = message.role === 'user'
  const [trace, setTrace] = useState<DecisionTrace | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)

  const handleExpand = async (expanded: boolean) => {
    if (!expanded) return
    if (!message.decision_id || trace || traceLoading) return
    setTraceLoading(true)
    try {
      const tr = await onLoadTrace(message.decision_id)
      setTrace(tr)
    } finally {
      setTraceLoading(false)
    }
  }

  return (
    <Box sx={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <Paper
        variant="outlined"
        sx={{
          maxWidth: 'min(860px, 100%)',
          px: 1.5,
          py: 1.25,
          bgcolor: isUser ? 'action.selected' : 'background.paper',
          borderRadius: 2,
        }}
      >
        <Stack spacing={0.5}>
          <Typography variant="caption" color="text.secondary">
            {isUser ? 'You' : 'Assistant'}
            {message.decision_id ? ` • trace ${message.decision_id}` : ''}
          </Typography>
          {isUser ? (
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
              {message.content}
            </Typography>
          ) : (
            <Box sx={{ '& > :first-of-type': { mt: 0 } }}>
              <MarkdownView text={message.content} />
            </Box>
          )}

          {message.decision_id && (
            <Accordion
              disableGutters
              elevation={0}
              onChange={(_, expanded) => void handleExpand(expanded)}
              sx={{
                mt: 0.5,
                bgcolor: 'transparent',
                '&:before': { display: 'none' },
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
                <Typography variant="body2">Tool calls & DecisionTrace</Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0 }}>
                <Stack spacing={1}>
                  <Button
                    size="small"
                    variant="outlined"
                    href={`/ai/decision-traces/${encodeURIComponent(message.decision_id)}`}
                  >
                    Open trace viewer
                  </Button>
                  {traceLoading && (
                    <Stack direction="row" spacing={1} alignItems="center">
                      <CircularProgress size={16} />
                      <Typography variant="body2" color="text.secondary">
                        Loading trace…
                      </Typography>
                    </Stack>
                  )}
                  {trace?.tools_called?.length ? (
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2">Tool calls</Typography>
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                        {JSON.stringify(trace.tools_called, null, 2)}
                      </Typography>
                    </Paper>
                  ) : null}
                  {trace?.final_outcome ? (
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2">Final outcome</Typography>
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                        {JSON.stringify(trace.final_outcome, null, 2)}
                      </Typography>
                    </Paper>
                  ) : null}
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}
        </Stack>
      </Paper>
    </Box>
  )
}

export function AiTradingManagerPage() {
  const [messages, setMessages] = useState<AiTmMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoscroll, setAutoscroll] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  const scrollRef = useRef<HTMLDivElement | null>(null)

  const loadThread = async () => {
    const thread = await fetchAiThread({ account_id: 'default', thread_id: 'default' })
    setMessages(thread.messages ?? [])
  }

  useEffect(() => {
    let active = true
    const run = async () => {
      try {
        await loadThread()
      } catch (e) {
        if (!active) return
        setError(e instanceof Error ? e.message : 'Failed to load AI thread')
      }
    }
    void run()
    return () => {
      active = false
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!autoscroll) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, autoscroll, busy])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    setAutoscroll(atBottom)
  }

  const handleSend = async () => {
    const content = input.trim()
    if (!content || busy) return
    setBusy(true)
    setError(null)
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await chatAi({ account_id: 'default', message: content, context: {}, signal: controller.signal as any })
      await loadThread()
      setInput('')
      setAutoscroll(true)
    } catch (e) {
      if (controller.signal.aborted) {
        setError('Stopped.')
      } else {
        setError(e instanceof Error ? e.message : 'Failed to send message')
      }
    } finally {
      setBusy(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
  }

  const onLoadTrace = async (decisionId: string) => {
    try {
      return await fetchDecisionTrace(decisionId)
    } catch {
      return null
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)' }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ pb: 1 }}>
        <Box>
          <Typography variant="h5">AI Trading Manager</Typography>
          <Typography variant="body2" color="text.secondary">
            Ask questions, propose trades, and (when enabled) execute policy‑gated actions with a full audit trail.
          </Typography>
        </Box>
        {!autoscroll && (
          <Button size="small" variant="outlined" onClick={() => setAutoscroll(true)}>
            Jump to latest
          </Button>
        )}
      </Stack>

      <Paper
        variant="outlined"
        sx={{
          flex: 1,
          minHeight: 0,
          overflow: 'auto',
          p: 2,
          bgcolor: 'background.default',
        }}
        ref={scrollRef}
        onScroll={handleScroll}
      >
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
          <Stack spacing={1.25}>
            {messages.map((m) => (
              <MessageBubble key={m.message_id} message={m} onLoadTrace={onLoadTrace} />
            ))}
          </Stack>
        )}
      </Paper>

      <Divider sx={{ my: 1.5 }} />

      <Paper
        variant="outlined"
        sx={{
          p: 1.5,
          position: 'sticky',
          bottom: 12,
          bgcolor: 'background.paper',
        }}
      >
        <Stack spacing={1}>
          <TextField
            label="Message"
            placeholder="Ask about holdings, positions, margins…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            multiline
            minRows={3}
            maxRows={10}
            fullWidth
            disabled={busy}
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
            {busy ? (
              <Button size="small" variant="outlined" onClick={handleStop}>
                Stop
              </Button>
            ) : null}
            <Button variant="contained" onClick={handleSend} disabled={busy || !input.trim()}>
              {busy ? <CircularProgress size={18} /> : 'Send'}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  )
}

