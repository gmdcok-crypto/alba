"""관리자 태블릿·폰에 띄울 출근 QR."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.database import Connection, get_db
from backend.deps import get_current_user
from backend.kiosk_qr import mint_kiosk_qr_payload

router = APIRouter(prefix="/kiosk", tags=["kiosk"])


@router.get("/attendance-qr")
def get_attendance_qr(
    store_id: int,
    user: dict = Depends(get_current_user),
    conn: Connection = Depends(get_db),
) -> dict:
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="사장님 계정만 QR을 표시할 수 있습니다.")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name FROM stores WHERE id = %s AND owner_id = %s LIMIT 1",
        (store_id, user["id"]),
    )
    store = cur.fetchone()
    if not store:
        raise HTTPException(status_code=403, detail="이 매장의 사장님만 가능합니다.")
    payload = mint_kiosk_qr_payload(store_id)
    payload["store_name"] = str(store["name"])
    return payload
