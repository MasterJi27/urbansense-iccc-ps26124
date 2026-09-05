"""HMAC claim tokens so a citizen can see only their own reports."""

from __future__ import annotations

import hashlib
import hmac
import time

from app.config import get_settings

CLAIM_TTL_SECONDS = 30 * 24 * 3600
_MAX_EVENTS = 20


def _secret() -> bytes:
    return get_settings().secret_key.encode()


def issue_citizen_claim(event_ids: list[str]) -> str:
    ids = [eid for eid in event_ids if eid][:_MAX_EVENTS]
    exp = int(time.time()) + CLAIM_TTL_SECONDS
    body = f"{','.join(ids)}.{exp}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{body}.{sig}"


def read_citizen_claim(token: str) -> list[str]:
    raw = (token or "").strip()
    if raw.count(".") < 2:
        raise ValueError("invalid citizen claim")
    body, sig = raw.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("invalid citizen claim")
    try:
        ids_part, exp_s = body.rsplit(".", 1)
        exp = int(exp_s)
    except ValueError as exc:
        raise ValueError("invalid citizen claim") from exc
    if exp < int(time.time()):
        raise ValueError("citizen claim expired")
    return [part for part in ids_part.split(",") if part][:_MAX_EVENTS]


def merge_citizen_claim(previous: str | None, event_id: str) -> str:
    ids: list[str] = []
    if previous:
        try:
            ids = read_citizen_claim(previous)
        except ValueError:
            ids = []
    if event_id not in ids:
        ids.append(event_id)
    return issue_citizen_claim(ids)
