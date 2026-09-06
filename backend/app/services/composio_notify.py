"""Officer ping via Composio when a second bus confirms. Not a vision API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("urbansense.composio")
EXECUTE_URL = "https://backend.composio.dev/api/v3/tools/execute"

_LAST: dict[str, Any] = {"ok": None, "error": None, "at": None, "status_code": None}


def last_notify() -> dict[str, Any]:
    return dict(_LAST)


def reset_last_notify() -> None:
    _LAST.update({"ok": None, "error": None, "at": None, "status_code": None})


def _mask_email(addr: str) -> str:
    raw = (addr or "").strip()
    if "@" not in raw:
        return ""
    local, _, domain = raw.partition("@")
    if not local or not domain:
        return ""
    return f"{local[0]}***@{domain}"


def _record(ok: bool, *, error: str | None = None, status_code: int | None = None) -> None:
    _LAST["ok"] = ok
    _LAST["error"] = (error or "").strip()[:280] or None
    _LAST["status_code"] = status_code
    _LAST["at"] = datetime.now(timezone.utc).isoformat()


def composio_status() -> dict[str, Any]:
    settings = get_settings()
    key = (settings.composio_api_key or "").strip()
    dest = (settings.composio_notify_to or "").strip()
    acct = (settings.composio_connected_account_id or "").strip()
    if not key:
        return {
            "honesty": "DISABLED",
            "ai_status": "DISABLED",
            "provider": "Composio",
            "note": "COMPOSIO_API_KEY not set. Fleet confirm still saves. No officer ping.",
            "last_ok": _LAST["ok"],
            "last_error": _LAST["error"],
        }
    if not dest:
        return {
            "honesty": "DISABLED",
            "ai_status": "DISABLED",
            "provider": "Composio",
            "note": "COMPOSIO_NOTIFY_TO not set.",
            "last_ok": _LAST["ok"],
            "last_error": _LAST["error"],
        }
    note = "Ping on FLEET_CONFIRMED only. Trigger is RULE_BASED fusion. Not used for YOLO."
    if not acct:
        note = "COMPOSIO_CONNECTED_ACCOUNT_ID not set; Gmail OAuth may not be on user_id=default. " + note
    if _LAST["error"]:
        note = f"Last ping failed: {_LAST['error']}. {note}"
    elif _LAST["ok"] is True:
        note = f"Last ping delivered. {note}"
    return {
        "honesty": "REAL",
        "ai_status": "REAL",
        "provider": "Composio",
        "channel": settings.composio_notify_channel,
        "notify_to": _mask_email(dest),
        "connected_account_set": bool(acct),
        "last_ok": _LAST["ok"],
        "last_error": _LAST["error"],
        "note": note,
    }


def _tool_and_args(settings, *, subject: str, body: str) -> tuple[str, dict[str, Any]]:
    channel = (settings.composio_notify_channel or "gmail").strip().lower()
    dest = settings.composio_notify_to.strip()
    if channel == "whatsapp":
        return "WHATSAPP_SEND_MESSAGE", {"to": dest, "message": f"{subject}\n{body}"}
    if channel == "slack":
        return "SLACK_SENDS_A_MESSAGE", {"channel": dest, "text": f"{subject}\n{body}"}
    return "GMAIL_SEND_EMAIL", {"recipient_email": dest, "subject": subject, "body": body}


def _execute_payload(settings, arguments: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"arguments": arguments}
    acct = (settings.composio_connected_account_id or "").strip()
    uid = (settings.composio_entity_id or "").strip()
    if acct:
        payload["connected_account_id"] = acct
    elif uid:
        payload["user_id"] = uid
    else:
        payload["user_id"] = "default"
    return payload


def _error_text(res: httpx.Response) -> str:
    snippet = (res.text or "")[:300]
    try:
        data = res.json()
    except Exception:
        return snippet or f"HTTP {res.status_code}"
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("slug") or snippet or f"HTTP {res.status_code}")
    if err:
        return str(err)
    if data.get("successful") is False:
        return snippet or "Composio returned unsuccessful"
    return snippet or f"HTTP {res.status_code}"


def notify_fleet_confirmed(event) -> dict[str, Any]:
    """Fail closed. Never raises into fusion."""
    status = composio_status()
    if status["honesty"] != "REAL":
        return status
    settings = get_settings()
    public = getattr(event, "public_code", "") or "EVENT"
    kind = getattr(event, "event_type", None)
    kind_s = kind.value if hasattr(kind, "value") else str(kind or "")
    extra = getattr(event, "extra", None) or {}
    base = (settings.public_base_url or "").rstrip("/")
    link = f"{base}/events/{getattr(event, 'id', '')}" if base else ""
    subject = f"SadakSaarthi fleet confirm {public}"
    body = (
        f"{public} · {kind_s} · FLEET_CONFIRMED\n"
        f"Second independent bus in 40 m / 6 h. Not inspector ground truth.\n"
        f"{link}\n"
        f"Ward/bus: {extra.get('patrol_note') or ''}"
    )
    tool, arguments = _tool_and_args(settings, subject=subject, body=body)
    payload = _execute_payload(settings, arguments)
    try:
        with httpx.Client(timeout=8.0) as client:
            res = client.post(
                f"{EXECUTE_URL}/{tool}",
                headers={"x-api-key": settings.composio_api_key.strip(), "Content-Type": "application/json"},
                json=payload,
            )
        data: dict[str, Any] = {}
        try:
            parsed = res.json()
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = {}
        if res.status_code >= 400 or data.get("successful") is False:
            err = _error_text(res)
            log.warning("composio %s failed %s %s", tool, res.status_code, err)
            _record(False, error=err, status_code=res.status_code)
            return {"honesty": "DISABLED", "ok": False, "status_code": res.status_code, "error": err}
        _record(True, status_code=res.status_code)
        return {"honesty": "REAL", "ok": True, "tool": tool}
    except Exception as exc:
        log.exception("composio ping skipped")
        _record(False, error=f"{type(exc).__name__}: {exc}"[:280])
        return {"honesty": "DISABLED", "ok": False}
