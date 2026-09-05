from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from urbansense_ai.status import SIMULATED


@dataclass
class Detection:
    klass: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x1,y1,x2,y2 normalized 0-1
    timestamp: datetime
    simulated: bool = True
    ai_status: str = SIMULATED
    model: str | None = None
    track_id: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Track:
    track_id: str
    klass: str
    confidence: float
    simulated: bool = True
    ai_status: str = SIMULATED
    bbox: tuple[float, float, float, float] | None = None
    centroid: tuple[float, float] | None = None


@dataclass
class PlateRead:
    plate: str
    confidence: float
    simulated: bool = True
    ai_status: str = SIMULATED
    model: str | None = None
    indian_format_ok: bool | None = None


class DetectionEngine(Protocol):
    def detect(self, frame) -> list[Detection]: ...


class TrackingEngine(Protocol):
    def update(self, detections: list[Detection], frame=None) -> list[Track]: ...


class OCRService(Protocol):
    def read_plate(self, crop) -> PlateRead: ...


class SeverityEngine(Protocol):
    def score(self, detections: list[Detection]) -> str: ...


class SimulationDetector:
    def __init__(self, klass: str = "pothole", confidence: float = 0.84) -> None:
        self.klass = klass
        self.confidence = confidence

    def detect(self, frame=None) -> list[Detection]:
        return [
            Detection(
                klass=self.klass,
                confidence=self.confidence,
                bbox=(0.3, 0.55, 0.5, 0.75),
                timestamp=datetime.now(timezone.utc),
                simulated=True,
                ai_status=SIMULATED,
                model=None,
            )
        ]


class SimulationOCR:
    def read_plate(self, crop=None) -> PlateRead:
        return PlateRead(plate="DL01AB1234", confidence=0.91, simulated=True, ai_status=SIMULATED, indian_format_ok=True)


class RuleSeverity:
    """Maps detector confidence to a label. This is NOT physical defect severity."""

    def score(self, detections: list[Detection]) -> str:
        if not detections:
            return "LOW"
        m = max(d.confidence for d in detections)
        if m >= 0.85:
            return "HIGH"
        if m >= 0.6:
            return "MEDIUM"
        return "LOW"


class PassthroughTracker:
    def update(self, detections: list[Detection], frame=None) -> list[Track]:
        return [
            Track(
                track_id=d.track_id or f"t{i}",
                klass=d.klass,
                confidence=d.confidence,
                simulated=d.simulated,
                ai_status=d.ai_status,
                bbox=d.bbox,
            )
            for i, d in enumerate(detections)
        ]


def to_plain(value):
    """Convert numpy scalars/arrays to plain Python types.

    YOLO outputs numpy float32; those must never reach the backend JSON
    columns (SQLAlchemy JSON serialization fails on them).
    """
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:
        pass
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    return value


def default_stack():
    return {
        "detection": SimulationDetector(),
        "tracking": PassthroughTracker(),
        "ocr": SimulationOCR(),
        "severity": RuleSeverity(),
        "mode": SIMULATED,
    }
