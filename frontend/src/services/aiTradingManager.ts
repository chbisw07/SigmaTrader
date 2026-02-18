export type AiTmMessage = {
  message_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  correlation_id?: string | null
  decision_id?: string | null
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

export type DecisionTrace = {
  decision_id: string
  correlation_id: string
  created_at: string
  account_id: string
  user_message: string
  final_outcome?: Record<string, unknown>
  explanations?: string[]
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

