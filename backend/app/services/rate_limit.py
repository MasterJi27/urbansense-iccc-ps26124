"""In-process sliding window. One App Service worker is enough for the jury host."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


class SlidingWindow:
    def __init__(self) -> None:
        self._lock = Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def hit(self, key: str, limit: int, window_s: float) -> tuple[bool, int]:
        now = monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - window_s
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, int(window_s - (now - q[0])) + 1)
                return False, retry
            q.append(now)
            return True, 0


limiter = SlidingWindow()


class FailureGate:
    """Consecutive failures lock an identity. Separate from the sliding IP window."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._fails: dict[str, deque[float]] = defaultdict(deque)
        self._until: dict[str, float] = {}

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._until.clear()

    def check(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            until = self._until.get(key, 0.0)
            if until > now:
                retry = max(1, int(until - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Temporarily locked after repeated failures.",
                    headers={"Retry-After": str(retry)},
                )

    def fail(self, key: str, *, limit: int = 5, window_s: float = 900, lock_s: float = 900) -> None:
        now = monotonic()
        with self._lock:
            queue = self._fails[key]
            cutoff = now - window_s
            while queue and queue[0] <= cutoff:
                queue.popleft()
            queue.append(now)
            if len(queue) >= limit:
                self._until[key] = now + lock_s

    def ok(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._until.pop(key, None)


gate = FailureGate()


def reset_limits() -> None:
    limiter.reset()
    gate.reset()


def client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce(key: str, *, limit: int, window_s: float) -> None:
    ok, retry = limiter.hit(key, limit, window_s)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Wait and retry.",
            headers={"Retry-After": str(retry)},
        )
