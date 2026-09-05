"""Real-AI validation: neural inference -> Observation -> Event -> API.

Guards: skipped if the optional AI runtime (ultralytics/cv2) or the
downloaded weights are unavailable. These tests prove REAL means an actual
neural-network forward pass executed, not merely that a model object exists.
"""

import sys
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("ultralytics")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai"))

from tests.test_auth import auth_header  # noqa: E402
from urbansense_ai.analytics import classify_los, congestion_should_emit  # noqa: E402
from urbansense_ai.mapping import rdd_event  # noqa: E402
from urbansense_ai.pipeline import FrameContext, PerceptionPipeline  # noqa: E402
from urbansense_ai.anpr import ANPREngine, FastALPRPlateDetector, FastPlateOCR, TrackPlateVoter  # noqa: E402
from urbansense_ai.plates import TesseractOCR, indian_format_ok, normalize_plate  # noqa: E402
from urbansense_ai.road_damage import RDD_CLASSES, Yolov8RoadDamageDetector  # noqa: E402
from urbansense_ai.signs import TrafficSignDetector  # noqa: E402
from urbansense_ai.speed import HomographySpeedEstimator  # noqa: E402
from urbansense_ai.status import EXPERIMENTAL, REAL, RULE_BASED, SIMULATED  # noqa: E402
from urbansense_ai.vehicles import ByteTrackAdapter, Yolov8VehicleDetector  # noqa: E402
from urbansense_ai.weights import COCO_PATH, RDD_PATH  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
POTHOLE_IMG = FIX / "pothole_big.jpg"
BUS_IMG = FIX / "bus.jpg"
PLATE_KA_IMG = FIX / "plate_ka198488.jpg"
PLATE_KERALA_IMG = FIX / "plate_kerala_car.jpg"


def test_rdd_weights_present_and_classes():
    assert RDD_PATH.exists() and RDD_PATH.stat().st_size > 1_000_000
    det = Yolov8RoadDamageDetector()
    assert det.model is not None
    assert det.ai_status == REAL
    assert list(det.model.names.values()) == RDD_CLASSES


def test_rdd_real_photo_detection():
    img = cv2.imread(str(POTHOLE_IMG))
    assert img is not None
    det = Yolov8RoadDamageDetector(conf=0.25)
    dets = det.detect(img)
    assert len(dets) >= 1
    for d in dets:
        assert d.klass in RDD_CLASSES
        assert d.confidence >= 0.25
        assert d.ai_status == REAL
        assert d.simulated is False


