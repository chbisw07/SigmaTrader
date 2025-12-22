import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'

type Paksha = 'Shukla Paksha' | 'Krishna Paksha'

const SYNODIC_MONTH_DAYS = 29.530588853
// Reference new moon: 2000-01-06 18:14 UTC (approx).
const REF_NEW_MOON_JD = 2451550.1

const TITHI_NAMES_1_TO_14 = [
  'Pratipada',
  'Dwitiya',
  'Tritiya',
  'Chaturthi',
  'Panchami',
  'Shashthi',
  'Saptami',
  'Ashtami',
  'Navami',
  'Dashami',
  'Ekadashi',
  'Dwadashi',
  'Trayodashi',
  'Chaturdashi',
] as const

function julianDayUtc(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5
}

function mod(n: number, m: number): number {
  return ((n % m) + m) % m
}

function formatHeaderDateTime(date: Date): string {
  const weekday = date.toLocaleDateString('en-US', { weekday: 'short' })
  const day = String(date.getDate()).padStart(2, '0')
  const month = date.toLocaleDateString('en-US', { month: 'short' })
  const year = date.getFullYear()
  const time = date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
  return `${weekday}, ${day} ${month} ${year}, ${time}`
}

function computeMoonPhase(date: Date): {
  phase: number
  illumination: number
  waxing: boolean
  paksha: Paksha
  tithiName: string
} {
  const jd = julianDayUtc(date)
  const ageDays = mod(jd - REF_NEW_MOON_JD, SYNODIC_MONTH_DAYS)
  const phase = ageDays / SYNODIC_MONTH_DAYS
  const waxing = phase < 0.5
  const illumination = 0.5 * (1 - Math.cos(2 * Math.PI * phase))

  const tithi = Math.min(30, Math.max(1, Math.floor(phase * 30) + 1))
  if (tithi <= 15) {
    const tithiName =
      tithi === 15 ? 'Purnima' : TITHI_NAMES_1_TO_14[tithi - 1] ?? `Tithi ${tithi}`
    return {
      phase,
      illumination,
      waxing,
      paksha: 'Shukla Paksha',
      tithiName,
    }
  }

  const krishnaIndex = tithi - 15
  const tithiName =
    krishnaIndex === 15
      ? 'Amavasya'
      : TITHI_NAMES_1_TO_14[krishnaIndex - 1] ?? `Tithi ${tithi}`
  return {
    phase,
    illumination,
    waxing,
    paksha: 'Krishna Paksha',
    tithiName,
  }
}

function MoonPhaseIcon({ phase, size = 22 }: { phase: number; size?: number }) {
  const k = Math.cos(2 * Math.PI * phase) // +1 new, -1 full, 0 quarter
  const waxing = phase < 0.5
  const r = 10
  const rx = Math.max(0.001, Math.abs(k) * r)

  const outerSweep = waxing ? 1 : 0
  const innerSweep = waxing ? (k >= 0 ? 1 : 0) : k >= 0 ? 0 : 1

  const innerArc =
    rx < 0.01
      ? 'L 0 -10'
      : `A ${rx.toFixed(3)} ${r} 0 0 ${innerSweep} 0 -10`

  const d = `M 0 -10 A ${r} ${r} 0 0 ${outerSweep} 0 10 ${innerArc} Z`

  return (
    <Box
      component="svg"
      viewBox="-12 -12 24 24"
      sx={{
        width: size,
        height: size,
        flex: '0 0 auto',
        display: 'block',
      }}
      aria-hidden="true"
    >
      <circle cx="0" cy="0" r="10" fill="rgba(255,255,255,0.18)" />
      <path d={d} fill="rgba(255,255,255,0.85)" />
      <circle
        cx="0"
        cy="0"
        r="10"
        fill="none"
        stroke="rgba(255,255,255,0.65)"
        strokeWidth="1"
      />
    </Box>
  )
}

export function MoonPhaseHeader() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const info = useMemo(() => computeMoonPhase(now), [now])
  const datetimeLabel = useMemo(() => formatHeaderDateTime(now), [now])

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        color: 'common.white',
        textAlign: 'center',
        maxWidth: '100%',
        overflow: 'hidden',
      }}
    >
      <Typography
        variant="body2"
        sx={{
          fontWeight: 600,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {info.paksha}, {info.tithiName}
      </Typography>
      <MoonPhaseIcon phase={info.phase} />
      <Typography
        variant="body2"
        sx={{
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          opacity: 0.95,
        }}
      >
        {datetimeLabel}
      </Typography>
    </Box>
  )
}

