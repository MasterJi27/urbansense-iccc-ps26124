"""Plate OCR + temporal voting. Indian format check is separate from generic OCR.

Inspired by the MIT ANPR repo's temporal-voting idea (reimplemented, no Turkish parser).
Fallback OCR: Tesseract (simple ANPR repo pattern) then simulated.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque

from urbansense_ai.engines import Detection, PlateRead
from urbansense_ai.status import REAL, RULE_BASED, SIMULATED
from urbansense_ai.weights import resolve_plate

# Common Indian registration pattern (approximate). Not a legal validator.
INDIAN_PLATE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")


def normalize_plate(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def indian_format_ok(text: str) -> bool:
    return bool(INDIAN_PLATE.match(normalize_plate(text)))


class TemporalVoter:
    def __init__(self, window: int = 8, min_dwell: int = 3) -> None:
        self._hist: dict[str, deque[tuple[str, float]]] = defaultdict(lambda: deque(maxlen=window))
        self._min = min_dwell

    def observe(self, track_id: str, text: str, confidence: float) -> str | None:
        key = normalize_plate(text)
        if not key:
            return None
        h = self._hist[track_id]
        h.append((key, confidence))
        if len(h) < self._min:
            return None
        counts: dict[str, float] = defaultdict(float)
        for t, c in h:
            counts[t] += c
        return max(counts, key=counts.get)


class TesseractOCR:
    def __init__(self) -> None:
        self.ok = False
        try:
            import pytesseract  # noqa: F401

            self.ok = True
        except Exception:
            self.ok = False

    def read_plate(self, crop) -> PlateRead:
        if not self.ok or crop is None:
            return PlateRead(plate="", confidence=0.0, simulated=True, ai_status=SIMULATED)
        try:
            import pytesseract
            import cv2

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
            text = pytesseract.image_to_string(gray, config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            plate = normalize_plate(text)
            conf = 0.55 if plate else 0.0
            return PlateRead(
                plate=plate,
                confidence=conf,
                simulated=False,
                ai_status=REAL if plate else SIMULATED,
                model="tesseract",
                indian_format_ok=indian_format_ok(plate) if plate else False,
            )
        except Exception:
            return PlateRead(plate="", confidence=0.0, simulated=True, ai_status=SIMULATED)


class PlateCropDetector:
    """Optional dedicated plate YOLO; otherwise uses lower third of a vehicle box."""

    def __init__(self, conf: float = 0.35) -> None:
        self.model = None
        path = resolve_plate()
        if path is None:
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(path))
        except Exception:
            self.model = None

    def detect(self, frame) -> list[Detection]:
        if self.model is None or frame is None:
            return []
        from datetime import datetime, timezone

        h, w = frame.shape[:2]
        out = []
        for result in self.model.predict(frame, conf=0.35, verbose=False):
            if result.boxes is None:
                continue
            for box in result.boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = xyxy
                out.append(
                    Detection(
                        klass="license_plate",
                        confidence=float(box.conf[0]),
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                        timestamp=datetime.now(timezone.utc),
                        simulated=False,
                        ai_status=REAL,
                        model="plate-yolo",
                    )
                )
        return out


def crop_norm(frame, bbox):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    xa, ya, xb, yb = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)
    xa, ya = max(0, xa), max(0, ya)
    xb, yb = min(w, xb), min(h, yb)
    if xb <= xa or yb <= ya:
        return None
    return frame[ya:yb, xa:xb]


def vehicle_plate_region(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    return (x1, y1 + 0.62 * (y2 - y1), x2, y2)
