import { useCallback, useEffect, useState } from 'react'

const STORAGE_PREFIX = 'st_sensitive_visibility_v1:'

function readBool(key: string, defaultValue: boolean): boolean {
  if (typeof window === 'undefined') return defaultValue
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${key}`)
    if (raw == null) return defaultValue
    if (raw === '1' || raw.toLowerCase() === 'true') return true
    if (raw === '0' || raw.toLowerCase() === 'false') return false
    return defaultValue
  } catch {
    return defaultValue
  }
}

function writeBool(key: string, value: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${key}`, value ? '1' : '0')
  } catch {
    // ignore persistence errors
  }
}

export function useSensitiveVisibility(key: string, defaultVisible = false): {
  visible: boolean
  setVisible: (next: boolean) => void
  toggle: () => void
} {
  const [visible, setVisibleState] = useState<boolean>(() => readBool(key, defaultVisible))

  useEffect(() => {
    setVisibleState(readBool(key, defaultVisible))
  }, [key, defaultVisible])

  const setVisible = useCallback(
    (next: boolean) => {
      setVisibleState(next)
      writeBool(key, next)
    },
    [key],
  )

  const toggle = useCallback(() => {
    setVisibleState((prev) => {
      const next = !prev
      writeBool(key, next)
      return next
    })
  }, [key])

  return { visible, setVisible, toggle }
}
