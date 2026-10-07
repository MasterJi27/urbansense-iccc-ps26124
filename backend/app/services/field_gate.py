"""Phone still gates. A bad fix or a known breaker does not become a pothole ticket."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.geo import bounding_box, haversine_m
from app.models.asset import Asset

GPS_MAX_M = 25.0
BREAKER_RADIUS_M = 25.0


def gps_block_reason(accuracy: float | None) -> str | None:
    if accuracy is None:
        return "GPS accuracy required"
    try:
        meters = float(accuracy)
    except (TypeError, ValueError):
        return "GPS accuracy required"
    if meters > GPS_MAX_M:
        return f"GPS accuracy {meters:.0f} m is worse than {GPS_MAX_M:.0f} m"
    return None


def _is_breaker(asset: Asset) -> bool:
    code = (asset.code or "").upper()
    name = (asset.name or "").upper()
    return code.startswith("BRK") or code.startswith("BREAKER") or "SPEED BREAKER" in name or "SPEED-BREAKER" in name


def speed_breaker_code(db: Session, lat: float, lon: float) -> str | None:
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, BREAKER_RADIUS_M)
    rows = (
        db.query(Asset)
        .filter(
            Asset.latitude >= min_lat,
            Asset.latitude <= max_lat,
            Asset.longitude >= min_lon,
            Asset.longitude <= max_lon,
        )
        .all()
    )
    nearest: tuple[float, str] | None = None
    for asset in rows:
        if not _is_breaker(asset):
            continue
        dist = haversine_m(lat, lon, asset.latitude, asset.longitude)
        if dist > BREAKER_RADIUS_M:
            continue
        if nearest is None or dist < nearest[0]:
            nearest = (dist, asset.code)
    return nearest[1] if nearest else None


def corridor_block_reason(lat: float, lon: float) -> str | None:
    settings = get_settings()
    radius = float(settings.demo_corridor_radius_m or 0)
    if radius <= 0:
        return None
    dist = haversine_m(lat, lon, settings.demo_corridor_lat, settings.demo_corridor_lon)
    if dist > radius:
        return "Outside the demo corridor. Still not filed."
    return None
