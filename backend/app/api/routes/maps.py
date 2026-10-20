"""Map tile proxy. The provider key stays on the server. Leaflet still draws the map.

The provider is a custom MAP_TILE_URL, else Azure Maps (key), else none: then the browser draws OpenStreetMap itself.
"""

from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.deps import get_current_user
from app.models.user import User
from app.services.map_tickets import issue_map_ticket, verify_map_ticket
from app.services.map_tiles import tile_source, upstream_url
from app.services.place import reverse_place
from app.services.rate_limit import client_ip, enforce

router = APIRouter(prefix="/maps", tags=["maps"])

MAX_TILE_BYTES = 1_500_000


def maps_enabled() -> bool:
    return tile_source().kind != "none"


@router.get("/config")
def maps_config(user: User = Depends(get_current_user)):
    src = tile_source()
    on = src.kind != "none"
    ticket = issue_map_ticket(user.id) if on else None
    if src.kind == "custom":
        note = f"Tiles from {src.provider} via server proxy. The key in MAP_TILE_URL stays on the server."
    else:
        note = "Azure Maps road tiles via server proxy. Ticket is not the subscription key. OSM if the key is missing."
    if src.problem:
        note += f" MAP_TILE_URL was ignored: it {src.problem}."
    return {
        "enabled": on,
        "provider": src.provider,
        "honesty": "REAL" if on else "RULE_BASED",
        "note": note,
        "tile_url": f"/maps/tiles/{{z}}/{{x}}/{{y}}.png?ticket={ticket}" if ticket else None,
        "attribution": src.attribution if on else None,
    }


@router.get("/place")
def maps_place(
    lat: float = Query(...),
    lon: float = Query(...),
    user: User = Depends(get_current_user),
):
    del user
    return reverse_place(lat, lon)


@router.get("/tiles/{z}/{x}/{y}.png")
def maps_tile(
    z: int,
    x: int,
    y: int,
    request: Request,
    ticket: str = Query(default=""),
):
    try:
        holder = verify_map_ticket(ticket)
    except ValueError:
        raise HTTPException(status_code=401, detail="Map ticket required") from None
    enforce(f"maps:{holder}:{client_ip(request)}", limit=180, window_s=60)
    src = tile_source()
    if src.kind == "none":
        raise HTTPException(status_code=404, detail="No map tile provider configured")
    if not (0 <= z <= 22 and x >= 0 and y >= 0):
        raise HTTPException(status_code=400, detail="bad tile")
    req = UrlRequest(upstream_url(src, z, x, y), headers={"User-Agent": "SadakSaarthi-ICCC/1.0"})
    try:
        with urlopen(req, timeout=12) as resp:
            data = resp.read(MAX_TILE_BYTES + 1)
            ctype = resp.headers.get("Content-Type", "image/png")
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"{src.provider} tile {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"{src.provider} unreachable") from exc
    media_type = (ctype.split(";")[0] or "image/png").strip().lower()
    if len(data) > MAX_TILE_BYTES:
        raise HTTPException(status_code=502, detail=f"{src.provider} tile too large")
    if not media_type.startswith("image/"):
        raise HTTPException(status_code=502, detail=f"{src.provider} did not return an image")
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
