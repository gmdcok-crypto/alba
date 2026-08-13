import './style.css'
import {
  adminSession,
  hhmm,
  managerSession,
  moveSession,
  type Employee,
  type Live,
  type PeriodAttendance,
  type Store,
  type User,
} from './api'

const { api, getUser, setSession, clearSession, getStoreId, setStoreId } = managerSession

const mounted = document.querySelector<HTMLDivElement>('#app')
if (!mounted) throw new Error('#app missing')
const root: HTMLDivElement = mounted

type Tab = 'live' | 'att' | 'emps' | 'more'

let user = getUser()
let store: Store | null = null
let tab: Tab = 'live'
let selectedEmpId: number | null = null
let liveTimer = 0
let attFrom = ''
let attTo = ''
let attEmpId: number | null = null

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c))
}

function val(id: string): string {
  return (document.querySelector<HTMLInputElement | HTMLSelectElement>(`#${id}`)?.value || '').trim()
}

function todayStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function monthStartStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

async function loadStores(): Promise<void> {
  const data = await api<{ items: Store[] }>('/api/stores')
  const saved = getStoreId()
  store = data.items.find((s) => s.id === saved) ?? data.items[0] ?? null
  if (store) setStoreId(store.id)
}

function logout(): void {
  window.clearInterval(liveTimer)
  clearSession()
  user = null
  store = null
  tab = 'live'
  selectedEmpId = null
  render()
}

function render(): void {
  window.clearInterval(liveTimer)
  if (!user) {
    renderAuth()
    return
  }
  if (user.role !== 'manager') {
    logout()
    return
  }
  if (!store) {
    root.innerHTML = `
      <div class="auth-shell">
        <h2 class="auth-title">지점이 없습니다</h2>
        <p class="auth-desc">배정된 매장을 찾을 수 없습니다. 관리자에게 문의하세요.</p>
        <button class="auth-switch" id="logout">로그아웃</button>
      </div>`
    root.querySelector('#logout')?.addEventListener('click', logout)
    return
  }
  renderMain()
}

function renderAuth(): void {
  root.innerHTML = `
    <div class="auth-shell">
      <div class="auth-brand">알바근태 · 점장</div>
      <p class="auth-tag">지점 사원 등록 · 출퇴근 현황</p>
      <div class="auth-panel">
        <h2 class="auth-title">점장 로그인</h2>
        <p class="auth-desc">처음이거나 인증이 취소된 경우 이름과 새 비밀번호를 함께 입력하세요.</p>
        <div class="auth-field"><label>이름</label><input id="name" autocomplete="name" placeholder="첫 로그인·인증취소 시 필수" /></div>
        <div class="auth-field"><label>아이디</label><input id="login_id" autocomplete="username" /></div>
        <div class="auth-field"><label>비밀번호</label><input id="password" type="password" autocomplete="current-password" /></div>
        <p class="auth-error" id="auth-error" hidden></p>
        <button class="btn-primary auth-submit" id="auth-submit">로그인</button>
        <a class="auth-switch" href="/admin.html" style="display:block;text-align:center;text-decoration:none;margin-top:8px">본사관리자이신가요?</a>
        <a class="auth-switch" href="/" style="display:block;text-align:center;text-decoration:none">알바 출퇴근으로</a>
      </div>
    </div>
  `
  root.querySelector('#auth-submit')?.addEventListener('click', () => void submitAuth())
}

async function submitAuth(): Promise<void> {
  const err = document.querySelector<HTMLParagraphElement>('#auth-error')
  try {
    const data = await api<{ access_token: string; refresh_token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        login_id: val('login_id'),
        password: val('password'),
        name: val('name'),
      }),
    })
    if (data.user.role === 'owner') {
      adminSession.setSession(data.access_token, data.refresh_token, data.user)
      window.location.replace('/admin.html')
      return
    }
    if (data.user.role !== 'manager') {
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

function renderMain(): void {
  const tabs: [Tab, string][] = [
    ['live', '현황'],
    ['att', '근태'],
    ['emps', '사원'],
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
      tab = btn.dataset.tab as Tab
      renderMain()
    })
  })
  void fillScreen()
}

