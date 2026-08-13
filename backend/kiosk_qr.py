"""매장 출근 QR 페이로드 서명·검증 (비밀은 서버에만 존재)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException


def _secret_bytes() -> bytes:
    raw = (os.getenv("KIOSK_QR_SECRET") or os.getenv("JWT_SECRET") or "").strip()
    if not raw:
        raw = "alba-dev-only-insecure-jwt-secret-change-in-production"
    return raw.encode("utf-8")


def mint_kiosk_qr_payload(store_id: int) -> dict[str, int | str]:
    exp = int(time.time()) + 45
    nonce = secrets.token_hex(10)
    v = 1
    kind = "alba-kiosk"
    msg = f"{v}|{kind}|{store_id}|{nonce}|{exp}"
    sig = hmac.new(_secret_bytes(), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"v": v, "kind": kind, "store_id": store_id, "nonce": nonce, "exp": exp, "sig": sig}


def verify_kiosk_qr_payload(raw: dict) -> int:
    if raw.get("v") != 1 or raw.get("kind") != "alba-kiosk":
        raise HTTPException(status_code=400, detail="유효하지 않은 출근 QR입니다.")
    exp = raw.get("exp")
    nonce = raw.get("nonce")
    sig = raw.get("sig")
    store_id = raw.get("store_id")
    try:
        store_i = int(store_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="QR 형식이 올바르지 않습니다.") from None
    if not isinstance(exp, int) or not isinstance(nonce, str) or not isinstance(sig, str):
        raise HTTPException(status_code=400, detail="QR 형식이 올바르지 않습니다.")
    if exp < int(time.time()):
        raise HTTPException(status_code=400, detail="만료된 QR입니다. 매장 화면의 코드를 다시 스캔하세요.")
    msg = f"1|alba-kiosk|{store_i}|{nonce}|{exp}"
    expect = hmac.new(_secret_bytes(), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        raise HTTPException(status_code=400, detail="QR 서명이 유효하지 않습니다.")
    return store_i
