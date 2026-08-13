import './admin.css'
import {
  adminSession,
  hhmm,
  type AttendanceEvent,
  type Department,
  type Employee,
  type Live,
  type Store,
  type User,
} from './api'

const { api, getUser, setSession, clearSession, getStoreId, setStoreId } = adminSession

const mounted = document.querySelector<HTMLDivElement>('#app')
if (!mounted) throw new Error('#app missing')
const root: HTMLDivElement = mounted

type View = 'dashboard' | 'company' | 'depts' | 'emps' | 'raw' | 'qr'
const VIEW_TITLE: Record<View, string> = {
  dashboard: '대시보드',
  company: '회사등록',
  depts: '부서관리',
  emps: '사원관리',
  raw: '원시데이터',
  qr: '출근 QR',
}

let user = getUser()
let stores: Store[] = []
let store: Store | null = null
let view: View = 'dashboard'
let authMode: 'login' | 'signup' = 'login'
let qrDrawTimer = 0
let qrTickTimer = 0
let selectedDeptId: number | null = null
let selectedEmpId: number | null = null
let selectedEventId: number | null = null
let rawFilterEmpId: number | null = null
let liveTimer = 0

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c))
}

function todayStr(offset = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

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
  window.clearInterval(qrDrawTimer)
  window.clearInterval(qrTickTimer)
  window.clearInterval(liveTimer)
  clearSession()
  user = null
  stores = []
  store = null
  view = 'dashboard'
  render()
}

function val(id: string): string {
  return (document.querySelector<HTMLInputElement | HTMLSelectElement>(`#${id}`)?.value || '').trim()
}

function render(): void {
  window.clearInterval(qrDrawTimer)
  window.clearInterval(qrTickTimer)
  window.clearInterval(liveTimer)
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
  renderShell()
}

function renderAuth(): void {
  const isSignup = authMode === 'signup'
  root.innerHTML = `
    <div class="auth-esl">
      <div class="auth-esl-card">
        <h1>알바근태 관리자</h1>
        <p>${isSignup ? '사장님 계정을 만들고 회사를 등록하세요.' : '아이디와 비밀번호로 로그인하세요.'}</p>
        ${isSignup ? `<div class="field"><label>이름</label><input id="name" autocomplete="name" /></div>` : ''}
        <div class="field" style="margin-top:10px"><label>아이디</label><input id="login_id" autocomplete="username" /></div>
        <div class="field" style="margin-top:10px"><label>비밀번호</label><input id="password" type="password" autocomplete="${isSignup ? 'new-password' : 'current-password'}" /></div>
        <p class="auth-error" id="auth-error" hidden></p>
        <div class="form-actions">
          <button class="btn btn-primary" id="auth-submit" style="width:100%">${isSignup ? '가입하기' : '로그인'}</button>
        </div>
        <button class="auth-switch" id="auth-switch">${isSignup ? '이미 계정이 있나요? 로그인' : '처음이신가요? 회원가입'}</button>
        <a class="auth-switch" href="/">알바 출퇴근으로</a>
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
  try {
    const path = authMode === 'signup' ? '/api/auth/signup' : '/api/auth/login'
    const body =
      authMode === 'signup'
        ? { login_id: val('login_id'), password: val('password'), name: val('name'), role: 'owner' as const }
        : { login_id: val('login_id'), password: val('password') }
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
    <div class="auth-esl">
      <div class="auth-esl-card">
        <h1>회사 등록</h1>
        <p>회사(매장) 이름을 등록하면 알바 사원을 추가할 수 있습니다.</p>
        <div class="field"><label>회사명</label><input id="onboard-input" /></div>
        <p class="auth-error" id="auth-error" hidden></p>
        <div class="form-actions">
          <button class="btn btn-primary" id="onboard-go" style="width:100%">등록</button>
        </div>
        <button class="auth-switch" id="logout">다른 계정으로</button>
      </div>
    </div>
  `
  root.querySelector('#logout')?.addEventListener('click', logout)
  root.querySelector('#onboard-go')?.addEventListener('click', () => void submitOnboard())
}

