"""Officer ping via Composio when a second bus confirms. Not a vision API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("urbansense.composio")
EXECUTE_URL = "https://backend.composio.dev/api/v3/tools/execute"


def composio_status() -> dict[str, Any]:
    settings = get_settings()
    key = (settings.composio_api_key or "").strip()
    dest = (settings.composio_notify_to or "").strip()
    if not key:
        return {
            "honesty": "DISABLED",
            "ai_status": "DISABLED",
            "provider": "Composio",
            "note": "COMPOSIO_API_KEY not set. Fleet confirm still saves. No officer ping.",
        }
    if not dest:
        return {
            "honesty": "DISABLED",
            "ai_status": "DISABLED",
            "provider": "Composio",
            "note": "COMPOSIO_NOTIFY_TO not set.",
        }
    return {
        "honesty": "REAL",
        "ai_status": "REAL",
        "provider": "Composio",
        "channel": settings.composio_notify_channel,
        "note": "Ping on FLEET_CONFIRMED only. Trigger is RULE_BASED fusion. Not used for YOLO.",
    }


def _tool_and_args(settings, *, subject: str, body: str) -> tuple[str, dict[str, Any]]:
    channel = (settings.composio_notify_channel or "gmail").strip().lower()
    dest = settings.composio_notify_to.strip()
    if channel == "whatsapp":
        return "WHATSAPP_SEND_MESSAGE", {"to": dest, "message": f"{subject}\n{body}"}
    if channel == "slack":
        return "SLACK_SENDS_A_MESSAGE", {"channel": dest, "text": f"{subject}\n{body}"}
    return "GMAIL_SEND_EMAIL", {"recipient_email": dest, "subject": subject, "body": body}


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
    payload = {
        "user_id": (settings.composio_entity_id or "default").strip() or "default",
        "arguments": arguments,
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            res = client.post(
                f"{EXECUTE_URL}/{tool}",
                headers={"x-api-key": settings.composio_api_key.strip(), "Content-Type": "application/json"},
                json=payload,
            )
        if res.status_code >= 400:
            log.warning("composio %s failed %s %s", tool, res.status_code, res.text[:300])
            return {"honesty": "DISABLED", "ok": False, "status_code": res.status_code}
        return {"honesty": "REAL", "ok": True, "tool": tool}
    except Exception:
        log.exception("composio ping skipped")
        return {"honesty": "DISABLED", "ok": False}
