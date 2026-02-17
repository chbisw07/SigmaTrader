const ENABLED_KEY = 'st_desktop_alert_notifications_enabled_v1'
const LAST_SEEN_TV_ALERT_ID_KEY = 'st_desktop_alert_notifications_last_seen_tv_alert_id_v1'
const LAST_SEEN_ALERT_EVENT_ID_KEY =
  'st_desktop_alert_notifications_last_seen_alert_event_id_v1'

export const DESKTOP_NOTIFICATIONS_CHANGED_EVENT = 'st_desktop_notifications_changed_v1'

function _safeGetItem(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function _safeSetItem(key: string, value: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // ignore
  }
}

function _safeRemoveItem(key: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export function getDesktopAlertNotificationsEnabled(): boolean {
  return _safeGetItem(ENABLED_KEY) === '1'
}

export function setDesktopAlertNotificationsEnabled(enabled: boolean): void {
  if (enabled) _safeSetItem(ENABLED_KEY, '1')
  else _safeRemoveItem(ENABLED_KEY)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(DESKTOP_NOTIFICATIONS_CHANGED_EVENT))
  }
}

function _parseStoredId(raw: string | null): number | null {
  if (!raw) return null
  const n = Number(raw)
  if (!Number.isFinite(n) || n <= 0) return null
  return Math.floor(n)
}

export function getLastSeenTvAlertId(): number | null {
  return _parseStoredId(_safeGetItem(LAST_SEEN_TV_ALERT_ID_KEY))
}

export function setLastSeenTvAlertId(id: number | null): void {
  if (id == null) _safeRemoveItem(LAST_SEEN_TV_ALERT_ID_KEY)
  else _safeSetItem(LAST_SEEN_TV_ALERT_ID_KEY, String(Math.floor(id)))
}

export function getLastSeenAlertEventId(): number | null {
  return _parseStoredId(_safeGetItem(LAST_SEEN_ALERT_EVENT_ID_KEY))
}

export function setLastSeenAlertEventId(id: number | null): void {
  if (id == null) _safeRemoveItem(LAST_SEEN_ALERT_EVENT_ID_KEY)
  else _safeSetItem(LAST_SEEN_ALERT_EVENT_ID_KEY, String(Math.floor(id)))
}

