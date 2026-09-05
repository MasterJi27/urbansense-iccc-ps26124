"""Traffic-sign detector. Classes from the source repo are Turkish — labeled as such."""

from __future__ import annotations

from datetime import datetime, timezone

from urbansense_ai.engines import Detection
from urbansense_ai.status import EXPERIMENTAL, SIMULATED
from urbansense_ai.weights import resolve_signs


class TrafficSignDetector:
    """Loads a custom YOLO if URBANSENSE_SIGN_WEIGHTS / models/traffic_sign/best.pt exists.

    Source labels are Turkish traffic signs — never an Indian MoRTH set.
    Status is EXPERIMENTAL even when weights load; disabled (no output) by
    default when weights are absent. Outputs include extra.domain = 'TR'.
    """

    def __init__(self, conf: float = 0.4) -> None:
        self.conf = conf
        self.model = None
        self.ai_status = SIMULATED
        self.enabled = False
        self.model_name = "traffic-sign-yolo-tr"
        path = resolve_signs()
        if path is None:
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(path))
            self.enabled = True
            self.ai_status = EXPERIMENTAL
        except Exception:
            self.model = None

    def detect(self, frame) -> list[Detection]:
        if self.model is None or frame is None:
            return []
        h, w = frame.shape[:2]
        now = datetime.now(timezone.utc)
        out = []
        for result in self.model.predict(frame, conf=self.conf, verbose=False):
            if result.boxes is None:
                continue
            names = result.names
            for box in result.boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = xyxy
                cls_id = int(box.cls[0])
                out.append(
                    Detection(
                        klass=str(names.get(cls_id, cls_id)),
                        confidence=float(box.conf[0]),
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                        timestamp=now,
                        simulated=False,
                        ai_status=EXPERIMENTAL,
                        model=self.model_name,
                        extra={"domain": "TR", "note": "Turkish traffic-sign classes, not IRC/Indian MoRTH set"},
                    )
                )
        return out
