import './style.css'
import {
  api,
  clearSession,
  getUser,
  setSession,
  type Role,
  type Store,
  type User,
} from './api'

type Today = {
  store_name: string
  clocked_in: boolean
  last_in_at: string | null
  last_out_at: string | null
  minutes: number
  hours_label: string
  hourly_wage: number
  pay_estimate: number
}

type SessionRow = {
  in_at: string | null
  out_at: string | null
  open: boolean
  minutes: number
  hours_label: string
}

type Records = {
  year: number
  month: number
  minutes: number
  hours_label: string
  hourly_wage: number
  pay_estimate: number
  sessions: SessionRow[]
}

type Live = {
  date: string
  working: { user_id: number; name: string; last_at: string | null }[]
  off: { user_id: number; name: string }[]
}

type Member = {
  user_id: number
  name: string
  login_id: string
  role: Role
  hourly_wage: number
  status: string
}

const WEEK = ['일', '월', '화', '수', '목', '금', '토']
const STORE_KEY = 'alba_store_id'

const mounted = document.querySelector<HTMLDivElement>('#app')
if (!mounted) throw new Error('#app missing')
const root: HTMLDivElement = mounted

let user = getUser()
let stores: Store[] = []
let store: Store | null = null
let tab: 'home' | 'list' | 'more' = 'home'
let authMode: 'login' | 'signup' = 'login'
let authRole: Role = 'worker'
let clockBusy = false
let clockTimer = 0

function money(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

function hhmm(value: string | null): string {
  if (!value) return '-'
  return value.slice(11, 16)
}

function dateLabel(d = new Date()): { line: string; main: string } {
  return {
    line: `${d.getFullYear()}년 ${d.getMonth() + 1}월`,
    main: `${d.getDate()}일 (${WEEK[d.getDay()]})`,
  }
}

function clockText(d = new Date()): string {
  return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function selectedStoreId(): number | null {
  const saved = Number(localStorage.getItem(STORE_KEY) || 0)
  if (saved && stores.some((s) => s.id === saved)) return saved
  return stores[0]?.id ?? null
}

function currentStore(): Store | null {
  const id = selectedStoreId()
  return stores.find((s) => s.id === id) ?? null
}

async function loadStores(): Promise<void> {
  const data = await api<{ items: Store[] }>('/api/stores')
  stores = data.items
  store = currentStore()
  if (store) localStorage.setItem(STORE_KEY, String(store.id))
}

function getLocation(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve(null)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 15000 },
    )
  })
}

function render(): void {
  if (!user) {
    renderAuth()
    return
  }
  if (!store) {
    renderOnboard()
    return
  }
  renderMain()
}

function renderAuth(): void {
  const isSignup = authMode === 'signup'
  root.innerHTML = `
    <div class="auth-shell">
      <div class="auth-brand">알바근태</div>
      <p class="auth-tag">모바일로 출근 · 퇴근 · 급여 확인</p>
      <div class="auth-panel">
        <h2 class="auth-title">${isSignup ? '회원가입' : '로그인'}</h2>
        <p class="auth-desc">${isSignup ? '사장님 또는 알바로 가입하세요.' : '아이디와 비밀번호를 입력하세요.'}</p>
        ${
          isSignup
            ? `<div class="segment">
                <button type="button" data-role="worker" class="${authRole === 'worker' ? 'is-on' : ''}">알바</button>
                <button type="button" data-role="owner" class="${authRole === 'owner' ? 'is-on' : ''}">사장님</button>
              </div>
              <div class="auth-field"><label>이름</label><input id="name" autocomplete="name" /></div>`
            : ''
        }
        <div class="auth-field"><label>아이디</label><input id="login_id" autocomplete="username" /></div>
        <div class="auth-field"><label>비밀번호</label><input id="password" type="password" autocomplete="${isSignup ? 'new-password' : 'current-password'}" /></div>
        <p class="auth-error" id="auth-error" hidden></p>
        <button class="btn-primary auth-submit" id="auth-submit">${isSignup ? '가입하기' : '로그인'}</button>
        <button class="auth-switch" id="auth-switch">${isSignup ? '이미 계정이 있나요? 로그인' : '처음이신가요? 회원가입'}</button>
      </div>
    </div>
  `
  root.querySelectorAll<HTMLButtonElement>('[data-role]').forEach((btn) => {
    btn.addEventListener('click', () => {
      authRole = btn.dataset.role === 'owner' ? 'owner' : 'worker'
      renderAuth()
    })
  })
  root.querySelector('#auth-switch')?.addEventListener('click', () => {
    authMode = isSignup ? 'login' : 'signup'
    renderAuth()
  })
  root.querySelector('#auth-submit')?.addEventListener('click', () => void submitAuth())
}

