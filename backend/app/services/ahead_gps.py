"""RULE_BASED pin: defect is ahead of the windshield, not under the phone GPS."""

from __future__ import annotations

from typing import Any

from app.geo import offset_by_heading, validate_coords


def ahead_meters_from_bbox(bbox: list[float] | None) -> float:
    if not bbox or len(bbox) < 4:
        return 18.0
    y2 = max(0.0, min(1.0, float(bbox[3])))
    height = max(0.0, float(bbox[3]) - float(bbox[1]))
    near, far = 8.0, 55.0
    lo, hi = 0.42, 0.96
    t = (hi - max(lo, min(hi, y2))) / (hi - lo)
    meters = near + t * (far - near)
    if height < 0.07:
        meters = min(70.0, meters + 12.0)
    return round(meters, 1)


def project_ahead(
    latitude: float,
    longitude: float,
    heading: float | None,
    bbox: list[float] | None,
) -> dict[str, Any]:
    validate_coords(latitude, longitude)
    if heading is None:
        return {
            "used": False,
            "latitude": latitude,
            "longitude": longitude,
            "ahead_m": 0,
            "honesty": "RULE_BASED",
            "note": "No heading. Pin stays on the phone GPS.",
        }
    meters = ahead_meters_from_bbox(bbox)
    plat, plon = offset_by_heading(latitude, longitude, heading, meters)
    return {
        "used": True,
        "latitude": plat,
        "longitude": plon,
        "phone_latitude": latitude,
        "phone_longitude": longitude,
        "ahead_m": meters,
        "heading": heading,
        "honesty": "RULE_BASED",
        "note": "Pin walked along heading from box height. Not stereo depth.",
    }
