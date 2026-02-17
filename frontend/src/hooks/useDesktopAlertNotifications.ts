import { useEffect, useMemo, useRef } from 'react'

import {
  getLastSeenAlertEventId,
  getLastSeenTvAlertId,
  setLastSeenAlertEventId,
  setLastSeenTvAlertId,
} from '../services/desktopNotifications'
import { listTvAlerts, type TvAlert } from '../services/tvAlerts'
import {
  listAlertDefinitions,
  listAlertEvents,
  type AlertDefinition,
  type AlertEvent,
} from '../services/alertsV3'

type DesktopAlertNotificationsOptions = {
  enabled: boolean
  pollIntervalMs?: number
}

function canShowNotifications(): boolean {
  if (typeof window === 'undefined') return false
  if (!('Notification' in window)) return false
  return Notification.permission === 'granted'
}

function safeNotify(
  title: string,
  body: string,
  options?: { tag?: string; url?: string },
): void {
  if (!canShowNotifications()) return
  try {
    const n = new Notification(title, {
      body,
      tag: options?.tag,
      icon: '/sigma_trader_logo.png',
    })
    const url = options?.url
    if (url) {
      n.onclick = () => {
        try {
          n.close()
        } catch {
          // ignore
        }
        try {
          window.focus()
        } catch {
          // ignore
        }
        window.location.assign(url)
      }
    }
  } catch {
    // ignore
  }
}

function summarizeTvAlert(a: TvAlert): { title: string; body: string; url: string; tag: string } {
  const exch = (a.exchange || '').trim()
  const sym = (a.symbol || '').trim()
  const key = exch && sym ? `${exch}:${sym}` : sym || exch || 'Alert'
  const action = (a.action || '').trim().toUpperCase()
  const qty = a.qty != null ? ` · qty ${a.qty}` : ''
  const price = a.price != null ? ` · @ ${a.price}` : ''
  const strat = (a.strategy_name || '').trim()
  const reason = (a.reason || '').trim()

  const title = action ? `SigmaTrader: ${key} ${action}` : `SigmaTrader: ${key}`
  const parts = [
    strat ? `Strategy: ${strat}` : null,
    qty || price ? `${qty}${price}`.trim().replace(/^·\s*/, '') : null,
    reason ? reason : null,
  ].filter(Boolean) as string[]

  const body = parts.length ? parts.join(' — ') : 'TradingView alert received'
  return {
    title,
    body,
    url: '/queue?tab=tv_alerts',
    tag: `st_tv_alert_${a.id}`,
  }
}

function summarizeAlertEvent(
  e: AlertEvent,
  alertName: string | null,
): { title: string; body: string; url: string; tag: string } {
  const exch = (e.exchange || '').trim()
  const sym = (e.symbol || '').trim()
  const key = exch && sym ? `${exch}:${sym}` : sym || exch || 'Alert'
  const name = (alertName || '').trim() || `Alert #${e.alert_definition_id}`
  const reason = (e.reason || '').trim()
  const title = `SigmaTrader: ${key}`
  const body = reason ? `${name} — ${reason}` : name
  return { title, body, url: '/alerts', tag: `st_alert_event_${e.id}` }
}

export function useDesktopAlertNotifications({
  enabled,
  pollIntervalMs = 15000,
}: DesktopAlertNotificationsOptions) {
  const lastSeenTvIdRef = useRef<number | null>(null)
  const lastSeenEventIdRef = useRef<number | null>(null)
  const alertNameByIdRef = useRef<Map<number, string>>(new Map())
  const inFlightRef = useRef(false)

  const shouldPoll = useMemo(() => enabled && pollIntervalMs > 0, [enabled, pollIntervalMs])

  useEffect(() => {
    if (!shouldPoll) return
    if (typeof window === 'undefined') return

    lastSeenTvIdRef.current = getLastSeenTvAlertId()
    lastSeenEventIdRef.current = getLastSeenAlertEventId()

    let active = true

    const ensureAlertNameMap = async () => {
      if (alertNameByIdRef.current.size > 0) return
      try {
        const defs: AlertDefinition[] = await listAlertDefinitions()
        if (!active) return
        const m = new Map<number, string>()
        for (const d of defs) m.set(d.id, d.name)
        alertNameByIdRef.current = m
      } catch {
        // ignore
      }
    }

    const pollTvAlerts = async () => {
      if (!canShowNotifications()) return
      const items = await listTvAlerts({ limit: 50 })
      const newestId = items[0]?.id ?? null
      if (lastSeenTvIdRef.current == null) {
        if (newestId != null) {
          lastSeenTvIdRef.current = newestId
          setLastSeenTvAlertId(newestId)
        }
        return
      }
      const lastSeen = lastSeenTvIdRef.current
      const newItems = items
        .filter((a) => a.id > lastSeen)
        .sort((a, b) => a.id - b.id)

      const maxPerTick = 3
      const toNotify = newItems.slice(0, maxPerTick)
      for (const a of toNotify) {
        const s = summarizeTvAlert(a)
        safeNotify(s.title, s.body, { url: s.url, tag: s.tag })
      }
      const maxId = newItems.reduce((acc, a) => Math.max(acc, a.id), lastSeen)
      if (maxId > lastSeen) {
        lastSeenTvIdRef.current = maxId
        setLastSeenTvAlertId(maxId)
      }
      if (newItems.length > maxPerTick) {
        safeNotify(
          'SigmaTrader: Alerts',
          `${newItems.length - maxPerTick} more TradingView alert(s) received`,
          { url: '/queue?tab=tv_alerts', tag: 'st_tv_alerts_overflow' },
        )
      }
    }

    const pollAlertEvents = async () => {
      if (!canShowNotifications()) return
      await ensureAlertNameMap()
      const items = await listAlertEvents({ limit: 50 })
      const newestId = items[0]?.id ?? null
      if (lastSeenEventIdRef.current == null) {
        if (newestId != null) {
          lastSeenEventIdRef.current = newestId
          setLastSeenAlertEventId(newestId)
        }
        return
      }
      const lastSeen = lastSeenEventIdRef.current
      const newItems = items
        .filter((e) => e.id > lastSeen)
        .sort((a, b) => a.id - b.id)

      const maxPerTick = 3
      const toNotify = newItems.slice(0, maxPerTick)
      for (const e of toNotify) {
        const name = alertNameByIdRef.current.get(e.alert_definition_id) ?? null
        const s = summarizeAlertEvent(e, name)
        safeNotify(s.title, s.body, { url: s.url, tag: s.tag })
      }
      const maxId = newItems.reduce((acc, e) => Math.max(acc, e.id), lastSeen)
      if (maxId > lastSeen) {
        lastSeenEventIdRef.current = maxId
        setLastSeenAlertEventId(maxId)
      }
      if (newItems.length > maxPerTick) {
        safeNotify(
          'SigmaTrader: Alerts',
          `${newItems.length - maxPerTick} more alert event(s) triggered`,
          { url: '/alerts', tag: 'st_alert_events_overflow' },
        )
      }
    }

    const tick = async () => {
      if (!active) return
      if (inFlightRef.current) return
      inFlightRef.current = true
      try {
        await Promise.allSettled([pollTvAlerts(), pollAlertEvents()])
      } catch {
        // ignore
      } finally {
        inFlightRef.current = false
      }
    }

    void tick()
    const id = window.setInterval(() => void tick(), pollIntervalMs)

    return () => {
      active = false
      window.clearInterval(id)
    }
  }, [pollIntervalMs, shouldPoll])
}
