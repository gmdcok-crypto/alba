"""Bearer JWT에서 현재 사용자 추출."""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.database import Connection, get_db
from backend.jwt_tokens import decode_token

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
    conn: Connection = Depends(get_db),
) -> dict[str, Any]:
    try:
        payload = decode_token(cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from None

    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    try:
        user_id = int(payload.get("sub") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from None

    cur = conn.cursor()
    cur.execute(
        "SELECT id, login_id, name, role FROM users WHERE id = %s LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    return row


def require_owner(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="사장님 계정만 사용할 수 있습니다.")
    return user
