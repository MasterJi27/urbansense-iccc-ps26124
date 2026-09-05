"""UrbanSense ANPR engine: fast-alpr plate detection + fast-plate-ocr reading.

Source (MIT): boost/Automatic_Number_Plate_Recognition_YOLO_OCR-main/.../src/anpr
(detector/fast_alpr.py, ocr/fast_plate.py, postprocess/temporal.py).
Deliberately NOT reused: api/ (FastAPI server), storage/, tracker/iou.py
(UrbanSense already has ByteTrack), postprocess/turkish.py + confusion.py
(Turkish-only parsing). Country validation is UrbanSense's own
RULE_BASED Indian regex in plates.py — never a Turkish parser.

Interface:

    ANPREngine
      ├── FastALPRPlateDetector  (preferred plate boxes, REAL)
      ├── FastPlateOCR           (preferred OCR, REAL)
      └── TesseractOCR           (fallback, from plates.py)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from urbansense_ai.engines import Detection, PlateRead, to_plain
from urbansense_ai.plates import TesseractOCR, crop_norm, indian_format_ok, normalize_plate
from urbansense_ai.status import REAL, RULE_BASED, SIMULATED

FAST_ALPR_MODEL = "yolo-v9-t-384-license-plate-end2end"
FAST_OCR_MODEL = "cct-s-v2-global-model"


def _mean_conf(char_probs) -> float:
    try:
        import numpy as np

        arr = np.asarray(char_probs, dtype=float).ravel()
        return float(arr.mean()) if arr.size else 1.0
    except Exception:
        try:
            vals = [float(v) for v in (char_probs or [])]
            return sum(vals) / len(vals) if vals else 1.0
        except Exception:
            return 1.0


class FastALPRPlateDetector:
    """YOLOv9-t ONNX plate detector bundled with fast-alpr. REAL when loaded."""

    def __init__(self, conf: float = 0.35) -> None:
        self.conf = conf
        self.model = None
        self.model_name = "fast-alpr-yolov9t-384"
        self.ai_status = SIMULATED
        try:
            from fast_alpr.default_detector import DefaultDetector

            self.model = DefaultDetector(model_name=FAST_ALPR_MODEL, conf_thresh=conf)
            self.ai_status = REAL
        except Exception:
            self.model = None

    @property
    def ok(self) -> bool:
        return self.model is not None

    def detect(self, frame) -> list[Detection]:
        if self.model is None or frame is None:
            return []
        h, w = frame.shape[:2]
        try:
            raw = self.model.predict(frame)
        except Exception:
            return []
        if raw and isinstance(raw[0], list):
            raw = raw[0]
        now = datetime.now(timezone.utc)
        out: list[Detection] = []
        for item in raw or []:
            try:
                box = item.bounding_box
                x1, y1, x2, y2 = float(box.x1), float(box.y1), float(box.x2), float(box.y2)
                out.append(
                    Detection(
                        klass="license_plate",
                        confidence=float(item.confidence),
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                        timestamp=now,
                        simulated=False,
                        ai_status=REAL,
                        model=self.model_name,
                    )
                )
            except Exception:
                continue
        return out


class FastPlateOCR:
    """fast-plate-ocr global recognizer with per-character confidences."""

    def __init__(self) -> None:
        self.model = None
        self.model_name = "fast-plate-ocr-cct-s-v2-global"
        self.ai_status = SIMULATED
        try:
            from fast_plate_ocr import LicensePlateRecognizer

            self.model = LicensePlateRecognizer(hub_ocr_model=FAST_OCR_MODEL, device="auto")
            self.ai_status = REAL
        except Exception:
            self.model = None

    @property
    def ok(self) -> bool:
        return self.model is not None

    def read_plate(self, crop) -> PlateRead:
        if self.model is None or crop is None:
            return PlateRead(plate="", confidence=0.0, simulated=True, ai_status=SIMULATED)
        try:
            results = self.model.run(crop, return_confidence=True)
        except Exception:
            return PlateRead(plate="", confidence=0.0, simulated=True, ai_status=SIMULATED)
        if not results or not getattr(results[0], "plate", None):
            return PlateRead(plate="", confidence=0.0, simulated=True,
                             ai_status=SIMULATED, model=self.model_name)
        text = normalize_plate(str(results[0].plate))
        conf = _mean_conf(getattr(results[0], "char_probs", None))
        if not text:
            return PlateRead(plate="", confidence=0.0, simulated=True,
                             ai_status=SIMULATED, model=self.model_name)
        return PlateRead(
            plate=text,
            confidence=conf,
            simulated=False,
            ai_status=REAL,
            model=self.model_name,
            indian_format_ok=indian_format_ok(text),
        )


class TrackPlateVoter:
    """Per-track, per-character confidence-weighted voting.

    Adapted from the boost ANPR repo's postprocess/temporal.py (MIT):
    keep top-K reads by confidence, then majority-vote each character
    position weighted by confidence. Keyed by UrbanSense (string) track IDs
    so plates stay associated with ByteTrack vehicle tracks.
    """

    def __init__(self, window: int = 8, min_dwell: int = 3, top_k: int = 3) -> None:
        self._hist: dict[str, deque[tuple[str, float]]] = defaultdict(lambda: deque(maxlen=window))
        self._confirmed: dict[str, str] = {}
        self._min = min_dwell
        self._top_k = top_k

    def observe(self, track_id: str, text: str, confidence: float) -> str | None:
        key = normalize_plate(text)
        if not key:
            return self._confirmed.get(track_id)
        hist = self._hist[track_id]
        hist.append((key, float(confidence)))
        if len(hist) < self._min:
            return self._confirmed.get(track_id)
        top = sorted(hist, key=lambda r: r[1], reverse=True)[: self._top_k]
        max_len = max(len(t) for t, _ in top)
        chars: list[str] = []
        for i in range(max_len):
            weights: dict[str, float] = defaultdict(float)
            for text_i, conf_i in top:
                if i < len(text_i):
                    weights[text_i[i]] += conf_i
            if weights:
                chars.append(max(weights.items(), key=lambda kv: kv[1])[0])
        voted = "".join(chars)
        self._confirmed[track_id] = voted
        return voted

    def confirmed_for(self, track_id: str) -> str | None:
        return self._confirmed.get(track_id)

    def forget(self, track_id: str) -> None:
        self._hist.pop(track_id, None)
        self._confirmed.pop(track_id, None)


class ANPREngine:
    """Preferred fast-alpr/fast-plate-ocr path with Tesseract fallback.

    Throttling: OCR runs at most once per ``min_interval_s`` per track and
    skips tiny crops, so the ~4 FPS demo pipeline survives. Results are
    cached per track; every call returns the latest read plus the voted
    registration candidate.
    """

    def __init__(self, min_interval_s: float = 1.5, min_crop_px: int = 60) -> None:
        self.detector = FastALPRPlateDetector()
        self.reader = FastPlateOCR()
        self.fallback = TesseractOCR()
        self.voter = TrackPlateVoter()
        self.min_interval_s = min_interval_s
        self.min_crop_px = min_crop_px
        self._last_run: dict[str, float] = {}
        self._cache: dict[str, dict] = {}

    @property
    def fast_ok(self) -> bool:
        return self.detector.ok and self.reader.ok

    def _throttled(self, track_id: str) -> bool:
        now = time.time()
        last = self._last_run.get(track_id, 0.0)
        if now - last < self.min_interval_s:
            return True
        self._last_run[track_id] = now
        return False

    def read_track(self, track_id: str, frame, vehicle_bbox_norm) -> dict:
        """Detect + OCR a plate for one vehicle track. Never raises."""
        cached = self._cache.get(track_id, {})
        if frame is None or vehicle_bbox_norm is None:
            return self._result(track_id, "", 0.0, SIMULATED, cached)
        if self._throttled(track_id):
            return self._result(
                track_id,
                cached.get("plate_text", ""),
                cached.get("ocr_confidence", 0.0),
                cached.get("ai_status", SIMULATED),
                cached,
            )
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = vehicle_bbox_norm
        vehicle_crop = crop_norm(
            frame, (max(0.0, x1), max(0.0, y1), min(1.0, x2), min(1.0, y2))
        )
        if vehicle_crop is None or vehicle_crop.shape[1] < 24:
            return self._result(track_id, "", 0.0, SIMULATED, cached)

        plate_text, conf, status = "", 0.0, SIMULATED
        if self.fast_ok:
            for det in self.detector.detect(vehicle_crop)[:1]:
                crop = crop_norm(vehicle_crop, det.bbox)
                if crop is None or crop.shape[1] < self.min_crop_px // 2:
                    continue
                read = self.reader.read_plate(crop)
                if read.plate:
                    plate_text, conf, status = read.plate, read.confidence, REAL
                    break
        if not plate_text:
            # Heuristic fallback: lower third of the vehicle box (plate zone).
            bx1, by1, bx2, by2 = 0.0, 0.62, 1.0, 1.0
            crop = crop_norm(vehicle_crop, (bx1, by1, bx2, by2))
            read = (self.reader.read_plate(crop) if self.reader.ok
                    else self.fallback.read_plate(crop))
            if read.plate:
                plate_text, conf = read.plate, read.confidence
                status = read.ai_status
        return self._result(track_id, plate_text, conf, status, cached)

    def _result(self, track_id: str, text: str, conf: float, status: str, cached: dict) -> dict:
        if text:
            confirmed = self.voter.observe(track_id, text, conf)
        else:
            confirmed = self.voter.confirmed_for(track_id)
        if text and (not cached or conf >= cached.get("ocr_confidence", 0.0)):
            cached = {"plate_text": text, "ocr_confidence": float(conf), "ai_status": status}
            self._cache[track_id] = cached
        else:
            cached = self._cache.get(track_id, {"plate_text": text,
                                                "ocr_confidence": float(conf),
                                                "ai_status": status})
        return {
            "track_id": track_id,
            "plate_text": to_plain(cached.get("plate_text", "")),
            "ocr_confidence": float(cached.get("ocr_confidence", 0.0)),
            "confirmed": confirmed,
            "format_valid": bool(indian_format_ok(cached.get("plate_text", ""))),
            "format_validator": "INDIA_RULE_BASED",
            "ai_status": cached.get("ai_status", SIMULATED),
        }

    def capabilities(self) -> dict:
        return {
            "plate_detection": {"ai_status": REAL if self.detector.ok else SIMULATED,
                                "model": self.detector.model_name if self.detector.ok else None},
            "ocr": {"ai_status": REAL if self.reader.ok else SIMULATED,
                    "model": self.reader.model_name if self.reader.ok else
                    ("tesseract" if self.fallback.ok else None),
                    "note": None if self.reader.ok else
                    "FALLBACK; fast-plate-ocr unavailable, Tesseract if installed else empty"},
            "temporal_voting": {"ai_status": RULE_BASED,
                                "model": "per-char confidence-weighted vote (adapted, MIT)",
                                "note": "Deterministic algorithm over OCR reads; not a neural model"},
            "indian_plate_format": {"ai_status": RULE_BASED,
                                    "note": "Regex format check only; does not prove OCR correctness"},
        }
