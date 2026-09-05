"""Vehicle + person detection. Tracking uses Ultralytics ByteTrack when available."""

from __future__ import annotations

from datetime import datetime, timezone

from urbansense_ai.engines import Detection, Track
from urbansense_ai.status import REAL, SIMULATED
from urbansense_ai.weights import resolve_coco

VEHICLE_IDS = {1, 2, 3, 5, 7}  # bicycle, car, motorcycle, bus, truck
PERSON_ID = 0


class Yolov8VehicleDetector:
    def __init__(self, conf: float = 0.35) -> None:
        self.conf = conf
        self.model = None
        self.model_name = "yolov8n-coco"
        self.ai_status = SIMULATED
        try:
            from ultralytics import YOLO

            self.model = YOLO(resolve_coco())
            self.ai_status = REAL
        except Exception:
            self.model = None

    def detect(self, frame) -> list[Detection]:
        if self.model is None or frame is None:
            return []
        h, w = frame.shape[:2]
        results = self.model.predict(frame, conf=self.conf, verbose=False, classes=list(VEHICLE_IDS | {PERSON_ID}))
        now = datetime.now(timezone.utc)
        out: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            names = result.names
            for box in result.boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                x1, y1, x2, y2 = xyxy
                out.append(
                    Detection(
                        klass=str(names.get(cls_id, cls_id)),
                        confidence=float(box.conf[0]),
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                        timestamp=now,
                        simulated=False,
                        ai_status=REAL,
                        model=self.model_name,
                    )
                )
        return out


class ByteTrackAdapter:
    """Ultralytics built-in ByteTrack (same mechanism as Edge-AI traffic_monitor)."""

    def __init__(self, detector: Yolov8VehicleDetector | None = None) -> None:
        self.detector = detector or Yolov8VehicleDetector()
        self.ai_status = self.detector.ai_status

    def update(self, detections: list[Detection], frame=None) -> list[Track]:
        if self.detector.model is None or frame is None:
            return [
                Track(track_id=d.track_id or f"t{i}", klass=d.klass, confidence=d.confidence, simulated=d.simulated, ai_status=d.ai_status, bbox=d.bbox)
                for i, d in enumerate(detections)
            ]
        h, w = frame.shape[:2]
        results = self.detector.model.track(
            frame, persist=True, conf=self.detector.conf, verbose=False, tracker="bytetrack.yaml"
        )
        tracks: list[Track] = []
        for result in results:
            if result.boxes is None:
                continue
            names = result.names
            ids = result.boxes.id
            for i, box in enumerate(result.boxes):
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = xyxy
                tid = str(int(ids[i])) if ids is not None else f"t{i}"
                cls_id = int(box.cls[0])
                tracks.append(
                    Track(
                        track_id=tid,
                        klass=str(names.get(cls_id, cls_id)),
                        confidence=float(box.conf[0]),
                        simulated=False,
                        ai_status=REAL,
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                        centroid=((x1 + x2) / 2 / w, (y1 + y2) / 2 / h),
                    )
                )
        return tracks
