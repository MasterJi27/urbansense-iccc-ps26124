"""Short-lived HMAC tickets for Leaflet <img> tiles. Not the Azure Maps key."""

from __future__ import annotations

import hashlib
import hmac
import time
from uuid import uuid4

from app.config import get_settings

TICKET_TTL_SECONDS = 20 * 60


def _secret() -> bytes:
    return get_settings().secret_key.encode()


def issue_map_ticket(user_id: str, ttl: int = TICKET_TTL_SECONDS) -> str:
    exp = int(time.time()) + max(60, ttl)
    nonce = uuid4().hex[:12]
    body = f"{user_id}.{exp}.{nonce}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{body}.{sig}"


def verify_map_ticket(ticket: str) -> str:
    raw = (ticket or "").strip()
    parts = raw.split(".")
    if len(parts) != 4:
        raise ValueError("invalid map ticket")
    user_id, exp_s, nonce, sig = parts
    if not user_id or not nonce or len(sig) < 20:
        raise ValueError("invalid map ticket")
    try:
        exp = int(exp_s)
    except ValueError as exc:
        raise ValueError("invalid map ticket") from exc
    if exp < int(time.time()):
        raise ValueError("map ticket expired")
    body = f"{user_id}.{exp_s}.{nonce}"
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("invalid map ticket")
    return user_id
