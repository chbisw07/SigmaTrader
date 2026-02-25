import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type MarketTick = {
  exchange: string
  symbol: string
  ltp: number
  prevClose?: number | null
}

type TickMessage = {
  type: 'ticks'
  ts: string
  data: Array<{
    exchange?: string | null
    symbol?: string | null
    ltp?: number | null
    prevClose?: number | null
  }>
}

type ErrorMessage = { type: 'error'; error?: string | null }

type SubscribeMessage = {
  type: 'subscribe'
  symbols: Array<{ exchange: string; symbol: string }>
}

function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}

function normalizeKeys(
  items: Array<{ symbol: string; exchange?: string | null }>,
): Array<{ exchange: string; symbol: string; key: string }> {
  const uniq = new Map<string, { exchange: string; symbol: string; key: string }>()
  for (const it of items) {
    const symbol = (it.symbol || '').trim().toUpperCase()
    if (!symbol) continue
    const exchange = (it.exchange || 'NSE').trim().toUpperCase() || 'NSE'
    const key = `${exchange}:${symbol}`
    if (!uniq.has(key)) uniq.set(key, { exchange, symbol, key })
  }
  return Array.from(uniq.values())
}

export type MarketTicksWsState = {
  connected: boolean
  lastTickTs: string | null
  lastMessageAtMs: number | null
  stale: boolean
  error: string | null
}