async function submitOnboard(): Promise<void> {
  const err = document.querySelector<HTMLParagraphElement>('#auth-error')
  try {
    const created = await api<Store>('/api/stores', {
      method: 'POST',
      body: JSON.stringify({ name: val('onboard-input') }),
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

function renderShell(): void {
  window.clearInterval(qrDrawTimer)
  window.clearInterval(qrTickTimer)
  window.clearInterval(liveTimer)
  const nav: { id: View; label: string }[] = [
    { id: 'dashboard', label: '대시보드' },
    { id: 'company', label: '회사등록' },
    { id: 'depts', label: '부서관리' },
    { id: 'emps', label: '사원관리' },
    { id: 'raw', label: '원시데이터' },
    { id: 'qr', label: '출근 QR' },
  ]
  root.innerHTML = `
    <div class="admin-esl-theme">
      <aside class="admin-esl-sidebar">
        <div class="admin-esl-logo">알바근태<span>${esc(store?.name || '')}</span></div>
        <nav class="admin-esl-nav">
          <div class="admin-esl-menu-title">관리</div>
          ${nav
            .map(
              (n) =>
                `<button class="admin-esl-menu-item ${view === n.id ? 'is-active' : ''}" data-view="${n.id}">${n.label}</button>`,
            )
            .join('')}
          <div class="admin-esl-sidebar-foot">
            <a class="admin-esl-menu-item" href="/tablet.html">태블릿 QR</a>
            <button class="admin-esl-menu-item" id="logout">로그아웃</button>
          </div>
        </nav>
      </aside>
      <div class="admin-esl-main">
        <header class="admin-esl-topbar">
          <div>
            <h2>${VIEW_TITLE[view]}</h2>
            <p>${esc(user?.name || '')} · 관리자</p>
          </div>
          <div class="admin-user">${esc(store?.name || '')}</div>
        </header>
        <div class="admin-esl-content" id="content"></div>
      </div>
    </div>
  `
  root.querySelectorAll<HTMLButtonElement>('[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      view = btn.dataset.view as View
      renderShell()
    })
  })
  root.querySelector('#logout')?.addEventListener('click', logout)
  void fillView()
}

async function fillView(): Promise<void> {
  const el = document.querySelector('#content')
  if (!el || !store) return
  try {
    if (view === 'dashboard') await fillDashboard(el)
    else if (view === 'company') fillCompany(el)
    else if (view === 'depts') await fillDepts(el)
    else if (view === 'emps') await fillEmps(el)
    else if (view === 'raw') await fillRaw(el)
    else await fillQr(el)
  } catch (e) {
    el.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '불러오기 실패'}</p>`
  }
}

async function fillDashboard(el: Element): Promise<void> {
  el.innerHTML = `<p class="empty">불러오는 중…</p>`
  const paint = async () => {
    if (!store) return
    const data = await api<Live>(`/api/owner/${store.id}/live`)
    const total = data.working.length + data.off.length
    el.innerHTML = `
      <div class="stat-grid">
        <div class="stat-card"><div class="stat-label">오늘</div><div class="stat-value">${esc(data.date)}</div></div>
        <div class="stat-card"><div class="stat-label">재직 알바</div><div class="stat-value">${total}명</div></div>
        <div class="stat-card"><div class="stat-label">근무 중</div><div class="stat-value">${data.working.length}명</div></div>
        <div class="stat-card"><div class="stat-label">미출근</div><div class="stat-value">${data.off.length}명</div></div>
      </div>
      <div class="panel-grid">
        <section class="panel">
          <div class="panel-hd"><h3>실시간 출근</h3></div>
          ${
            data.working.length
              ? `<table class="data-table"><thead><tr><th>사번</th><th>이름</th><th>부서</th><th>출근</th></tr></thead><tbody>
              ${data.working
                .map(
                  (p) =>
                    `<tr><td>${esc(p.employee_no)}</td><td>${esc(p.name)}</td><td>${esc(p.department_name || '-')}</td><td>${hhmm(p.last_at)}</td></tr>`,
                )
                .join('')}
              </tbody></table>`
              : '<p class="empty">현재 근무 중인 알바가 없습니다.</p>'
          }
        </section>
        <section class="panel">
          <div class="panel-hd"><h3>미출근</h3></div>
          ${
            data.off.length
              ? `<table class="data-table"><thead><tr><th>사번</th><th>이름</th><th>부서</th></tr></thead><tbody>
              ${data.off
                .map(
                  (p) =>
                    `<tr><td>${esc(p.employee_no)}</td><td>${esc(p.name)}</td><td>${esc(p.department_name || '-')}</td></tr>`,
                )
                .join('')}
              </tbody></table>`
              : '<p class="empty">대기 중인 알바가 없습니다. 사원관리에서 등록하세요.</p>'
          }
        </section>
      </div>
    `
  }
  try {
    await paint()
    liveTimer = window.setInterval(() => {
      void paint().catch(() => undefined)
    }, 15_000)
  } catch (e) {
    el.innerHTML = `<p class="empty">${e instanceof Error ? e.message : '실패'}</p>`
  }
}

function fillCompany(el: Element): void {
  el.innerHTML = `
    <section class="panel-form">
      <div class="form-grid">
        <div class="field span-2"><label>회사명</label><input id="co-name" value="${esc(store?.name || '')}" /></div>
      </div>
      <p class="empty" style="text-align:left;padding:12px 0 0">알바는 관리자가 사원관리에서 등록합니다. 알바 앱에서는 이름과 사번으로 로그인합니다.</p>
      <div class="form-actions">
        <button class="btn btn-primary" id="co-save">저장</button>
      </div>
    </section>
  `
  document.querySelector('#co-save')?.addEventListener('click', () => {
    void api(`/api/stores/${store!.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name: val('co-name') }),
    })
      .then(() => loadStores())
      .then(() => renderShell())
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
}

