"""지점관리."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, IntegrityError, get_db
from backend.deps import manager_department_id, require_owner, require_staff, require_store_access

router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentCreate(BaseModel):
    store_id: int
    name: str = Field(..., min_length=1, max_length=64)
    code: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=32)


def _require_store_owner(conn: Connection, store_id: int, user: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM stores WHERE id = %s AND owner_id = %s LIMIT 1",
        (store_id, user["id"]),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="이 매장의 사장님만 가능합니다.")


def _next_dept_code(conn: Connection, store_id: int) -> str:
    cur = conn.cursor()
    cur.execute("SELECT code FROM departments WHERE store_id = %s", (store_id,))
    max_n = 0
    for row in cur.fetchall() or []:
        m = re.match(r"^D(\d+)$", str(row["code"]), re.I)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"D{max_n + 1:03d}"


@router.get("")
def list_departments(
    store_id: int,
    user: dict = Depends(require_staff),
    conn: Connection = Depends(get_db),
) -> dict:
    require_store_access(conn, store_id, user)
    cur = conn.cursor()
    dept_id = manager_department_id(user)
    if dept_id is not None:
        cur.execute(
            "SELECT id, store_id, code, name FROM departments WHERE store_id = %s AND id = %s ORDER BY code",
            (store_id, dept_id),
        )
    else:
        cur.execute(
            "SELECT id, store_id, code, name FROM departments WHERE store_id = %s ORDER BY code",
            (store_id,),
        )
    return {"items": cur.fetchall() or []}


@router.post("", status_code=201)
def create_department(
    body: DepartmentCreate,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_store_owner(conn, body.store_id, user)
    name = body.name.strip()
    code = (body.code or "").strip() or _next_dept_code(conn, body.store_id)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO departments (store_id, code, name) VALUES (%s, %s, %s)",
            (body.store_id, code, name),
        )
        conn.commit()
        new_id = cur.lastrowid
    except IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 지점코드입니다.") from e
    return {"id": int(new_id), "code": code, "name": name}


@router.put("/{dept_id}")
def update_department(
    dept_id: int,
    body: DepartmentUpdate,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT id, store_id FROM departments WHERE id = %s LIMIT 1", (dept_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="지점을 찾을 수 없습니다.")
    _require_store_owner(conn, int(row["store_id"]), user)
    try:
        cur.execute(
            "UPDATE departments SET code=%s, name=%s WHERE id=%s",
            (body.code.strip(), body.name.strip(), dept_id),
        )
        conn.commit()
    except IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 지점코드입니다.") from e
    return {"ok": True}


@router.delete("/{dept_id}")
def delete_department(
    dept_id: int,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT id, store_id FROM departments WHERE id = %s LIMIT 1", (dept_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="지점을 찾을 수 없습니다.")
    _require_store_owner(conn, int(row["store_id"]), user)
    cur.execute("DELETE FROM departments WHERE id = %s", (dept_id,))
    conn.commit()
    return {"ok": True}
