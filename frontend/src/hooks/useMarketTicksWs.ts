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
  onFlush?: (ticksByKey: Map<string, MarketTick>, ts: string | null) => void
}): MarketTicksWsState {
  const enabled = opts.enabled
  const flushMs = opts.flushMs ?? 1000
  const staleMs = opts.staleMs ?? 10_000

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

  const sendSubscribe = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    const payload: SubscribeMessage = {
      type: 'subscribe',
      symbols: normalizedRef.current.map((k) => ({ exchange: k.exchange, symbol: k.symbol })),
    }
    ws.send(JSON.stringify(payload))
  }, [])

  useEffect(() => {
    if (!enabled) {
      setConnected(false)
      setError(null)
      const ws = wsRef.current
      wsRef.current = null
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        try {
          ws.close()
        } catch {
          // ignore
        }
      }
      return
    }

    const ws = new WebSocket(wsUrl('/ws/market/ticks'))
    wsRef.current = ws
    setError(null)

    ws.onopen = () => {
      setConnected(true)
      sendSubscribe()
    }
    ws.onclose = () => {
      setConnected(false)
    }
    ws.onerror = () => {
      setError('Live ticks websocket error')
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

    return () => {
      wsRef.current = null
      try {
        ws.close()
      } catch {
        // ignore
      }
      setConnected(false)
    }
  }, [enabled, sendSubscribe])

  useEffect(() => {
    if (!enabled || !connected) return
    sendSubscribe()
  }, [connected, enabled, subscriptionKey, sendSubscribe])

  useEffect(() => {
    if (!enabled) return
    const id = window.setInterval(() => {
      onFlushRef.current?.(new Map(ticksRef.current), lastTickTs)
    }, flushMs)
    return () => window.clearInterval(id)
  }, [enabled, flushMs, lastTickTs])

  const stale =
    connected && lastMessageAtMs != null ? Date.now() - lastMessageAtMs > staleMs : false

  return { connected, lastTickTs, lastMessageAtMs, stale, error }
}
