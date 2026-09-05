from app.config import get_settings
from app.services.composio_notify import composio_status, notify_fleet_confirmed
from tests.test_auth import auth_header


def test_composio_disabled_without_key():
    get_settings.cache_clear()
    status = composio_status()
    assert status["honesty"] == "DISABLED"
    assert status["provider"] == "Composio"


def test_composio_notify_noop_without_key():
    class _Ev:
        public_code = "EVENT-TEST"
        event_type = type("T", (), {"value": "POTHOLE"})()
        extra = {}
        id = "x"

    out = notify_fleet_confirmed(_Ev())
    assert out["honesty"] == "DISABLED"


def test_capabilities_includes_composio(client, admin_token):
    r = client.get("/ai/capabilities", headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "composio" in body
    assert body["composio"]["honesty"] in {"REAL", "DISABLED"}


def test_second_bus_calls_composio_hook(client, admin_token, monkeypatch):
    called = {}

    def fake(ev):
        called["code"] = ev.public_code
        return {"ok": True, "honesty": "REAL"}

    monkeypatch.setattr("app.services.observations.notify_fleet_confirmed", fake)
    headers = auth_header(admin_token)
    a = client.post(
        "/observations",
        json={
            "event_type": "POTHOLE",
            "severity": "HIGH",
            "latitude": 28.7010,
            "longitude": 77.1010,
            "source_type": "PHONE",
            "source_id": "BUS-042",
            "confidence": 0.8,
            "simulated": True,
        },
        headers=headers,
    )
    b = client.post(
        "/observations",
        json={
            "event_type": "POTHOLE",
            "severity": "HIGH",
            "latitude": 28.70105,
            "longitude": 77.10104,
            "source_type": "PHONE",
            "source_id": "BUS-017",
            "confidence": 0.8,
            "simulated": True,
        },
        headers=headers,
    )
    assert a.status_code == 200 and b.status_code == 200
    assert b.json()["event"]["extra"]["patrol_state"] == "FLEET_CONFIRMED"
    assert called.get("code")
