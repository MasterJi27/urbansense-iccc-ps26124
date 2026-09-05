"""Rule-based traffic analytics. Not trained models."""

from __future__ import annotations

from urbansense_ai.engines import Track
from urbansense_ai.status import RULE_BASED


def classify_los(num_vehicles: int, avg_speed_kmh: float | None, roi_area_m2: float = 300.0) -> tuple[str, str]:
    """Highway Capacity Manual-style LOS buckets (rule table)."""
    if avg_speed_kmh is None or num_vehicles == 0:
        return "A", "Free flow / insufficient data"
    density = num_vehicles / max(roi_area_m2, 1.0) * 1000.0
    if avg_speed_kmh > 50 and density < 5:
        return "A", "Free flow"
    if avg_speed_kmh > 40 and density < 10:
        return "B", "Reasonable free flow"
    if avg_speed_kmh > 30 and density < 18:
        return "C", "Stable flow"
    if avg_speed_kmh > 20 and density < 26:
        return "D", "Approaching unstable"
    if avg_speed_kmh > 10 and density < 40:
        return "E", "Unstable / at capacity"
    return "F", "Forced flow / jam"


def congestion_should_emit(los: str, persist_frames: int, need: int = 8) -> bool:
    return los in {"E", "F"} and persist_frames >= need


def rash_driving(speed_kmh: float | None, speed_limit: float = 60.0) -> bool:
    return speed_kmh is not None and speed_kmh > speed_limit * 1.35


def pedestrian_risk(tracks: list[Track]) -> tuple[bool, float]:
    """Proximity of person vs vehicle boxes. RULE_BASED."""
    people = [t for t in tracks if t.klass == "person" and t.bbox]
    vehicles = [t for t in tracks if t.klass != "person" and t.bbox]
    best = 0.0
    hit = False
    for p in people:
        px1, py1, px2, py2 = p.bbox
        pcx, pcy = (px1 + px2) / 2, (py1 + py2) / 2
        for v in vehicles:
            vx1, vy1, vx2, vy2 = v.bbox
            vcx, vcy = (vx1 + vx2) / 2, (vy1 + vy2) / 2
            dist = ((pcx - vcx) ** 2 + (pcy - vcy) ** 2) ** 0.5
            if dist < 0.12:
                hit = True
                best = max(best, 1.0 - dist / 0.12)
    return hit, best


def default_analytics_meta() -> dict:
    return {"ai_status": RULE_BASED}
