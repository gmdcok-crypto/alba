"""모바일 JWT (HS256): access + refresh."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt

_ALGO = "HS256"


def _secret() -> str:
    s = (os.getenv("JWT_SECRET") or "").strip()
    if s:
        return s
    return "alba-dev-only-insecure-jwt-secret-change-in-production"


def _access_expire_minutes() -> int:
    return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


def _refresh_expire_days() -> int:
    return int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "365"))


def create_access_token(user_id: int, login_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_access_expire_minutes())
    return jwt.encode(
        {
            "sub": str(user_id),
            "login_id": login_id,
            "role": role,
            "typ": "access",
            "exp": expire,
        },
        _secret(),
        algorithm=_ALGO,
    )


def create_refresh_token(user_id: int, jti: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_refresh_expire_days())
    return jwt.encode(
        {
            "sub": str(user_id),
            "typ": "refresh",
            "jti": jti,
            "exp": expire,
        },
        _secret(),
        algorithm=_ALGO,
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=[_ALGO])
