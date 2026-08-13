"""사장님: 실시간 근무 · 일자별 기록."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from backend.attendance_util import minutes_to_hours_label, pair_sessions
from backend.database import Connection, get_db
from backend.deps import get_current_user, manager_department_id, require_store_access
from backend.kst import dt_iso, now_kst

router = APIRouter(prefix="/owner", tags=["owner"])


def _require_owner_store(conn: Connection, store_id: int, user: dict) -> None:
    require_store_access(conn, store_id, user)


@router.get("/{store_id}/live")
def live(
    store_id: int,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_owner_store(conn, store_id, user)
    today = now_kst().strftime("%Y-%m-%d")
    cur = conn.cursor()
    dept_id = manager_department_id(user)
    sql = """
        SELECT e.id AS employee_id, e.employee_no, e.name, e.hourly_wage, e.status,
               d.name AS department_name
        FROM employees e
        LEFT JOIN departments d ON d.id = e.department_id
        WHERE e.store_id = %s AND e.status <> '퇴사'
    """
    params: list[object] = [store_id]
    if dept_id is not None:
        sql += " AND e.department_id = %s"
        params.append(dept_id)
    sql += " ORDER BY e.name ASC"
    cur.execute(sql, tuple(params))
    members = cur.fetchall() or []
    working = []
    off = []
    for mem in members:
        cur.execute(
            """
            SELECT event_type, occurred_at
            FROM attendance_events
            WHERE store_id = %s AND employee_id = %s
              AND occurred_at >= %s AND occurred_at < %s
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1
            """,
            (store_id, mem["employee_id"], f"{today} 00:00:00", f"{today} 23:59:59.999"),
        )
        last = cur.fetchone()
        item = {
            "employee_id": mem["employee_id"],
            "employee_no": mem["employee_no"],
            "user_id": mem["employee_id"],
            "name": mem["name"],
            "department_name": mem.get("department_name") or "",
            "hourly_wage": mem["hourly_wage"],
            "last_at": dt_iso(last["occurred_at"]) if last else None,
            "clocked_in": bool(last and last["event_type"] == "IN"),
        }
        if item["clocked_in"]:
            working.append(item)
        else:
            off.append(item)
    return {"working": working, "off": off, "date": today}


@router.get("/{store_id}/day")
def day_records(
    store_id: int,
    date: str,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_owner_store(conn, store_id, user)
    try:
        day = datetime.strptime(date[:10], "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다.") from e
    nxt = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    start = day.strftime("%Y-%m-%d") + " 00:00:00"
    end = nxt + " 00:00:00"
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.id AS employee_id, e.name, e.hourly_wage
        FROM employees e
        WHERE e.store_id = %s AND e.status <> '퇴사'
        ORDER BY e.name ASC
        """,
        (store_id,),
    )
    members = cur.fetchall() or []
    items = []
    for mem in members:
        cur.execute(
            """
            SELECT event_type, occurred_at
            FROM attendance_events
            WHERE store_id = %s AND employee_id = %s
              AND occurred_at >= %s AND occurred_at < %s
            ORDER BY occurred_at ASC, id ASC
            """,
            (store_id, mem["employee_id"], start, end),
        )
        events = cur.fetchall() or []
        if not events:
            continue
        sessions = pair_sessions(events, until=now_kst())
        minutes = sum(int(s["minutes"]) for s in sessions)
        wage = int(mem.get("hourly_wage") or 0)
        items.append(
            {
                "user_id": mem["employee_id"],
                "employee_id": mem["employee_id"],
                "name": mem["name"],
                "hourly_wage": wage,
                "minutes": minutes,
                "hours_label": minutes_to_hours_label(minutes),
                "pay_estimate": int(minutes / 60 * wage) if wage else 0,
                "sessions": [
                    {
                        "in_at": dt_iso(s["in_at"]),
                        "out_at": dt_iso(s["out_at"]),
                        "open": s["open"],
                        "hours_label": minutes_to_hours_label(int(s["minutes"])),
                    }
                    for s in sessions
                ],
            }
        )
    return {"date": date[:10], "items": items}
