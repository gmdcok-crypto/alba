"""사원관리 · 인증취소."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Connection, IntegrityError, get_db
from backend.deps import manager_department_id, require_staff, require_store_access

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeCreate(BaseModel):
    store_id: int
    employee_no: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    department_name: str = ""
    hire_date: str = Field(..., min_length=8)
    status: str = "재직"
    hourly_wage: int = 0


class EmployeeUpdate(BaseModel):
    employee_no: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    department_name: str = ""
    hire_date: str = Field(..., min_length=8)
    status: str = "재직"
    hourly_wage: Optional[int] = None


def _assert_employee_scope(conn: Connection, emp: dict, user: dict) -> None:
    require_store_access(conn, int(emp["store_id"]), user)
    dept_id = manager_department_id(user)
    if dept_id is not None and int(emp.get("department_id") or 0) != dept_id:
        raise HTTPException(status_code=403, detail="다른 지점 사원은 관리할 수 없습니다.")


def _department_name_for_write(conn: Connection, store_id: int, user: dict, department_name: str) -> str:
    if user.get("role") == "manager":
        return str(user.get("department_name") or "")
    return department_name


def _load_employee(conn: Connection, emp_id: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.id, e.store_id, e.employee_no, e.name, e.department_id, e.hire_date,
               e.status, e.auth_status, e.hourly_wage, d.name AS department_name
        FROM employees e
        LEFT JOIN departments d ON d.id = e.department_id
        WHERE e.id = %s
        LIMIT 1
        """,
        (emp_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="사원을 찾을 수 없습니다.")
    return row


def _resolve_department_id(conn: Connection, store_id: int, department_name: str) -> Optional[int]:
    name = department_name.strip()
    if not name:
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM departments WHERE store_id = %s AND name = %s LIMIT 1",
        (store_id, name),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="지점을 찾을 수 없습니다.")
    return int(row["id"])


def _parse_hire_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as e:
        raise HTTPException(status_code=400, detail="입사일 형식이 올바르지 않습니다.") from e


def _revoke_tokens(conn: Connection, emp_id: int) -> None:
    cur = conn.cursor()
    cur.execute(
        "UPDATE employee_refresh_tokens SET revoked = 1 WHERE employee_id = %s AND revoked = 0",
        (emp_id,),
    )


@router.get("")
def list_employees(
    store_id: int,
    user: dict = Depends(require_staff),
    conn: Connection = Depends(get_db),
) -> dict:
    require_store_access(conn, store_id, user)
    cur = conn.cursor()
    dept_id = manager_department_id(user)
    sql = """
        SELECT e.id, e.store_id, e.employee_no, e.name, e.department_id, e.hire_date,
               e.status, e.auth_status, e.hourly_wage, d.name AS department_name
        FROM employees e
        LEFT JOIN departments d ON d.id = e.department_id
        WHERE e.store_id = %s
    """
    params: list[object] = [store_id]
    if dept_id is not None:
        sql += " AND e.department_id = %s"
        params.append(dept_id)
    sql += " ORDER BY e.employee_no ASC"
    cur.execute(sql, tuple(params))
    items = []
    for row in cur.fetchall() or []:
        hd = row.get("hire_date")
        items.append(
            {
                **row,
                "hire_date": hd.isoformat() if hasattr(hd, "isoformat") else (str(hd)[:10] if hd else None),
                "auth_label": "인증" if str(row.get("auth_status") or "") == "O" else "미인증",
            }
        )
    return {"items": items}


@router.post("", status_code=201)
def create_employee(
    body: EmployeeCreate,
    user: dict = Depends(require_staff),
    conn: Connection = Depends(get_db),
) -> dict:
    require_store_access(conn, body.store_id, user)
    dept_name = _department_name_for_write(conn, body.store_id, user, body.department_name)
    dept_id = _resolve_department_id(conn, body.store_id, dept_name)
    hd = _parse_hire_date(body.hire_date)
    status = body.status.strip() or "재직"
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO employees
              (store_id, employee_no, name, department_id, hire_date, status, password_hash, auth_status, hourly_wage)
            VALUES (%s, %s, %s, %s, %s, %s, NULL, 'X', %s)
            """,
            (
                body.store_id,
                body.employee_no.strip(),
                body.name.strip(),
                dept_id,
                hd.isoformat(),
                status,
                max(0, int(body.hourly_wage or 0)),
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid)
    except IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 사번입니다.") from e
    return {"id": new_id}


@router.put("/{emp_id}")
def update_employee(
    emp_id: int,
    body: EmployeeUpdate,
    user: dict = Depends(require_staff),
    conn: Connection = Depends(get_db),
) -> dict:
    row = _load_employee(conn, emp_id)
    _assert_employee_scope(conn, row, user)
    dept_name = _department_name_for_write(conn, int(row["store_id"]), user, body.department_name)
    dept_id = _resolve_department_id(conn, int(row["store_id"]), dept_name)
    hd = _parse_hire_date(body.hire_date)
    status = body.status.strip() or "재직"
    wage = int(row.get("hourly_wage") or 0) if body.hourly_wage is None else max(0, int(body.hourly_wage))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE employees
            SET employee_no=%s, name=%s, department_id=%s, hire_date=%s, status=%s, hourly_wage=%s
            WHERE id=%s
            """,
            (body.employee_no.strip(), body.name.strip(), dept_id, hd.isoformat(), status, wage, emp_id),
        )
        if status == "퇴사":
            cur.execute(
                "UPDATE employees SET password_hash=NULL, auth_status='X' WHERE id=%s",
                (emp_id,),
            )
            _revoke_tokens(conn, emp_id)
        conn.commit()
    except IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail="이미 사용 중인 사번입니다.") from e
    return {"ok": True}


@router.post("/{emp_id}/revoke-auth")
def revoke_employee_auth(
    emp_id: int,
    user: dict = Depends(require_staff),
    conn: Connection = Depends(get_db),
) -> dict:
    row = _load_employee(conn, emp_id)
    _assert_employee_scope(conn, row, user)
    cur = conn.cursor()
    cur.execute(
        "UPDATE employees SET password_hash=NULL, auth_status='X' WHERE id=%s",
        (emp_id,),
    )
    _revoke_tokens(conn, emp_id)
    conn.commit()
    return {"ok": True}


@router.delete("/{emp_id}")
def delete_employee(
    emp_id: int,
    user: dict = Depends(require_staff),
    conn: Connection = Depends(get_db),
) -> dict:
    row = _load_employee(conn, emp_id)
    _assert_employee_scope(conn, row, user)
    cur = conn.cursor()
    cur.execute("DELETE FROM employees WHERE id = %s", (emp_id,))
    conn.commit()
    return {"ok": True}
