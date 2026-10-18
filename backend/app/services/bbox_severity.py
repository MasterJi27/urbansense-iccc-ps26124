"""RoadGuardian-style severity from box area. RULE_BASED, not depth."""

from __future__ import annotations

from app.models.event import Severity

# Fraction of the frame covered by the largest damage box.
_HIGH = 0.12
_MEDIUM = 0.05


def _xyxy(box) -> tuple[float, float, float, float] | None:
    if box is None:
        return None
    if isinstance(box, dict):
        if {"x1", "y1", "x2", "y2"} <= set(box):
            return float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"])
        if {"x", "y", "w", "h"} <= set(box):
            x, y, w, h = float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"])
            return x, y, x + w, y + h
        return None
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        return float(box[0]), float(box[1]), float(box[2]), float(box[3])
    return None


def box_fraction(box, frame_w: float = 640.0, frame_h: float = 640.0) -> float:
    parsed = _xyxy(box)
    if parsed is None:
        return 0.0
    x1, y1, x2, y2 = parsed
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    denom = max(1.0, float(frame_w) * float(frame_h))
    return min(1.0, area / denom)


def severity_from_boxes(
    boxes: list | None,
    *,
    frame_w: float = 640.0,
    frame_h: float = 640.0,
) -> dict:
    fracs = [box_fraction(b, frame_w, frame_h) for b in (boxes or [])]
    frac = max(fracs) if fracs else 0.0
    if frac >= _HIGH:
        sev = Severity.HIGH
    elif frac >= _MEDIUM:
        sev = Severity.MEDIUM
    else:
        sev = Severity.LOW
    return {
        "severity": sev,
        "bbox_frac": round(frac, 4),
        "bbox_count": len(fracs),
        "honesty": "RULE_BASED",
        "method": "bbox-area",
        "note": "Largest box / frame. Not stereo depth. Never CRITICAL from area alone.",
    }


def severity_for_detection(det: dict) -> dict:
    """One rule for every RDD route: the top detection's box area sets severity.

    Area alone is monotonic, so a bigger box is never graded below a smaller one. The class default
    (pothole = HIGH, crack = MEDIUM) is only the answer when the detection carries no usable box; mixing it
    in below a threshold made a 1% pothole HIGH while an 8% one was MEDIUM.
    """
    box = det.get("bbox")
    graded = severity_from_boxes([box], frame_w=1, frame_h=1)
    if box_fraction(box, 1, 1) > 0:  # unrounded: bbox_frac rounds a sliver of a box down to 0
        return graded
    try:
        fallback = Severity(det.get("severity"))
    except ValueError:
        fallback = Severity.MEDIUM
    return {**graded, "severity": fallback, "method": "class-default", "note": "No usable box. Class default severity."}
