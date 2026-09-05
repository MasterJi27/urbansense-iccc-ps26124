"""Per-frame perception → UrbanSense observation payloads."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from urbansense_ai.analytics import classify_los, congestion_should_emit, pedestrian_risk, rash_driving
from urbansense_ai.anpr import ANPREngine
from urbansense_ai.engines import Detection, to_plain
from urbansense_ai.mapping import rdd_event, vehicle_event
from urbansense_ai.road_damage import Yolov8RoadDamageDetector
from urbansense_ai.signs import TrafficSignDetector
from urbansense_ai.speed import HomographySpeedEstimator
from urbansense_ai.status import RULE_BASED, SIMULATED
from urbansense_ai.vehicles import ByteTrackAdapter, Yolov8VehicleDetector


@dataclass
class FrameContext:
    latitude: float
    longitude: float
    gps_accuracy: float | None = None
    source_id: str = "WEBCAM-01"
    source_type: str = "PHONE"
    sensor_id: str | None = None
    bus_id: str | None = None
    route_id: str | None = None
    heading: float | None = None


class PerceptionPipeline:
    def __init__(self) -> None:
        self.road = Yolov8RoadDamageDetector()
        self.vehicles = Yolov8VehicleDetector()
        self.tracker = ByteTrackAdapter(self.vehicles)
        self.signs = TrafficSignDetector()
        self.anpr = ANPREngine()
        self.speed = HomographySpeedEstimator()
        self._congestion_streak = 0
        self._last_emit: dict[str, float] = {}

    def capabilities(self) -> dict[str, Any]:
        caps = {
            "road_damage": {"ai_status": self.road.ai_status, "model": self.road.model_name},
            "vehicles": {"ai_status": self.vehicles.ai_status, "model": self.vehicles.model_name},
            "tracking": {"ai_status": self.tracker.ai_status, "model": "ultralytics-bytetrack"},
            "traffic_signs": {
                "ai_status": self.signs.ai_status,
                "model": self.signs.model_name,
                "enabled": self.signs.enabled,
                "dataset": "Turkish (TR) — not Indian MoRTH",
                "limitation": "Disabled by default without weights; Turkish class set if weights present",
            },
            "speed": self.speed.meta(),
            "congestion": {"ai_status": RULE_BASED},
            "rash_driving": {"ai_status": RULE_BASED},
            "pedestrian_risk": {"ai_status": RULE_BASED},
            "waterlogging": {"ai_status": SIMULATED, "note": "No local waterlogging weights"},
        }
        caps.update(self.anpr.capabilities())
        return caps

    def process(self, frame, ctx: FrameContext) -> list[dict]:
        now = datetime.now(timezone.utc)
        payloads: list[dict] = []
        t = time.time()

        for det in self.road.detect(frame):
            etype, sev = rdd_event(det.klass)
            payloads.append(self._obs(ctx, now, etype, sev, det.confidence, det, extra={"rdd_class": det.klass}))

        tracks = self.tracker.update([], frame)
        speeds = []
        h, w = frame.shape[:2]
        for tr in tracks:
            if tr.centroid:
                kmh = self.speed.update(tr.track_id, tr.centroid[0] * w, tr.centroid[1] * h, t)
                if kmh is not None:
                    speeds.append(kmh)
                if rash_driving(kmh) and self._throttle(f"rash-{tr.track_id}", 8):
                    plate = None
                    pconf = None
                    plate_status = SIMULATED
                    plate_valid = False
                    if tr.bbox is not None:
                        res = self.anpr.read_track(tr.track_id, frame, tr.bbox)
                        plate = res["confirmed"] or res["plate_text"] or None
                        pconf = res["ocr_confidence"] or None
                        plate_status = res["ai_status"]
                        plate_valid = res["format_valid"]
                    payloads.append(
                        self._obs(
                            ctx,
                            now,
                            "RASH_DRIVING",
                            "HIGH",
                            0.7,
                            extra={
                                "ai_status": RULE_BASED,
                                "speed_kmh": kmh,
                                "track_id": tr.track_id,
                                "speed_calibrated": self.speed.calibrated,
                                "plate_ai_status": plate_status,
                                "plate_format_valid": plate_valid,
                                "plate_validator": "INDIA_RULE_BASED",
                            },
                            plate=plate,
                            plate_confidence=pconf,
                            speed_kmh=kmh,
                            simulated=not self.speed.calibrated,
                        )
                    )
            et = vehicle_event(tr.klass)
            if et == "PEDESTRIAN":
                continue
            # Vehicle tracks feed counting/speed only; do not spam UrbanEvent per box.

        n_veh = sum(1 for tr in tracks if tr.klass != "person")
        avg = sum(speeds) / len(speeds) if speeds else None
        los, desc = classify_los(n_veh, avg)
        if congestion_should_emit(los, self._congestion_streak + 1):
            self._congestion_streak += 1
        else:
            self._congestion_streak = self._congestion_streak + 1 if los in {"E", "F"} else 0
        if congestion_should_emit(los, self._congestion_streak) and self._throttle("cong", 15):
            payloads.append(
                self._obs(
                    ctx,
                    now,
                    "TRAFFIC_CONGESTION",
                    "HIGH" if los == "F" else "MEDIUM",
                    0.65,
                    extra={"ai_status": RULE_BASED, "los": los, "los_desc": desc, "vehicle_count": n_veh, "avg_speed_kmh": avg},
                    simulated=False,
                )
            )

        risk, score = pedestrian_risk(tracks)
        if risk and self._throttle("ped", 6):
            payloads.append(
                self._obs(
                    ctx,
                    now,
                    "PEDESTRIAN_RISK",
                    "HIGH",
                    score,
                    extra={"ai_status": RULE_BASED, "method": "bbox-proximity"},
                    simulated=False,
                )
            )

        for det in self.signs.detect(frame):
            payloads.append(
                self._obs(
                    ctx,
                    now,
                    "DAMAGED_SIGN",
                    "LOW",
                    det.confidence,
                    det,
                    extra={**det.extra, "note": "Sign *detected*; not classified as damaged. Domain=TR."},
                    simulated=False,
                )
            )

        return payloads

    def _throttle(self, key: str, seconds: float) -> bool:
        now = time.time()
        last = self._last_emit.get(key, 0)
        if now - last < seconds:
            return False
        self._last_emit[key] = now
        return True

    def _obs(
        self,
        ctx: FrameContext,
        now: datetime,
        event_type: str,
        severity: str,
        confidence: float,
        det: Detection | None = None,
        extra: dict | None = None,
        plate: str | None = None,
        plate_confidence: float | None = None,
        speed_kmh: float | None = None,
        simulated: bool | None = None,
    ) -> dict:
        meta = extra or {}
        if det:
            meta.setdefault("ai_status", det.ai_status)
            meta.setdefault("model", det.model)
            meta.setdefault("bbox", det.bbox)
            meta.setdefault("detector_class", det.klass)
        if simulated is not None:
            sim = simulated
        elif det is not None:
            sim = det.simulated
        else:
            sim = meta.get("ai_status") == SIMULATED
        meta = to_plain(meta)
        return {
            "event_type": event_type,
            "severity": severity,
            "latitude": ctx.latitude,
            "longitude": ctx.longitude,
            "gps_accuracy": ctx.gps_accuracy,
            "timestamp": now.isoformat(),
            "source_type": ctx.source_type,
            "source_id": ctx.source_id,
            "sensor_id": ctx.sensor_id,
            "bus_id": ctx.bus_id,
            "route_id": ctx.route_id,
            "confidence": min(1.0, max(0.0, float(confidence))),
            "simulated": sim,
            "heading": ctx.heading,
            "speed_kmh": None if speed_kmh is None else float(speed_kmh),
            "plate_text": plate,
            "plate_confidence": None if plate_confidence is None else float(plate_confidence),
            "extra": meta,
        }