async function submitAuth(): Promise<void> {
  const err = document.querySelector<HTMLParagraphElement>('#auth-error')
  const loginId = (document.querySelector<HTMLInputElement>('#login_id')?.value || '').trim()
  const password = document.querySelector<HTMLInputElement>('#password')?.value || ''
  const name = (document.querySelector<HTMLInputElement>('#name')?.value || '').trim()
  if (err) {
    err.hidden = true
    err.textContent = ''
  }
  try {
    const path = authMode === 'signup' ? '/api/auth/signup' : '/api/auth/login'
    const body =
      authMode === 'signup'
        ? { login_id: loginId, password, name, role: authRole }
        : { login_id: loginId, password }
    const data = await api<{ access_token: string; refresh_token: string; user: User }>(path, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    setSession(data.access_token, data.refresh_token, data.user)
    user = data.user
    await loadStores()
    render()
  } catch (e) {
    if (err) {
      err.hidden = false
      err.textContent = e instanceof Error ? e.message : '실패했습니다.'
    }
  }
}

function renderOnboard(): void {
  const isOwner = user?.role === 'owner'
  root.innerHTML = `
    <div class="auth-shell">
      <div class="auth-brand">알바근태</div>
      <h2 class="auth-title">${isOwner ? '매장을 등록하세요' : '매장에 입장하세요'}</h2>
      <p class="auth-desc">${
        isOwner
          ? '매장 이름을 넣으면 알바 초대코드가 만들어집니다.'
          : '사장님에게 받은 6자리 초대코드를 입력하세요.'
      }</p>
      <div class="auth-field">
        <label>${isOwner ? '매장 이름' : '초대코드'}</label>
        <input id="onboard-input" ${isOwner ? '' : 'style="text-transform:uppercase;letter-spacing:.12em"' } />
      </div>
      <p class="auth-error" id="auth-error" hidden></p>
      <button class="btn-primary auth-submit" id="onboard-go">${isOwner ? '매장 만들기' : '입장'}</button>
      <button class="auth-switch" id="logout">다른 계정으로</button>
    </div>
  `
  root.querySelector('#logout')?.addEventListener('click', logout)
  root.querySelector('#onboard-go')?.addEventListener('click', () => void submitOnboard())
}

async function submitOnboard(): Promise<void> {
  const err = document.querySelector<HTMLParagraphElement>('#auth-error')
  const value = (document.querySelector<HTMLInputElement>('#onboard-input')?.value || '').trim()
  try {
    if (user?.role === 'owner') {
      const created = await api<Store>('/api/stores', {
        method: 'POST',
        body: JSON.stringify({ name: value }),
      })
      localStorage.setItem(STORE_KEY, String(created.id))
    } else {
      await api('/api/stores/join', {
        method: 'POST',
        body: JSON.stringify({ invite_code: value.toUpperCase() }),
      })
    }
    await loadStores()
    render()
  } catch (e) {
    if (err) {
      err.hidden = false
      err.textContent = e instanceof Error ? e.message : '실패했습니다.'
    }
  }
}

function logout(): void {
  clearSession()
  localStorage.removeItem(STORE_KEY)
  user = null
  stores = []
  store = null
  tab = 'home'
  render()
}

function renderMain(): void {
  const isOwner = user?.role === 'owner'
  const tabs = isOwner
    ? [
        ['home', '현황'],
        ['list', '직원'],
        ['more', '더보기'],
      ]
    : [
        ['home', '출퇴근'],
        ['list', '기록'],
        ['more', '더보기'],
      ]
  root.innerHTML = `
    <div class="main-shell">
      <div class="screens">
        <section class="screen is-active" id="screen"></section>
      </div>
      <nav class="tab-bar">
        ${tabs
          .map(
            ([id, label]) =>
              `<button class="tab ${tab === id ? 'is-active' : ''}" data-tab="${id}">${label}</button>`,
          )
          .join('')}
      </nav>
    </div>
  `
  root.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      tab = btn.dataset.tab as typeof tab
      renderMain()
    })
  })
  void fillScreen()
}

