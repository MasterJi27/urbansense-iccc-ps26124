"""Geospatial helpers. Distance math is application-layer so fusion tests run without PostGIS."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def validate_coords(lat: float, lon: float) -> None:
    if lat < -90 or lat > 90:
        raise ValueError("latitude must be between -90 and 90")
    if lon < -180 or lon > 180:
        raise ValueError("longitude must be between -180 and 180")


def bounding_box(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """Axis-aligned prefilter. Haversine still decides the real distance."""
    meters_per_deg_lat = 111_320.0
    dlat = radius_m / meters_per_deg_lat
    cos_lat = max(abs(math.cos(math.radians(lat))), 0.01)
    dlon = radius_m / (meters_per_deg_lat * cos_lat)
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
