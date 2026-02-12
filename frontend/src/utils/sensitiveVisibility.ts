import { useCallback, useSyncExternalStore } from 'react'

const STORAGE_PREFIX = 'st_sensitive_visibility_v1:'
const EVENT_NAME = 'st_sensitive_visibility_changed_v1'

const cache = new Map<string, boolean>()
const subscribers = new Map<string, Set<() => void>>()
let globalListenersAttached = false

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
  try {
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { key, value } }))
  } catch {
    // ignore event errors
  }
}

function publish(key: string): void {
  const set = subscribers.get(key)
  if (!set || set.size === 0) return
  for (const cb of set) cb()
}

function getCached(key: string, defaultVisible: boolean): boolean {
  if (cache.has(key)) return cache.get(key)!
  const v = readBool(key, defaultVisible)
  cache.set(key, v)
  return v
}

function setCached(key: string, value: boolean): void {
  cache.set(key, value)
  writeBool(key, value)
  publish(key)
}

function ensureGlobalListeners(): void {
  if (globalListenersAttached) return
  if (typeof window === 'undefined') return
  globalListenersAttached = true

  window.addEventListener(EVENT_NAME, (evt: Event) => {
    const detail = (evt as CustomEvent<{ key?: string; value?: boolean }>).detail
    const k = detail?.key
    if (!k) return
    if (typeof detail.value === 'boolean') {
      cache.set(k, detail.value)
    } else {
      cache.set(k, readBool(k, false))
    }
    publish(k)
  })

  window.addEventListener('storage', (evt: StorageEvent) => {
    if (evt.storageArea !== window.localStorage) return
    const fullKey = evt.key || ''
    if (!fullKey.startsWith(STORAGE_PREFIX)) return
    const k = fullKey.slice(STORAGE_PREFIX.length)
    cache.set(k, readBool(k, false))
    publish(k)
  })
}

export function useSensitiveVisibility(key: string, defaultVisible = false): {
  visible: boolean
  setVisible: (next: boolean) => void
  toggle: () => void
} {
  const subscribe = useCallback(
    (cb: () => void) => {
      ensureGlobalListeners()
      let set = subscribers.get(key)
      if (!set) {
        set = new Set()
        subscribers.set(key, set)
      }
      set.add(cb)
      return () => {
        const s = subscribers.get(key)
        if (!s) return
        s.delete(cb)
        if (s.size === 0) subscribers.delete(key)
      }
    },
    [key],
  )

  const getSnapshot = useCallback(() => getCached(key, defaultVisible), [key, defaultVisible])
  const visible = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  const setVisible = useCallback(
    (next: boolean) => {
      setCached(key, next)
    },
    [key],
  )

  const toggle = useCallback(() => {
    const next = !getCached(key, defaultVisible)
    setCached(key, next)
  }, [key, defaultVisible, getSnapshot])

  return { visible, setVisible, toggle }
}
