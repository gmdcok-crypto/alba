"""매장 · 초대코드 · 직원."""

from __future__ import annotations

import secrets
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, get_db
from backend.deps import get_current_user
from backend.kst import now_kst_str

router = APIRouter(prefix="/stores", tags=["stores"])


class CreateStoreBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class JoinBody(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=16)


class PatchStoreBody(BaseModel):
    name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    geofence_m: Optional[int] = None


class PatchMemberBody(BaseModel):
    hourly_wage: Optional[int] = None
    status: Optional[str] = None


def _invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _store_row(conn: Connection, store_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, owner_id, name, invite_code, lat, lng, geofence_m, created_at
        FROM stores WHERE id = %s LIMIT 1
        """,
        (store_id,),
    )
    return cur.fetchone()


def _require_owner_of(conn: Connection, store_id: int, user: dict) -> dict:
    store = _store_row(conn, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다.")
    if int(store["owner_id"]) != int(user["id"]):
        raise HTTPException(status_code=403, detail="이 매장의 사장님만 가능합니다.")
    return store


@router.post("")
def create_store(
    body: CreateStoreBody,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="사장님 계정만 매장을 만들 수 있습니다.")
    code = _invite_code()
    cur = conn.cursor()
    for _ in range(8):
        cur.execute("SELECT id FROM stores WHERE invite_code = %s LIMIT 1", (code,))
        if not cur.fetchone():
            break
        code = _invite_code()
    now = now_kst_str()
    cur.execute(
        """
        INSERT INTO stores (owner_id, name, invite_code, geofence_m, created_at)
        VALUES (%s, %s, %s, 0, %s)
        """,
        (user["id"], body.name.strip(), code, now),
    )
    store_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO store_members (store_id, user_id, hourly_wage, status, created_at)
        VALUES (%s, %s, 0, 'active', %s)
        """,
        (store_id, user["id"], now),
    )
    conn.commit()
    store = _store_row(conn, int(store_id))
    if not store:
        raise HTTPException(status_code=500, detail="매장 생성에 실패했습니다.")
    return store


@router.get("")
def my_stores(
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id, s.owner_id, s.name, s.invite_code, s.lat, s.lng, s.geofence_m,
               m.hourly_wage, m.status
        FROM store_members m
        JOIN stores s ON s.id = m.store_id
        WHERE m.user_id = %s AND m.status = 'active'
        ORDER BY s.id ASC
        """,
        (user["id"],),
    )
    rows = cur.fetchall() or []
    return {"items": rows}


@router.post("/join")
def join_store(
    body: JoinBody,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    if user["role"] != "worker":
        raise HTTPException(status_code=403, detail="알바 계정만 초대코드로 입장할 수 있습니다.")
    code = body.invite_code.strip().upper()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, owner_id, name, invite_code FROM stores WHERE invite_code = %s LIMIT 1",
        (code,),
    )
    store = cur.fetchone()
    if not store:
        raise HTTPException(status_code=404, detail="초대코드가 올바르지 않습니다.")
    cur.execute(
        "SELECT id, status FROM store_members WHERE store_id = %s AND user_id = %s LIMIT 1",
        (store["id"], user["id"]),
    )
    existing = cur.fetchone()
    now = now_kst_str()
    if existing:
        if existing.get("status") == "active":
            return store
        cur.execute(
            "UPDATE store_members SET status = 'active' WHERE id = %s",
            (existing["id"],),
        )
    else:
        cur.execute(
            """
            INSERT INTO store_members (store_id, user_id, hourly_wage, status, created_at)
            VALUES (%s, %s, 0, 'active', %s)
            """,
            (store["id"], user["id"], now),
        )
    conn.commit()
    return store


@router.patch("/{store_id}")
def patch_store(
    store_id: int,
    body: PatchStoreBody,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_owner_of(conn, store_id, user)
    fields: list[str] = []
    params: list[object] = []
    if body.name is not None:
        fields.append("name = %s")
        params.append(body.name.strip())
    if body.lat is not None:
        fields.append("lat = %s")
        params.append(body.lat)
    if body.lng is not None:
        fields.append("lng = %s")
        params.append(body.lng)
    if body.geofence_m is not None:
        fields.append("geofence_m = %s")
        params.append(max(0, body.geofence_m))
    if not fields:
        store = _store_row(conn, store_id)
        return store or {}
    params.append(store_id)
    cur = conn.cursor()
    cur.execute(f"UPDATE stores SET {', '.join(fields)} WHERE id = %s", tuple(params))
    conn.commit()
    store = _store_row(conn, store_id)
    return store or {}


@router.get("/{store_id}/members")
def list_members(
    store_id: int,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_owner_of(conn, store_id, user)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.id, m.user_id, u.name, u.login_id, u.role, m.hourly_wage, m.status, m.created_at
        FROM store_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.store_id = %s
        ORDER BY u.role DESC, u.name ASC
        """,
        (store_id,),
    )
    return {"items": cur.fetchall() or []}


@router.patch("/{store_id}/members/{member_user_id}")
def patch_member(
    store_id: int,
    member_user_id: int,
    body: PatchMemberBody,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_owner_of(conn, store_id, user)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM store_members WHERE store_id = %s AND user_id = %s LIMIT 1",
        (store_id, member_user_id),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다.")
    fields: list[str] = []
    params: list[object] = []
    if body.hourly_wage is not None:
        fields.append("hourly_wage = %s")
        params.append(max(0, body.hourly_wage))
    if body.status is not None:
        if body.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="status 값이 올바르지 않습니다.")
        fields.append("status = %s")
        params.append(body.status)
    if fields:
        params.append(row["id"])
        cur.execute(
            f"UPDATE store_members SET {', '.join(fields)} WHERE id = %s",
            tuple(params),
        )
        conn.commit()
    cur.execute(
        """
        SELECT m.id, m.user_id, u.name, u.login_id, m.hourly_wage, m.status
        FROM store_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.id = %s
        """,
        (row["id"],),
    )
    return cur.fetchone() or {}
