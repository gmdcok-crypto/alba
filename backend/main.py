"""알바 근태 API — SQLite(로컬) / MariaDB(운영) + KST."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from datetime import datetime
from typing import Union

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from backend.database import DictCursor, get_connection, on_railway, use_mysql
from backend.routes import attendance_events, auth, clock, departments, employees, kiosk, managers, owner, stores
from backend.schema_ensure import ensure_schema

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("alba-api")


def _root_log_level() -> int:
    if os.getenv("LOG_LEVEL"):
        return getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_NAME"):
        return logging.WARNING
    return logging.INFO


logging.basicConfig(level=_root_log_level(), format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    conn = get_connection()
    try:
        ensure_schema(conn)
        logger.info("schema ready (%s)", "mysql" if use_mysql() else "sqlite")
        if on_railway() and not (os.getenv("JWT_SECRET") or "").strip():
            logger.warning("JWT_SECRET 이 없습니다. 웹 서비스 Variables에 강한 임의 문자열을 넣으세요.")
        yield
    finally:
        conn.close()


app = FastAPI(title="alba-api", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def static_cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(auth.router, prefix="/api")
app.include_router(stores.router, prefix="/api")
app.include_router(departments.router, prefix="/api")
app.include_router(managers.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(attendance_events.router, prefix="/api")
app.include_router(clock.router, prefix="/api")
app.include_router(kiosk.router, prefix="/api")
app.include_router(owner.router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error("unhandled %s: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "error_type": type(exc).__name__},
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "alba-api",
        "stack": "fastapi",
        "db": "mysql" if use_mysql() else "sqlite",
        "railway": on_railway(),
    }


@app.get("/api/db/ping", response_model=None)
def db_ping() -> Union[dict, JSONResponse]:
    try:
        conn = get_connection()
        try:
            cur = conn.cursor(DictCursor)
            if conn.kind == "mysql":
                cur.execute("SET time_zone = '+09:00'")
                cur.execute("SELECT NOW() AS db_now, @@session.time_zone AS tz")
            else:
                cur.execute("SELECT datetime('now','localtime') AS db_now")
            row = cur.fetchone() or {}
        finally:
            conn.close()
        db_now = row.get("db_now")
        now_str = db_now.isoformat() if isinstance(db_now, datetime) else (str(db_now) if db_now is not None else None)
        return {
            "ok": True,
            "db": "mysql" if use_mysql() else "sqlite",
            "sessionTimeZone": row.get("tz"),
            "nowKstSession": now_str,
        }
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


_STATIC_DIST = Path(__file__).resolve().parent.parent / "client" / "dist"
_INDEX = _STATIC_DIST / "index.html"


def _html(name: str) -> Union[FileResponse, JSONResponse]:
    path = _STATIC_DIST / name
    if not path.exists():
        return JSONResponse(
            {"detail": "client/dist 가 없습니다. Railway 빌드에서 Vite 가 실행됐는지 확인하세요."},
            status_code=503,
        )
    return FileResponse(path)


@app.get("/", response_model=None)
def spa_index() -> Union[FileResponse, JSONResponse]:
    return _html("index.html")


@app.get("/admin.html", response_model=None)
def admin_pwa() -> Union[FileResponse, JSONResponse]:
    return _html("admin.html")


@app.get("/tablet.html", response_model=None)
def tablet_kiosk() -> Union[FileResponse, JSONResponse]:
    return _html("tablet.html")


if _STATIC_DIST.exists():
    app.mount("/", StaticFiles(directory=_STATIC_DIST, html=True), name="frontend")
else:
    logger.warning("client/dist 가 없어 정적 프론트를 서빙하지 않습니다.")
