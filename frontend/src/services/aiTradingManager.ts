export type AiTmMessage = {
  message_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  correlation_id?: string | null
  decision_id?: string | null
  attachments?: Array<{
    file_id: string
    filename: string
    size?: number | null
    mime?: string | null
  }>
}

export type AiTmThread = {
  thread_id: string
  account_id: string
  messages: AiTmMessage[]
}

export async function fetchAiThread(params?: {
  account_id?: string
  thread_id?: string
}): Promise<AiTmThread> {
  const url = new URL('/api/ai/thread', window.location.origin)
  if (params?.account_id) url.searchParams.set('account_id', params.account_id)
  if (params?.thread_id) url.searchParams.set('thread_id', params.thread_id)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load AI thread (${res.status})`)
  return (await res.json()) as AiTmThread
}

export type AiThreadSummary = {
  thread_id: string
  title: string
  updated_at: string
  message_count: number
}

export async function fetchAiThreads(params?: { account_id?: string; limit?: number }): Promise<AiThreadSummary[]> {
  const url = new URL('/api/ai/threads', window.location.origin)
  if (params?.account_id) url.searchParams.set('account_id', params.account_id)
  if (params?.limit != null) url.searchParams.set('limit', String(params.limit))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load AI threads (${res.status})`)
  return (await res.json()) as AiThreadSummary[]
}

export async function createAiThread(payload?: { account_id?: string }): Promise<{ thread_id: string; account_id: string }> {
  const url = new URL('/api/ai/threads', window.location.origin)
  if (payload?.account_id) url.searchParams.set('account_id', payload.account_id)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to create AI thread (${res.status})`)
  return (await res.json()) as { thread_id: string; account_id: string }
}

export async function postAiMessage(payload: {
  account_id?: string
  content: string
}): Promise<{ thread: AiTmThread; decision_id: string }> {
  const res = await fetch('/api/ai/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account_id: payload.account_id ?? 'default', content: payload.content }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to post AI message (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { thread: AiTmThread; decision_id: string }
}

export type AiChatToolCall = {
  name: string
  arguments: Record<string, unknown>
  status: 'ok' | 'blocked' | 'error' | string
  duration_ms: number
  result_preview: string
  error?: string | null
}

export async function chatAi(payload: {
  account_id?: string
  thread_id?: string
  message: string
  context?: Record<string, unknown>
  attachments?: Array<{ file_id: string; how?: string }>
  ui_context?: Record<string, unknown>
  signal?: AbortSignal
}): Promise<{
  assistant_message: string
  decision_id: string
  tool_calls: AiChatToolCall[]
  render_blocks?: Array<Record<string, unknown>>
  attachments_used?: Array<Record<string, unknown>>
  thread?: AiTmThread | null
}> {
  const res = await fetch('/api/ai/chat', {
    method: 'POST',
    signal: payload.signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_id: payload.account_id ?? 'default',
      thread_id: payload.thread_id ?? 'default',
      message: payload.message,
      context: payload.context ?? {},
      attachments: payload.attachments ?? [],
      ui_context: payload.ui_context ?? null,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to chat (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as {
    assistant_message: string
    decision_id: string
    tool_calls: AiChatToolCall[]
    render_blocks?: Array<Record<string, unknown>>
    attachments_used?: Array<Record<string, unknown>>
    thread?: AiTmThread | null
  }
}

export type AiChatStreamEvent =
  | { type: 'decision'; decision_id: string; correlation_id?: string }
  | { type: 'tool_call'; name: string; arguments?: Record<string, unknown>; status: string; duration_ms?: number; result_preview?: string; error?: string | null }
  | { type: 'assistant_delta'; text: string }
  | { type: 'done'; assistant_message: string; decision_id: string }
  | { type: 'error'; error: string }

export async function chatAiStream(payload: {
  account_id?: string
  thread_id?: string
  message: string
  context?: Record<string, unknown>
  attachments?: Array<{ file_id: string; how?: string }>
  ui_context?: Record<string, unknown>
  signal?: AbortSignal
  onEvent?: (ev: AiChatStreamEvent) => void
}): Promise<{ assistant_message: string; decision_id: string }> {
  const res = await fetch('/api/ai/chat/stream', {
    method: 'POST',
    signal: payload.signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_id: payload.account_id ?? 'default',
      thread_id: payload.thread_id ?? 'default',
      message: payload.message,
      context: payload.context ?? {},
      attachments: payload.attachments ?? [],
      ui_context: payload.ui_context ?? null,
    }),
  })

  // Fallback to non-streaming if endpoint isn't available.
  if (res.status === 404 || res.status === 405) {
    const out = await chatAi(payload)
    payload.onEvent?.({ type: 'decision', decision_id: out.decision_id })
    payload.onEvent?.({ type: 'assistant_delta', text: out.assistant_message })
    payload.onEvent?.({ type: 'done', assistant_message: out.assistant_message, decision_id: out.decision_id })
    return { assistant_message: out.assistant_message, decision_id: out.decision_id }
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to chat stream (${res.status})${body ? `: ${body}` : ''}`)
  }
  if (!res.body) throw new Error('No response body for streaming chat')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let final: { assistant_message: string; decision_id: string } | null = null

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    while (true) {
      const idx = buf.indexOf('\n')
      if (idx < 0) break
      const line = buf.slice(0, idx).trim()
      buf = buf.slice(idx + 1)
      if (!line) continue
      let ev: AiChatStreamEvent | null = null
      try {
        ev = JSON.parse(line) as AiChatStreamEvent
      } catch {
        continue
      }
      payload.onEvent?.(ev)
      if (ev.type === 'done') final = { assistant_message: ev.assistant_message, decision_id: ev.decision_id }
      if (ev.type === 'error') throw new Error(ev.error || 'chat_stream_error')
    }
  }

  if (!final) throw new Error('Streaming chat ended without done event')
  return final
}

