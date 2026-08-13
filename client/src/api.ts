export type Role = 'owner' | 'manager' | 'worker'

export type User = {
  id: number
  login_id: string
  name: string
  role: Role
  employee_no?: string
  store_id?: number
  store_name?: string
  hourly_wage?: number
  auth_status?: string
  department_id?: number
  department_name?: string
}

export type Manager = {
  id: number
  store_id: number
  department_id: number
  user_id: number
  login_id: string
  name: string
  department_name: string
  department_code: string
}

export type Department = {
  id: number
  store_id: number
  code: string
  name: string
}

export type Employee = {
  id: number
  store_id: number
  employee_no: string
  name: string
  department_id: number | null
  department_name: string | null
  hire_date: string | null
  status: string
  auth_status: string
  auth_label: string
  hourly_wage: number
}

export type AttendanceEvent = {
  id: number
  event_type: string
  event_label: string
  occurred_at: string
  source: string | null
  employee_no: string
  employee_name: string
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

export type Today = {
  store_name: string
  clocked_in: boolean
  last_in_at: string | null
  last_out_at: string | null
  minutes: number
  hours_label: string
  hourly_wage: number
  pay_estimate: number
}

export type SessionRow = {
  in_at: string | null
  out_at: string | null
  open: boolean
  minutes: number
  hours_label: string
}

export type Records = {
  year: number
  month: number
  minutes: number
  hours_label: string
  hourly_wage: number
  pay_estimate: number
  sessions: SessionRow[]
}

export type Live = {
  date: string
  working: {
    employee_id: number
    employee_no: string
    name: string
    department_name?: string
    last_at: string | null
  }[]
  off: {
    employee_id: number
    employee_no: string
    name: string
    department_name?: string
  }[]
}

export type Member = {
  user_id: number
  name: string
  login_id: string
  role: Role
  hourly_wage: number
  status: string
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

export function createSession(prefix: string, refreshPath = '/api/auth/refresh') {
  const ACCESS_KEY = `${prefix}_access`
  const REFRESH_KEY = `${prefix}_refresh`
  const USER_KEY = `${prefix}_user`
  const STORE_KEY = `${prefix}_store_id`

  function getUser(): User | null {
    try {
      const raw = localStorage.getItem(USER_KEY)
      return raw ? (JSON.parse(raw) as User) : null
    } catch {
      return null
    }
  }

  function setSession(access: string, refresh: string, user: User): void {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  }

  function clearSession(): void {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(USER_KEY)
  }

  function getStoreId(): number | null {
    const n = Number(localStorage.getItem(STORE_KEY) || 0)
    return n || null
  }

  function setStoreId(id: number): void {
    localStorage.setItem(STORE_KEY, String(id))
  }

  async function tryRefresh(): Promise<boolean> {
    const refresh = localStorage.getItem(REFRESH_KEY)
    if (!refresh) return false
    const res = await fetch(refreshPath, {
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

  async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
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

  return { getUser, setSession, clearSession, getStoreId, setStoreId, api, STORE_KEY }
}

export const workerSession = createSession('alba_worker', '/api/auth/worker/refresh')
export const adminSession = createSession('alba_admin')

export function money(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

export function hhmm(value: string | null): string {
  if (!value) return '-'
  return value.slice(11, 16)
}

export const WEEK = ['일', '월', '화', '수', '목', '금', '토']
