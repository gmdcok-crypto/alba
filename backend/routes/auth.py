"""회원가입 · 로그인 · 토큰 갱신."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, get_db
from backend.deps import get_current_user
from backend.jwt_tokens import create_access_token, create_refresh_token, decode_token
from backend.kst import now_kst, now_kst_str
from backend.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupBody(BaseModel):
    login_id: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=4, max_length=72)
    role: Literal["owner", "worker"]


class LoginBody(BaseModel):
    login_id: str
    password: str


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
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "login_id": user["login_id"],
            "name": user["name"],
            "role": user["role"],
        },
    }


@router.post("/signup")
def signup(body: SignupBody, conn: Connection = Depends(get_db)) -> dict:
    login_id = body.login_id.strip()
    name = body.name.strip()
    if not login_id or not name:
        raise HTTPException(status_code=400, detail="아이디와 이름을 입력하세요.")
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
    if not row or not verify_password(body.password, str(row["password_hash"])):
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


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return user
