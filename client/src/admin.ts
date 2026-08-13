import './style.css'
import {
  adminSession,
  hhmm,
  money,
  type Live,
  type Member,
  type Store,
  type User,
} from './api'

const { api, getUser, setSession, clearSession, getStoreId, setStoreId } = adminSession

const mounted = document.querySelector<HTMLDivElement>('#app')
if (!mounted) throw new Error('#app missing')
const root: HTMLDivElement = mounted

let user = getUser()
let stores: Store[] = []
let store: Store | null = null
let tab: 'home' | 'list' | 'qr' | 'more' = 'home'
let authMode: 'login' | 'signup' = 'login'
let qrDrawTimer = 0
let qrTickTimer = 0

function pickStore(): Store | null {
  const saved = getStoreId()
  if (saved && stores.some((s) => s.id === saved)) {
    return stores.find((s) => s.id === saved) ?? null
  }
  return stores[0] ?? null
}

async function loadStores(): Promise<void> {
  const data = await api<{ items: Store[] }>('/api/stores')
  stores = data.items
  store = pickStore()
  if (store) setStoreId(store.id)
}

function logout(): void {
  clearSession()
  user = null
  stores = []
  store = null
  tab = 'home'
  render()
}

function render(): void {
  if (!user) {
    renderAuth()
    return
  }
  if (user.role !== 'owner') {
    window.location.replace('/')
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
      <div class="auth-brand">알바근태 · 관리자</div>
      <p class="auth-tag">매장 QR · 근무 현황 · 시급</p>
      <div class="auth-panel">
        <h2 class="auth-title">${isSignup ? '사장님 회원가입' : '사장님 로그인'}</h2>
        <p class="auth-desc">${isSignup ? '매장을 만들고 알바를 초대하세요.' : '아이디와 비밀번호를 입력하세요.'}</p>
        ${isSignup ? `<div class="auth-field"><label>이름</label><input id="name" autocomplete="name" /></div>` : ''}
        <div class="auth-field"><label>아이디</label><input id="login_id" autocomplete="username" /></div>
        <div class="auth-field"><label>비밀번호</label><input id="password" type="password" autocomplete="${isSignup ? 'new-password' : 'current-password'}" /></div>
        <p class="auth-error" id="auth-error" hidden></p>
        <button class="btn-primary auth-submit" id="auth-submit">${isSignup ? '가입하기' : '로그인'}</button>
        <button class="auth-switch" id="auth-switch">${isSignup ? '이미 계정이 있나요? 로그인' : '처음이신가요? 회원가입'}</button>
        <a class="auth-switch" href="/" style="display:block;text-align:center;text-decoration:none;margin-top:8px">알바 출퇴근으로</a>
      </div>
    </div>
  `
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
        ? { login_id: loginId, password, name, role: 'owner' as const }
        : { login_id: loginId, password }
    const data = await api<{ access_token: string; refresh_token: string; user: User }>(path, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (data.user.role !== 'owner') {
      window.location.replace('/')
      return
    }
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
  root.innerHTML = `
    <div class="auth-shell">
      <div class="auth-brand">알바근태 · 관리자</div>
      <h2 class="auth-title">매장을 등록하세요</h2>
      <p class="auth-desc">매장 이름을 넣으면 알바 초대코드가 만들어집니다.</p>
      <div class="auth-field">
        <label>매장 이름</label>
        <input id="onboard-input" />
      </div>
      <p class="auth-error" id="auth-error" hidden></p>
      <button class="btn-primary auth-submit" id="onboard-go">매장 만들기</button>
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
    const created = await api<Store>('/api/stores', {
      method: 'POST',
      body: JSON.stringify({ name: value }),
    })
    setStoreId(created.id)
    await loadStores()
    render()
  } catch (e) {
    if (err) {
      err.hidden = false
      err.textContent = e instanceof Error ? e.message : '실패했습니다.'
    }
  }
}

