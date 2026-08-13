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

    role = str(payload.get("role") or "")
    if role == "worker":
        raise HTTPException(status_code=403, detail="사장님 계정만 사용할 수 있습니다.")

    cur = conn.cursor()
    cur.execute(
        "SELECT id, login_id, name, role FROM users WHERE id = %s LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    return row


def get_current_employee(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
    conn: Connection = Depends(get_db),
) -> dict[str, Any]:
    try:
        payload = decode_token(cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from None

    if payload.get("typ") != "access" or payload.get("role") != "worker":
        raise HTTPException(status_code=401, detail="알바 로그인이 필요합니다.")

    try:
        emp_id = int(payload.get("sub") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.id, e.store_id, e.employee_no, e.name, e.status, e.auth_status,
               e.hourly_wage, e.department_id, s.name AS store_name
        FROM employees e
        JOIN stores s ON s.id = e.store_id
        WHERE e.id = %s
        LIMIT 1
        """,
        (emp_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="사원을 찾을 수 없습니다.")
    if str(row.get("auth_status") or "") != "O":
        raise HTTPException(status_code=401, detail="인증이 취소되었습니다. 관리자에게 문의하세요.")
    if str(row.get("status") or "") == "퇴사":
        raise HTTPException(status_code=401, detail="퇴사한 사원은 로그인할 수 없습니다.")
    row["role"] = "worker"
    row["login_id"] = row["employee_no"]
    return row


def require_owner(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="사장님 계정만 사용할 수 있습니다.")
    return user