async function fillScreen(): Promise<void> {
  const el = document.querySelector('#screen')
  if (!el || !store || !user) return
  if (tab === 'live') await fillLive(el)
  else if (tab === 'att') await fillAtt(el)
  else if (tab === 'emps') await fillEmps(el)
  else fillMore(el)
}

async function fillLive(el: Element): Promise<void> {
  const branch = user?.department_name || store?.name || ''
  el.innerHTML = `
    <header class="screen-header">
      <h1>출퇴근 현황</h1>
      <p class="sub">${esc(branch)}</p>
    </header>
    <div id="live-body"><p class="empty">불러오는 중…</p></div>
  `
  const paint = async () => {
    if (!store) return
    const data = await api<Live>(`/api/owner/${store.id}/live`)
    const body = document.querySelector('#live-body')
    if (!body) return
    body.innerHTML = `
      <div class="summary-row">
        <div class="summary-card"><div class="k">근무 중</div><div class="v">${data.working.length}명</div></div>
        <div class="summary-card"><div class="k">미출근</div><div class="v">${data.off.length}명</div></div>
      </div>
      <div class="pad">
        <p class="sub" style="margin:0 0 8px;font-weight:700">실시간 출근</p>
        ${
          data.working.length
            ? data.working
                .map(
                  (p) => `
            <div class="person-row">
              <div>
                <div class="name">${esc(p.name)}</div>
                <div class="meta">${esc(p.employee_no)} · 출근 ${hhmm(p.last_at)}</div>
              </div>
              <span class="badge badge-in">근무 중</span>
            </div>`,
                )
                .join('')
            : '<p class="empty" style="margin:0 0 16px">현재 근무 중인 알바가 없습니다.</p>'
        }
        <p class="sub" style="margin:18px 0 8px;font-weight:700">미출근</p>
        ${
          data.off.length
            ? data.off
                .map(
                  (p) => `
            <div class="person-row">
              <div>
                <div class="name">${esc(p.name)}</div>
                <div class="meta">${esc(p.employee_no)}</div>
              </div>
              <span class="badge badge-out">대기</span>
            </div>`,
                )
                .join('')
            : '<p class="empty" style="margin:0">등록된 사원이 없습니다.</p>'
        }
      </div>
    `
  }
  try {
    await paint()
    liveTimer = window.setInterval(() => {
      void paint().catch(() => undefined)
    }, 15_000)
  } catch (e) {
    const body = document.querySelector('#live-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

async function fillAtt(el: Element): Promise<void> {
  if (!attFrom) attFrom = monthStartStr()
  if (!attTo) attTo = todayStr()
  const branch = user?.department_name || store?.name || ''
  let emps: Employee[] = []
  try {
    const empData = await api<{ items: Employee[] }>(`/api/employees?store_id=${store!.id}`)
    emps = empData.items
  } catch {
    emps = []
  }
  const empOptions = ['<option value="">전체 사원</option>']
    .concat(
      emps.map(
        (e) =>
          `<option value="${e.id}" ${attEmpId === e.id ? 'selected' : ''}>${esc(e.employee_no)} ${esc(e.name)}</option>`,
      ),
    )
    .join('')
  el.innerHTML = `
    <header class="screen-header">
      <h1>근태현황</h1>
      <p class="sub">${esc(branch)} · 기간별 출퇴근</p>
    </header>
    <div class="filter-bar">
      <div class="auth-field"><label>시작일</label><input id="att-from" type="date" value="${esc(attFrom)}" /></div>
      <div class="auth-field"><label>종료일</label><input id="att-to" type="date" value="${esc(attTo)}" /></div>
      <div class="auth-field span-2"><label>사원</label><select id="att-emp">${empOptions}</select></div>
      <button class="btn-primary span-2" type="button" id="att-search" style="margin:0;min-height:44px">조회</button>
    </div>
    <div id="att-body"><p class="empty">불러오는 중…</p></div>
  `
  const paint = async () => {
    if (!store) return
    const empQ = attEmpId ? `&employee_id=${attEmpId}` : ''
    const data = await api<PeriodAttendance>(
      `/api/owner/${store.id}/period?date_from=${attFrom}&date_to=${attTo}${empQ}`,
    )
    const body = document.querySelector('#att-body')
    if (!body) return
    body.innerHTML = `
      <div class="summary-row">
        <div class="summary-card"><div class="k">기록</div><div class="v">${data.items.length}건</div></div>
        <div class="summary-card"><div class="k">총 근무</div><div class="v">${esc(data.hours_label)}</div></div>
      </div>
      ${
        data.items.length
          ? `<div class="table-scroll">
          <table class="data-table is-static">
            <thead>
              <tr>
                <th>날짜</th>
                <th>사번</th>
                <th>이름</th>
                <th>출근</th>
                <th>퇴근</th>
                <th>근무</th>
              </tr>
            </thead>
            <tbody>
              ${data.items
                .map(
                  (r) => `
                <tr>
                  <td>${esc(r.date)}</td>
                  <td>${esc(r.employee_no)}</td>
                  <td>${esc(r.name)}</td>
                  <td>${hhmm(r.in_at)}</td>
                  <td>${r.open ? '미퇴근' : hhmm(r.out_at)}</td>
                  <td>${esc(r.hours_label)}</td>
                </tr>`,
                )
                .join('')}
            </tbody>
          </table>
        </div>`
          : '<p class="empty" style="margin:12px 20px">해당 기간 출퇴근 기록이 없습니다.</p>'
      }
    `
  }
  el.querySelector('#att-search')?.addEventListener('click', () => {
    attFrom = val('att-from') || monthStartStr()
    attTo = val('att-to') || todayStr()
    const emp = val('att-emp')
    attEmpId = emp ? Number(emp) : null
    void fillAtt(el)
  })
  try {
    await paint()
  } catch (e) {
    const body = document.querySelector('#att-body')
    if (body) body.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

async function fillEmps(el: Element): Promise<void> {
  const data = await api<{ items: Employee[] }>(`/api/employees?store_id=${store!.id}`)
  const items = data.items
  const selected = items.find((e) => e.id === selectedEmpId) ?? null
  const branch = user?.department_name || ''
  el.innerHTML = `
    <header class="screen-header">
      <h1>사원관리</h1>
      <p class="sub">${esc(branch)} · ${items.length}명</p>
    </header>
    ${
      items.length
        ? `<div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>사번</th>
              <th>이름</th>
              <th>상태</th>
              <th>인증</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${items
              .map(
                (e) => `
              <tr class="${selected?.id === e.id ? 'is-active' : ''}" data-id="${e.id}">
                <td>${esc(e.employee_no)}</td>
                <td>${esc(e.name)}</td>
                <td>${esc(e.status)}</td>
                <td><span class="badge ${e.auth_status === 'O' ? 'badge-in' : 'badge-open'}">${esc(e.auth_label)}</span></td>
                <td><button type="button" class="table-link" data-revoke="${e.id}">인증취소</button></td>
              </tr>`,
              )
              .join('')}
          </tbody>
        </table>
      </div>`
        : '<p class="empty" style="margin:8px 20px 16px">아직 등록된 사원이 없습니다.</p>'
    }
    <div class="pad">
      <p class="sub" style="margin:0 0 12px;font-weight:700">${selected ? '사원 수정' : '새 사원 등록'}</p>
      <div class="auth-field"><label>사번</label><input id="emp-no" value="${esc(selected?.employee_no || '')}" /></div>
      <div class="auth-field"><label>이름</label><input id="emp-name" value="${esc(selected?.name || '')}" /></div>
      <div class="auth-field"><label>입사일</label><input id="emp-hire" type="date" value="${esc(selected?.hire_date || todayStr())}" /></div>
      <div class="auth-field"><label>상태</label>
        <select id="emp-status">
          <option ${selected?.status === '재직' || !selected ? 'selected' : ''}>재직</option>
          <option ${selected?.status === '퇴사' ? 'selected' : ''}>퇴사</option>
        </select>
      </div>
      <div class="auth-field"><label>시급</label><input id="emp-wage" type="number" min="0" value="${selected?.hourly_wage ?? 0}" /></div>
      <div class="btn-row">
        <button class="btn-primary" type="button" id="emp-create">등록</button>
        <button class="btn-secondary" type="button" id="emp-update">수정</button>
        <button class="btn-danger" type="button" id="emp-delete">삭제</button>
      </div>
      ${selected ? `<button class="auth-switch" type="button" id="emp-new">새 등록으로</button>` : ''}
    </div>
  `
  const reload = () => void fillEmps(el)
  el.querySelectorAll<HTMLTableRowElement>('tbody tr[data-id]').forEach((row) => {
    row.addEventListener('click', (ev) => {
      if ((ev.target as HTMLElement).closest('[data-revoke]')) return
      selectedEmpId = Number(row.dataset.id)
      reload()
    })
  })
  el.querySelectorAll<HTMLButtonElement>('[data-revoke]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation()
      const id = Number(btn.dataset.revoke)
      if (!window.confirm('모바일 인증을 취소할까요?')) return
      void api(`/api/employees/${id}/revoke-auth`, { method: 'POST' })
        .then(() => reload())
        .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
    })
  })
  function payload() {
    return {
      store_id: store!.id,
      employee_no: val('emp-no'),
      name: val('emp-name'),
      department_name: user?.department_name || '',
      hire_date: val('emp-hire'),
      status: val('emp-status'),
      hourly_wage: Number(val('emp-wage') || 0),
    }
  }
  el.querySelector('#emp-create')?.addEventListener('click', () => {
    const body = payload()
    if (!body.employee_no || !body.name) {
      window.alert('사번과 이름을 입력하세요.')
      return
    }
    void api('/api/employees', { method: 'POST', body: JSON.stringify(body) })
      .then(() => {
        selectedEmpId = null
        reload()
      })
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  el.querySelector('#emp-update')?.addEventListener('click', () => {
    if (!selected) {
      window.alert('수정할 사원을 테이블에서 선택하세요.')
      return
    }
    const body = payload()
    if (!body.employee_no || !body.name) {
      window.alert('사번과 이름을 입력하세요.')
      return
    }
    void api(`/api/employees/${selected.id}`, { method: 'PUT', body: JSON.stringify(body) })
      .then(() => reload())
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  el.querySelector('#emp-delete')?.addEventListener('click', () => {
    if (!selected) {
      window.alert('삭제할 사원을 테이블에서 선택하세요.')
      return
    }
    if (!window.confirm('사원을 삭제할까요?')) return
    void api(`/api/employees/${selected.id}`, { method: 'DELETE' })
      .then(() => {
        selectedEmpId = null
        reload()
      })
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  el.querySelector('#emp-new')?.addEventListener('click', () => {
    selectedEmpId = null
    reload()
  })
}

function fillMore(el: Element): void {
  el.innerHTML = `
    <header class="screen-header">
      <h1>더보기</h1>
      <p class="sub">${esc(user?.name || '')} · 점장</p>
    </header>
    <div class="pad">
      <div class="status-card">
        <div class="label">담당 지점</div>
        <div class="state">${esc(user?.department_name || '-')}</div>
        <div class="detail">${esc(store?.name || '')}</div>
      </div>
    </div>
    <div class="menu-list">
      <button class="menu-item" id="logout"><span>로그아웃</span><span class="chev">›</span></button>
    </div>
  `
  document.querySelector('#logout')?.addEventListener('click', logout)
}

function adoptManagerLoginFromAdmin(): void {
  if (getUser()) return
  if (adminSession.getUser()?.role !== 'manager') return
  moveSession(adminSession, managerSession)
}

async function boot(): Promise<void> {
  adoptManagerLoginFromAdmin()
  user = getUser()
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
