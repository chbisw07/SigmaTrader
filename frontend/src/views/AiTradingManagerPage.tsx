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
import FormControl from '@mui/material/FormControl'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import {
  chatAiStream,
  createAiThread,
  fetchAiThreads,
  fetchAiThread,
  fetchDecisionTrace,
  uploadAiFiles,
  type AiFileMeta,
  type AiTmMessage,
  type AiThreadSummary,
  type AiChatStreamEvent,
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
  const rm = (plan.risk_model || {}) as any
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
        {rm.entry_price != null || rm.stop_price != null || rm.qty != null ? (
          <Typography variant="body2" color="text.secondary">
            entry {rm.entry_price ?? '—'} • stop {rm.stop_price ?? '—'} • qty {rm.qty ?? '—'}
          </Typography>
        ) : null}
      </Stack>
    </Paper>
  )
}

function ExecutionSummary({ trace }: { trace: DecisionTrace }) {
  const exec: any = (trace.final_outcome as any)?.execution
  if (!exec) return null
  const executed = Boolean(exec.executed)
  const veto = Boolean(exec.veto)
  const reason = exec.reason ? String(exec.reason) : null
  const pollStatus = exec.execution?.poll?.status ? String(exec.execution.poll.status) : null
  const orders = Array.isArray(exec.execution?.orders) ? exec.execution.orders : []
  return (
    <Paper variant="outlined" sx={{ p: 1 }}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">Execution</Typography>
        <Chip
          size="small"
          color={executed ? 'success' : veto ? 'error' : 'default'}
          label={executed ? 'EXECUTED' : veto ? 'VETO' : 'PENDING'}
        />
      </Stack>
      {reason ? (
        <Typography variant="caption" color="text.secondary">
          Reason: {reason}
        </Typography>
      ) : null}
      {pollStatus ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
          Poll: {pollStatus}
        </Typography>
      ) : null}
      {orders.length ? (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          Orders: {orders.map((o: any) => o.broker_order_id || o.order_id || '—').join(', ')}
        </Typography>
      ) : null}
      <Box sx={{ mt: 0.5 }}>
        <Accordion disableGutters elevation={0} sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
            <Typography variant="body2">Raw execution</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            <JsonBlock value={exec} />
          </AccordionDetails>
        </Accordion>
      </Box>
    </Paper>
  )
}