export function useMarketTicksWs(opts: {
  enabled: boolean
  symbols: Array<{ symbol: string; exchange?: string | null }>
  flushMs?: number
  staleMs?: number
  reconnectOnStale?: boolean
  onFlush?: (ticksByKey: Map<string, MarketTick>, ts: string | null) => void
}): MarketTicksWsState {
  const enabled = opts.enabled
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const flushMs = opts.flushMs ?? 1000
  const staleMs = opts.staleMs ?? 10_000
  const reconnectOnStale = opts.reconnectOnStale ?? true

  const normalized = useMemo(() => normalizeKeys(opts.symbols), [opts.symbols])
  const subscriptionKey = useMemo(
    () => normalized.map((k) => k.key).join('|'),
    [normalized],
  )
  const normalizedRef = useRef(normalized)
  normalizedRef.current = normalized
  const onFlushRef = useRef(opts.onFlush)
  onFlushRef.current = opts.onFlush

  const [connected, setConnected] = useState(false)
  const [lastTickTs, setLastTickTs] = useState<string | null>(null)
  const [lastMessageAtMs, setLastMessageAtMs] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const ticksRef = useRef<Map<string, MarketTick>>(new Map())
  const connectedAtMsRef = useRef<number | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const closingRef = useRef(false)

  const sendSubscribe = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    const payload: SubscribeMessage = {
      type: 'subscribe',
      symbols: normalizedRef.current.map((k) => ({ exchange: k.exchange, symbol: k.symbol })),
    }
    ws.send(JSON.stringify(payload))
  }, [])

  const closeWs = useCallback(() => {
    const ws = wsRef.current
    wsRef.current = null
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      try {
        ws.close()
      } catch {
        // ignore
      }
    }
  }, [])

  const connectRef = useRef<(() => void) | null>(null)

  const scheduleReconnect = useCallback(() => {
    if (!enabledRef.current) return
    if (reconnectTimerRef.current != null) return
    const attempt = reconnectAttemptsRef.current
    const base = Math.min(30_000, 500 * Math.pow(2, attempt))
    const jitter = Math.floor(Math.random() * 250)
    const delay = Math.max(500, base + jitter)
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null
      if (!enabledRef.current) return
      connectRef.current?.()
    }, delay)
  }, [])

  useEffect(() => {
    if (!enabled) {
      setConnected(false)
      setError(null)
      closingRef.current = true
      reconnectAttemptsRef.current = 0
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      closeWs()
      return
    }

    const connect = () => {
      if (!enabledRef.current) return
      // If something else already connected, don't replace it.
      const existing = wsRef.current
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)
      ) {
        return
      }

      closingRef.current = false
      setError(null)
      setLastMessageAtMs(null)

      const ws = new WebSocket(wsUrl('/ws/market/ticks'))
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        connectedAtMsRef.current = Date.now()
        reconnectAttemptsRef.current = 0
        if (reconnectTimerRef.current != null) {
          window.clearTimeout(reconnectTimerRef.current)
          reconnectTimerRef.current = null
        }
        sendSubscribe()
      }
      ws.onclose = () => {
        setConnected(false)
        connectedAtMsRef.current = null
        if (!closingRef.current && enabledRef.current) {
          reconnectAttemptsRef.current += 1
          scheduleReconnect()
        }
      }
      ws.onerror = () => {
        setError('Live ticks websocket error')
        try {
          ws.close()
        } catch {
          // ignore
        }
      }
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(ev.data) as TickMessage | ErrorMessage
          if (parsed && parsed.type === 'error') {
            setError(parsed.error ? String(parsed.error) : 'Live ticks error')
            return
          }
          if (!parsed || parsed.type !== 'ticks' || !Array.isArray(parsed.data)) return
          const ts = String(parsed.ts || '')
          setLastTickTs(ts || null)
          setLastMessageAtMs(Date.now())
          for (const row of parsed.data) {
            const symbol = (row.symbol || '').trim().toUpperCase()
            if (!symbol) continue
            const exchange = (row.exchange || 'NSE').trim().toUpperCase() || 'NSE'
            const ltp = row.ltp != null ? Number(row.ltp) : null
            if (ltp == null || !Number.isFinite(ltp) || ltp <= 0) continue
            const prevClose =
              row.prevClose != null && Number.isFinite(Number(row.prevClose))
                ? Number(row.prevClose)
                : null
            ticksRef.current.set(`${exchange}:${symbol}`, { exchange, symbol, ltp, prevClose })
          }
        } catch {
          // ignore parse errors
        }
      }
    }

    connectRef.current = connect
    connect()

    return () => {
      closingRef.current = true
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      closeWs()
      setConnected(false)
      connectedAtMsRef.current = null
    }
  }, [closeWs, enabled, scheduleReconnect, sendSubscribe])

  useEffect(() => {
    if (!enabled || !connected) return
    sendSubscribe()
  }, [connected, enabled, subscriptionKey, sendSubscribe])

  useEffect(() => {
    if (!enabled) return
    // Keep the connection alive in the presence of proxies by periodically
    // sending a small message + re-subscribing (idempotent).
    const id = window.setInterval(() => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      try {
        ws.send(JSON.stringify({ type: 'ping' }))
      } catch {
        // ignore
      }
      sendSubscribe()
    }, 15_000)
    return () => window.clearInterval(id)
  }, [enabled, sendSubscribe])

  useEffect(() => {
    if (!enabled) return
    const id = window.setInterval(() => {
      onFlushRef.current?.(new Map(ticksRef.current), lastTickTs)
    }, flushMs)
    return () => window.clearInterval(id)
  }, [enabled, flushMs, lastTickTs])

  const stale = useMemo(() => {
    if (!connected) return false
    const base = lastMessageAtMs ?? connectedAtMsRef.current
    if (base == null) return true
    return Date.now() - base > staleMs
  }, [connected, lastMessageAtMs, staleMs])

  useEffect(() => {
    if (!enabled || !reconnectOnStale) return
    if (!connected || !stale) return
    // Force a reconnect to recover from silent stalls (broker/proxy hangs).
    reconnectAttemptsRef.current += 1
    closeWs()
    scheduleReconnect()
  }, [closeWs, connected, enabled, reconnectOnStale, scheduleReconnect, stale])

  return { connected, lastTickTs, lastMessageAtMs, stale, error }
}