async function fillScreen(): Promise<void> {
  const el = document.querySelector('#screen')
  if (!el || !store || !user) return
  if (user.role === 'owner') {
    if (tab === 'home') await fillOwnerLive(el)
    else if (tab === 'list') await fillOwnerStaff(el)
    else fillMore(el)
    return
  }
  if (tab === 'home') await fillWorkerHome(el)
  else if (tab === 'list') await fillWorkerRecords(el)
  else fillMore(el)
}

async function fillWorkerHome(el: Element): Promise<void> {
  const d = dateLabel()
  el.innerHTML = `
    <header class="screen-header">
      <h1>${store?.name ?? ''}</h1>
      <p class="sub">${user?.name} 님</p>
    </header>
    <div class="home-date">
      <div class="home-date-top">
        <div>
          <div class="date-line">${d.line}</div>
          <div class="date-main">${d.main}</div>
        </div>
        <div class="home-clock" id="live-clock">${clockText()}</div>
      </div>
    </div>
    <div id="home-body"><p class="empty">불러오는 중…</p></div>
  `
  const clockEl = document.querySelector('#live-clock')
  window.clearInterval(clockTimer)
  clockTimer = window.setInterval(() => {
    if (clockEl) clockEl.textContent = clockText()
  }, 1000)
  try {
    const today = await api<Today>(`/api/clock/today?store_id=${store!.id}`)
    const now = new Date()
    const month = await api<Records>(
      `/api/clock/records?store_id=${store!.id}&year=${now.getFullYear()}&month=${now.getMonth() + 1}`,
    )
    const body = document.querySelector('#home-body')
    if (!body) return
    body.innerHTML = `
      <div class="status-card">
        <div class="label">오늘 상태</div>
        <div class="state">${today.clocked_in ? '근무 중' : '퇴근'}</div>
        <div class="detail">출근 ${hhmm(today.last_in_at)} · 퇴근 ${hhmm(today.last_out_at)} · ${today.hours_label}</div>
      </div>
      <button class="btn-primary ${today.clocked_in ? 'btn-out' : ''}" id="clock-btn">
        ${today.clocked_in ? '퇴근하기' : '출근하기'}
      </button>
      <p class="msg msg-err" id="clock-msg" hidden></p>
      <div class="summary-row">
        <div class="summary-card"><div class="k">이번 달 근무</div><div class="v">${month.hours_label}</div></div>
        <div class="summary-card"><div class="k">예상 급여</div><div class="v">${money(month.pay_estimate)}</div></div>
      </div>
    `
    document.querySelector('#clock-btn')?.addEventListener('click', () => {
      void doClock(today.clocked_in ? 'out' : 'in')
    })
  } catch (e) {
    const body = document.querySelector('#home-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '불러오기 실패'}</p>`
  }
}

async function doClock(intent: 'in' | 'out'): Promise<void> {
  if (clockBusy || !store) return
  clockBusy = true
  const msg = document.querySelector<HTMLParagraphElement>('#clock-msg')
  const btn = document.querySelector<HTMLButtonElement>('#clock-btn')
  if (btn) btn.disabled = true
  try {
    const loc = await getLocation()
    await api('/api/clock', {
      method: 'POST',
      body: JSON.stringify({
        store_id: store.id,
        intent,
        lat: loc?.lat ?? null,
        lng: loc?.lng ?? null,
      }),
    })
    await fillScreen()
  } catch (e) {
    if (msg) {
      msg.hidden = false
      msg.textContent = e instanceof Error ? e.message : '실패했습니다.'
    }
  } finally {
    clockBusy = false
    if (btn) btn.disabled = false
  }
}

async function fillWorkerRecords(el: Element): Promise<void> {
  const now = new Date()
  el.innerHTML = `
    <header class="screen-header">
      <h1>근무 기록</h1>
      <p class="sub">${now.getFullYear()}년 ${now.getMonth() + 1}월</p>
    </header>
    <div id="list-body"><p class="empty">불러오는 중…</p></div>
  `
  try {
    const data = await api<Records>(
      `/api/clock/records?store_id=${store!.id}&year=${now.getFullYear()}&month=${now.getMonth() + 1}`,
    )
    const body = document.querySelector('#list-body')
    if (!body) return
    if (!data.sessions.length) {
      body.innerHTML = `<p class="empty">이번 달 기록이 없습니다.</p>`
      return
    }
    body.innerHTML = `
      <div class="summary-row">
        <div class="summary-card"><div class="k">합계</div><div class="v">${data.hours_label}</div></div>
        <div class="summary-card"><div class="k">예상 급여</div><div class="v">${money(data.pay_estimate)}</div></div>
      </div>
      <div class="record-list">
        ${data.sessions
          .map(
            (s) => `
          <div class="record-item">
            <div>
              <div class="d">${(s.in_at || '').slice(0, 10)}</div>
              <div class="t">${hhmm(s.in_at)} → ${s.open ? '근무 중' : hhmm(s.out_at)}</div>
            </div>
            <span class="badge ${s.open ? 'badge-open' : 'badge-out'}">${s.hours_label}</span>
          </div>`,
          )
          .join('')}
      </div>
    `
  } catch (e) {
    const body = document.querySelector('#list-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

async function fillOwnerLive(el: Element): Promise<void> {
  el.innerHTML = `
    <header class="screen-header">
      <h1>${store?.name ?? ''}</h1>
      <p class="sub">오늘 근무 현황</p>
    </header>
    <div class="invite-box">
      <div class="k">알바 초대코드</div>
      <div class="code">${store?.invite_code ?? ''}</div>
    </div>
    <div id="live-body"><p class="empty">불러오는 중…</p></div>
  `
  try {
    const data = await api<Live>(`/api/owner/${store!.id}/live`)
    const body = document.querySelector('#live-body')
    if (!body) return
    body.innerHTML = `
      <div class="pad">
        <div class="status-card">
          <div class="label">지금 근무 중</div>
          <div class="state">${data.working.length}명</div>
        </div>
        ${
          data.working.length
            ? data.working
                .map(
                  (p) => `
            <div class="person-row">
              <div>
                <div class="name">${p.name}</div>
                <div class="meta">출근 ${hhmm(p.last_at)}</div>
              </div>
              <span class="badge badge-in">근무 중</span>
            </div>`,
                )
                .join('')
            : '<p class="empty" style="margin:0 0 16px">현재 근무 중인 알바가 없습니다.</p>'
        }
        <p class="sub" style="margin:18px 0 8px;font-weight:700;color:var(--text)">미출근</p>
        ${
          data.off.length
            ? data.off
                .map(
                  (p) => `
            <div class="person-row">
              <div class="name">${p.name}</div>
              <span class="badge badge-out">대기</span>
            </div>`,
                )
                .join('')
            : '<p class="empty" style="margin:0">등록된 알바가 없습니다. 초대코드를 알려주세요.</p>'
        }
      </div>
    `
  } catch (e) {
    const body = document.querySelector('#live-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

async function fillOwnerStaff(el: Element): Promise<void> {
  el.innerHTML = `
    <header class="screen-header">
      <h1>직원</h1>
      <p class="sub">시급을 누르면 수정할 수 있습니다.</p>
    </header>
    <div id="staff-body"><p class="empty">불러오는 중…</p></div>
  `
  try {
    const data = await api<{ items: Member[] }>(`/api/stores/${store!.id}/members`)
    const workers = data.items.filter((m) => m.role === 'worker')
    const body = document.querySelector('#staff-body')
    if (!body) return
    if (!workers.length) {
      body.innerHTML = `<p class="empty">아직 입장한 알바가 없습니다.</p>`
      return
    }
    body.innerHTML = `
      <div class="pad">
        ${workers
          .map(
            (m) => `
          <div class="person-row">
            <div>
              <div class="name">${m.name}</div>
              <div class="meta">${m.login_id} · ${m.status === 'active' ? '재직' : '중지'}</div>
            </div>
            <button class="badge badge-out" data-wage="${m.user_id}">${money(m.hourly_wage)} / 시</button>
          </div>`,
          )
          .join('')}
      </div>
    `
    body.querySelectorAll<HTMLButtonElement>('[data-wage]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = Number(btn.dataset.wage)
        const current = workers.find((w) => w.user_id === id)
        const next = window.prompt('시급 (원)', String(current?.hourly_wage ?? 0))
        if (next == null) return
        const wage = Number(next.replace(/[^\d]/g, ''))
        if (!Number.isFinite(wage)) return
        void api(`/api/stores/${store!.id}/members/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ hourly_wage: wage }),
        }).then(() => fillOwnerStaff(el))
      })
    })
  } catch (e) {
    const body = document.querySelector('#staff-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

function fillMore(el: Element): void {
  const storeOptions = stores
    .map((s) => `<option value="${s.id}" ${store?.id === s.id ? 'selected' : ''}>${s.name}</option>`)
    .join('')
  el.innerHTML = `
    <header class="screen-header">
      <h1>더보기</h1>
      <p class="sub">${user?.name} · ${user?.role === 'owner' ? '사장님' : '알바'}</p>
    </header>
    <div class="pad">
      ${
        stores.length > 1
          ? `<div class="auth-field"><label>매장</label>
             <select id="store-select" style="width:100%;padding:12px 14px;border:1px solid var(--border);border-radius:10px;font-size:1rem">${storeOptions}</select></div>`
          : ''
      }
      ${
        user?.role === 'owner'
          ? `<div class="invite-box"><div class="k">초대코드</div><div class="code">${store?.invite_code ?? ''}</div></div>
             <div class="auth-field"><label>매장 위치 반경 (m, 0이면 미사용)</label>
             <input id="geofence" type="number" min="0" value="${store?.geofence_m ?? 0}" /></div>
             <button class="btn-primary" id="save-geo" style="width:100%;margin:0 0 16px">위치 반경 저장 (현재 위치)</button>`
          : `<button class="btn-secondary" id="join-more" style="width:100%;margin:0 0 16px">다른 매장 입장</button>`
      }
    </div>
    <div class="menu-list">
      <button class="menu-item" id="logout"><span>로그아웃</span><span class="chev">›</span></button>
    </div>
  `
  document.querySelector('#logout')?.addEventListener('click', logout)
  document.querySelector('#store-select')?.addEventListener('change', (ev) => {
    const id = Number((ev.target as HTMLSelectElement).value)
    localStorage.setItem(STORE_KEY, String(id))
    store = stores.find((s) => s.id === id) ?? store
    renderMain()
  })
  document.querySelector('#join-more')?.addEventListener('click', () => {
    const code = window.prompt('초대코드')
    if (!code) return
    void api('/api/stores/join', {
      method: 'POST',
      body: JSON.stringify({ invite_code: code.trim().toUpperCase() }),
    })
      .then(() => loadStores())
      .then(() => render())
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  document.querySelector('#save-geo')?.addEventListener('click', () => {
    void (async () => {
      const meters = Number((document.querySelector<HTMLInputElement>('#geofence')?.value || '0'))
      const loc = await getLocation()
      await api(`/api/stores/${store!.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          geofence_m: meters,
          lat: loc?.lat ?? store?.lat,
          lng: loc?.lng ?? store?.lng,
        }),
      })
      await loadStores()
      window.alert(meters > 0 ? `반경 ${meters}m 로 저장했습니다.` : '위치 제한을 껐습니다.')
      renderMain()
    })().catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
}

async function boot(): Promise<void> {
  if (user) {
    try {
      user = await api<User>('/api/auth/me')
      localStorage.setItem('alba_user', JSON.stringify(user))
      await loadStores()
    } catch {
      logout()
      return
    }
  }
  render()
}

void boot()
