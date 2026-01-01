import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import { useEffect, useId, useMemo, useState } from 'react'

import { useTimeSettings } from '../timeSettingsContext'

type Paksha = 'Shukla Paksha' | 'Krishna Paksha'

// Panchang-style tithi is based on the angular separation between the Moon and the Sun
// (geocentric ecliptic longitudes). This is substantially more accurate than using a
// fixed reference new moon + synodic month approximation, and matches common Indian
// calendar computations (Surya Siddhanta-style tithi is also based on this separation).

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

function mod2pi(x: number): number {
  return mod(x, 2 * Math.PI)
}

function toDaysSinceJ2000(date: Date): number {
  // J2000.0 = 2000-01-01 12:00 TT (we use UTC; good enough for UI display).
  return julianDayUtc(date) - 2451545.0
}

// Low-precision solar/lunar longitude helpers (adapted from common simplified algorithms).
// These are sufficient for phase/tithi classification for UI purposes.
const RAD = Math.PI / 180

function solarMeanAnomaly(d: number): number {
  return RAD * (357.5291 + 0.98560028 * d)
}

function eclipticLongitudeOfSun(M: number): number {
  const C =
    RAD *
    (1.9148 * Math.sin(M) +
      0.02 * Math.sin(2 * M) +
      0.0003 * Math.sin(3 * M))
  const P = RAD * 102.9372 // perihelion of Earth
  return mod2pi(M + C + P + Math.PI)
}

function eclipticLongitudeOfMoon(d: number): number {
  const L = RAD * (218.316 + 13.176396 * d) // mean longitude
  const M = RAD * (134.963 + 13.064993 * d) // mean anomaly
  // We only need geocentric ecliptic longitude; a single dominant term is fine.
  return mod2pi(L + RAD * 6.289 * Math.sin(M))
}

function formatHeaderDateTime(date: Date, timeZone?: string): string {
  const opts: Intl.DateTimeFormatOptions = {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    ...(timeZone ? { timeZone } : {}),
  }

  const parts = new Intl.DateTimeFormat('en-US', opts).formatToParts(date)
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? ''

  const weekday = get('weekday')
  const day = get('day')
  const month = get('month')
  const year = get('year')
  const hour = get('hour')
  const minute = get('minute')
  const second = get('second')
  const dayPeriod = get('dayPeriod')

  return `${weekday}, ${day} ${month} ${year}, ${hour}:${minute}:${second} ${dayPeriod}`
}

function computeMoonPhase(date: Date): {
  phase: number
  illumination: number
  waxing: boolean
  paksha: Paksha
  tithiName: string
} {
  const d = toDaysSinceJ2000(date)
  const sunLng = eclipticLongitudeOfSun(solarMeanAnomaly(d))
  const moonLng = eclipticLongitudeOfMoon(d)

  // Elongation: 0=new moon, π=full moon, 2π=new.
  const elong = mod2pi(moonLng - sunLng)
  const phase = elong / (2 * Math.PI)
  const waxing = elong < Math.PI
  const illumination = 0.5 * (1 - Math.cos(elong))

  const tithi = Math.min(30, Math.max(1, Math.floor((elong * 30) / (2 * Math.PI)) + 1))
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
  // Phase here is based on elongation (0=new, 0.5=full).
  // Build a simple mask-based moon icon:
  // - Draw a dim "dark disk" as the base.
  // - Draw a bright disk, then mask it with a shifted dark disk.
  // This yields a gibbous/crescent shape that becomes almost fully white
  // near Purnima (as expected for Shukla Chaturdashi).
  const rawId = useId()
  const id = rawId.replace(/[^a-zA-Z0-9_-]/g, '_')
  const p = mod(phase, 1)
  const waxing = p < 0.5
  const r = 10

  // Illumination fraction (0..1): 0=new, 1=full.
  const illum = 0.5 * (1 - Math.cos(2 * Math.PI * p))
  // Shift the dark mask: 0=new (fully covered), 2r=full (not covered).
  // Keep a tiny dark sliver for "almost full" nights (e.g., Chaturdashi),
  // but remove it at true full moon.
  const dxMaxNonFull = 2 * r - 1.2
  const dx = illum >= 0.9995 ? 2 * r : Math.min(dxMaxNonFull, 2 * r * illum)
  const darkX = waxing ? -dx : dx

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
      <defs>
        <mask
          id={`moon-mask-${id}`}
          x={-12}
          y={-12}
          width={24}
          height={24}
          maskUnits="userSpaceOnUse"
          maskContentUnits="userSpaceOnUse"
        >
          <rect x="-12" y="-12" width="24" height="24" fill="white" />
          <circle cx={darkX} cy="0" r={r} fill="black" />
        </mask>
      </defs>
      <circle cx="0" cy="0" r={r} fill="rgba(0,0,0,0.28)" />
      <circle
        cx="0"
        cy="0"
        r={r}
        fill="rgba(255,255,255,1)"
        mask={`url(#moon-mask-${id})`}
      />
      <circle
        cx="0"
        cy="0"
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.75)"
        strokeWidth="1"
      />
    </Box>
  )
}

export function MoonPhaseHeader() {
  const { displayTimeZone } = useTimeSettings()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const info = useMemo(() => computeMoonPhase(now), [now])
  const tz = displayTimeZone === 'LOCAL' ? undefined : displayTimeZone
  const datetimeLabel = useMemo(() => formatHeaderDateTime(now, tz), [now, tz])

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.25,
        color: 'common.white',
        textAlign: 'center',
        maxWidth: '100%',
        overflow: 'hidden',
      }}
    >
      <Typography
        variant="body1"
        sx={{
          fontWeight: 600,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          fontSize: '0.95rem',
        }}
      >
        {info.paksha}, {info.tithiName}
      </Typography>
      <MoonPhaseIcon phase={info.phase} size={24} />
      <Typography
        variant="body1"
        sx={{
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          opacity: 0.95,
          fontSize: '0.95rem',
        }}
      >
        {datetimeLabel}
      </Typography>
    </Box>
  )
}