function MessageBubble({
  message,
  onLoadTrace,
  liveToolCalls,
}: {
  message: AiTmMessage
  onLoadTrace: (decisionId: string) => Promise<DecisionTrace | null>
  liveToolCalls?: Array<Record<string, unknown>>
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
                  {!trace && liveToolCalls?.length ? (
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2">Tool calls (live)</Typography>
                      <JsonBlock value={liveToolCalls} />
                    </Paper>
                  ) : null}
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
                      <Stack spacing={0.75} sx={{ mt: 0.5 }}>
                        {trace.tools_called.map((t, idx) => (
                          <Accordion
                            key={`${t.tool_name}-${idx}`}
                            disableGutters
                            elevation={0}
                            sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}
                          >
                            <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
                              <Stack
                                direction="row"
                                spacing={1}
                                alignItems="center"
                                sx={{ width: '100%', justifyContent: 'space-between' }}
                              >
                                <Typography variant="body2">{t.tool_name}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {t.duration_ms ?? '—'} ms
                                </Typography>
                              </Stack>
                            </AccordionSummary>
                            <AccordionDetails sx={{ pt: 0 }}>
                              <Stack spacing={0.75}>
                                <Typography variant="caption" color="text.secondary">
                                  Operator payload stored locally:{' '}
                                  {String(t.operator_payload_meta?.items_count ?? t.broker_raw_count ?? 0)} items •{' '}
                                  {String(t.operator_payload_meta?.payload_bytes ?? 0)} bytes
                                  {t.ui_rendered_count != null ? ` • UI rendered ${t.ui_rendered_count}` : ''}
                                  {t.llm_summary_count != null ? ` • Summary count ${t.llm_summary_count}` : ''}
                                  {t.truncation_reason ? ` • ${t.truncation_reason}` : ''}
                                </Typography>
                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                  Summary sent to LLM
                                </Typography>
                                <JsonBlock value={(t.llm_summary as any) ?? t.output_summary ?? {}} />
                              </Stack>
                            </AccordionDetails>
                          </Accordion>
                        ))}
                      </Stack>
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
  const accountId = 'default'
  const [messages, setMessages] = useState<AiTmMessage[]>([])
  const [threads, setThreads] = useState<AiThreadSummary[]>([])
  const [threadId, setThreadId] = useState<string>(() => {
    if (typeof window === 'undefined') return 'default'
    try {
      return window.localStorage.getItem('st_ai_thread_id_v1') || 'default'
    } catch {
      return 'default'
    }
  })
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoscroll, setAutoscroll] = useState(true)
  const abortRef = useRef<AbortController | null>(null)
  const [liveToolCallsByDecision, setLiveToolCallsByDecision] = useState<Record<string, any[]>>({})

  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const scrollRef = useRef<HTMLDivElement | null>(null)

  const loadThreads = async () => {
    const out = await fetchAiThreads({ account_id: accountId, limit: 50 })
    setThreads(out)
  }

  const loadThread = async (tid?: string) => {
    const thread = await fetchAiThread({ account_id: accountId, thread_id: tid ?? threadId })
    setMessages(thread.messages ?? [])
  }

  useEffect(() => {
    let active = true
    const run = async () => {
      try {
        await loadThreads()
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
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem('st_ai_thread_id_v1', threadId)
    } catch {
      // ignore
    }
    void loadThread(threadId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId])

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

      const localUserId = `local-${Date.now()}-u`
      const localAsstId = `local-${Date.now()}-a`
      const nowIso = new Date().toISOString()
      setMessages((prev) => [
        ...prev,
        {
          message_id: localUserId,
          role: 'user',
          content,
          created_at: nowIso,
          attachments: uploaded.map((m) => ({ file_id: m.file_id, filename: m.filename, size: m.size, mime: m.mime })),
        },
        {
          message_id: localAsstId,
          role: 'assistant',
          content: '',
          created_at: nowIso,
        },
      ])

      let currentDecisionId: string | null = null
      const onEvent = (ev: AiChatStreamEvent) => {
        if (ev.type === 'decision') {
          currentDecisionId = ev.decision_id
          setMessages((prev) =>
            prev.map((m) => (m.message_id === localAsstId ? { ...m, decision_id: ev.decision_id } : m)),
          )
        } else if (ev.type === 'assistant_delta') {
          setMessages((prev) =>
            prev.map((m) => (m.message_id === localAsstId ? { ...m, content: (m.content || '') + ev.text } : m)),
          )
        } else if (ev.type === 'tool_call') {
          const did = currentDecisionId
          if (!did) return
          setLiveToolCallsByDecision((prev) => ({ ...prev, [did]: [...(prev[did] ?? []), ev as any] }))
        }
      }

      await chatAiStream({
        account_id: accountId,
        thread_id: threadId,
        message: content,
        context: {},
        attachments: uploaded.map((m) => ({ file_id: m.file_id, how: 'auto' })),
        ui_context: { page: 'ai' },
        signal: controller.signal as any,
        onEvent,
      })

      await loadThreads()
      await loadThread()
      setInput('')
      setPendingFiles([])
      setLiveToolCallsByDecision({})
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
        <Stack direction="row" spacing={1} alignItems="center">
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <Select
              value={threadId}
              onChange={(e) => setThreadId(String(e.target.value))}
              displayEmpty
              disabled={busy}
            >
              <MenuItem value="default">Default</MenuItem>
              {threads
                .filter((t) => t.thread_id !== 'default')
                .map((t) => (
                  <MenuItem key={t.thread_id} value={t.thread_id}>
                    {t.title}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
          <Button
            size="small"
            variant="outlined"
            onClick={async () => {
              const t = await createAiThread({ account_id: accountId })
              setThreadId(t.thread_id)
            }}
            disabled={busy}
          >
            New chat
          </Button>
          {!autoscroll && (
            <Button size="small" variant="outlined" onClick={() => setAutoscroll(true)}>
              Jump to latest
            </Button>
          )}
        </Stack>
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
              <MessageBubble
                key={m.message_id}
                message={m}
                onLoadTrace={onLoadTrace}
                liveToolCalls={m.decision_id ? liveToolCallsByDecision[m.decision_id] : undefined}
              />
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
