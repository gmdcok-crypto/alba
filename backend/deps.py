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
    if str(row.get("role") or "") == "manager":
        scope = manager_scope(conn, int(row["id"]))
        if not scope:
            raise HTTPException(status_code=401, detail="배정된 지점이 없습니다. 관리자에게 문의하세요.")
        if str(scope.get("auth_status") or "") != "O":
            raise HTTPException(status_code=401, detail="인증이 취소되었습니다. 관리자에게 문의하세요.")
        row.update(scope)
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


def manager_scope(conn: Connection, user_id: int) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT bm.store_id, bm.department_id, bm.auth_status,
               d.name AS department_name, s.name AS store_name
        FROM branch_managers bm
        JOIN departments d ON d.id = bm.department_id
        JOIN stores s ON s.id = bm.store_id
        WHERE bm.user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )
    return cur.fetchone()


def require_owner(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="사장님 계정만 사용할 수 있습니다.")
    return user


def require_staff(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="관리자 계정만 사용할 수 있습니다.")
    return user


def require_store_access(conn: Connection, store_id: int, user: dict[str, Any]) -> None:
    if user.get("role") == "owner":
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM stores WHERE id = %s AND owner_id = %s LIMIT 1",
            (store_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="이 매장의 사장님만 가능합니다.")
        return
    if user.get("role") == "manager":
        if int(user.get("store_id") or 0) != int(store_id):
            raise HTTPException(status_code=403, detail="이 지점의 점장만 가능합니다.")
        return
    raise HTTPException(status_code=403, detail="권한이 없습니다.")


def manager_department_id(user: dict[str, Any]) -> int | None:
    if user.get("role") != "manager":
        return None
    try:
        return int(user.get("department_id") or 0) or None
    except (TypeError, ValueError):
        return None
