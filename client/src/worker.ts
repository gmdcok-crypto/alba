import './style.css'
import {
  hhmm,
  money,
  WEEK,
  workerSession,
  type Records,
  type Store,
  type Today,
  type User,
} from './api'

const { api, getUser, setSession, clearSession, setStoreId } = workerSession

const mounted = document.querySelector<HTMLDivElement>('#app')
if (!mounted) throw new Error('#app missing')
const root: HTMLDivElement = mounted

let user = getUser()
let store: Store | null = null
let tab: 'home' | 'list' | 'more' = 'home'
let view: 'app' | 'scan' = 'app'
let pendingIntent: 'in' | 'out' = 'in'
let clockTimer = 0
let scanClockTimer = 0

function dateLabel(d = new Date()): { line: string; main: string } {
  return {
    line: `${d.getFullYear()}년 ${d.getMonth() + 1}월`,
    main: `${d.getDate()}일 (${WEEK[d.getDay()]})`,
  }
}

function clockText(d = new Date()): string {
  return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function storeFromUser(u: User | null): Store | null {
  if (!u?.store_id) return null
  return {
    id: u.store_id,
    owner_id: 0,
    name: u.store_name || '',
    invite_code: '',
    lat: null,
    lng: null,
    geofence_m: 0,
    hourly_wage: u.hourly_wage || 0,
    status: 'active',
  }
}

function logout(): void {
  clearSession()
  user = null
  store = null
  tab = 'home'
  view = 'app'
  render()
}

function render(): void {
  if (!user) {
    renderAuth()
    return
  }
  if (user.role === 'owner') {
    window.location.replace('/admin.html')
    return
  }
  store = storeFromUser(user)
  if (!store) {
    root.innerHTML = `<div class="auth-shell"><p class="auth-desc">매장 정보가 없습니다. 관리자에게 문의하세요.</p><button class="auth-switch" id="logout">로그아웃</button></div>`
    root.querySelector('#logout')?.addEventListener('click', logout)
    return
  }
  if (view === 'scan') {
    renderScan()
    return
  }
  renderMain()
}

function renderAuth(): void {
  root.innerHTML = `
    <div class="auth-shell">
      <div class="auth-brand">알바근태</div>
      <p class="auth-tag">매장 QR을 찍어 출근 · 퇴근</p>
      <div class="auth-panel">
        <h2 class="auth-title">알바 로그인</h2>
        <p class="auth-desc">관리자에게 등록된 이름과 사번으로 로그인하세요. 처음이거나 인증이 취소된 경우 이름과 새 비밀번호를 함께 입력합니다.</p>
        <div class="auth-field"><label>사번</label><input id="employee_no" autocomplete="username" /></div>
        <div class="auth-field"><label>이름</label><input id="name" autocomplete="name" placeholder="첫 로그인·인증취소 시 필수" /></div>
        <div class="auth-field"><label>비밀번호</label><input id="password" type="password" autocomplete="current-password" /></div>
        <p class="auth-error" id="auth-error" hidden></p>
        <button class="btn-primary auth-submit" id="auth-submit">로그인</button>
        <a class="auth-switch" href="/admin.html" style="display:block;text-align:center;text-decoration:none;margin-top:8px">사장님이신가요?</a>
      </div>
    </div>
  `
  root.querySelector('#auth-submit')?.addEventListener('click', () => void submitAuth())
}

async function submitAuth(): Promise<void> {
  const err = document.querySelector<HTMLParagraphElement>('#auth-error')
  const employeeNo = (document.querySelector<HTMLInputElement>('#employee_no')?.value || '').trim()
  const password = document.querySelector<HTMLInputElement>('#password')?.value || ''
  const name = (document.querySelector<HTMLInputElement>('#name')?.value || '').trim()
  if (err) {
    err.hidden = true
    err.textContent = ''
  }
  try {
    const data = await api<{ access_token: string; refresh_token: string; user: User }>('/api/auth/worker/login', {
      method: 'POST',
      body: JSON.stringify({ employee_no: employeeNo, name, password }),
    })
    setSession(data.access_token, data.refresh_token, data.user)
    user = data.user
    store = storeFromUser(user)
    if (store) setStoreId(store.id)
    render()
  } catch (e) {
    if (err) {
      err.hidden = false
      err.textContent = e instanceof Error ? e.message : '실패했습니다.'
    }
  }
}

function renderMain(): void {
  const tabs = [
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
  if (tab === 'home') await fillHome(el)
  else if (tab === 'list') await fillRecords(el)
  else fillMore(el)
}

async function fillHome(el: Element): Promise<void> {
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
    const today = await api<Today>('/api/clock/today')
    const now = new Date()
    const month = await api<Records>(
      `/api/clock/records?year=${now.getFullYear()}&month=${now.getMonth() + 1}`,
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
        ${today.clocked_in ? '퇴근 QR 스캔' : '출근 QR 스캔'}
      </button>
      <p class="empty" style="margin-top:0">매장에 띄워 둔 QR을 카메라로 찍으세요.</p>
      <div class="summary-row">
        <div class="summary-card"><div class="k">이번 달 근무</div><div class="v">${month.hours_label}</div></div>
        <div class="summary-card"><div class="k">예상 급여</div><div class="v">${money(month.pay_estimate)}</div></div>
      </div>
    `
    document.querySelector('#clock-btn')?.addEventListener('click', () => {
      pendingIntent = today.clocked_in ? 'out' : 'in'
      view = 'scan'
      render()
    })
  } catch (e) {
    const body = document.querySelector('#home-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '불러오기 실패'}</p>`
  }
}

function renderScan(): void {
  root.innerHTML = `
    <div class="main-shell main-shell--scan">
      <div class="attend-scan-page">
        <header class="screen-header">
          <h1>${pendingIntent === 'out' ? '퇴근 · QR 스캔' : '출근 · QR 스캔'}</h1>
          <p class="sub">${store?.name ?? ''}</p>
        </header>
        <div class="scan-wrap">
          <div id="qr-reader" class="qr-reader-host"></div>
          <div class="scan-overlay scan-overlay--frame" aria-hidden="true">
            <div class="scan-frame"></div>
          </div>
          <p class="scan-hint-in-frame">매장 태블릿·휴대폰의 QR을 프레임 안에 맞춰 주세요.</p>
        </div>
        <p class="scan-digital-clock" id="scan-digital-clock">${clockText()}</p>
        <p class="scan-err" id="scan-err" hidden></p>
        <div class="scan-footer-actions">
          <button type="button" class="scan-mock-success" id="scan-dev-qr" ${import.meta.env.DEV ? '' : 'hidden'}>
            개발: QR JSON 붙여넣기
          </button>
          <button type="button" class="btn-text" id="scan-cancel">취소</button>
        </div>
      </div>
    </div>
  `
  const clockEl = document.querySelector('#scan-digital-clock')
  window.clearInterval(scanClockTimer)
  scanClockTimer = window.setInterval(() => {
    if (clockEl) clockEl.textContent = clockText()
  }, 250)
  document.querySelector('#scan-cancel')?.addEventListener('click', () => {
    view = 'app'
    void import('./qr_scan').then((m) => m.stopAttendQrScanner())
    render()
  })
  document.querySelector('#scan-dev-qr')?.addEventListener('click', () => {
    const raw = window.prompt('QR JSON')
    if (raw) void handleDecodedQr(raw)
  })
  void beginScan()
}

async function beginScan(): Promise<void> {
  const qrScan = await import('./qr_scan')
  await qrScan.startAttendQrScanner(
    (text) => void handleDecodedQr(text),
    (msg) => {
      const errEl = document.querySelector<HTMLParagraphElement>('#scan-err')
      if (errEl) {
        errEl.hidden = false
        errEl.textContent = msg
      }
    },
  )
}

async function handleDecodedQr(raw: string): Promise<void> {
  const errEl = document.querySelector<HTMLParagraphElement>('#scan-err')
  try {
    await api('/api/clock/qr', {
      method: 'POST',
      body: JSON.stringify({ qr: raw, intent: pendingIntent }),
    })
    view = 'app'
    tab = 'home'
    const qrScan = await import('./qr_scan')
    await qrScan.stopAttendQrScanner()
    render()
  } catch (e) {
    if (errEl) {
      errEl.hidden = false
      errEl.textContent = e instanceof Error ? e.message : '실패했습니다.'
    }
    queueMicrotask(() => void beginScan())
  }
}

async function fillRecords(el: Element): Promise<void> {
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
      `/api/clock/records?year=${now.getFullYear()}&month=${now.getMonth() + 1}`,
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

function fillMore(el: Element): void {
  el.innerHTML = `
    <header class="screen-header">
      <h1>더보기</h1>
      <p class="sub">${user?.name} · 사번 ${user?.employee_no || user?.login_id || ''}</p>
    </header>
    <div class="pad">
      <p class="empty" style="text-align:left;margin:0 0 16px">계정은 관리자가 등록합니다. 퇴사·인증취소 후에는 다시 로그인할 수 없습니다.</p>
    </div>
    <div class="menu-list">
      <button class="menu-item" id="logout"><span>로그아웃</span><span class="chev">›</span></button>
    </div>
  `
  document.querySelector('#logout')?.addEventListener('click', logout)
}

async function boot(): Promise<void> {
  if (user) {
    try {
      user = await api<User>('/api/auth/worker/me')
      store = storeFromUser(user)
      if (store) setStoreId(store.id)
    } catch {
      logout()
      return
    }
  }
  render()
}

void boot()
