"""Bound observation extras so a client cannot store a secret dump or a 2 MB JSON blob."""

from __future__ import annotations

from typing import Any

_MAX_KEYS = 80
_MAX_KEY = 80
_MAX_STR = 4000
_MAX_LIST = 64
_MAX_DEPTH = 4
_DROP_KEYS = {
    "password",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "apikey",
    "subscription-key",
    "subscription_key",
    "azure_maps_subscription_key",
    "database_url",
    "connection_string",
}


def sanitize_extra(extra: Any, *, depth: int = 0) -> dict[str, Any] | None:
    if extra is None:
        return None
    if not isinstance(extra, dict):
        return None
    return _clip_dict(extra, depth)


def _clip_value(value: Any, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return float(value)
    if not isinstance(value, (str, bytes, dict, list, tuple)) and hasattr(value, "item"):
        try:
            return _clip_value(value.item(), depth)
        except Exception:
            return None
    if isinstance(value, str):
        return value[:_MAX_STR]
    if isinstance(value, dict):
        return _clip_dict(value, depth)
    if isinstance(value, (list, tuple)):
        return [_clip_value(item, depth + 1) for item in list(value)[:_MAX_LIST]]
    return None


def _clip_dict(extra: dict[str, Any], depth: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in extra.items():
        if len(out) >= _MAX_KEYS:
            break
        if not isinstance(key, str) or not key or len(key) > _MAX_KEY:
            continue
        if key.strip().lower() in _DROP_KEYS:
            continue
        clipped = _clip_value(value, depth + 1)
        if clipped is not None or value is None or isinstance(value, bool):
            out[key] = clipped
    return out
