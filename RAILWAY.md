# Railway 배포 (알바근태)

한 웹 서비스가 **FastAPI(루트 `/api`)** 와 **모바일 화면(`/`)** 을 같이 서빙합니다. DB는 **같은 프로젝트의 Railway MySQL** 입니다.

- **GitHub**: https://github.com/gmdcok-crypto/alba
- **접속 주소**: https://alba-production-702a.up.railway.app
- **헬스**: https://alba-production-702a.up.railway.app/api/health
- **DB 확인**: https://alba-production-702a.up.railway.app/api/db/ping

## 서비스 구성

프로젝트 안에 서비스를 두 개 둡니다.

1. **MySQL** — Database → Add MySQL  
2. **웹(alba)** — GitHub `gmdcok-crypto/alba` / 브랜치 `main` / **Root Directory 비움(저장소 루트)**

빌더는 **Nixpacks** 만 씁니다. Settings → Build → Builder = **Nixpacks** (Dockerfile / Railpack 아님).

`railway.toml` 이 프론트(`vite build`)만 돌리고, Python 패키지는 Nixpacks 설치 단계에서 한 번만 깔립니다.

빌드가 길었던 이유: Python+Node 런타임을 같이 받고, `vite`/`tsc`/`pip`를 빌드 명령에서 **또** 설치하고 있었습니다. 배포용 명령은 `npm ci` + `vite build` 만 남겼습니다.

## MySQL 연결 (웹 서비스 Variables)

MySQL 서비스에만 변수가 있으면 웹 앱은 DB를 못 봅니다. **웹 서비스 Variables**에 MySQL 값을 **참조**로 넣으세요.

Railway UI: 웹 서비스 → Variables → **Add Variable Reference** → MySQL 서비스 선택.

| 웹 서비스 변수 | MySQL에서 참조 | 설명 |
|----------------|----------------|------|
| `MYSQLHOST` | MySQL `MYSQLHOST` | **사설 호스트** (`*.railway.internal`). 공개 프록시 쓰지 말 것 |
| `MYSQLPORT` | `MYSQLPORT` | 보통 `3306` |
| `MYSQLUSER` | `MYSQLUSER` | |
| `MYSQLPASSWORD` | `MYSQLPASSWORD` | |
| `MYSQLDATABASE` | `MYSQLDATABASE` | 실제 DB 이름 (예: `railway` 또는 `alba`) |
| `MYSQL_URL` | `MYSQL_URL` 또는 `MYSQL_PRIVATE_URL` | 있으면 사설 URL 우선 |

`MYSQL_PUBLIC_URL` / `*.proxy.rlwy.net` 은 웹→DB 연결에 쓰지 않습니다. 같은 프로젝트 안에서는 사설망만 사용합니다. (공개 URL은 PC에서 HeidiSQL 접속할 때만)

추가로:

| 변수 | 값 |
|------|-----|
| `JWT_SECRET` | 강한 임의 문자열 (운영 필수) |
| `KIOSK_QR_SECRET` | 출근 QR HMAC. 없으면 `JWT_SECRET` 사용 |

변수 넣은 뒤 **Redeploy**.

기동 시 `backend/schema_ensure.py` 가 테이블을 자동 생성합니다. SQL 파일을 따로 돌릴 필요 없습니다.

## 확인

1. Settings → Networking 도메인이 `alba-production-702a.up.railway.app` 인지  
2. `/api/health` → `"db": "mysql"`  
3. `/api/db/ping` → `"ok": true`  
4. 루트 `/` 에 로그인 화면

`db` 가 `sqlite` 이거나 ping 이 실패하면 웹 서비스에 MySQL 참조 변수가 없는 것입니다.

## 로컬과의 차이

- 로컬: MySQL 변수 없으면 SQLite (`data/alba.db`)
- Railway: MySQL 없으면 기동 실패 (디스크가 비영속이라 SQLite 금지)
