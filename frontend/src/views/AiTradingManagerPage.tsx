import { useEffect, useMemo, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Alert from '@mui/material/Alert'
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
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import EditIcon from '@mui/icons-material/Edit'
import FormatQuoteIcon from '@mui/icons-material/FormatQuote'
import ReplayIcon from '@mui/icons-material/Replay'
import ImageIcon from '@mui/icons-material/Image'
import DescriptionIcon from '@mui/icons-material/Description'
import FormControl from '@mui/material/FormControl'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Tabs from '@mui/material/Tabs'
import Tab from '@mui/material/Tab'
import { useSearchParams } from 'react-router-dom'

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
import { AiCoveragePanel } from '../components/ai/AiCoveragePanel'
import { AiJournalPanel } from '../components/ai/AiJournalPanel'

type AttachmentRef = NonNullable<AiTmMessage['attachments']>[number]

async function copyTextToClipboard(text: string): Promise<boolean> {
  const raw = String(text ?? '')
  try {
    await navigator.clipboard.writeText(raw)
    return true
  } catch {
    // Fallback for older browsers / denied permissions.
    try {
      const el = document.createElement('textarea')
      el.value = raw
      el.style.position = 'fixed'
      el.style.left = '-9999px'
      document.body.appendChild(el)
      el.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(el)
      return ok
    } catch {
      return false
    }
  }
}

function isImageLike(name: string, mime?: string | null): boolean {
  const mt = (mime || '').toLowerCase()
  if (mt.startsWith('image/')) return true
  const ext = (name.split('.').pop() || '').toLowerCase()
  return ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)
}

