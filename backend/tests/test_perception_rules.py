import sys
from pathlib import Path

from tests.test_auth import auth_header

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai"))

from urbansense_ai.analytics import classify_los, rash_driving
from urbansense_ai.mapping import rdd_event
from urbansense_ai.plates import indian_format_ok


def test_rdd_mapping():
    assert rdd_event("Potholes") == ("POTHOLE", "HIGH")


def test_indian_plate_not_turkish():
    assert indian_format_ok("DL01AB1234")
    assert not indian_format_ok("34ABC123")


def test_los_jam():
    assert classify_los(25, 5.0)[0] == "F"
    assert rash_driving(100, 60)


def test_ai_capabilities_auth(client, admin_token):
    r = client.get("/ai/capabilities", headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "road_damage" in body or "available" in body or "hint" in body
