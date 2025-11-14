import { useEffect, useState } from 'react'

export type HealthStatus = 'idle' | 'loading' | 'ok' | 'error'

type HealthResponse = {
  status: string
  service: string
  environment: string
}

export function useHealth(pollIntervalMs = 15000) {
  const [status, setStatus] = useState<HealthStatus>('idle')
  const [data, setData] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let timerId: number | undefined

    const checkHealth = async () => {
      setStatus((prev) => (prev === 'idle' ? 'loading' : prev))
      try {
        const response = await fetch('/health')
        if (!active) return

        if (!response.ok) {
          throw new Error(`Health check failed with status ${response.status}`)
        }

        const json = (await response.json()) as HealthResponse
        setData(json)
        setStatus(json.status === 'ok' ? 'ok' : 'error')
        setError(null)
      } catch (err) {
        if (!active) return
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }

    void checkHealth()

    if (pollIntervalMs > 0) {
      timerId = window.setInterval(checkHealth, pollIntervalMs)
    }

    return () => {
      active = false
      if (timerId !== undefined) {
        window.clearInterval(timerId)
      }
    }
  }, [pollIntervalMs])

  return {
    status,
    data,
    error,
    isLoading: status === 'idle' || status === 'loading',
  }
}