export type AiFileSummary = {
  kind: 'csv' | 'xlsx' | 'unknown' | string
  columns: string[]
  row_count: number
  preview_rows: Array<Record<string, unknown>>
  sheets?: string[]
  active_sheet?: string | null
}

export type AiFileMeta = {
  file_id: string
  filename: string
  size: number
  mime?: string | null
  created_at: string
  summary: AiFileSummary
}

export async function uploadAiFiles(files: File[]): Promise<AiFileMeta[]> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const res = await fetch('/api/ai/files', { method: 'POST', body: form })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to upload file(s) (${res.status})${body ? `: ${body}` : ''}`)
  }
  const data = (await res.json()) as { files: AiFileMeta[] }
  return data.files ?? []
}

export type DecisionTrace = {
  decision_id: string
  correlation_id: string
  created_at: string
  account_id: string
  user_message: string
  inputs_used?: Record<string, unknown>
  tools_called?: Array<{
    tool_name: string
    input_summary?: Record<string, unknown>
    output_summary?: Record<string, unknown>
    duration_ms?: number | null
    operator_payload_meta?: {
      payload_id: string
      payload_bytes?: number
      items_count?: number
    } | null
    llm_summary?: Record<string, unknown> | null
    broker_raw_count?: number | null
    ui_rendered_count?: number | null
    llm_summary_count?: number | null
    truncation_reason?: string | null
  }>
  riskgate_result?: {
    outcome: string
    reasons?: string[]
    reason_codes?: Array<Record<string, unknown>>
    computed_risk_metrics?: Record<string, unknown>
    policy_version?: string
    policy_hash?: string | null
  } | null
  final_outcome?: Record<string, unknown>
  explanations?: string[]
}

export type CoverageUnmanagedCount = {
  account_id: string
  unmanaged_open: number
  open_total: number
}

export type PositionShadow = {
  shadow_id: string
  account_id: string
  symbol: string
  product: string
  side: string
  qty_current: number
  avg_price?: number | null
  ltp?: number | null
  pnl_abs?: number | null
  pnl_pct?: number | null
  source: string
  status: string
  first_seen_at?: string | null
  last_seen_at?: string | null
  managed?: boolean
  playbook_id?: string | null
  playbook_mode?: string | null
  playbook_horizon?: string | null
}

export type ManagePlaybook = {
  playbook_id: string
  scope_type: string
  scope_key?: string | null
  enabled: boolean
  mode: string
  horizon: string
  review_cadence_min: number
  exit_policy: Record<string, unknown>
  scale_policy: Record<string, unknown>
  execution_style: string
  allow_strategy_exits: boolean
  behavior_on_strategy_exit: string
  notes?: string | null
  version: number
  created_at?: string | null
  updated_at?: string | null
}

export async function fetchCoverageUnmanagedCount(params?: { account_id?: string }): Promise<CoverageUnmanagedCount> {
  const url = new URL('/api/ai/coverage/unmanaged-count', window.location.origin)
  if (params?.account_id) url.searchParams.set('account_id', params.account_id)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load unmanaged count (${res.status})`)
  return (await res.json()) as CoverageUnmanagedCount
}

