export type CurrentUser = {
  id: number
  username: string
  role: string
  display_name?: string | null
  theme_id?: string | null
}

export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const res = await fetch('/api/auth/me', { credentials: 'include' })
  if (res.status === 401) {
    return null
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to load current user (${res.status})${
        body ? `: ${body}` : ''
      }`,
    )
  }
  return (await res.json()) as CurrentUser
}

export async function login(
  username: string,
  password: string,
): Promise<CurrentUser> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Login failed (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as CurrentUser
}

export async function register(
  username: string,
  password: string,
  displayName?: string,
): Promise<CurrentUser> {
  const res = await fetch('/api/auth/register', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      display_name: displayName ?? username,
    }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Registration failed (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as CurrentUser
}

export async function logout(): Promise<void> {
  const res = await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
  if (!res.ok && res.status !== 204) {
    const body = await res.text()
    throw new Error(
      `Logout failed (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
}

export async function updateTheme(themeId: string): Promise<CurrentUser> {
  const res = await fetch('/api/auth/theme', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme_id: themeId }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to update theme (${res.status})${body ? `: ${body}` : ''}`,
    )
  }
  return (await res.json()) as CurrentUser
}

function extractFastApiDetail(text: string): string {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    if (typeof parsed?.detail === 'string') return parsed.detail
  } catch {
    // Not JSON; fall back to raw body.
  }
  return text
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const res = await fetch('/api/auth/change-password', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })

  if (res.status === 204) return
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    const detail = body ? extractFastApiDetail(body) : ''
    throw new Error(
      `Change password failed (${res.status})${detail ? `: ${detail}` : ''}`,
    )
  }
}
