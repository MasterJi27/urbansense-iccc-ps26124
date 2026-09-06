"""Short-lived ICCC field-booth PIN. One active booth; up to 4 phones until expiry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import randbelow
from threading import Lock

TTL_SECONDS = 15 * 60
MAX_JOINS = 4


@dataclass
class FieldBooth:
    code: str
    user_id: str
    role: str
    full_name: str
    expires_at: datetime
    bus_code: str
    joins: int = 0
    max_joins: int = MAX_JOINS

    @property
    def expires_in(self) -> int:
        remaining = int((self.expires_at - datetime.now(timezone.utc)).total_seconds())
        return max(0, remaining)

    @property
    def redeemed(self) -> bool:
        return self.joins >= self.max_joins

    def is_live(self) -> bool:
        return self.expires_in > 0


_lock = Lock()
_booth: FieldBooth | None = None


def reset_booth() -> None:
    global _booth
    with _lock:
        _booth = None


def current_booth() -> FieldBooth | None:
    with _lock:
        if _booth is None or not _booth.is_live():
            return None
        return _booth


def issue_booth(*, user_id: str, role: str, full_name: str, bus_code: str) -> FieldBooth:
    global _booth
    booth = FieldBooth(
        code=f"{randbelow(1_000_000):06d}",
        user_id=user_id,
        role=role,
        full_name=full_name,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=TTL_SECONDS),
        bus_code=bus_code,
    )
    with _lock:
        _booth = booth
    return booth


def redeem_booth(code: str) -> FieldBooth:
    cleaned = "".join(ch for ch in (code or "") if ch.isdigit())
    with _lock:
        booth = _booth
        if booth is None or not booth.expires_in or booth.joins >= booth.max_joins or booth.code != cleaned:
            raise ValueError("invalid or expired field booth code")
        booth.joins += 1
        return booth
