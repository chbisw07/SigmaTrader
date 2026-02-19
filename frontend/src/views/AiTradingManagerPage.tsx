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
import Chip from '@mui/material/Chip'
import AttachFileIcon from '@mui/icons-material/AttachFile'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import {
  chatAi,
  fetchAiThread,
  fetchDecisionTrace,
  uploadAiFiles,
  type AiFileMeta,
  type AiTmMessage,
  type DecisionTrace,
} from '../services/aiTradingManager'

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

function JsonBlock({ value }: { value: unknown }) {
  return (
    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
      {JSON.stringify(value, null, 2)}
    </Typography>
  )
}

function RiskGateSummary({ trace }: { trace: DecisionTrace }) {
  const rg = trace.riskgate_result
  if (!rg) return null
  const outcome = (rg.outcome || '').toUpperCase()
  const color: 'success' | 'error' | 'default' = outcome === 'ALLOW' ? 'success' : outcome === 'DENY' ? 'error' : 'default'
  return (
    <Paper variant="outlined" sx={{ p: 1 }}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">RiskGate</Typography>
        <Chip size="small" color={color} label={outcome || 'UNKNOWN'} />
      </Stack>
      {rg.policy_version ? (
        <Typography variant="caption" color="text.secondary">
          Policy: {rg.policy_version}
          {rg.policy_hash ? ` • ${rg.policy_hash}` : ''}
        </Typography>
      ) : null}
      {rg.reasons?.length ? (
        <Box sx={{ mt: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            Reasons
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {rg.reasons.map((r) => `• ${r}`).join('\n')}
          </Typography>
        </Box>
      ) : null}
    </Paper>
  )
}

function TradePlanSummary({ trace }: { trace: DecisionTrace }) {
  const plan: any = (trace.final_outcome as any)?.trade_plan
  if (!plan) return null
  const intent = (plan.intent || {}) as any
  return (
    <Paper variant="outlined" sx={{ p: 1 }}>
      <Typography variant="subtitle2">TradePlan</Typography>
      <Stack spacing={0.25}>
        <Typography variant="caption" color="text.secondary">
          Plan ID: {plan.plan_id || '—'}
        </Typography>
        <Typography variant="body2">
          {String(intent.side || '—')} {Array.isArray(intent.symbols) ? intent.symbols.join(', ') : '—'} •{' '}
          {String(intent.product || '—')}
          {intent.risk_budget_pct != null ? ` • risk ${intent.risk_budget_pct}%` : ''}
        </Typography>
      </Stack>
    </Paper>
  )
}

function ExecutionSummary({ trace }: { trace: DecisionTrace }) {
  const exec: any = (trace.final_outcome as any)?.execution
  if (!exec) return null
  return (
    <Paper variant="outlined" sx={{ p: 1 }}>
      <Typography variant="subtitle2">Execution</Typography>
      <JsonBlock value={exec} />
    </Paper>
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
          {isUser && message.attachments?.length ? (
            <Typography variant="caption" color="text.secondary">
              Attachments: {message.attachments.map((a) => a.filename).join(', ')}
            </Typography>
          ) : null}

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
                  {trace ? <RiskGateSummary trace={trace} /> : null}
                  {trace ? <TradePlanSummary trace={trace} /> : null}
                  {trace ? <ExecutionSummary trace={trace} /> : null}
                  {trace?.tools_called?.length ? (
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2">Tool calls</Typography>
                      <TableContainer sx={{ mt: 0.5 }}>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Tool</TableCell>
                              <TableCell align="right">Duration (ms)</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {trace.tools_called.map((t, idx) => (
                              <TableRow key={`${t.tool_name}-${idx}`}>
                                <TableCell>{t.tool_name}</TableCell>
                                <TableCell align="right">{t.duration_ms ?? '—'}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Paper>
                  ) : null}
                  {trace?.final_outcome && !((trace.final_outcome as any)?.trade_plan || (trace.final_outcome as any)?.execution) ? (
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2">Final outcome</Typography>
                      <JsonBlock value={trace.final_outcome} />
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

  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

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
      let uploaded: AiFileMeta[] = []
      if (pendingFiles.length) {
        uploaded = await uploadAiFiles(pendingFiles)
      }
      await chatAi({
        account_id: 'default',
        message: content,
        context: {},
        attachments: uploaded.map((m) => ({ file_id: m.file_id, how: 'auto' })),
        ui_context: { page: 'ai' },
        signal: controller.signal as any,
      })
      await loadThread()
      setInput('')
      setPendingFiles([])
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

  const addFiles = (files: FileList | File[]) => {
    const next = [...pendingFiles]
    const list: File[] = Array.isArray(files) ? files : Array.from(files)
    for (const f of list) {
      const ext = f.name.split('.').pop()?.toLowerCase()
      if (ext !== 'csv' && ext !== 'xlsx') continue
      next.push(f)
    }
    setPendingFiles(next)
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
          borderColor: isDragging ? 'primary.main' : 'divider',
        }}
        onDragEnter={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setIsDragging(true)
        }}
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setIsDragging(true)
        }}
        onDragLeave={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setIsDragging(false)
        }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setIsDragging(false)
          if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files)
        }}
      >
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">
              Drag & drop CSV/XLSX here, or attach files.
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".csv,.xlsx"
                style={{ display: 'none' }}
                onChange={(e) => {
                  if (e.target.files?.length) addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
              <Tooltip title="Attach files">
                <IconButton size="small" onClick={() => fileInputRef.current?.click()} disabled={busy}>
                  <AttachFileIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Stack>
          {pendingFiles.length ? (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              {pendingFiles.map((f, idx) => (
                <Chip
                  key={`${f.name}-${idx}`}
                  label={`${f.name} (${Math.round(f.size / 1024)}KB)`}
                  onDelete={
                    busy
                      ? undefined
                      : () => setPendingFiles((prev) => prev.filter((_, i) => i !== idx))
                  }
                  size="small"
                  variant="outlined"
                />
              ))}
            </Stack>
          ) : null}
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
