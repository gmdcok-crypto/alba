"""점장관리 — 지점별 점장 계정."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, IntegrityError, get_db
from backend.deps import require_owner
from backend.kst import now_kst_str
from backend.passwords import hash_password

router = APIRouter(prefix="/managers", tags=["managers"])


class ManagerCreate(BaseModel):
    store_id: int
    department_name: str = Field(..., min_length=1)
    login_id: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    password: Optional[str] = None


class ManagerUpdate(BaseModel):
    department_name: str = Field(..., min_length=1)
    login_id: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    password: Optional[str] = None


def _require_store_owner(conn: Connection, store_id: int, user: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM stores WHERE id = %s AND owner_id = %s LIMIT 1",
        (store_id, user["id"]),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="이 매장의 사장님만 가능합니다.")


def _resolve_department(conn: Connection, store_id: int, department_name: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name FROM departments WHERE store_id = %s AND name = %s LIMIT 1",
        (store_id, department_name.strip()),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="지점을 찾을 수 없습니다.")
    return row


def _load_manager(conn: Connection, mgr_id: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT bm.id, bm.store_id, bm.department_id, bm.user_id, bm.auth_status,
               u.login_id, u.name, d.name AS department_name, d.code AS department_code
        FROM branch_managers bm
        JOIN users u ON u.id = bm.user_id
        JOIN departments d ON d.id = bm.department_id
        WHERE bm.id = %s
        LIMIT 1
        """,
        (mgr_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="점장을 찾을 수 없습니다.")
    return row


@router.get("")
def list_managers(
    store_id: int,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_store_owner(conn, store_id, user)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT bm.id, bm.store_id, bm.department_id, bm.user_id, bm.auth_status,
               u.login_id, u.name, d.name AS department_name, d.code AS department_code
        FROM branch_managers bm
        JOIN users u ON u.id = bm.user_id
        JOIN departments d ON d.id = bm.department_id
        WHERE bm.store_id = %s
        ORDER BY d.code, u.name
        """,
        (store_id,),
    )
    items = []
    for row in cur.fetchall() or []:
        items.append(
            {
                **row,
                "auth_label": "인증" if str(row.get("auth_status") or "") == "O" else "미인증",
            }
        )
    return {"items": items}


@router.post("", status_code=201)
def create_manager(
    body: ManagerCreate,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_store_owner(conn, body.store_id, user)
    dept = _resolve_department(conn, body.store_id, body.department_name)
    login_id = body.login_id.strip()
    name = body.name.strip()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE login_id = %s LIMIT 1", (login_id,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
    cur.execute(
        "SELECT id FROM branch_managers WHERE department_id = %s LIMIT 1",
        (dept["id"],),
    )
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="이미 점장이 등록된 지점입니다.")
    now = now_kst_str()
    pwd = (body.password or "").strip()
    auth_status = "O" if len(pwd) >= 4 else "X"
    pwd_hash = hash_password(pwd) if auth_status == "O" else hash_password(uuid.uuid4().hex)
    try:
        cur.execute(
            """
            INSERT INTO users (login_id, name, password_hash, role, created_at)
            VALUES (%s, %s, %s, 'manager', %s)
            """,
            (login_id, name, pwd_hash, now),
        )
        user_id = int(cur.lastrowid)
        cur.execute(
            """
            INSERT INTO branch_managers (store_id, department_id, user_id, auth_status)
            VALUES (%s, %s, %s, %s)
            """,
            (body.store_id, dept["id"], user_id, auth_status),
        )
        new_id = int(cur.lastrowid)
        cur.execute(
            """
            INSERT INTO store_members (store_id, user_id, hourly_wage, status, created_at)
            VALUES (%s, %s, 0, 'active', %s)
            """,
            (body.store_id, user_id, now),
        )
        conn.commit()
    except IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail="점장 등록에 실패했습니다.") from e
    return {"id": new_id}


@router.put("/{mgr_id}")
def update_manager(
    mgr_id: int,
    body: ManagerUpdate,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    row = _load_manager(conn, mgr_id)
    _require_store_owner(conn, int(row["store_id"]), user)
    dept = _resolve_department(conn, int(row["store_id"]), body.department_name)
    login_id = body.login_id.strip()
    name = body.name.strip()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM users WHERE login_id = %s AND id <> %s LIMIT 1",
        (login_id, row["user_id"]),
    )
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
    cur.execute(
        "SELECT id FROM branch_managers WHERE department_id = %s AND id <> %s LIMIT 1",
        (dept["id"], mgr_id),
    )
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="이미 점장이 등록된 지점입니다.")
    try:
        if body.password and body.password.strip():
            cur.execute(
                """
                UPDATE users SET login_id=%s, name=%s, password_hash=%s WHERE id=%s
                """,
                (login_id, name, hash_password(body.password.strip()), row["user_id"]),
            )
            cur.execute(
                "UPDATE branch_managers SET department_id=%s, auth_status='O' WHERE id=%s",
                (dept["id"], mgr_id),
            )
        else:
            cur.execute(
                "UPDATE users SET login_id=%s, name=%s WHERE id=%s",
                (login_id, name, row["user_id"]),
            )
            cur.execute(
                "UPDATE branch_managers SET department_id=%s WHERE id=%s",
                (dept["id"], mgr_id),
            )
        conn.commit()
    except IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail="점장 수정에 실패했습니다.") from e
    return {"ok": True}


@router.post("/{mgr_id}/revoke-auth")
def revoke_manager_auth(
    mgr_id: int,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    row = _load_manager(conn, mgr_id)
    _require_store_owner(conn, int(row["store_id"]), user)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash=%s WHERE id=%s",
        (hash_password(uuid.uuid4().hex), row["user_id"]),
    )
    cur.execute(
        "UPDATE branch_managers SET auth_status='X' WHERE id=%s",
        (mgr_id,),
    )
    cur.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = %s AND revoked = 0",
        (row["user_id"],),
    )
    conn.commit()
    return {"ok": True}


@router.delete("/{mgr_id}")
def delete_manager(
    mgr_id: int,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    row = _load_manager(conn, mgr_id)
    _require_store_owner(conn, int(row["store_id"]), user)
    cur = conn.cursor()
    cur.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = %s AND revoked = 0",
        (row["user_id"],),
    )
    cur.execute("DELETE FROM branch_managers WHERE id = %s", (mgr_id,))
    cur.execute(
        "DELETE FROM store_members WHERE store_id = %s AND user_id = %s",
        (row["store_id"], row["user_id"]),
    )
    cur.execute("DELETE FROM users WHERE id = %s", (row["user_id"],))
    conn.commit()
    return {"ok": True}
