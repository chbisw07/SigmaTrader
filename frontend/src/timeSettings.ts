export type DisplayTimeZone = 'LOCAL' | string

export const DISPLAY_TIMEZONE_STORAGE_KEY = 'st_display_timezone_v1'
export const DEFAULT_DISPLAY_TIMEZONE: DisplayTimeZone = 'Asia/Kolkata'

export function getSystemTimeZone(): string | null {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    return tz || null
  } catch {
    return null
  }
}

export function isValidIanaTimeZone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

export function normalizeDisplayTimeZone(raw: unknown): DisplayTimeZone {
  if (raw == null) return DEFAULT_DISPLAY_TIMEZONE
  const s = String(raw).trim()
  if (!s) return DEFAULT_DISPLAY_TIMEZONE
  if (s.toUpperCase() === 'LOCAL') return 'LOCAL'
  if (isValidIanaTimeZone(s)) return s
  return DEFAULT_DISPLAY_TIMEZONE
}

export function loadDisplayTimeZone(): DisplayTimeZone {
  if (typeof window === 'undefined') return DEFAULT_DISPLAY_TIMEZONE
  try {
    return normalizeDisplayTimeZone(
      window.localStorage.getItem(DISPLAY_TIMEZONE_STORAGE_KEY),
    )
  } catch {
    return DEFAULT_DISPLAY_TIMEZONE
  }
}

export function saveDisplayTimeZone(tz: DisplayTimeZone): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(DISPLAY_TIMEZONE_STORAGE_KEY, tz)
  } catch {
    // ignore
  }
}

