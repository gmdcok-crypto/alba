"""모바일 출퇴근 (QR)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.attendance_util import minutes_to_hours_label, pair_sessions
from backend.database import Connection, get_db
from backend.deps import get_current_user
from backend.kiosk_qr import verify_kiosk_qr_payload
from backend.kst import dt_iso, now_kst, now_kst_str, parse_dt

router = APIRouter(prefix="/clock", tags=["clock"])


class ClockQrBody(BaseModel):
    qr: str = Field(..., min_length=1, description="스캔한 QR 문자열(JSON)")
    intent: Literal["in", "out"]


def _member(conn: Connection, store_id: int, user_id: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.hourly_wage, m.status, s.name AS store_name, s.lat, s.lng, s.geofence_m
        FROM store_members m
        JOIN stores s ON s.id = m.store_id
        WHERE m.store_id = %s AND m.user_id = %s LIMIT 1
        """,
        (store_id, user_id),
    )
    row = cur.fetchone()
    if not row or row.get("status") != "active":
        raise HTTPException(status_code=403, detail="이 매장에 소속되어 있지 않습니다.")
    return row


def _today_events(conn: Connection, store_id: int, user_id: int) -> list[dict]:
    today = now_kst().strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, event_type, occurred_at, lat, lng
        FROM attendance_events
        WHERE store_id = %s AND user_id = %s AND occurred_at >= %s AND occurred_at < %s
        ORDER BY occurred_at ASC, id ASC
        """,
        (store_id, user_id, f"{today} 00:00:00", f"{today} 23:59:59.999"),
    )
    return cur.fetchall() or []


def _month_events(
    conn: Connection, store_id: int, user_id: int, year: int, month: int
) -> list[dict]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT event_type, occurred_at, lat, lng
        FROM attendance_events
        WHERE store_id = %s AND user_id = %s
          AND occurred_at >= %s AND occurred_at < %s
        ORDER BY occurred_at ASC, id ASC
        """,
        (
            store_id,
            user_id,
            start.strftime("%Y-%m-%d %H:%M:%S"),
            end.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    return cur.fetchall() or []


@router.get("/today")
def clock_today(
    store_id: int,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    member = _member(conn, store_id, int(user["id"]))
    events = _today_events(conn, store_id, int(user["id"]))
    now = now_kst()
    sessions = pair_sessions(events, until=now)
    last = events[-1] if events else None
    clocked_in = bool(last and last["event_type"] == "IN")
    minutes = sum(int(s["minutes"]) for s in sessions)
    wage = int(member.get("hourly_wage") or 0)
    pay = int(minutes / 60 * wage) if wage else 0
    return {
        "store_name": member["store_name"],
        "clocked_in": clocked_in,
        "last_in_at": dt_iso(next((e["occurred_at"] for e in reversed(events) if e["event_type"] == "IN"), None)),
        "last_out_at": dt_iso(next((e["occurred_at"] for e in reversed(events) if e["event_type"] == "OUT"), None)),
        "minutes": minutes,
        "hours_label": minutes_to_hours_label(minutes),
        "hourly_wage": wage,
        "pay_estimate": pay,
        "events": [
            {
                "event_type": e["event_type"],
                "occurred_at": dt_iso(e["occurred_at"]),
            }
            for e in events
        ],
    }


@router.post("/qr")
def clock_with_qr(
    body: ClockQrBody,
    request: Request,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    if user.get("role") != "worker":
        raise HTTPException(status_code=403, detail="알바 계정만 출퇴근할 수 있습니다.")
    try:
        data = json.loads(body.qr.strip())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="QR 내용을 JSON으로 읽을 수 없습니다.") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="QR 데이터 형식이 올바르지 않습니다.")

    store_id = verify_kiosk_qr_payload(data)
    _member(conn, store_id, int(user["id"]))
    event_type = "IN" if body.intent == "in" else "OUT"
    events = _today_events(conn, store_id, int(user["id"]))
    last = events[-1] if events else None
    last_type = last["event_type"] if last else None

    if body.intent == "in" and last_type == "IN":
        raise HTTPException(status_code=409, detail="이미 출근 중입니다. 퇴근 후 다시 출근하세요.")
    if body.intent == "out" and last_type != "IN":
        raise HTTPException(status_code=409, detail="출근 기록이 없어 퇴근할 수 없습니다.")

    if last:
        last_at = parse_dt(last["occurred_at"])
        if last_at and (now_kst() - last_at).total_seconds() < 45:
            raise HTTPException(status_code=429, detail="잠시 후 다시 시도하세요.")

    ua = (request.headers.get("user-agent") or "")[:250]
    now = now_kst_str()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO attendance_events
          (store_id, user_id, event_type, occurred_at, lat, lng, source, device_info, created_at)
        VALUES (%s, %s, %s, %s, NULL, NULL, 'QR', %s, %s)
        """,
        (store_id, user["id"], event_type, now, ua or None, now),
    )
    conn.commit()
    return {
        "ok": True,
        "event_type": event_type,
        "occurred_at": now,
        "store_id": store_id,
    }


@router.get("/records")
def records(
    store_id: int,
    year: int,
    month: int,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    member = _member(conn, store_id, int(user["id"]))
    events = _month_events(conn, store_id, int(user["id"]), year, month)
    sessions = pair_sessions(events, until=now_kst())
    minutes = sum(int(s["minutes"]) for s in sessions if not s["open"])
    open_minutes = sum(int(s["minutes"]) for s in sessions if s["open"])
    wage = int(member.get("hourly_wage") or 0)
    pay = int(minutes / 60 * wage) if wage else 0
    return {
        "year": year,
        "month": month,
        "minutes": minutes,
        "open_minutes": open_minutes,
        "hours_label": minutes_to_hours_label(minutes),
        "hourly_wage": wage,
        "pay_estimate": pay,
        "sessions": [
            {
                "in_at": dt_iso(s["in_at"]),
                "out_at": dt_iso(s["out_at"]),
                "open": s["open"],
                "minutes": s["minutes"],
                "hours_label": minutes_to_hours_label(int(s["minutes"])),
            }
            for s in reversed(sessions)
        ],
    }
