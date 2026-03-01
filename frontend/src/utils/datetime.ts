const HAS_TIMEZONE_SUFFIX_RE = /(z|[+-]\d{2}:?\d{2})$/i
const NAIVE_DATETIME_RE =
  /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?$/

export function parseBackendDate(value: unknown): Date | null {
  if (value instanceof Date) return value
  if (typeof value === 'number') return new Date(value)
  if (typeof value !== 'string') return null

  const raw = value.trim()
  if (!raw) return null

  let normalized = raw
  if (!HAS_TIMEZONE_SUFFIX_RE.test(normalized) && NAIVE_DATETIME_RE.test(normalized)) {
    normalized = normalized.replace(' ', 'T') + 'Z'
  }

  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) return null
  return d
}

export function formatInTimeZone(
  value: unknown,
  timeZone?: string,
  opts?: Intl.DateTimeFormatOptions,
): string {
  const d = parseBackendDate(value)
  if (!d) return ''
  const options = { ...opts, ...(timeZone ? { timeZone } : {}) }
  return d.toLocaleString('en-IN', options)
}

export function formatIst(
  value: unknown,
  opts?: Intl.DateTimeFormatOptions,
): string {
  return formatInTimeZone(value, 'Asia/Kolkata', opts)
}

export function formatInDisplayTimeZone(
  value: unknown,
  displayTimeZone: 'LOCAL' | string,
  opts?: Intl.DateTimeFormatOptions,
): string {
  if (displayTimeZone === 'LOCAL') return formatInTimeZone(value, undefined, opts)
  return formatInTimeZone(value, displayTimeZone, opts)
}

export function getClientTimeContext(): {
  client_now_ms: number
  client_time_zone: string | null
  client_utc_offset_minutes: number
} {
  const now = new Date()
  let tz: string | null = null
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone ?? null
  } catch {
    tz = null
  }
  // JS getTimezoneOffset() is minutes to add to local time to get UTC.
  // Convert to "minutes ahead of UTC" (e.g., IST => +330).
  const utcOffsetMinutes = -now.getTimezoneOffset()
  return {
    client_now_ms: now.getTime(),
    client_time_zone: tz,
    client_utc_offset_minutes: utcOffsetMinutes,
  }
}
