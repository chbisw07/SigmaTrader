const LS_PREFIX = 'st_ai_tm_flags_v1'
export const AI_TM_FLAGS_CHANGED_EVENT = 'st_ai_tm_flags_changed_v1'

function readBoolParam(name: string): boolean | null {
  if (typeof window === 'undefined') return null
  try {
    const params = new URLSearchParams(window.location.search)
    const v = params.get(name)
    if (v === null) return null
    if (v === '1' || v === 'true') return true
    if (v === '0' || v === 'false') return false
  } catch {
    // ignore
  }
  return null
}

function readBoolLS(name: string): boolean | null {
  if (typeof window === 'undefined') return null
  try {
    const v = window.localStorage.getItem(`${LS_PREFIX}:${name}`)
    if (v === null) return null
    if (v === '1') return true
    if (v === '0') return false
  } catch {
    // ignore
  }
  return null
}

function writeBoolLS(name: string, enabled: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(`${LS_PREFIX}:${name}`, enabled ? '1' : '0')
    window.dispatchEvent(new Event(AI_TM_FLAGS_CHANGED_EVENT))
  } catch {
    // ignore
  }
}

export type AiTmFeatureFlags = {
  ai_assistant_enabled: boolean
  ai_execution_enabled: boolean
  kite_mcp_enabled: boolean
  monitoring_enabled: boolean
}

export function getAiTmFeatureFlags(): AiTmFeatureFlags {
  const ai_assistant_enabled =
    readBoolParam('ai_assistant_enabled') ??
    readBoolLS('ai_assistant_enabled') ??
    false
  const ai_execution_enabled =
    readBoolParam('ai_execution_enabled') ??
    readBoolLS('ai_execution_enabled') ??
    false
  const kite_mcp_enabled =
    readBoolParam('kite_mcp_enabled') ?? readBoolLS('kite_mcp_enabled') ?? false
  const monitoring_enabled =
    readBoolParam('monitoring_enabled') ??
    readBoolLS('monitoring_enabled') ??
    false

  return {
    ai_assistant_enabled,
    ai_execution_enabled,
    kite_mcp_enabled,
    monitoring_enabled,
  }
}

export function isAiAssistantEnabled(): boolean {
  return getAiTmFeatureFlags().ai_assistant_enabled
}

export function isAiExecutionEnabled(): boolean {
  return getAiTmFeatureFlags().ai_execution_enabled
}

export function isKiteMcpEnabled(): boolean {
  return getAiTmFeatureFlags().kite_mcp_enabled
}

export function isMonitoringEnabled(): boolean {
  return getAiTmFeatureFlags().monitoring_enabled
}

export function setAiTmFeatureFlag(name: keyof AiTmFeatureFlags, enabled: boolean): void {
  writeBoolLS(name, enabled)
}
