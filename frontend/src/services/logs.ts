export type AppLog = {
  id: number
  level: 'INFO' | 'WARNING' | 'ERROR'
  message: string
  timestamp: string
}

// For now these are purely frontend-only logs collected during this session.
let nextId = 1
const buffer: AppLog[] = []
const MAX_LOGS = 100

export function recordAppLog(level: AppLog['level'], message: string): void {
  buffer.unshift({
    id: nextId++,
    level,
    message,
    timestamp: new Date().toISOString(),
  })
  if (buffer.length > MAX_LOGS) {
    buffer.pop()
  }
}

export function getAppLogs(): AppLog[] {
  return buffer
}

