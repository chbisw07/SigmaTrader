import { useCallback, useEffect, useState } from 'react'

import { listCustomIndicators, type CustomIndicator } from '../services/alertsV3'

export function useCustomIndicators({ enabled }: { enabled?: boolean } = {}) {
  const [customIndicators, setCustomIndicators] = useState<CustomIndicator[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await listCustomIndicators()
      setCustomIndicators(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load custom indicators')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (enabled === false) return
    void refresh()
  }, [enabled, refresh])

  return { customIndicators, loading, error, refresh }
}

