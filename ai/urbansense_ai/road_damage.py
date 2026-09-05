from __future__ import annotations

from datetime import datetime, timezone

from urbansense_ai.engines import Detection
from urbansense_ai.status import REAL, SIMULATED
from urbansense_ai.weights import resolve_rdd

RDD_CLASSES = ["Longitudinal Crack", "Transverse Crack", "Alligator Crack", "Potholes"]


class Yolov8RoadDamageDetector:
    """YOLOv8 RDD2022 small weights (oracl4/RoadDamageDetection). REAL when weights load."""

    def __init__(self, conf: float = 0.35) -> None:
        self.conf = conf
        self.model = None
        self.model_name = "YOLOv8_Small_RDD"
        self.ai_status = SIMULATED
        path = resolve_rdd()
        if path is None:
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(path))
            self.ai_status = REAL
        except Exception:
            self.model = None
            self.ai_status = SIMULATED

    def detect(self, frame) -> list[Detection]:
        if self.model is None or frame is None:
            return []
        h, w = frame.shape[:2]
        results = self.model.predict(frame, conf=self.conf, verbose=False, imgsz=640)
        out: list[Detection] = []
        now = datetime.now(timezone.utc)
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                label = RDD_CLASSES[cls_id] if cls_id < len(RDD_CLASSES) else f"class_{cls_id}"
                x1, y1, x2, y2 = xyxy
                out.append(
                    Detection(
                        klass=label,
                        confidence=float(box.conf[0]),
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                        timestamp=now,
                        simulated=False,
                        ai_status=REAL,
                        model=self.model_name,
                    )
                )
        return out
