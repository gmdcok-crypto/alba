"""출퇴근 페어링 · 근무시간 · 거리 계산."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from backend.kst import parse_dt


def pair_sessions(
    events: list[dict[str, Any]],
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """IN/OUT 을 짝지어 세션 목록을 만든다. 열린 출근은 until 까지 계산."""
    sessions: list[dict[str, Any]] = []
    open_in: dict[str, Any] | None = None
    for ev in events:
        et = str(ev.get("event_type") or "")
        if et == "IN":
            if open_in is not None:
                sessions.append(_session(open_in, None, until))
            open_in = ev
        elif et == "OUT" and open_in is not None:
            sessions.append(_session(open_in, ev, until))
            open_in = None
    if open_in is not None:
        sessions.append(_session(open_in, None, until))
    return sessions


def _session(
    inn: dict[str, Any],
    out: dict[str, Any] | None,
    until: datetime | None,
) -> dict[str, Any]:
    in_at = parse_dt(inn.get("occurred_at"))
    out_at = parse_dt(out.get("occurred_at")) if out else None
    end = out_at or until
    minutes = 0
    if in_at and end and end > in_at:
        minutes = int((end - in_at).total_seconds() // 60)
    return {
        "in_at": inn.get("occurred_at"),
        "out_at": out.get("occurred_at") if out else None,
        "open": out is None,
        "minutes": minutes,
        "in_lat": inn.get("lat"),
        "in_lng": inn.get("lng"),
        "out_lat": out.get("lat") if out else None,
        "out_lng": out.get("lng") if out else None,
    }


def minutes_to_hours_label(minutes: int) -> str:
    h, m = divmod(max(0, minutes), 60)
    if h and m:
        return f"{h}시간 {m}분"
    if h:
        return f"{h}시간"
    return f"{m}분"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