function renderMain(): void {
  window.clearInterval(qrDrawTimer)
  window.clearInterval(qrTickTimer)
  const tabs = [
    ['home', '현황'],
    ['list', '직원'],
    ['qr', '출근 QR'],
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
  if (tab === 'home') await fillLive(el)
  else if (tab === 'list') await fillStaff(el)
  else if (tab === 'qr') await fillQr(el)
  else fillMore(el)
}

async function fillLive(el: Element): Promise<void> {
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

async function fillStaff(el: Element): Promise<void> {
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
        }).then(() => fillStaff(el))
      })
    })
  } catch (e) {
    const body = document.querySelector('#staff-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

async function fillQr(el: Element): Promise<void> {
  el.innerHTML = `
    <header class="screen-header">
      <h1>출근 인증 QR</h1>
      <p class="sub">${store?.name ?? ''} · 알바가 이 코드를 찍습니다</p>
    </header>
    <div class="admin-qr-card">
      <canvas id="admin-qr-canvas" aria-label="출근 인증 QR"></canvas>
      <p class="admin-qr-count" id="admin-qr-count">불러오는 중…</p>
    </div>
    <a class="btn-secondary" href="/tablet.html" style="display:block;text-align:center;text-decoration:none">태블릿 전체화면</a>
  `
  const { default: QRCode } = await import('qrcode')
  const canvas = document.getElementById('admin-qr-canvas') as HTMLCanvasElement | null
  const countEl = document.getElementById('admin-qr-count')
  let nextAt = Date.now()

  async function draw(): Promise<void> {
    if (!canvas || !store) return
    const payload = await api<Record<string, unknown>>(`/api/kiosk/attendance-qr?store_id=${store.id}`)
    await QRCode.toCanvas(canvas, JSON.stringify(payload), {
      width: 280,
      margin: 2,
      color: { dark: '#0b0f17ff', light: '#ffffffff' },
      errorCorrectionLevel: 'M',
    })
    nextAt = Date.now() + 30_000
  }

  function tick(): void {
    if (!countEl) return
    const sec = Math.max(0, Math.ceil((nextAt - Date.now()) / 1000))
    countEl.textContent = `${sec}초 후 갱신`
  }

  try {
    await draw()
    tick()
    qrDrawTimer = window.setInterval(() => {
      void draw().catch((e: unknown) => {
        if (countEl) countEl.textContent = e instanceof Error ? e.message : 'QR 실패'
      })
    }, 30_000)
    qrTickTimer = window.setInterval(tick, 250)
  } catch (e) {
    if (countEl) countEl.textContent = e instanceof Error ? e.message : 'QR 실패'
  }
}

function fillMore(el: Element): void {
  const storeOptions = stores
    .map((s) => `<option value="${s.id}" ${store?.id === s.id ? 'selected' : ''}>${s.name}</option>`)
    .join('')
  el.innerHTML = `
    <header class="screen-header">
      <h1>더보기</h1>
      <p class="sub">${user?.name} · 사장님</p>
    </header>
    <div class="pad">
      ${
        stores.length > 1
          ? `<div class="auth-field"><label>매장</label>
             <select id="store-select" class="field-select">${storeOptions}</select></div>`
          : ''
      }
      <div class="invite-box"><div class="k">초대코드</div><div class="code">${store?.invite_code ?? ''}</div></div>
    </div>
    <div class="menu-list">
      <a class="menu-item" href="/tablet.html"><span>태블릿 출근 QR</span><span class="chev">›</span></a>
      <button class="menu-item" id="logout"><span>로그아웃</span><span class="chev">›</span></button>
    </div>
  `
  document.querySelector('#logout')?.addEventListener('click', logout)
  document.querySelector('#store-select')?.addEventListener('change', (ev) => {
    const id = Number((ev.target as HTMLSelectElement).value)
    setStoreId(id)
    store = stores.find((s) => s.id === id) ?? store
    renderMain()
  })
}

async function boot(): Promise<void> {
  if (user) {
    try {
      user = await api<User>('/api/auth/me')
      await loadStores()
    } catch {
      logout()
      return
    }
  }
  render()
}

void boot()
