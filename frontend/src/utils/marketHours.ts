type MarketHoursOptions = {
  timeZone?: string
  openHHMM?: [number, number]
  closeHHMM?: [number, number]
}

function getTimePartsInZone(
  date: Date,
  timeZone: string,
): { weekday: string; hour: number; minute: number } | null {
  try {
    const fmt = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    const parts = fmt.formatToParts(date)
    const weekday = parts.find((p) => p.type === 'weekday')?.value ?? ''
    const hourStr = parts.find((p) => p.type === 'hour')?.value ?? ''
    const minuteStr = parts.find((p) => p.type === 'minute')?.value ?? ''
    const hour = Number(hourStr)
    const minute = Number(minuteStr)
    if (!weekday || !Number.isFinite(hour) || !Number.isFinite(minute)) return null
    return { weekday, hour, minute }
  } catch {
    return null
  }
}

export function isMarketOpen(now: Date = new Date(), opts?: MarketHoursOptions): boolean {
  const timeZone = opts?.timeZone ?? 'Asia/Kolkata'
  const [openH, openM] = opts?.openHHMM ?? [9, 15]
  const [closeH, closeM] = opts?.closeHHMM ?? [15, 30]

  const parts = getTimePartsInZone(now, timeZone)
  if (!parts) return false

  const wd = parts.weekday.toLowerCase()
  if (wd.startsWith('sat') || wd.startsWith('sun')) return false

  const minutes = parts.hour * 60 + parts.minute
  const start = openH * 60 + openM
  const end = closeH * 60 + closeM
  return minutes >= start && minutes <= end
}