export async function fetchCoverageShadows(params?: {
  account_id?: string
  status_filter?: string
  unmanaged_only?: boolean
  limit?: number
}): Promise<PositionShadow[]> {
  const url = new URL('/api/ai/coverage/shadows', window.location.origin)
  url.searchParams.set('account_id', params?.account_id ?? 'default')
  if (params?.status_filter) url.searchParams.set('status_filter', params.status_filter)
  if (params?.unmanaged_only != null) url.searchParams.set('unmanaged_only', String(params.unmanaged_only))
  if (params?.limit != null) url.searchParams.set('limit', String(params.limit))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load coverage shadows (${res.status})`)
  return (await res.json()) as PositionShadow[]
}

export async function syncCoverageFromLatestSnapshot(params?: { account_id?: string }): Promise<Record<string, unknown>> {
  const url = new URL('/api/ai/coverage/sync', window.location.origin)
  url.searchParams.set('account_id', params?.account_id ?? 'default')
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to sync coverage (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as Record<string, unknown>
}

export async function attachPlaybookToShadow(payload: { shadow_id: string; template?: string }): Promise<ManagePlaybook> {
  const url = new URL(`/api/ai/position-shadows/${payload.shadow_id}/attach-playbook`, window.location.origin)
  if (payload.template) url.searchParams.set('template', payload.template)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to attach playbook (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as ManagePlaybook
}

export async function updateManagePlaybook(payload: {
  playbook_id: string
  patch: Partial<{
    enabled: boolean
    mode: string
    horizon: string
    review_cadence_min: number
    exit_policy: Record<string, unknown>
    scale_policy: Record<string, unknown>
    execution_style: string
    allow_strategy_exits: boolean
    behavior_on_strategy_exit: string
    notes: string | null
  }>
}): Promise<ManagePlaybook> {
  const res = await fetch(`/api/ai/manage-playbooks/${payload.playbook_id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload.patch),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to update playbook (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as ManagePlaybook
}

export async function fetchManagePlaybook(payload: { playbook_id: string }): Promise<ManagePlaybook> {
  const res = await fetch(`/api/ai/manage-playbooks/${payload.playbook_id}`)
  if (!res.ok) throw new Error(`Failed to load playbook (${res.status})`)
  return (await res.json()) as ManagePlaybook
}

export type JournalEvent = {
  event_id: string
  position_shadow_id: string
  ts: string
  event_type: string
  source: string
  intent_payload?: Record<string, unknown>
  riskgate_result?: Record<string, unknown> | null
  playbook_result?: Record<string, unknown> | null
  broker_result?: Record<string, unknown> | null
  notes?: string | null
}

export type JournalForecast = {
  forecast_id: string
  position_shadow_id: string
  created_at: string
  author: string
  outlook_pct?: number | null
  horizon_days?: number | null
  confidence?: number | null
  rationale_tags?: string[]
  thesis_text?: string | null
  invalidation_text?: string | null
}

export async function fetchJournalEvents(payload: { shadow_id: string; limit?: number }): Promise<JournalEvent[]> {
  const url = new URL('/api/ai/journal/events', window.location.origin)
  url.searchParams.set('shadow_id', payload.shadow_id)
  if (payload.limit != null) url.searchParams.set('limit', String(payload.limit))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load journal events (${res.status})`)
  return (await res.json()) as JournalEvent[]
}

export async function fetchJournalForecasts(payload: { shadow_id: string; limit?: number }): Promise<JournalForecast[]> {
  const url = new URL('/api/ai/journal/forecasts', window.location.origin)
  url.searchParams.set('shadow_id', payload.shadow_id)
  if (payload.limit != null) url.searchParams.set('limit', String(payload.limit))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load forecasts (${res.status})`)
  return (await res.json()) as JournalForecast[]
}