def test_detection_maps_to_observation_fields(client, admin_token):
    img = cv2.imread(str(POTHOLE_IMG))
    det = Yolov8RoadDamageDetector(conf=0.25)
    dets = det.detect(img)
    assert dets
    etype, sev = rdd_event(dets[0].klass)
    payload = {
        "event_type": etype,
        "severity": sev,
        "latitude": 28.6328,
        "longitude": 77.2195,
        "gps_accuracy": 5.0,
        "source_type": "PHONE",
        "source_id": "VALIDATION-CAM",
        "confidence": dets[0].confidence,
        "simulated": dets[0].simulated,
        "extra": {"ai_status": dets[0].ai_status, "model": dets[0].model},
    }
    r = client.post("/observations", json=payload, headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    obs = body["observation"]
    for field in ("id", "event_type", "confidence", "timestamp", "latitude",
                  "longitude", "source_type", "source_id", "simulated"):
        assert field in obs, field
    assert obs["simulated"] is False
    assert body["event"]["extra"]["ai_status"] == REAL


def test_analyze_frame_endpoint_creates_event(client, admin_token):
    with open(POTHOLE_IMG, "rb") as fh:
        r = client.post(
            "/ai/analyze-frame",
            files={"file": ("pothole.jpg", fh, "image/jpeg")},
            data={"latitude": 28.6328, "longitude": 77.2195,
                  "source_id": "VALIDATION-CAM", "source_type": "PHONE"},
            headers=auth_header(admin_token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["count"] >= 1
    assert body["items"][0]["simulated"] is False


def test_capabilities_report_honestly(client, admin_token):
    r = client.get("/ai/capabilities", headers=auth_header(admin_token))
    assert r.status_code == 200
    caps = r.json()
    assert caps["road_damage"]["ai_status"] == REAL
    assert caps["vehicles"]["ai_status"] == REAL
    assert caps["tracking"]["ai_status"] == REAL
    assert caps["speed"]["ai_status"] == EXPERIMENTAL
    assert caps["speed"]["calibrated"] is False
    assert caps["waterlogging"]["ai_status"] == SIMULATED
    assert caps["traffic_signs"]["enabled"] is False
    assert caps["congestion"]["ai_status"] == RULE_BASED
    assert caps["indian_plate_format"]["ai_status"] == RULE_BASED
    assert caps["plate_detection"]["ai_status"] == REAL
    assert caps["ocr"]["ai_status"] == REAL
    assert caps["temporal_voting"]["ai_status"] == RULE_BASED


def test_vehicle_track_ids_persist():
    img = cv2.imread(str(BUS_IMG))
    assert img is not None
    assert COCO_PATH.exists()
    det = Yolov8VehicleDetector()
    assert det.ai_status == REAL
    tracker = ByteTrackAdapter(det)
    first = tracker.update([], img)
    second = tracker.update([], img)
    assert len(first) >= 1
    assert {t.track_id for t in first} == {t.track_id for t in second}
    assert all(t.ai_status == REAL for t in first)


def test_congestion_needs_persistence():
    assert classify_los(0, None)[0] == "A"
    assert congestion_should_emit("F", 1) is False
    assert congestion_should_emit("F", 8) is True


def test_speed_is_experimental_math():
    est = HomographySpeedEstimator()
    assert est.calibrated is False
    assert est.meta()["ai_status"] == EXPERIMENTAL
    assert "moving-camera" in est.meta()["note"]
    assert est.update("v1", 320.0, 400.0, 0.0) is None  # need history
    assert est.update("v1", 321.0, 401.0, 0.2) is None
    kmh = est.update("v1", 330.0, 410.0, 0.6)
    assert kmh is None or 0 <= kmh <= 200


def test_anpr_fallback_and_signs_disabled():
    ocr = TesseractOCR()
    if not ocr.ok:  # OS Tesseract missing: honest empty result, never fake text
        read = ocr.read_plate(None)
        assert read.plate == ""
        assert read.ai_status == SIMULATED
    signs = TrafficSignDetector()
    assert signs.enabled is False
    assert signs.ai_status == SIMULATED


def test_no_turkish_parser_in_runtime():
    import urbansense_ai.anpr as anpr_mod
    import urbansense_ai.pipeline as pipe
    import urbansense_ai.plates as plates

    for mod in (pipe, plates, anpr_mod):
        assert not hasattr(mod, "parse_turkish_plate")
    assert indian_format_ok("DL01AB1234")
    assert not indian_format_ok("34ABC123")


def test_full_pipeline_produces_fused_event():
    img = cv2.imread(str(POTHOLE_IMG))
    pipe = PerceptionPipeline()
    ctx = FrameContext(latitude=28.6328, longitude=77.2195, source_id="VALIDATION-CAM")
    payloads = pipe.process(img, ctx)
    road = [p for p in payloads if p["event_type"] in ("POTHOLE", "ROAD_DAMAGE")]
    assert road, "pipeline must emit a road observation for the pothole photo"
    first = road[0]
    for field in ("event_type", "confidence", "timestamp", "latitude", "longitude",
                  "source_type", "source_id", "extra", "simulated"):
        assert field in first, field
    assert first["extra"]["ai_status"] == REAL
    assert first["simulated"] is False


fast_alpr = pytest.importorskip("fast_alpr")
pytest.importorskip("fast_plate_ocr")


def test_plate_detector_adapter_real():
    img = cv2.imread(str(PLATE_KA_IMG))
    det = FastALPRPlateDetector()
    assert det.ok
    assert det.ai_status == REAL
    dets = det.detect(img)
    assert len(dets) >= 1
    assert dets[0].klass == "license_plate"
    assert dets[0].ai_status == REAL
    assert dets[0].simulated is False


def test_fast_ocr_adapter_real_indian_plate():
    import numpy as np

    img = cv2.imread(str(PLATE_KA_IMG))
    det = FastALPRPlateDetector()
    dets = det.detect(img)
    assert dets
    h, w = img.shape[:2]
    x1, y1, x2, y2 = dets[0].bbox
    crop = img[max(0, int(y1 * h)):int(y2 * h), max(0, int(x1 * w)):int(x2 * w)]
    read = FastPlateOCR().read_plate(crop)
    assert read.ai_status == REAL
    assert read.simulated is False
    assert normalize_plate(read.plate) == "KA19P8488"
    assert read.confidence > 0.5
    assert read.indian_format_ok is True


def test_ocr_car_scene_plate():
    img = cv2.imread(str(PLATE_KERALA_IMG))
    det = FastALPRPlateDetector()
    dets = det.detect(img)
    assert len(dets) >= 1
    assert max(d.confidence for d in dets) > 0.5


def test_track_voter_per_char_correction():
    voter = TrackPlateVoter(window=8, min_dwell=3, top_k=3)
    assert voter.observe("t17", "DL8CAF5032", 0.71) is None
    assert voter.observe("t17", "DL8CAF5032", 0.82) is None
    # One noisy read with a wrong char must not win the per-char vote.
    assert voter.observe("t17", "DL8CAF503Z", 0.59) == "DL8CAF5032"
    assert voter.confirmed_for("t17") == "DL8CAF5032"


def test_track_association_and_throttle():
    img = cv2.imread(str(PLATE_KA_IMG))
    engine = ANPREngine(min_interval_s=3600)  # force throttle after first read
    first = engine.read_track("KA-1", img, (0.0, 0.0, 1.0, 1.0))
    assert first["plate_text"] == "KA19P8488"
    assert first["ai_status"] == REAL
    assert first["format_valid"] is True
    assert first["format_validator"] == "INDIA_RULE_BASED"
    second = engine.read_track("KA-1", img, (0.0, 0.0, 1.0, 1.0))
    assert second["plate_text"] == "KA19P8488"  # cached, no re-inference
    other = engine.read_track("KA-2", img, (0.0, 0.0, 1.0, 1.0))
    assert other["plate_text"] == "KA19P8488"  # per-track state is independent


def test_anpr_capabilities_real():
    engine = ANPREngine()
    caps = engine.capabilities()
    assert caps["plate_detection"]["ai_status"] == REAL
    assert caps["ocr"]["ai_status"] == REAL
    assert caps["temporal_voting"]["ai_status"] == RULE_BASED
    assert caps["indian_plate_format"]["ai_status"] == RULE_BASED


def test_incident_observation_with_plate(client, admin_token):
    import json

    engine = ANPREngine(min_interval_s=0)
    img = cv2.imread(str(PLATE_KA_IMG))
    res = engine.read_track("INC-9", img, (0.0, 0.0, 1.0, 1.0))
    payload = {
        "event_type": "RASH_DRIVING",
        "severity": "HIGH",
        "latitude": 28.6328,
        "longitude": 77.2195,
        "source_type": "PHONE",
        "source_id": "ANPR-TEST",
        "confidence": 0.7,
        "simulated": False,
        "plate_text": res["confirmed"] or res["plate_text"],
        "plate_confidence": res["ocr_confidence"],
        "extra": {
            "ai_status": RULE_BASED,
            "track_id": res["track_id"],
            "plate_ai_status": res["ai_status"],
            "plate_format_valid": res["format_valid"],
            "plate_validator": res["format_validator"],
        },
    }
    json.dumps(payload)  # JSON-serializable contract
    r = client.post("/observations", json=payload, headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["observation"]["plate_text"] == "KA19P8488"
    assert body["event"]["extra"]["plate_ai_status"] == REAL
