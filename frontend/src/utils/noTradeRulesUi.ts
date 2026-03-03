const UI_PAUSE_AUTO_MARKER_RE = /#\s*UI_PAUSE_AUTO\b/i

export function isValidHHMM(value: string): boolean {
  const s = (value || '').trim()
  const m = /^(\d{2}):(\d{2})$/.exec(s)
  if (!m) return false
  const hh = Number(m[1])
  const mm = Number(m[2])
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return false
  return hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59
}

export function extractUiPauseAutoWindow(
  rulesText: string,
): { start: string; end: string } | null {
  const lines = String(rulesText || '').split(/\r?\n/)
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i]
    if (!UI_PAUSE_AUTO_MARKER_RE.test(line)) continue
    const m =
      /^\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s+PAUSE_AUTO\s+ALL\b/i.exec(line)
    if (!m) return null
    const start = m[1]
    const end = m[2]
    if (!isValidHHMM(start) || !isValidHHMM(end)) return null
    return { start, end }
  }
  return null
}

export function clearUiPauseAutoRule(rulesText: string): string {
  const lines = String(rulesText || '').split(/\r?\n/)
  const kept = lines.filter((l) => !UI_PAUSE_AUTO_MARKER_RE.test(l))
  while (kept.length > 0 && !kept[kept.length - 1].trim()) kept.pop()
  return kept.join('\n')
}

export function setUiPauseAutoRule(
  rulesText: string,
  startHHMM: string,
  endHHMM: string,
): string {
  if (!isValidHHMM(startHHMM) || !isValidHHMM(endHHMM)) return String(rulesText || '')
  const base = clearUiPauseAutoRule(rulesText)
  const baseLines = base ? base.split(/\r?\n/) : []
  const ruleLine = `${startHHMM}-${endHHMM} PAUSE_AUTO ALL # UI_PAUSE_AUTO`
  const out = [...baseLines, ruleLine]
  return out.join('\n').trimEnd()
}

