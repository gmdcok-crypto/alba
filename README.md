# 알바근태

모바일로 쓰는 알바 출퇴근 · 근무기록 · 예상급여 프로그램입니다.

사장님은 관리자 PWA(또는 매장 태블릿)에 출근 QR을 띄워 둡니다. 알바는 본인 PWA로 그 QR을 찍어 출근·퇴근합니다.

## 기능 (1차)

- **알바 PWA** (`/`) — 매장 QR 스캔으로 출근 · 퇴근, 근무기록 · 예상 급여
- **관리자 PWA** (`/admin.html`) — 매장·초대코드, 근무 현황, 시급, 출근 QR 표시
- **태블릿 QR** (`/tablet.html`) — 매장 기기 전체화면. 약 30초마다 서명 QR 갱신
- 하루 여러 타임 출퇴근 가능

운영:

- 알바: https://alba-production-702a.up.railway.app/
- 관리자: https://alba-production-702a.up.railway.app/admin.html
- 매장 QR: https://alba-production-702a.up.railway.app/tablet.html

FastAPI가 루트에서 API(`/api`)와 PWA를 같이 서빙하고, DB는 Railway MySQL 입니다. 배포 방법은 `RAILWAY.md` 를 보세요.

로컬은 **SQLite** (`data/alba.db`)라 DB 설치 없이 바로 돌아갑니다.

## 로컬 실행

PowerShell:

```powershell
cd d:\alba
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

cd client
npm install
```

터미널 두 개:

```powershell
# API
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8000
```

```powershell
# 모바일 화면
cd client
npm run dev
```

| 화면 | 주소 |
|------|------|
| 알바 PWA | http://127.0.0.1:5173/ |
| 관리자 PWA | http://127.0.0.1:5173/admin.html |
| 매장 출근 QR | http://127.0.0.1:5173/tablet.html |

같은 Wi‑Fi 폰/태블릿은 `http://<PC IP>:5173/...` 입니다. 관리자(또는 태블릿)에 QR을 띄운 뒤, 알바가 출근/퇴근 버튼 → 카메라로 그 QR을 찍습니다.

로컬에서 API 스모크 테스트로 만든 계정:

| 역할 | 아이디 | 비밀번호 |
|------|--------|----------|
| 사장님 | `boss1` | `1234` |
| 알바 | `alba1` | `1234` |

## 스택

기존 `attend` 와 같습니다.

- FastAPI + PyJWT + bcrypt
- Vite + TypeScript (모바일 웹)
- SQLite (로컬) / Railway MySQL (운영)
