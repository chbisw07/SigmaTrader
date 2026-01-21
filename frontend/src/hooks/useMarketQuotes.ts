import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchMarketQuotes, type MarketQuote } from '../services/marketQuotes'
import { fetchMarketDataStatus } from '../services/marketData'

export type QuotesState = {
  quotesByKey: Record<string, MarketQuote>
  error: string | null
  loading: boolean
}

export function useMarketQuotes(
  items: Array<{ symbol: string; exchange?: string | null }>,
  opts?: { pollMs?: number | null },
): QuotesState {
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null)
  const [quotesByKey, setQuotesByKey] = useState<Record<string, MarketQuote>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const status = await fetchMarketDataStatus()
        if (cancelled) return
        setMarketOpen(status.market_open ?? null)
      } catch {
        if (cancelled) return
        setMarketOpen(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const pollMs = useMemo(() => {
    // Explicit override: number = fixed interval, null = no polling (one fetch).
    if (opts?.pollMs !== undefined) return opts.pollMs
    // Default behavior (per product decision): poll every 5 minutes during
    // market hours; outside market hours, fetch once and keep last price.
    if (marketOpen === true) return 5 * 60 * 1000
    if (marketOpen === false) return null
    // Unknown market status: be conservative and poll slowly.
    return 5 * 60 * 1000
  }, [marketOpen, opts?.pollMs])

  const normalized = useMemo(() => {
    const uniq = new Map<string, { symbol: string; exchange: string }>()
    for (const it of items) {
      const sym = (it.symbol || '').trim().toUpperCase()
      if (!sym) continue
      const exch = (it.exchange || 'NSE').trim().toUpperCase() || 'NSE'
      const key = `${exch}:${sym}`
      if (!uniq.has(key)) uniq.set(key, { symbol: sym, exchange: exch })
    }
    return Array.from(uniq.values())
  }, [items])

  const normalizedRef = useRef(normalized)
  normalizedRef.current = normalized

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      const payload = normalizedRef.current
      if (!payload.length) return
      try {
        setLoading(true)
        setError(null)
        const quotes = await fetchMarketQuotes(payload)
        if (cancelled) return
        const next: Record<string, MarketQuote> = {}
        for (const q of quotes) {
          const sym = (q.symbol || '').trim().toUpperCase()
          const exch = (q.exchange || 'NSE').trim().toUpperCase() || 'NSE'
          if (!sym) continue
          next[`${exch}:${sym}`] = q
        }
        setQuotesByKey(next)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load quotes')
      } finally {
        if (cancelled) return
        setLoading(false)
      }
    }

    if (!normalized.length) {
      setQuotesByKey({})
      setError(null)
      setLoading(false)
      return () => {
        cancelled = true
      }
    }

    void load()
    if (pollMs == null) {
      return () => {
        cancelled = true
      }
    }
    const id = window.setInterval(() => void load(), pollMs)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [pollMs, normalized.length])

  return { quotesByKey, error, loading }
}