export async function upsertJournalForecast(payload: Partial<JournalForecast> & { position_shadow_id: string }): Promise<JournalForecast> {
  const res = await fetch('/api/ai/journal/forecasts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to save forecast (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as JournalForecast
}

export type JournalPostmortem = {
  postmortem_id: string
  position_shadow_id: string
  closed_at: string
  realized_pnl_abs?: number | null
  realized_pnl_pct?: number | null
  mfe_abs?: number | null
  mfe_pct?: number | null
  mae_abs?: number | null
  mae_pct?: number | null
  peak_price_while_open?: number | null
  exit_quality: string
  exit_quality_explanation?: string | null
  forecast_vs_actual?: Record<string, unknown>
}

export async function fetchLatestPostmortem(payload: { shadow_id: string }): Promise<JournalPostmortem> {
  const url = new URL('/api/ai/journal/postmortem', window.location.origin)
  url.searchParams.set('shadow_id', payload.shadow_id)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load postmortem (${res.status})`)
  return (await res.json()) as JournalPostmortem
}

export async function fetchDecisionTrace(decisionId: string): Promise<DecisionTrace> {
  const res = await fetch(`/api/ai/decision-traces/${encodeURIComponent(decisionId)}`)
  if (!res.ok) throw new Error(`Failed to load DecisionTrace (${res.status})`)
  return (await res.json()) as DecisionTrace
}

export type AiTmException = {
  exception_id: string
  account_id: string
  exception_type: string
  severity: string
  key: string
  summary: string
  status: string
  created_at: string
  updated_at: string
  related_decision_id?: string | null
  related_run_id?: string | null
  details?: Record<string, unknown>
}

export async function ackAiException(payload: { exception_id: string }): Promise<{
  exception: AiTmException
  decision_id: string
}> {
  const res = await fetch(`/api/ai/exceptions/${encodeURIComponent(payload.exception_id)}/ack`, { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to acknowledge exception (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { exception: AiTmException; decision_id: string }
}

export async function fetchAiExceptions(params?: {
  account_id?: string
  status_filter?: string
  limit?: number
}): Promise<AiTmException[]> {
  const url = new URL('/api/ai/exceptions', window.location.origin)
  if (params?.account_id) url.searchParams.set('account_id', params.account_id)
  if (params?.status_filter) url.searchParams.set('status_filter', params.status_filter)
  if (params?.limit) url.searchParams.set('limit', String(params.limit))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load AI exceptions (${res.status})`)
  return (await res.json()) as AiTmException[]
}

export async function runAiReconcile(payload?: { account_id?: string }): Promise<{
  run_id: string
  deltas: unknown[]
  severity_counts: Record<string, number>
  decision_id: string
}> {
  const url = new URL('/api/ai/reconcile', window.location.origin)
  if (payload?.account_id) url.searchParams.set('account_id', payload.account_id)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to run reconciliation (${res.status})`)
  return (await res.json()) as {
    run_id: string
    deltas: unknown[]
    severity_counts: Record<string, number>
    decision_id: string
  }
}

export type TradeIntent = {
  symbols: string[]
  side: 'BUY' | 'SELL'
  product?: 'MIS' | 'CNC'
  constraints?: Record<string, unknown>
  risk_budget_pct?: number | null
}

export type TradePlan = {
  plan_id: string
  intent: TradeIntent
  entry_rules?: unknown[]
  sizing_method?: string
  risk_model?: Record<string, unknown>
  order_skeleton?: Record<string, unknown>
  validity_window?: Record<string, unknown>
  idempotency_scope?: string
}

export async function createTradePlan(payload: { account_id?: string; intent: TradeIntent }): Promise<{
  plan: TradePlan
  decision_id: string
}> {
  const res = await fetch('/api/ai/trade-plans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_id: payload.account_id ?? 'default',
      intent: payload.intent,
    }),
  })
  if (!res.ok) throw new Error(`Failed to create trade plan (${res.status})`)
  return (await res.json()) as { plan: TradePlan; decision_id: string }
}

export type Playbook = {
  playbook_id: string
  account_id: string
  name: string
  description?: string | null
  plan_id: string
  enabled: boolean
  armed: boolean
  armed_at?: string | null
  armed_by_message_id?: string | null
  cadence_sec?: number | null
  next_run_at?: string | null
  last_run_at?: string | null
  created_at: string
  updated_at: string
}

export async function createPlaybook(payload: {
  account_id?: string
  name: string
  description?: string
  plan: TradePlan
  cadence_sec?: number | null
}): Promise<{ playbook: Playbook; decision_id: string }> {
  const res = await fetch('/api/ai/playbooks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_id: payload.account_id ?? 'default',
      name: payload.name,
      description: payload.description ?? null,
      plan: payload.plan,
      cadence_sec: payload.cadence_sec ?? null,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to create playbook (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { playbook: Playbook; decision_id: string }
}

export async function fetchPlaybooks(params?: { account_id?: string }): Promise<Playbook[]> {
  const url = new URL('/api/ai/playbooks', window.location.origin)
  if (params?.account_id) url.searchParams.set('account_id', params.account_id)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load playbooks (${res.status})`)
  return (await res.json()) as Playbook[]
}

