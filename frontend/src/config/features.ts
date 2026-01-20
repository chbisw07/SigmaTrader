export const FEATURE_GROUPS_REDESIGN = 'FEATURE_GROUPS_REDESIGN'

const LS_KEY = 'st_feature_groups_redesign_v1'

export function isGroupsRedesignEnabled(): boolean {
  if (typeof window === 'undefined') return false
  try {
    const params = new URLSearchParams(window.location.search)
    const qp = params.get('feature_groups_redesign')
    if (qp === '1' || qp === 'true') return true
    if (qp === '0' || qp === 'false') return false
  } catch {
    // ignore
  }

  try {
    return window.localStorage.getItem(LS_KEY) === '1'
  } catch {
    return false
  }
}

export function setGroupsRedesignEnabled(enabled: boolean): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(LS_KEY, enabled ? '1' : '0')
  } catch {
    // ignore
  }
}

