"""Serve the ICCC SPA for browser tab loads that collide with API paths."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse
from starlette.requests import Request

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "static_dash"

_SKIP_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/ui/",
    "/evidence/",
    "/maps/",
    "/ws/",
)


def is_browser_document(request: Request) -> bool:
    dest = (request.headers.get("sec-fetch-dest") or "").lower()
    mode = (request.headers.get("sec-fetch-mode") or "").lower()
    return dest == "document" and mode in {"navigate", "nested-navigate"}


def should_serve_spa(request: Request) -> bool:
    if request.method != "GET" or not is_browser_document(request):
        return False
    path = request.url.path
    if path == "/health" or any(path == p or path.startswith(p) for p in _SKIP_PREFIXES):
        return False
    return (DASHBOARD_DIR / "index.html").is_file()


SPA_HEADERS = {
    "Cache-Control": "no-store",
    "Vary": "Accept, Sec-Fetch-Dest, Sec-Fetch-Mode",
}

HIDDEN_WHEN_NOT_DEV = frozenset({"docs", "redoc", "openapi.json"})


def is_hidden_api_surface(path: str) -> bool:
    return path.strip("/").lower() in HIDDEN_WHEN_NOT_DEV


def spa_index() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html", headers=SPA_HEADERS)
