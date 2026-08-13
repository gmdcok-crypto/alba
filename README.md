# 알바근태

모바일로 쓰는 알바 출퇴근 · 근무기록 · 예상급여 프로그램입니다.

사장님은 매장을 만들고 초대코드를 알려줍니다. 알바는 폰에서 출근/퇴근하고, 이번 달 근무시간과 시급 기준 예상 급여를 확인합니다.

## 기능 (1차)

- 사장님 / 알바 회원가입 · 로그인
- 매장 생성, 6자리 초대코드 입장
- 휴대폰 출근 · 퇴근 (하루 여러 타임 가능)
- 근무 기록, 이번 달 합계 · 예상 급여
- 사장님: 실시간 근무 현황, 시급 설정
- 선택: 매장 위치 반경 안에서만 출퇴근

로컬은 **SQLite** (`data/alba.db`)라 DB 설치 없이 바로 돌아갑니다. Railway 등에서는 MariaDB/MySQL 환경 변수가 있으면 그걸 씁니다.

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

브라우저에서 http://127.0.0.1:5173 을 엽니다. 같은 Wi‑Fi 폰에서는 `http://<PC IP>:5173` 으로 접속합니다.

로컬에서 API 스모크 테스트로 만든 계정:

| 역할 | 아이디 | 비밀번호 |
|------|--------|----------|
| 사장님 | `boss1` | `1234` |
| 알바 | `alba1` | `1234` |

## 스택

기존 `attend` 와 같습니다.

- FastAPI + PyJWT + bcrypt
- Vite + TypeScript (모바일 웹)
- SQLite (로컬) / MariaDB (운영)
