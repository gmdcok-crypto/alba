"""회원가입 · 로그인 · 토큰 갱신."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, get_db
from backend.deps import get_current_employee, get_current_user, manager_scope
from backend.jwt_tokens import create_access_token, create_refresh_token, decode_token
from backend.kst import now_kst, now_kst_str
from backend.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupBody(BaseModel):
    login_id: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=4, max_length=72)
    role: Literal["owner"] = "owner"


class WorkerLoginBody(BaseModel):
    employee_no: str = Field(..., min_length=1, max_length=32)
    name: str = ""
    password: str = Field(..., min_length=4, max_length=72)


class LoginBody(BaseModel):
    login_id: str
    password: str
    name: str = ""


class RefreshBody(BaseModel):
    refresh_token: str


def _token_pair(conn: Connection, user: dict) -> dict:
    jti = uuid.uuid4().hex
    access = create_access_token(int(user["id"]), user["login_id"], user["role"])
    refresh = create_refresh_token(int(user["id"]), jti)
    expires = (now_kst() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO refresh_tokens (user_id, jti, expires_at, revoked, created_at)
        VALUES (%s, %s, %s, 0, %s)
        """,
        (user["id"], jti, expires, now_kst_str()),
    )
    conn.commit()
    payload = {
        "id": user["id"],
        "login_id": user["login_id"],
        "name": user["name"],
        "role": user["role"],
    }
    if str(user.get("role") or "") == "manager":
        scope = manager_scope(conn, int(user["id"]))
        if scope:
            payload.update(
                {
                    "store_id": scope["store_id"],
                    "department_id": scope["department_id"],
                    "department_name": scope["department_name"],
                    "store_name": scope["store_name"],
                }
            )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": payload,
    }


def _worker_payload(emp: dict) -> dict:
    return {
        "id": emp["id"],
        "login_id": emp["employee_no"],
        "employee_no": emp["employee_no"],
        "name": emp["name"],
        "role": "worker",
        "store_id": emp["store_id"],
        "store_name": emp.get("store_name"),
        "department_id": emp.get("department_id"),
        "department_name": emp.get("department_name") or "",
        "hourly_wage": emp.get("hourly_wage") or 0,
        "auth_status": emp.get("auth_status"),
        "status": emp.get("status"),
    }


def _worker_token_pair(conn: Connection, emp: dict) -> dict:
    jti = uuid.uuid4().hex
    access = create_access_token(int(emp["id"]), emp["employee_no"], "worker")
    refresh = create_refresh_token(int(emp["id"]), jti)
    expires = (now_kst() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO employee_refresh_tokens (employee_id, jti, expires_at, revoked, created_at)
        VALUES (%s, %s, %s, 0, %s)
        """,
        (emp["id"], jti, expires, now_kst_str()),
    )
    conn.commit()
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": _worker_payload(emp),
    }


@router.post("/signup")
def signup(body: SignupBody, conn: Connection = Depends(get_db)) -> dict:
    login_id = body.login_id.strip()
    name = body.name.strip()
    if not login_id or not name:
        raise HTTPException(status_code=400, detail="아이디와 이름을 입력하세요.")
    if body.role != "owner":
        raise HTTPException(status_code=400, detail="알바는 관리자가 등록합니다. 사번으로 로그인하세요.")
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE login_id = %s LIMIT 1", (login_id,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
    cur.execute(
        """
        INSERT INTO users (login_id, name, password_hash, role, created_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (login_id, name, hash_password(body.password), body.role, now_kst_str()),
    )
    conn.commit()
    cur.execute(
        "SELECT id, login_id, name, role FROM users WHERE id = %s",
        (cur.lastrowid,),
    )
    user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=500, detail="가입에 실패했습니다.")
    return _token_pair(conn, user)


@router.post("/login")
def login(body: LoginBody, conn: Connection = Depends(get_db)) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, login_id, name, role, password_hash FROM users WHERE login_id = %s LIMIT 1",
        (body.login_id.strip(),),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    if str(row.get("role") or "") == "manager":
        scope = manager_scope(conn, int(row["id"]))
        auth_status = str((scope or {}).get("auth_status") or "X")
        if auth_status != "O":
            name = body.name.strip()
            if not name:
                raise HTTPException(
                    status_code=401,
                    detail="처음 로그인하거나 인증이 취소된 경우 이름과 새 비밀번호를 입력하세요.",
                )
            if name != str(row.get("name") or ""):
                raise HTTPException(status_code=401, detail="아이디 또는 이름이 올바르지 않습니다.")
            if len(body.password) < 4:
                raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다.")
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE id=%s",
                (hash_password(body.password), row["id"]),
            )
            cur.execute(
                "UPDATE branch_managers SET auth_status='O' WHERE user_id=%s",
                (row["id"],),
            )
            conn.commit()
            return _token_pair(conn, row)
    if not verify_password(body.password, str(row["password_hash"])):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    return _token_pair(conn, row)


