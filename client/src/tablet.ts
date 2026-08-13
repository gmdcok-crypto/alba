import './tablet.css'
import QRCode from 'qrcode'
import { adminSession, type Store, type User } from './api'

const { api, getUser, setSession, getStoreId, setStoreId } = adminSession

const REFRESH_MS = 30_000
const mounted = document.querySelector<HTMLDivElement>('#tablet-root')
if (!mounted) throw new Error('#tablet-root missing')
const root: HTMLDivElement = mounted

function formatKSTDateLine(d: Date): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(d)
}

function formatKSTWeekdayTime(d: Date): string {
  const weekday = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    weekday: 'long',
  }).format(d)
  const time = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d)
  return `${weekday} ${time}`
}

function qrSize(): number {
  const w = Math.min(window.innerWidth - 80, window.innerHeight * 0.45)
  return Math.max(200, Math.min(400, Math.floor(w)))
}

let store: Store | null = null
let nextRefreshAt = Date.now() + REFRESH_MS

function renderLogin(): void {
  root.innerHTML = `
    <div class="tablet-login">
      <h1>출근 인증 QR</h1>
      <p>사장님 계정으로 로그인한 뒤 매장 태블릿에 띄워 두세요.</p>
      <input id="login_id" placeholder="아이디" autocomplete="username" />
      <input id="password" type="password" placeholder="비밀번호" autocomplete="current-password" />
      <p class="tablet-err" id="err" hidden></p>
      <button type="button" id="go">로그인</button>
      <a href="/admin.html">관리자 PWA로</a>
    </div>
  `
  document.querySelector('#go')?.addEventListener('click', () => void submitLogin())
}

async function submitLogin(): Promise<void> {
  const err = document.querySelector<HTMLParagraphElement>('#err')
  const loginId = (document.querySelector<HTMLInputElement>('#login_id')?.value || '').trim()
  const password = document.querySelector<HTMLInputElement>('#password')?.value || ''
  try {
    const data = await api<{ access_token: string; refresh_token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ login_id: loginId, password }),
    })
    if (data.user.role !== 'owner') {
      throw new Error('사장님 계정만 사용할 수 있습니다.')
    }
    setSession(data.access_token, data.refresh_token, data.user)
    await bootQr()
  } catch (e) {
    if (err) {
      err.hidden = false
      err.textContent = e instanceof Error ? e.message : '실패'
    }
  }
}

function renderKiosk(): void {
  root.innerHTML = `
    <div class="tablet-layout">
      <header class="tablet-header">
        <h1>출근 인증 QR</h1>
        <p class="tablet-store">${store?.name ?? ''}</p>
      </header>
      <div class="tablet-qr-card">
        <div class="tablet-qr-frame">
          <canvas id="tablet-qr-canvas" aria-label="동적 출근 인증 QR 코드"></canvas>
        </div>
        <dl class="tablet-meta">
          <div>
            <dt>현재 시각</dt>
            <dd class="tablet-clock">
              <span class="tablet-clock__date" id="tablet-clock-date">—</span>
              <span class="tablet-clock__line2" id="tablet-clock-line2">—</span>
            </dd>
          </div>
          <div>
            <dt>다음 QR 갱신</dt>
            <dd id="tablet-countdown">—</dd>
          </div>
        </dl>
      </div>
    </div>
  `
  const canvas = document.getElementById('tablet-qr-canvas') as HTMLCanvasElement
  const clockDateEl = document.getElementById('tablet-clock-date')
  const clockLine2El = document.getElementById('tablet-clock-line2')
  const countdownEl = document.getElementById('tablet-countdown')

  async function drawQr(): Promise<void> {
    if (!store) return
    try {
      const payload = await api<Record<string, unknown>>(`/api/kiosk/attendance-qr?store_id=${store.id}`)
      await QRCode.toCanvas(canvas, JSON.stringify(payload), {
        width: qrSize(),
        margin: 2,
        color: { dark: '#0b0f17ff', light: '#ffffffff' },
        errorCorrectionLevel: 'M',
      })
      nextRefreshAt = Date.now() + REFRESH_MS
      countdownEl?.classList.remove('tablet-countdown--error')
    } catch (e) {
      if (countdownEl) {
        countdownEl.textContent = e instanceof Error ? e.message : 'API 연결 실패'
        countdownEl.classList.add('tablet-countdown--error')
      }
    }
  }

  function tick(): void {
    const now = new Date()
    if (clockDateEl) clockDateEl.textContent = formatKSTDateLine(now)
    if (clockLine2El) clockLine2El.textContent = formatKSTWeekdayTime(now)
    if (countdownEl && !countdownEl.classList.contains('tablet-countdown--error')) {
      const sec = Math.max(0, Math.ceil((nextRefreshAt - Date.now()) / 1000))
      countdownEl.textContent = `${sec}초 후`
    }
  }

  void drawQr()
  window.setInterval(() => {
    void drawQr()
  }, REFRESH_MS)
  window.setInterval(tick, 250)
  tick()
  window.addEventListener('resize', () => {
    void drawQr()
  })
}

async function bootQr(): Promise<void> {
  const data = await api<{ items: Store[] }>('/api/stores')
  const saved = getStoreId()
  store = data.items.find((s) => s.id === saved) ?? data.items[0] ?? null
  if (!store) {
    root.innerHTML = `<div class="tablet-login"><h1>매장이 없습니다</h1><a href="/admin.html">관리자에서 매장을 만드세요</a></div>`
    return
  }
  setStoreId(store.id)
  renderKiosk()
}

async function boot(): Promise<void> {
  const user = getUser()
  if (!user) {
    renderLogin()
    return
  }
  try {
    const me = await api<User>('/api/auth/me')
    if (me.role !== 'owner') {
      renderLogin()
      return
    }
    await bootQr()
  } catch {
    renderLogin()
  }
}

void boot()
