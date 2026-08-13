"""사장님: 실시간 근무 · 일자별 기록."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

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
    dept_id = manager_department_id(user)
    sql = """
        SELECT e.id AS employee_id, e.name, e.hourly_wage
        FROM employees e
        WHERE e.store_id = %s AND e.status <> '퇴사'
    """
    params: list[object] = [store_id]
    if dept_id is not None:
        sql += " AND e.department_id = %s"
        params.append(dept_id)
    sql += " ORDER BY e.name ASC"
    cur.execute(sql, tuple(params))
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


def _occurred_day(value: object) -> str:
    parsed = value if isinstance(value, datetime) else None
    if parsed is None:
        text = str(value).replace("T", " ")
        return text[:10]
    return parsed.strftime("%Y-%m-%d")


@router.get("/{store_id}/period")
def period_records(
    store_id: int,
    date_from: str,
    date_to: str,
    employee_id: Optional[int] = None,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    _require_owner_store(conn, store_id, user)
    try:
        start_day = datetime.strptime(date_from[:10], "%Y-%m-%d")
        end_day = datetime.strptime(date_to[:10], "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다.") from e
    if end_day < start_day:
        raise HTTPException(status_code=400, detail="종료일이 시작일보다 빠릅니다.")
    if (end_day - start_day).days > 92:
        raise HTTPException(status_code=400, detail="조회 기간은 93일 이하여야 합니다.")

    start = start_day.strftime("%Y-%m-%d") + " 00:00:00"
    end = (end_day + timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"
    today = now_kst().strftime("%Y-%m-%d")
    dept_id = manager_department_id(user)
    cur = conn.cursor()
    sql = """
        SELECT e.id AS employee_id, e.employee_no, e.name
        FROM employees e
        WHERE e.store_id = %s
    """
    params: list[object] = [store_id]
    if dept_id is not None:
        sql += " AND e.department_id = %s"
        params.append(dept_id)
    if employee_id:
        sql += " AND e.id = %s"
        params.append(int(employee_id))
    sql += " ORDER BY e.name ASC"
    cur.execute(sql, tuple(params))
    members = cur.fetchall() or []
    emp_ids = [int(m["employee_id"]) for m in members]
    empty = {
        "date_from": date_from[:10],
        "date_to": date_to[:10],
        "minutes": 0,
        "hours_label": minutes_to_hours_label(0),
        "items": [],
    }
    if not emp_ids:
        return empty

    placeholders = ",".join(["%s"] * len(emp_ids))
    cur.execute(
        f"""
        SELECT employee_id, event_type, occurred_at
        FROM attendance_events
        WHERE store_id = %s AND employee_id IN ({placeholders})
          AND occurred_at >= %s AND occurred_at < %s
        ORDER BY employee_id ASC, occurred_at ASC, id ASC
        """,
        tuple([store_id, *emp_ids, start, end]),
    )
    grouped: dict[tuple[int, str], list] = defaultdict(list)
    for ev in cur.fetchall() or []:
        grouped[(int(ev["employee_id"]), _occurred_day(ev["occurred_at"]))].append(ev)

    emp_map = {int(m["employee_id"]): m for m in members}
    items = []
    total_minutes = 0
    for (eid, day), evs in grouped.items():
        mem = emp_map.get(eid)
        if not mem:
            continue
        if day == today:
            cap = now_kst()
        else:
            cap = datetime.strptime(f"{day} 23:59:59", "%Y-%m-%d %H:%M:%S")
        for sess in pair_sessions(evs, until=cap):
            minutes = int(sess["minutes"])
            total_minutes += minutes
            items.append(
                {
                    "date": day,
                    "employee_id": eid,
                    "employee_no": mem["employee_no"],
                    "name": mem["name"],
                    "in_at": dt_iso(sess["in_at"]),
                    "out_at": dt_iso(sess["out_at"]),
                    "open": bool(sess["open"]),
                    "minutes": minutes,
                    "hours_label": minutes_to_hours_label(minutes),
                }
            )
    items.sort(key=lambda r: (r["name"], r["in_at"] or ""))
    items.sort(key=lambda r: r["date"], reverse=True)
    return {
        "date_from": date_from[:10],
        "date_to": date_to[:10],
        "minutes": total_minutes,
        "hours_label": minutes_to_hours_label(total_minutes),
        "items": items,
    }
