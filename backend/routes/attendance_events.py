"""원시 출퇴근 자료 편집."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, get_db
from backend.deps import require_owner
from backend.kst import now_kst_str

router = APIRouter(prefix="/attendance-events", tags=["attendance-events"])

_TYPE_MAP = {
    "IN": "IN",
    "OUT": "OUT",
    "출근": "IN",
    "퇴근": "OUT",
}


class AttendanceEventWrite(BaseModel):
    store_id: int
    employee_no: str = Field(..., min_length=1)
    event_type: str
    event_date: str
    event_time: str


def _require_store_owner(conn: Connection, store_id: int, user: dict) -> dict:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, owner_id FROM stores WHERE id = %s AND owner_id = %s LIMIT 1",
        (store_id, user["id"]),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="이 매장의 사장님만 가능합니다.")
    return row


def _normalize_event_type(value: str) -> str:
    key = (value or "").strip().upper()
    mapped = _TYPE_MAP.get(key) or _TYPE_MAP.get(value.strip())
    if not mapped:
        raise HTTPException(status_code=400, detail="구분값은 출근 또는 퇴근이어야 합니다.")
    return mapped


def _parse_occurred_at(event_date: str, event_time: str) -> str:
    raw = f"{event_date.strip()[:10]} {event_time.strip()}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="일시 형식이 올바르지 않습니다.")


def _resolve_employee(conn: Connection, store_id: int, employee_no: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, employee_no, name FROM employees
        WHERE store_id = %s AND employee_no = %s
        LIMIT 1
        """,
        (store_id, employee_no.strip()),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="사번을 찾을 수 없습니다.")
    return row


@router.get("")
def list_attendance_events(
    store_id: int,
    date_from: str,
    date_to: str,
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_store_owner(conn, store_id, user)
    cur = conn.cursor()
    sql = """
        SELECT a.id, a.event_type, a.occurred_at, a.source, e.employee_no, e.name AS employee_name
        FROM attendance_events a
        INNER JOIN employees e ON e.id = a.employee_id
        WHERE a.store_id = %s
          AND a.occurred_at >= %s AND a.occurred_at < %s
    """
    params: list[object] = [store_id, f"{date_from[:10]} 00:00:00", f"{date_to[:10]} 23:59:59.999"]
    if department_id:
        sql += " AND e.department_id = %s"
        params.append(int(department_id))
    if employee_id:
        sql += " AND a.employee_id = %s"
        params.append(employee_id)
    sql += " ORDER BY a.occurred_at DESC, a.id DESC"
    cur.execute(sql, tuple(params))
    items = []
    for r in cur.fetchall() or []:
        oc = r["occurred_at"]
        oc_iso = oc.isoformat() if hasattr(oc, "isoformat") else str(oc)
        items.append(
            {
                "id": int(r["id"]),
                "event_type": r["event_type"],
                "event_label": "출근" if r["event_type"] == "IN" else "퇴근",
                "occurred_at": oc_iso,
                "source": r.get("source"),
                "employee_no": r["employee_no"],
                "employee_name": r["employee_name"],
            }
        )
    return {"items": items}


@router.post("", status_code=201)
def create_attendance_event(
    body: AttendanceEventWrite,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    store = _require_store_owner(conn, body.store_id, user)
    emp = _resolve_employee(conn, body.store_id, body.employee_no)
    event_type = _normalize_event_type(body.event_type)
    occurred_at = _parse_occurred_at(body.event_date, body.event_time)
    now = now_kst_str()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO attendance_events
          (store_id, user_id, employee_id, event_type, occurred_at, source, device_info, created_at)
        VALUES (%s, %s, %s, %s, %s, 'MANUAL', 'admin-raw-edit', %s)
        """,
        (body.store_id, store["owner_id"], emp["id"], event_type, occurred_at, now),
    )
    conn.commit()
    return {"id": int(cur.lastrowid)}


@router.put("/{event_id}")
def update_attendance_event(
    event_id: int,
    body: AttendanceEventWrite,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    store = _require_store_owner(conn, body.store_id, user)
    emp = _resolve_employee(conn, body.store_id, body.employee_no)
    event_type = _normalize_event_type(body.event_type)
    occurred_at = _parse_occurred_at(body.event_date, body.event_time)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, store_id FROM attendance_events WHERE id = %s LIMIT 1",
        (event_id,),
    )
    row = cur.fetchone()
    if not row or int(row["store_id"]) != body.store_id:
        raise HTTPException(status_code=404, detail="해당 원시자료를 찾을 수 없습니다.")
    cur.execute(
        """
        UPDATE attendance_events
        SET employee_id=%s, user_id=%s, event_type=%s, occurred_at=%s, source='MANUAL', device_info='admin-raw-edit'
        WHERE id=%s
        """,
        (emp["id"], store["owner_id"], event_type, occurred_at, event_id),
    )
    conn.commit()
    return {"ok": True}


@router.delete("/{event_id}")
def delete_attendance_event(
    event_id: int,
    store_id: int,
    user: dict = Depends(require_owner),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_store_owner(conn, store_id, user)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM attendance_events WHERE id = %s AND store_id = %s LIMIT 1",
        (event_id, store_id),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="해당 원시자료를 찾을 수 없습니다.")
    cur.execute("DELETE FROM attendance_events WHERE id = %s", (event_id,))
    conn.commit()
    return {"ok": True}
