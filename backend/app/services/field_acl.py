"""Field-booth JWT may ingest stills. It may not open ICCC desks."""

from __future__ import annotations

FIELD_EXACT = {
    ("GET", "/auth/me"),
    ("GET", "/maps/config"),
    ("GET", "/maps/place"),
    ("GET", "/health"),
    ("POST", "/ingest/phone"),
    ("POST", "/ingest/phone/still"),
    ("POST", "/ingest/phone/probe"),
    ("POST", "/ingest/cctv/still"),
    ("POST", "/ai/analyze-frame"),
    ("GET", "/ai/capabilities"),
    ("GET", "/cameras"),
    ("GET", "/cameras/presets"),
    ("POST", "/cameras"),
    ("POST", "/sensor-nodes/heartbeat"),
}


def field_path_allowed(method: str, path: str) -> bool:
    verb = method.upper()
    if (verb, path) in FIELD_EXACT:
        return True
    if verb == "GET" and path.startswith("/evidence/"):
        return True
    if verb == "GET" and path.startswith("/maps/tiles/"):
        return True
    if verb == "GET" and path.startswith("/events/"):
        rest = path[len("/events/") :]
        if not rest or "/" in rest:
            return False
        return True
    return False
