"""Azure Maps tile proxy. Key stays on the server. Leaflet still draws the map."""

from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.config import get_settings
from app.deps import get_current_user
from app.models.user import User
from app.services.map_tickets import issue_map_ticket, verify_map_ticket
from app.services.rate_limit import client_ip, enforce

router = APIRouter(prefix="/maps", tags=["maps"])


def maps_enabled() -> bool:
    return bool(get_settings().azure_maps_subscription_key.strip())


@router.get("/config")
def maps_config(user: User = Depends(get_current_user)):
    on = maps_enabled()
    ticket = issue_map_ticket(user.id) if on else None
    return {
        "enabled": on,
        "provider": "Azure Maps" if on else "OpenStreetMap",
        "honesty": "REAL" if on else "RULE_BASED",
        "note": "Azure Maps road tiles via server proxy. Ticket is not the subscription key. OSM if the key is missing.",
        "tile_url": f"/maps/tiles/{{z}}/{{x}}/{{y}}.png?ticket={ticket}" if ticket else None,
    }


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
    key = get_settings().azure_maps_subscription_key.strip()
    if not key:
        raise HTTPException(status_code=404, detail="Azure Maps key not configured")
    if not (0 <= z <= 22 and x >= 0 and y >= 0):
        raise HTTPException(status_code=400, detail="bad tile")
    upstream = (
        "https://atlas.microsoft.com/map/tile"
        f"?api-version=2.1&tilesetId=microsoft.base.road&zoom={z}&x={x}&y={y}&subscription-key={key}"
    )
    req = UrlRequest(upstream, headers={"User-Agent": "UrbanSense-ICCC/1.0"})
    try:
        with urlopen(req, timeout=12) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "image/png")
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Azure Maps tile {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail="Azure Maps unreachable") from exc
    return Response(
        content=data,
        media_type=ctype.split(";")[0] or "image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