function formatBytes(n?: number | null): string {
  const b = Number(n || 0)
  if (!Number.isFinite(b) || b <= 0) return '0B'
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${Math.round(b / 1024)}KB`
  return `${(b / (1024 * 1024)).toFixed(1)}MB`
}

function cellText(node: Element | null): string {
  const t = (node?.textContent ?? '').trim()
  return t.replace(/\r?\n+/g, '<br>').replace(/\s+/g, ' ')
}

function escapeMdCell(text: string): string {
  return text.replace(/\|/g, '\\|')
}

function tableToMarkdown(tableEl: HTMLTableElement): string {
  const headRows = Array.from(tableEl.querySelectorAll('thead tr'))
  const bodyRows = Array.from(tableEl.querySelectorAll('tbody tr'))
  const allRows = headRows.length ? [...headRows, ...bodyRows] : Array.from(tableEl.querySelectorAll('tr'))

  const grid = allRows.map((tr) => Array.from(tr.querySelectorAll('th,td')).map((c) => escapeMdCell(cellText(c))))
  if (!grid.length) return ''

  const colCount = Math.max(...grid.map((r) => r.length))
  const norm = grid.map((r) => (r.length === colCount ? r : [...r, ...Array.from({ length: colCount - r.length }, () => '')]))

  const header = headRows.length ? norm[0] : norm[0]
  const body = headRows.length ? norm.slice(1) : norm.slice(1)

  const headerLine = `| ${header.join(' | ')} |`
  const sepLine = `| ${Array.from({ length: colCount }, () => '---').join(' | ')} |`
  const bodyLines = body.map((r) => `| ${r.join(' | ')} |`)

  return [headerLine, sepLine, ...bodyLines].join('\n')
}

function CopyableMarkdownTable({ children }: { children: any }) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [copied, setCopied] = useState(false)

  const doCopy = async () => {
    const tableEl = wrapRef.current?.querySelector('table') as HTMLTableElement | null
    if (!tableEl) return
    const md = tableToMarkdown(tableEl)
    if (!md) return
    const ok = await copyTextToClipboard(md)
    if (!ok) return
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }

  return (
    <Box ref={wrapRef} sx={{ position: 'relative', my: 1 }}>
      <Tooltip title={copied ? 'Copied' : 'Copy table as Markdown'}>
        <IconButton
          size="small"
          onClick={() => void doCopy()}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            bgcolor: 'background.paper',
            border: 1,
            borderColor: 'divider',
            '&:hover': { bgcolor: 'action.hover' },
            zIndex: 1,
          }}
        >
          <ContentCopyIcon fontSize="inherit" />
        </IconButton>
      </Tooltip>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">{children}</Table>
      </TableContainer>
    </Box>
  )
}

function PendingAttachmentPill({
  file,
  attachmentRef,
  onRemove,
}: {
  file?: File | null
  attachmentRef?: AttachmentRef | null
  onRemove: () => void
}) {
  const name = file?.name ?? attachmentRef?.filename ?? 'attachment'
  const mime = file?.type ?? attachmentRef?.mime ?? null
  const size = file?.size ?? attachmentRef?.size ?? null
  const image = isImageLike(name, mime)

  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!file || !image) {
      setBlobUrl(null)
      return
    }
    const mk = (URL as any)?.createObjectURL as ((f: Blob) => string) | undefined
    const rv = (URL as any)?.revokeObjectURL as ((u: string) => void) | undefined
    if (typeof mk !== 'function') return
    const u = mk(file)
    setBlobUrl(u)
    return () => {
      if (typeof rv === 'function') rv(u)
    }
  }, [file, image])

  const inlineUrl = attachmentRef?.file_id && image ? `/api/ai/files/${encodeURIComponent(attachmentRef.file_id)}/raw` : null

  return (
    <Paper
      variant="outlined"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        px: 1,
        py: 0.5,
        borderRadius: 2,
      }}
    >
      {image ? (
        <Box
          sx={{
            width: 44,
            height: 44,
            borderRadius: 1,
            overflow: 'hidden',
            bgcolor: 'action.hover',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Box
            component="img"
            src={blobUrl || inlineUrl || undefined}
            alt={name}
            sx={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={(e) => {
              ;(e.currentTarget as any).style.display = 'none'
            }}
          />
          {!blobUrl && !inlineUrl ? <ImageIcon fontSize="small" /> : null}
        </Box>
      ) : (
        <DescriptionIcon fontSize="small" />
      )}
      <Box sx={{ minWidth: 120, maxWidth: 280 }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap title={name}>
          {name}
        </Typography>
        <Typography variant="caption" color="text.secondary" noWrap>
          {mime || 'file'} • {formatBytes(size)}
          {attachmentRef?.file_id ? ' • saved' : ''}
        </Typography>
      </Box>
      <Box sx={{ flex: 1 }} />
      <Tooltip title="Remove">
        <IconButton size="small" onClick={onRemove}>
          <Box component="span" sx={{ fontSize: 14, lineHeight: 1 }}>
            ×
          </Box>
        </IconButton>
      </Tooltip>
    </Paper>
  )
}

function MarkdownView({ text }: { text: string }) {
  const components = useMemo(
    () => ({
      table: ({ children }: any) => <CopyableMarkdownTable>{children}</CopyableMarkdownTable>,
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
  canRetry,
  onRetry,
  onQuote,
  onEdit,
  onLoadTrace,
  liveToolCalls,
}: {
  message: AiTmMessage
  canRetry: boolean
  onRetry: () => void
  onQuote: (m: AiTmMessage) => void
  onEdit: (m: AiTmMessage) => void
  onLoadTrace: (decisionId: string) => Promise<DecisionTrace | null>
  liveToolCalls?: Array<Record<string, unknown>>
}) {
  const isUser = message.role === 'user'
  const [trace, setTrace] = useState<DecisionTrace | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [copied, setCopied] = useState(false)

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

  const handleCopy = async () => {
    const base = String(message.content ?? '')
    const attachments = isUser && message.attachments?.length ? message.attachments : []
    const md =
      attachments.length > 0
        ? `${base}\n\nAttachments:\n${attachments.map((a) => `- ${a.filename} (${a.mime || 'file'}, ${a.size} bytes)`).join('\n')}`
        : base
    const ok = await copyTextToClipboard(md)
    if (!ok) return
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
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
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">
              {isUser ? 'You' : 'Assistant'}
              {message.decision_id ? ` • trace ${message.decision_id}` : ''}
            </Typography>
            <Stack direction="row" spacing={0.25} alignItems="center">
              {!isUser && canRetry ? (
                <Tooltip title="Retry (resend last user message)">
                  <IconButton size="small" onClick={onRetry}>
                    <ReplayIcon fontSize="inherit" />
                  </IconButton>
                </Tooltip>
              ) : null}
              <Tooltip title="Quote into prompt">
                <IconButton size="small" onClick={() => onQuote(message)}>
                  <FormatQuoteIcon fontSize="inherit" />
                </IconButton>
              </Tooltip>
              {isUser ? (
                <Tooltip title="Edit & resend">
                  <IconButton size="small" onClick={() => onEdit(message)}>
                    <EditIcon fontSize="inherit" />
                  </IconButton>
                </Tooltip>
              ) : null}
              <Tooltip title={copied ? 'Copied' : 'Copy as Markdown'}>
                <IconButton size="small" onClick={() => void handleCopy()}>
                  <ContentCopyIcon fontSize="inherit" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Stack>
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
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', pt: 0.25 }}>
              {message.attachments.map((a) => {
                const img = isImageLike(a.filename, a.mime)
                const inlineUrl = img ? `/api/ai/files/${encodeURIComponent(a.file_id)}/raw` : null
                return (
                  <Paper
                    key={a.file_id}
                    variant="outlined"
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      px: 1,
                      py: 0.5,
                      borderRadius: 2,
                      cursor: 'pointer',
                    }}
                    onClick={() => window.open(`/api/ai/files/${encodeURIComponent(a.file_id)}/download`, '_blank')}
                    title="Open attachment"
                  >
                    {img ? (
                      <Box
                        sx={{
                          width: 36,
                          height: 36,
                          borderRadius: 1,
                          overflow: 'hidden',
                          bgcolor: 'action.hover',
                        }}
                      >
                        <Box
                          component="img"
                          src={inlineUrl || undefined}
                          alt={a.filename}
                          sx={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={(e) => {
                            ;(e.currentTarget as any).style.display = 'none'
                          }}
                        />
                      </Box>
                    ) : (
                      <DescriptionIcon fontSize="small" />
                    )}
                    <Box sx={{ minWidth: 120, maxWidth: 300 }}>
                      <Typography variant="caption" sx={{ fontWeight: 600 }} noWrap>
                        {a.filename}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {a.mime || 'file'} • {formatBytes(a.size)}
                      </Typography>
                    </Box>
                  </Paper>
                )
              })}
            </Stack>
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
                      <Table size="small" sx={{ mt: 0.5 }}>
                        <TableHead>
                          <TableRow>
                            <TableCell>Tool</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Duration</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {liveToolCalls.slice(-20).map((t: any, idx: number) => (
                            <TableRow key={`${String(t?.name || 'tool')}-${idx}`}>
                              <TableCell sx={{ fontFamily: 'monospace' }}>{String(t?.name || '—')}</TableCell>
                              <TableCell>{String(t?.status || '—')}</TableCell>
                              <TableCell>{t?.duration_ms != null ? `${t.duration_ms}ms` : '—'}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
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
                      <Table size="small" sx={{ mt: 0.5 }}>
                        <TableHead>
                          <TableRow>
                            <TableCell>Tool</TableCell>
                            <TableCell>Duration</TableCell>
                            <TableCell>Payload</TableCell>
                            <TableCell>Notes</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {trace.tools_called.map((t, idx) => (
                            <TableRow key={`${t.tool_name}-${idx}`}>
                              <TableCell sx={{ fontFamily: 'monospace' }}>{t.tool_name}</TableCell>
                              <TableCell>{t.duration_ms != null ? `${t.duration_ms}ms` : '—'}</TableCell>
                              <TableCell>
                                {t.operator_payload_meta?.items_count ?? t.broker_raw_count ?? 0} items •{' '}
                                {t.operator_payload_meta?.payload_bytes ?? 0} bytes
                              </TableCell>
                              <TableCell>{t.truncation_reason || '—'}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      <Stack spacing={0.75} sx={{ mt: 1 }}>
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
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') || 'chat').toLowerCase()
  const shadowParam = searchParams.get('shadow') || ''

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
  const [pendingAttachmentRefs, setPendingAttachmentRefs] = useState<AttachmentRef[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const promptRef = useRef<HTMLTextAreaElement | null>(null)

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

  const sendMessage = async (opts: {
    content: string
    files?: File[]
    attachmentRefs?: AttachmentRef[]
    clearDraft?: boolean
  }) => {
    const content = opts.content.trim()
    if (!content || busy) return
    setBusy(true)
    setError(null)
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const files = opts.files ?? pendingFiles
      const refs = opts.attachmentRefs ?? pendingAttachmentRefs
      let uploaded: AiFileMeta[] = []
      if (files.length) {
        uploaded = await uploadAiFiles(files)
      }

      const attachmentRows: AttachmentRef[] = []
      const seen = new Set<string>()
      for (const a of [...uploaded.map((m) => ({ file_id: m.file_id, filename: m.filename, size: m.size, mime: m.mime })), ...refs]) {
        if (!a?.file_id || seen.has(a.file_id)) continue
        seen.add(a.file_id)
        attachmentRows.push(a)
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
          attachments: attachmentRows,
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
        attachments: attachmentRows.map((a) => ({ file_id: a.file_id, how: 'auto' })),
        ui_context: { page: 'ai' },
        signal: controller.signal as any,
        onEvent,
      })

      await loadThreads()
      await loadThread()
      if (opts.clearDraft !== false) {
        setInput('')
        setPendingFiles([])
        setPendingAttachmentRefs([])
      }
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

  const handleSend = async () => {
    return sendMessage({ content: input, clearDraft: true })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (busy) {
        handleStop()
      } else {
        setInput('')
        setPendingFiles([])
        setPendingAttachmentRefs([])
        setError(null)
      }
      return
    }
    if (e.key === 'ArrowUp' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !busy && !input.trim()) {
      const ta = e.target as HTMLTextAreaElement
      if (ta?.selectionStart === 0 && ta?.selectionEnd === 0) {
        const last = [...messages].reverse().find((m) => m.role === 'user' && String(m.content || '').trim())
        if (last) {
          e.preventDefault()
          setInput(last.content)
          setPendingFiles([])
          setPendingAttachmentRefs(last.attachments ?? [])
          window.setTimeout(() => promptRef.current?.focus(), 0)
        }
      }
      return
    }
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
    const list: File[] = Array.isArray(files) ? files : Array.from(files)
    const rejected: string[] = []
    setPendingFiles((prev) => {
      const next = [...prev]
      for (const f of list) {
        const ext = f.name.split('.').pop()?.toLowerCase() || ''
        const isCsv = ext === 'csv'
        const isXlsx = ext === 'xlsx'
        const isImage = (f.type || '').toLowerCase().startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)
        if (!isCsv && !isXlsx && !isImage) {
          rejected.push(f.name || 'file')
          continue
        }
        const key = `${f.name}:${f.size}:${f.lastModified}`
        const exists = next.some((x) => `${x.name}:${x.size}:${x.lastModified}` === key)
        if (!exists) next.push(f)
      }
      return next
    })
    if (rejected.length) {
      setError(`Unsupported attachment(s): ${rejected.join(', ')}. Supported: .csv, .xlsx, images.`)
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData?.items ?? [])
    const files: File[] = []
    for (const it of items) {
      if (it.kind !== 'file') continue
      const f = it.getAsFile()
      if (f) files.push(f)
    }
    if (files.length) addFiles(files)
  }

  const handleQuote = (m: AiTmMessage) => {
    const raw = String(m.content || '').trim()
    if (!raw) return
    const block = `\n\n\`\`\`md\n${raw}\n\`\`\`\n`
    setInput((prev) => (prev ? `${prev}${block}` : block.trimStart()))
    window.setTimeout(() => promptRef.current?.focus(), 0)
  }

  const handleEdit = (m: AiTmMessage) => {
    if (m.role !== 'user') return
    setInput(String(m.content || ''))
    setPendingFiles([])
    setPendingAttachmentRefs(m.attachments ?? [])
    window.setTimeout(() => promptRef.current?.focus(), 0)
  }

  const retryFromAssistantIndex = (idx: number) => {
    for (let i = idx - 1; i >= 0; i--) {
      const m = messages[i]
      if (m?.role === 'user' && String(m.content || '').trim()) {
        void sendMessage({ content: m.content, files: [], attachmentRefs: m.attachments ?? [], clearDraft: false })
        return
      }
    }
    setError('Nothing to retry.')
  }

  const setTab = (next: string, patch?: Record<string, string | null>) => {
    const sp = new URLSearchParams(searchParams)
    sp.set('tab', next)
    if (patch) {
      for (const [k, v] of Object.entries(patch)) {
        if (v == null || v === '') sp.delete(k)
        else sp.set(k, v)
      }
    }
    setSearchParams(sp, { replace: true })
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
        {tab === 'chat' ? (
          <Stack direction="row" spacing={1} alignItems="center">
            <FormControl size="small" sx={{ minWidth: 220 }}>
              <Select value={threadId} onChange={(e) => setThreadId(String(e.target.value))} displayEmpty disabled={busy}>
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
        ) : (
          <Stack direction="row" spacing={1} alignItems="center">
            <Button size="small" variant="outlined" onClick={() => setTab('chat', { shadow: null })}>
              Back to chat
            </Button>
          </Stack>
        )}
      </Stack>

      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(String(v), { shadow: String(v) === 'journal' ? shadowParam : null })}
        sx={{ mb: 1 }}
      >
        <Tab value="chat" label="Chat" />
        <Tab value="coverage" label="Coverage" />
        <Tab value="journal" label="Journal" />
      </Tabs>

      {tab !== 'chat' ? (
        <Paper
          variant="outlined"
          sx={{
            flex: 1,
            minHeight: 0,
            overflow: 'auto',
            bgcolor: 'background.default',
          }}
        >
          {tab === 'coverage' ? (
            <AiCoveragePanel accountId={accountId} onOpenJournal={(sid) => setTab('journal', { shadow: sid })} />
          ) : (
            <AiJournalPanel
              accountId={accountId}
              shadowId={shadowParam || null}
              onShadowChange={(sid) => setTab('journal', { shadow: sid })}
            />
          )}
        </Paper>
      ) : (
        <>
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
                {messages.map((m, idx) => {
                  const canRetry =
                    m.role === 'assistant' &&
                    messages.slice(0, idx).some((p) => p.role === 'user' && String(p.content || '').trim())
                  return (
                    <MessageBubble
                      key={m.message_id}
                      message={m}
                      canRetry={canRetry}
                      onRetry={() => retryFromAssistantIndex(idx)}
                      onQuote={handleQuote}
                      onEdit={handleEdit}
                      onLoadTrace={onLoadTrace}
                      liveToolCalls={m.decision_id ? liveToolCallsByDecision[m.decision_id] : undefined}
                    />
                  )
                })}
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
          {error && <Alert severity="error">{error}</Alert>}
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">
              Drag & drop files here, paste images (Ctrl+V), or attach.
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".csv,.xlsx,image/*"
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
          {pendingAttachmentRefs.length || pendingFiles.length ? (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              {pendingAttachmentRefs.map((a) => (
                <PendingAttachmentPill
                  key={a.file_id}
                  attachmentRef={a}
                  onRemove={() => {
                    if (busy) return
                    setPendingAttachmentRefs((prev) => prev.filter((x) => x.file_id !== a.file_id))
                  }}
                />
              ))}
              {pendingFiles.map((f, idx) => (
                <PendingAttachmentPill
                  key={`${f.name}-${idx}`}
                  file={f}
                  onRemove={() => {
                    if (busy) return
                    setPendingFiles((prev) => prev.filter((_, i) => i !== idx))
                  }}
                />
              ))}
            </Stack>
          ) : null}
          <TextField
            label="Message"
            placeholder="Ask about holdings, positions, margins…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
            inputRef={promptRef as any}
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
        </>
      )}
    </Box>
  )
}
