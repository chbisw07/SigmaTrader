import { useCallback, useEffect, useState } from 'react'

const STORAGE_PREFIX = 'st_sensitive_visibility_v1:'
const EVENT_NAME = 'st_sensitive_visibility_changed_v1'

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
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { key, value } }))
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

  useEffect(() => {
    if (typeof window === 'undefined') return

    const onCustom = (evt: Event) => {
      const detail = (evt as CustomEvent<{ key?: string; value?: boolean }>).detail
      if (!detail || detail.key !== key) return
      if (typeof detail.value === 'boolean') {
        setVisibleState(detail.value)
      } else {
        setVisibleState(readBool(key, defaultVisible))
      }
    }

    const onStorage = (evt: StorageEvent) => {
      if (evt.storageArea !== window.localStorage) return
      if (evt.key !== `${STORAGE_PREFIX}${key}`) return
      setVisibleState(readBool(key, defaultVisible))
    }

    window.addEventListener(EVENT_NAME, onCustom)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(EVENT_NAME, onCustom)
      window.removeEventListener('storage', onStorage)
    }
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
