const ACCESS_KEY = 'alba_access'
const REFRESH_KEY = 'alba_refresh'
const USER_KEY = 'alba_user'

export type Role = 'owner' | 'worker'

export type User = {
  id: number
  login_id: string
  name: string
  role: Role
}

export type Store = {
  id: number
  owner_id: number
  name: string
  invite_code: string
  lat: number | null
  lng: number | null
  geofence_m: number
  hourly_wage?: number
  status?: string
}

function detailMessage(data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d) && d[0] && typeof d[0] === 'object' && 'msg' in d[0]) {
      return String((d[0] as { msg: unknown }).msg)
    }
  }
  return fallback
}

export function getUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function setSession(access: string, refresh: string, user: User): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return false
  const res = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) return false
  const data = (await res.json()) as {
    access_token: string
    refresh_token: string
    user: User
  }
  setSession(data.access_token, data.refresh_token, data.user)
  return true
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const access = localStorage.getItem(ACCESS_KEY)
  if (access) headers.set('Authorization', `Bearer ${access}`)
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401 && retry) {
    const ok = await tryRefresh()
    if (ok) return api<T>(path, init, false)
    clearSession()
    throw new Error('로그인이 만료되었습니다.')
  }
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    throw new Error(detailMessage(data, `요청 실패 (${res.status})`))
  }
  return data as T
}