async function fillDepts(el: Element): Promise<void> {
  const data = await api<{ items: Department[] }>(`/api/departments?store_id=${store!.id}`)
  const items = data.items
  const selected = items.find((d) => d.id === selectedDeptId) ?? null
  el.innerHTML = `
    <div class="split">
      <div class="crud-list">
        <button class="list-item ${selected ? '' : 'is-active'}" id="dept-new"><div class="t">+ 새 부서</div></button>
        ${items
          .map(
            (d) => `
          <button class="list-item ${selected?.id === d.id ? 'is-active' : ''}" data-id="${d.id}">
            <div class="t">${esc(d.name)}</div>
            <div class="s">${esc(d.code)}</div>
          </button>`,
          )
          .join('')}
      </div>
      <form class="crud-form" id="dept-form">
        <div class="form-grid">
          <div class="field"><label>부서코드</label><input id="dept-code" value="${esc(selected?.code || '')}" placeholder="비우면 자동" /></div>
          <div class="field"><label>부서명</label><input id="dept-name" value="${esc(selected?.name || '')}" /></div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit">저장</button>
          ${selected ? `<button class="btn btn-danger" type="button" id="dept-del">삭제</button>` : ''}
        </div>
      </form>
    </div>
  `
  document.querySelector('#dept-new')?.addEventListener('click', () => {
    selectedDeptId = null
    void fillDepts(el)
  })
  el.querySelectorAll<HTMLButtonElement>('[data-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedDeptId = Number(btn.dataset.id)
      void fillDepts(el)
    })
  })
  document.querySelector('#dept-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault()
    const payload = { store_id: store!.id, code: val('dept-code') || undefined, name: val('dept-name') }
    const req = selected
      ? api(`/api/departments/${selected.id}`, {
          method: 'PUT',
          body: JSON.stringify({ code: val('dept-code'), name: val('dept-name') }),
        })
      : api('/api/departments', { method: 'POST', body: JSON.stringify(payload) })
    void req
      .then(() => fillDepts(el))
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  document.querySelector('#dept-del')?.addEventListener('click', () => {
    if (!selected || !window.confirm('부서를 삭제할까요?')) return
    void api(`/api/departments/${selected.id}`, { method: 'DELETE' })
      .then(() => {
        selectedDeptId = null
        return fillDepts(el)
      })
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
}

async function fillEmps(el: Element): Promise<void> {
  const [empData, deptData] = await Promise.all([
    api<{ items: Employee[] }>(`/api/employees?store_id=${store!.id}`),
    api<{ items: Department[] }>(`/api/departments?store_id=${store!.id}`),
  ])
  const items = empData.items
  const depts = deptData.items
  const selected = items.find((d) => d.id === selectedEmpId) ?? null
  const deptOptions = ['<option value="">선택</option>']
    .concat(
      depts.map(
        (d) =>
          `<option value="${esc(d.name)}" ${selected?.department_name === d.name ? 'selected' : ''}>${esc(d.name)}</option>`,
      ),
    )
    .join('')
  el.innerHTML = `
    <div class="split-table">
      <section class="table-panel">
        <div class="panel-hd">
          <h3>등록 사원 ${items.length}명</h3>
        </div>
        ${
          items.length
            ? `<table class="data-table">
            <thead>
              <tr>
                <th>사번</th>
                <th>이름</th>
                <th>부서</th>
                <th>입사일</th>
                <th>상태</th>
                <th>인증</th>
                <th class="num">시급</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${items
                .map(
                  (e) => `
                <tr class="${selected?.id === e.id ? 'is-active' : ''}" data-id="${e.id}" style="cursor:pointer">
                  <td>${esc(e.employee_no)}</td>
                  <td>${esc(e.name)}</td>
                  <td>${esc(e.department_name || '-')}</td>
                  <td>${esc(e.hire_date || '-')}</td>
                  <td>${esc(e.status)}</td>
                  <td><span class="badge ${e.auth_status === 'O' ? 'badge-ok' : 'badge-warn'}">${esc(e.auth_label)}</span></td>
                  <td class="num">${Number(e.hourly_wage || 0).toLocaleString('ko-KR')}</td>
                  <td>
                    <div class="row-actions">
                      <button type="button" class="btn" data-revoke="${e.id}">인증취소</button>
                      <button type="button" class="btn btn-danger" data-del="${e.id}">삭제</button>
                    </div>
                  </td>
                </tr>`,
                )
                .join('')}
            </tbody>
          </table>`
            : '<p class="empty">등록된 사원이 없습니다. 오른쪽에서 사원을 등록하세요.</p>'
        }
      </section>
      <aside class="register-panel">
        <div class="panel-hd">
          <div>
            <h3>${selected ? '사원 수정' : '사원 등록'}</h3>
            <p>${selected ? '행을 눌러 선택한 사원을 수정합니다.' : '이름과 사번으로 알바 앱에 로그인합니다.'}</p>
          </div>
        </div>
        <form class="crud-form" id="emp-form">
          <div class="form-grid" style="grid-template-columns:1fr">
            <div class="field"><label>사번</label><input id="emp-no" value="${esc(selected?.employee_no || '')}" /></div>
            <div class="field"><label>이름</label><input id="emp-name" value="${esc(selected?.name || '')}" /></div>
            <div class="field"><label>부서</label><select id="emp-dept">${deptOptions}</select></div>
            <div class="field"><label>입사일</label><input id="emp-hire" type="date" value="${esc(selected?.hire_date || todayStr())}" /></div>
            <div class="field"><label>상태</label>
              <select id="emp-status">
                <option ${selected?.status === '재직' || !selected ? 'selected' : ''}>재직</option>
                <option ${selected?.status === '퇴사' ? 'selected' : ''}>퇴사</option>
              </select>
            </div>
            <div class="field"><label>시급</label><input id="emp-wage" type="number" min="0" value="${selected?.hourly_wage ?? 0}" /></div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit">${selected ? '수정 저장' : '등록'}</button>
            ${selected ? `<button class="btn" type="button" id="emp-new">새 등록</button>` : ''}
          </div>
        </form>
      </aside>
    </div>
  `
  document.querySelector('#emp-new')?.addEventListener('click', () => {
    selectedEmpId = null
    void fillEmps(el)
  })
  el.querySelectorAll<HTMLTableRowElement>('tr[data-id]').forEach((row) => {
    row.addEventListener('click', (ev) => {
      if ((ev.target as HTMLElement).closest('button')) return
      selectedEmpId = Number(row.dataset.id)
      void fillEmps(el)
    })
  })
  document.querySelector('#emp-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault()
    const payload = {
      store_id: store!.id,
      employee_no: val('emp-no'),
      name: val('emp-name'),
      department_name: val('emp-dept'),
      hire_date: val('emp-hire'),
      status: val('emp-status'),
      hourly_wage: Number(val('emp-wage') || 0),
    }
    const req = selected
      ? api(`/api/employees/${selected.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      : api('/api/employees', { method: 'POST', body: JSON.stringify(payload) })
    void req
      .then(() => {
        selectedEmpId = null
        return fillEmps(el)
      })
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  el.querySelectorAll<HTMLButtonElement>('[data-revoke]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation()
      const id = Number(btn.dataset.revoke)
      if (!window.confirm('모바일 인증을 취소할까요? 알바가 다시 이름·사번으로 비밀번호를 설정해야 합니다.')) return
      void api(`/api/employees/${id}/revoke-auth`, { method: 'POST' })
        .then(() => fillEmps(el))
        .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
    })
  })
  el.querySelectorAll<HTMLButtonElement>('[data-del]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation()
      const id = Number(btn.dataset.del)
      if (!window.confirm('사원을 삭제할까요?')) return
      void api(`/api/employees/${id}`, { method: 'DELETE' })
        .then(() => {
          if (selectedEmpId === id) selectedEmpId = null
          return fillEmps(el)
        })
        .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
    })
  })
}

function sourceLabel(source: string | null): string {
  if (source === 'QR') return 'QR'
  if (source === 'MANUAL') return '수동'
  return source || '-'
}

async function fillRaw(el: Element): Promise<void> {
  const from = document.querySelector<HTMLInputElement>('#raw-from')?.value || todayStr(-7)
  const to = document.querySelector<HTMLInputElement>('#raw-to')?.value || todayStr()
  const [empData, evData] = await Promise.all([
    api<{ items: Employee[] }>(`/api/employees?store_id=${store!.id}`),
    api<{ items: AttendanceEvent[] }>(
      `/api/attendance-events?store_id=${store!.id}&date_from=${from}&date_to=${to}${rawFilterEmpId ? `&employee_id=${rawFilterEmpId}` : ''}`,
    ),
  ])
  const emps = empData.items
  const events = evData.items
  const selectedEv = events.find((e) => e.id === selectedEventId) ?? null
  const occurred = selectedEv?.occurred_at || ''
  const formEmpNo = selectedEv?.employee_no || ''
  const empFilterOptions = ['<option value="">전체 사원</option>']
    .concat(
      emps.map(
        (e) =>
          `<option value="${e.id}" ${rawFilterEmpId === e.id ? 'selected' : ''}>${esc(e.employee_no)} ${esc(e.name)}</option>`,
      ),
    )
    .join('')
  const empFormOptions = ['<option value="">사원 선택</option>']
    .concat(
      emps.map(
        (e) =>
          `<option value="${esc(e.employee_no)}" ${formEmpNo === e.employee_no ? 'selected' : ''}>${esc(e.employee_no)} ${esc(e.name)}</option>`,
      ),
    )
    .join('')
  el.innerHTML = `
    <div class="page-toolbar">
      <div class="field"><label>시작일</label><input id="raw-from" type="date" value="${esc(from)}" /></div>
      <div class="field"><label>종료일</label><input id="raw-to" type="date" value="${esc(to)}" /></div>
      <div class="field"><label>사원</label><select id="raw-emp">${empFilterOptions}</select></div>
      <button class="btn btn-primary" id="raw-search">조회</button>
    </div>
    <div class="split-table">
      <section class="table-panel">
        <div class="panel-hd">
          <h3>출퇴근 기록 ${events.length}건</h3>
        </div>
        ${
          events.length
            ? `<table class="data-table">
            <thead>
              <tr>
                <th>일시</th>
                <th>사번</th>
                <th>이름</th>
                <th>구분</th>
                <th>출처</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${events
                .map(
                  (e) => `
                <tr class="${selectedEv?.id === e.id ? 'is-active' : ''}" data-ev="${e.id}" style="cursor:pointer">
                  <td>${esc(e.occurred_at.slice(0, 16).replace('T', ' '))}</td>
                  <td>${esc(e.employee_no)}</td>
                  <td>${esc(e.employee_name)}</td>
                  <td>${esc(e.event_label)}</td>
                  <td>${esc(sourceLabel(e.source))}</td>
                  <td>
                    <div class="row-actions">
                      <button type="button" class="btn btn-danger" data-del="${e.id}">삭제</button>
                    </div>
                  </td>
                </tr>`,
                )
                .join('')}
            </tbody>
          </table>`
            : '<p class="empty">조회된 원시데이터가 없습니다. 오른쪽에서 기록을 등록하세요.</p>'
        }
      </section>
      <aside class="register-panel">
        <div class="panel-hd">
          <div>
            <h3>${selectedEv ? '기록 수정' : '기록 등록'}</h3>
            <p>${selectedEv ? '행을 눌러 선택한 기록을 수정합니다.' : '누락된 출근·퇴근을 수동으로 넣습니다.'}</p>
          </div>
        </div>
        <form class="crud-form" id="raw-form">
          <div class="form-grid" style="grid-template-columns:1fr">
            <div class="field"><label>사원</label><select id="raw-no">${empFormOptions}</select></div>
            <div class="field"><label>구분</label>
              <select id="raw-type">
                <option value="IN" ${selectedEv?.event_type === 'IN' || !selectedEv ? 'selected' : ''}>출근</option>
                <option value="OUT" ${selectedEv?.event_type === 'OUT' ? 'selected' : ''}>퇴근</option>
              </select>
            </div>
            <div class="field"><label>날짜</label><input id="raw-date" type="date" value="${esc(occurred.slice(0, 10) || todayStr())}" /></div>
            <div class="field"><label>시각</label><input id="raw-time" type="time" step="1" value="${esc((occurred.slice(11, 19) || '09:00:00').slice(0, 8))}" /></div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit">${selectedEv ? '수정 저장' : '등록'}</button>
            ${selectedEv ? `<button class="btn" type="button" id="raw-clear">새 등록</button>` : ''}
          </div>
        </form>
      </aside>
    </div>
  `
  const reload = () => void fillRaw(el)
  document.querySelector('#raw-search')?.addEventListener('click', () => {
    const emp = val('raw-emp')
    rawFilterEmpId = emp ? Number(emp) : null
    selectedEventId = null
    reload()
  })
  el.querySelectorAll<HTMLTableRowElement>('tr[data-ev]').forEach((row) => {
    row.addEventListener('click', (ev) => {
      if ((ev.target as HTMLElement).closest('button')) return
      selectedEventId = Number(row.dataset.ev)
      reload()
    })
  })
  document.querySelector('#raw-form')?.addEventListener('submit', (ev) => {
    ev.preventDefault()
    const payload = {
      store_id: store!.id,
      employee_no: val('raw-no'),
      event_type: val('raw-type'),
      event_date: val('raw-date'),
      event_time: val('raw-time'),
    }
    const req = selectedEv
      ? api(`/api/attendance-events/${selectedEv.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      : api('/api/attendance-events', { method: 'POST', body: JSON.stringify(payload) })
    void req
      .then(() => {
        selectedEventId = null
        reload()
      })
      .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
  })
  document.querySelector('#raw-clear')?.addEventListener('click', () => {
    selectedEventId = null
    reload()
  })
  el.querySelectorAll<HTMLButtonElement>('[data-del]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation()
      const id = Number(btn.dataset.del)
      if (!window.confirm('이 기록을 삭제할까요?')) return
      void api(`/api/attendance-events/${id}?store_id=${store!.id}`, { method: 'DELETE' })
        .then(() => {
          if (selectedEventId === id) selectedEventId = null
          reload()
        })
        .catch((e: unknown) => window.alert(e instanceof Error ? e.message : '실패'))
    })
  })
}

async function fillQr(el: Element): Promise<void> {
  el.innerHTML = `
    <div class="admin-qr-card">
      <canvas id="admin-qr-canvas" aria-label="출근 인증 QR"></canvas>
      <p class="admin-qr-count" id="admin-qr-count">불러오는 중…</p>
      <p class="empty">알바가 이 QR을 찍으면 출근·퇴근됩니다. 태블릿 전체화면을 권장합니다.</p>
      <a class="btn btn-primary" href="/tablet.html" style="display:inline-flex;align-items:center;text-decoration:none;margin-top:8px">태블릿 전체화면</a>
    </div>
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
      color: { dark: '#0b1b33ff', light: '#ffffffff' },
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
