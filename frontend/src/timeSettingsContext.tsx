import { createContext, useContext, useEffect, useMemo, useState } from 'react'

import {
  DISPLAY_TIMEZONE_STORAGE_KEY,
  type DisplayTimeZone,
  loadDisplayTimeZone,
  normalizeDisplayTimeZone,
  saveDisplayTimeZone,
} from './timeSettings'

type TimeSettingsContextValue = {
  displayTimeZone: DisplayTimeZone
  setDisplayTimeZone: (tz: DisplayTimeZone) => void
}

const TimeSettingsContext = createContext<TimeSettingsContextValue | null>(null)

export function TimeSettingsProvider({ children }: { children: React.ReactNode }) {
  const [displayTimeZone, setDisplayTimeZoneState] = useState<DisplayTimeZone>(() =>
    loadDisplayTimeZone(),
  )

  const setDisplayTimeZone = (tz: DisplayTimeZone) => {
    const normalized = normalizeDisplayTimeZone(tz)
    setDisplayTimeZoneState(normalized)
    saveDisplayTimeZone(normalized)
  }

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== DISPLAY_TIMEZONE_STORAGE_KEY) return
      setDisplayTimeZoneState(normalizeDisplayTimeZone(e.newValue))
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const value = useMemo(
    () => ({ displayTimeZone, setDisplayTimeZone }),
    [displayTimeZone],
  )

  return (
    <TimeSettingsContext.Provider value={value}>
      {children}
    </TimeSettingsContext.Provider>
  )
}

export function useTimeSettings(): TimeSettingsContextValue {
  const ctx = useContext(TimeSettingsContext)
  if (!ctx) {
    throw new Error('useTimeSettings must be used within TimeSettingsProvider')
  }
  return ctx
}