@router.post("/refresh")
def refresh(body: RefreshBody, conn: Connection = Depends(get_db)) -> dict:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from None
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    jti = str(payload.get("jti") or "")
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, revoked FROM refresh_tokens WHERE jti = %s LIMIT 1",
        (jti,),
    )
    token_row = cur.fetchone()
    if not token_row or int(token_row.get("revoked") or 0) != 0:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    cur.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE jti = %s",
        (jti,),
    )
    conn.commit()
    cur.execute(
        "SELECT id, login_id, name, role FROM users WHERE id = %s LIMIT 1",
        (token_row["user_id"],),
    )
    user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    return _token_pair(conn, user)


@router.post("/worker/login")
def worker_login(body: WorkerLoginBody, conn: Connection = Depends(get_db)) -> dict:
    emp_no = body.employee_no.strip()
    name = body.name.strip()
    cur = conn.cursor()
    if name:
        cur.execute(
            """
            SELECT e.id, e.store_id, e.employee_no, e.name, e.status, e.auth_status,
                   e.password_hash, e.hourly_wage, e.department_id,
                   s.name AS store_name, d.name AS department_name
            FROM employees e
            JOIN stores s ON s.id = e.store_id
            LEFT JOIN departments d ON d.id = e.department_id
            WHERE e.employee_no = %s AND e.name = %s
            """,
            (emp_no, name),
        )
    else:
        cur.execute(
            """
            SELECT e.id, e.store_id, e.employee_no, e.name, e.status, e.auth_status,
                   e.password_hash, e.hourly_wage, e.department_id,
                   s.name AS store_name, d.name AS department_name
            FROM employees e
            JOIN stores s ON s.id = e.store_id
            LEFT JOIN departments d ON d.id = e.department_id
            WHERE e.employee_no = %s
            """,
            (emp_no,),
        )
    rows = cur.fetchall() or []
    if len(rows) > 1:
        raise HTTPException(status_code=400, detail="같은 사번이 여러 매장에 있습니다. 이름을 함께 입력하세요.")
    emp = rows[0] if rows else None
    if not emp:
        raise HTTPException(status_code=401, detail="사번 또는 이름이 올바르지 않습니다.")
    if str(emp.get("status") or "") == "퇴사":
        raise HTTPException(status_code=401, detail="퇴사한 사원은 로그인할 수 없습니다.")

    pwd_hash = emp.get("password_hash")
    auth_status = str(emp.get("auth_status") or "X")
    if not pwd_hash or auth_status != "O":
        if not name:
            raise HTTPException(
                status_code=401,
                detail="처음 로그인하거나 인증이 취소된 경우 이름과 새 비밀번호를 입력하세요.",
            )
        cur.execute(
            "UPDATE employees SET password_hash=%s, auth_status='O' WHERE id=%s",
            (hash_password(body.password), emp["id"]),
        )
        conn.commit()
        emp["auth_status"] = "O"
        return _worker_token_pair(conn, emp)

    if not verify_password(body.password, str(pwd_hash)):
        raise HTTPException(status_code=401, detail="사번 또는 비밀번호가 올바르지 않습니다.")
    return _worker_token_pair(conn, emp)


@router.post("/worker/refresh")
def worker_refresh(body: RefreshBody, conn: Connection = Depends(get_db)) -> dict:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from None
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    jti = str(payload.get("jti") or "")
    cur = conn.cursor()
    cur.execute(
        "SELECT employee_id, revoked FROM employee_refresh_tokens WHERE jti = %s LIMIT 1",
        (jti,),
    )
    token_row = cur.fetchone()
    if not token_row or int(token_row.get("revoked") or 0) != 0:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    cur.execute("UPDATE employee_refresh_tokens SET revoked = 1 WHERE jti = %s", (jti,))
    conn.commit()
    cur.execute(
        """
        SELECT e.id, e.store_id, e.employee_no, e.name, e.status, e.auth_status,
               e.hourly_wage, e.department_id, s.name AS store_name, d.name AS department_name
        FROM employees e
        JOIN stores s ON s.id = e.store_id
        LEFT JOIN departments d ON d.id = e.department_id
        WHERE e.id = %s
        LIMIT 1
        """,
        (token_row["employee_id"],),
    )
    emp = cur.fetchone()
    if not emp or str(emp.get("auth_status") or "") != "O" or str(emp.get("status") or "") == "퇴사":
        raise HTTPException(status_code=401, detail="인증이 취소되었습니다. 관리자에게 문의하세요.")
    return _worker_token_pair(conn, emp)


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@router.get("/worker/me")
def worker_me(emp: dict = Depends(get_current_employee)) -> dict:
    return _worker_payload(emp)
