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
