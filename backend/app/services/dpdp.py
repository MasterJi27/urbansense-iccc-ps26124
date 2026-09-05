"""Server-side DPDP masking. Client hide is not authorization."""

from __future__ import annotations

from typing import Any

from app.models.user import User, UserRole

_PLATE_KEYS = ("plate_text",)
_CONTACT_KEYS = ("citizen_contact", "contact")


def iccc_desk(user: User | None) -> bool:
    if user is None:
        return False
    if getattr(user, "auth_scope", "iccc") == "field":
        return False
    return user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.INSPECTOR}


def mask_plate(text: str | None) -> str | None:
    if not text:
        return text
    raw = "".join(ch for ch in text if ch.isalnum())
    if len(raw) <= 4:
        return "••••"
    return f"{raw[:4]}••••"


def mask_contact(text: str | None) -> str | None:
    if not text:
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        return f"••••{digits[-4:]}"
    if len(text) <= 2:
        return "••"
    return f"{text[0]}•••"


def _scrub_extra(extra: dict | None, *, reveal: bool) -> dict | None:
    if not extra:
        return extra
    out = dict(extra)
    if not reveal:
        for key in _CONTACT_KEYS:
            if out.get(key):
                out[key] = mask_contact(str(out[key]))
        if out.get("citizen_qr_payload"):
            out["citizen_qr_payload"] = "[redacted]"
    return out


def sanitize_observation(data: dict[str, Any], user: User | None) -> dict[str, Any]:
    out = dict(data)
    reveal = iccc_desk(user)
    if not reveal and out.get("plate_text"):
        out["plate_text"] = mask_plate(str(out["plate_text"]))
    if "extra" in out:
        out["extra"] = _scrub_extra(out.get("extra"), reveal=reveal)
    return out


def sanitize_event(data: dict[str, Any], user: User | None) -> dict[str, Any]:
    out = dict(data)
    reveal = iccc_desk(user)
    extra = out.get("extra")
    if isinstance(extra, dict):
        out["extra"] = _scrub_extra(extra, reveal=reveal)
        if not reveal and out["extra"].get("plate_text"):
            out["extra"]["plate_text"] = mask_plate(str(out["extra"]["plate_text"]))
    obs = out.get("observations")
    if isinstance(obs, list):
        out["observations"] = [
            sanitize_observation(row, user) if isinstance(row, dict) else row for row in obs
        ]
    return out
