from pathlib import Path

from app.services.rdd_cloud import detect_rdd, rdd_cloud_status
from tests.test_auth import auth_header

JPEG = b"\xff\xd8\xff\xd9" + b"not-a-real-photo"


def test_rdd_status_does_not_crash():
    status = rdd_cloud_status()
    assert status["honesty"] in {"REAL", "DISABLED"}
    assert "onnxruntime-cpu" in status["runtime"]


def test_rdd_garbage_jpeg_has_no_boxes():
    out = detect_rdd(JPEG)
    assert out["detections"] == []


def test_health_reports_rdd(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["rdd"] in {"REAL", "DISABLED"}


def test_probe_returns_detections_key(client, admin_token):
    r = client.post(
        "/ingest/phone/probe",
        headers=auth_header(admin_token),
        files={"file": ("probe.jpg", JPEG, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ingested"] is False
    assert "detections" in body
    assert "rdd" in body
    assert body["vision"]["skipped"] is True


def test_capabilities_exposes_cloud_rdd(client, admin_token):
    r = client.get("/ai/capabilities", headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "road_damage" in body
    assert body["road_damage"]["honesty"] in {"REAL", "DISABLED"}


def test_rdd_fixture_if_present():
    path = Path(__file__).resolve().parent / "fixtures" / "pothole_big.jpg"
    if not path.is_file():
        return
    out = detect_rdd(path.read_bytes())
    if rdd_cloud_status()["honesty"] != "REAL":
        return
    assert out["ok"] is True
    assert out["count"] >= 1
