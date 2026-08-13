"""알바 근태 API — SQLite(로컬) / MariaDB(운영) + KST."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from backend.database import get_connection, use_mysql
from backend.routes import auth, clock, owner, stores
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
app.include_router(clock.router, prefix="/api")
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
        "db": "mysql" if use_mysql() else "sqlite",
    }


_STATIC_DIST = Path(__file__).resolve().parent.parent / "client" / "dist"
if _STATIC_DIST.exists():
    app.mount("/", StaticFiles(directory=_STATIC_DIST, html=True), name="frontend")
else:
    logger.warning("client/dist 가 없어 정적 프론트를 서빙하지 않습니다.")