export async function setPlaybookArmed(payload: {
  playbook_id: string
  armed: boolean
  authorization_message_id?: string
}): Promise<{
  playbook: Playbook
  decision_id: string
}> {
  const url = new URL(`/api/ai/playbooks/${encodeURIComponent(payload.playbook_id)}/arm`, window.location.origin)
  url.searchParams.set('armed', payload.armed ? '1' : '0')
  if (payload.authorization_message_id) {
    url.searchParams.set('authorization_message_id', payload.authorization_message_id)
  }
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to arm playbook (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { playbook: Playbook; decision_id: string }
}

export async function runPlaybookNow(payload: {
  playbook_id: string
  authorization_message_id?: string
}): Promise<{ decision_id: string; outcome: Record<string, unknown> }> {
  const url = new URL(`/api/ai/playbooks/${encodeURIComponent(payload.playbook_id)}/run-now`, window.location.origin)
  if (payload.authorization_message_id) {
    url.searchParams.set('authorization_message_id', payload.authorization_message_id)
  }
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Failed to run playbook (${res.status})${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as { decision_id: string; outcome: Record<string, unknown> }
}

export async function resyncExpectedLedger(payload?: { account_id?: string }): Promise<{
  updated_positions: number
  decision_id: string
}> {
  const url = new URL('/api/ai/expected-ledger/resync', window.location.origin)
  if (payload?.account_id) url.searchParams.set('account_id', payload.account_id)
  const res = await fetch(url.toString(), { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to resync expected ledger (${res.status})`)
  return (await res.json()) as { updated_positions: number; decision_id: string }
}

export type PlaybookRun = {
  run_id: string
  playbook_id: string
  dedupe_key: string
  decision_id?: string | null
  authorization_message_id?: string | null
  status: string
  outcome?: Record<string, unknown>
  started_at: string
  completed_at?: string | null
}

export async function fetchPlaybookRuns(payload: { playbook_id: string; limit?: number }): Promise<PlaybookRun[]> {
  const url = new URL(`/api/ai/playbooks/${encodeURIComponent(payload.playbook_id)}/runs`, window.location.origin)
  if (payload.limit) url.searchParams.set('limit', String(payload.limit))
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load playbook runs (${res.status})`)
  return (await res.json()) as PlaybookRun[]
}

export type PortfolioDiagnostics = {
  as_of_ts: string
  account_id: string
  drift: Array<{
    symbol: string
    product: string
    expected_qty: number
    broker_qty: number
    delta_qty: number
    last_price?: number | null
  }>
  risk_budgets: Record<string, unknown>
  correlation: Record<string, unknown>
  market_context?: {
    as_of_ts: string
    exchange: string
    timeframe: string
    items: Array<{
      symbol: string
      exchange: string
      timeframe: string
      as_of_ts: string
      close?: number | null
      sma20?: number | null
      sma50?: number | null
      atr14?: number | null
      atr14_pct?: number | null
      vol20_ann_pct?: number | null
      trend_regime: 'up' | 'down' | 'range' | 'unknown'
      volatility_regime: 'low' | 'normal' | 'high' | 'unknown'
      notes?: string[]
    }>
    summary?: Record<string, unknown>
  } | null
}

export async function fetchPortfolioDiagnostics(payload?: { account_id?: string }): Promise<PortfolioDiagnostics> {
  const url = new URL('/api/ai/portfolio/diagnostics', window.location.origin)
  if (payload?.account_id) url.searchParams.set('account_id', payload.account_id)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to load portfolio diagnostics (${res.status})`)
  return (await res.json()) as PortfolioDiagnostics
}
