import pytest

from urbansense_ai.analytics import classify_los, congestion_should_emit, pedestrian_risk, rash_driving
from urbansense_ai.engines import Track, to_plain
from urbansense_ai.mapping import rdd_event
from urbansense_ai.plates import indian_format_ok, normalize_plate, TemporalVoter
from urbansense_ai.signs import TrafficSignDetector
from urbansense_ai.speed import HomographySpeedEstimator
from urbansense_ai.status import EXPERIMENTAL, REAL, RULE_BASED, SIMULATED


def test_rdd_mapping():
    assert rdd_event("Potholes")[0] == "POTHOLE"
    assert rdd_event("Alligator Crack")[0] == "ROAD_DAMAGE"


def test_indian_plate():
    assert indian_format_ok("DL01AB1234")
    assert not indian_format_ok("34ABC123")  # Turkish-style, not IN


def test_temporal_vote():
    v = TemporalVoter(window=8, min_dwell=3)
    assert v.observe("1", "DL01AB1234", 0.8) is None
    assert v.observe("1", "DL01AB1234", 0.7) is None
    assert normalize_plate(v.observe("1", "DL01AB1234", 0.9) or "") == "DL01AB1234"


def test_los_and_congestion():
    los, _ = classify_los(20, 8.0, 300)
    assert los == "F"
    assert congestion_should_emit("F", 8)


def test_rash_and_ped():
    assert rash_driving(90, 60)
    assert not rash_driving(40, 60)
    tracks = [
        Track(track_id="p", klass="person", confidence=0.9, bbox=(0.4, 0.4, 0.5, 0.6)),
        Track(track_id="c", klass="car", confidence=0.9, bbox=(0.41, 0.41, 0.55, 0.65)),
    ]
    hit, score = pedestrian_risk(tracks)
    assert hit and score > 0


def test_statuses_are_distinct():
    assert len({REAL, RULE_BASED, EXPERIMENTAL, SIMULATED}) == 4


def test_speed_is_experimental_until_calibrated():
    est = HomographySpeedEstimator()
    assert est.calibrated is False
    assert est.meta()["ai_status"] == EXPERIMENTAL
    cal = HomographySpeedEstimator(
        image_pts=[[0, 0], [640, 0], [640, 480], [0, 480]],
        world_pts=[[0, 0], [8, 0], [8, 6], [0, 6]],
    )
    assert cal.calibrated is True


def test_signs_disabled_without_weights():
    det = TrafficSignDetector()
    assert det.enabled is False
    assert det.ai_status == SIMULATED


def test_congestion_single_frame_does_not_emit():
    assert congestion_should_emit("F", 1) is False
    assert congestion_should_emit("E", 7) is False
    assert congestion_should_emit("F", 8) is True


def test_voter_tracks_are_independent():
    v = TemporalVoter(window=8, min_dwell=3)
    for _ in range(3):
        v.observe("car-a", "DL01AB1234", 0.8)
    for _ in range(2):
        v.observe("car-b", "MH02XY9999", 0.7)
    assert v.observe("car-a", "DL01AB1234", 0.9) == "DL01AB1234"
    assert v.observe("car-b", "MH02XY9999", 0.7) == "MH02XY9999"


def test_to_plain_sanitizes_numpy():
    np = pytest.importorskip("numpy")
    out = to_plain({"bbox": (np.float32(0.1), np.float32(0.2)), "n": np.int64(3)})
    assert out["n"] == 3 and type(out["n"]) is int
    assert all(type(v) is float for v in out["bbox"])
    assert abs(out["bbox"][0] - 0.1) < 1e-6
    import json

    json.dumps(out)  # must survive backend JSON columns


def test_track_plate_voter_corrects_noisy_char():
    from urbansense_ai.anpr import TrackPlateVoter

    voter = TrackPlateVoter(window=8, min_dwell=3, top_k=3)
    assert voter.observe("t17", "DL8CAF5032", 0.71) is None
    assert voter.observe("t17", "DL8CAF5032", 0.82) is None
    assert voter.observe("t17", "DL8CAF503Z", 0.59) == "DL8CAF5032"
    assert voter.confirmed_for("t17") == "DL8CAF5032"
    voter.forget("t17")
    assert voter.confirmed_for("t17") is None


def test_fast_anpr_stack_reads_indian_plate():
    pytest.importorskip("fast_alpr")
    pytest.importorskip("fast_plate_ocr")
    cv2 = pytest.importorskip("cv2")
    from pathlib import Path

    from urbansense_ai.anpr import ANPREngine

    img_path = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures" / "plate_ka198488.jpg"
    img = cv2.imread(str(img_path))
    assert img is not None
    engine = ANPREngine(min_interval_s=0)
    assert engine.fast_ok
    res = engine.read_track("KA-TEST", img, (0.0, 0.0, 1.0, 1.0))
    assert res["plate_text"] == "KA19P8488"
    assert res["ai_status"] == "REAL"
    assert res["format_valid"] is True
    import json

    json.dumps(res)
