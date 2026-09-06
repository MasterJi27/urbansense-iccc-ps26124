from types import SimpleNamespace

from app.config import get_settings
from app.services.composio_notify import (
    _execute_payload,
    composio_status,
    notify_fleet_confirmed,
    reset_last_notify,
)
from tests.test_auth import auth_header


def test_composio_disabled_without_key():
    get_settings.cache_clear()
    reset_last_notify()
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
    assert "last_error" in body["composio"] or body["composio"]["honesty"] == "DISABLED"


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


def _ready_settings(**overrides):
    base = dict(
        composio_api_key="ak_test_not_real",
        composio_notify_to="officer@example.com",
        composio_notify_channel="gmail",
        composio_entity_id="default",
        composio_connected_account_id="gmail_test_account",
        public_base_url="https://example.test",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_execute_payload_prefers_connected_account():
    settings = _ready_settings()
    payload = _execute_payload(settings, {"recipient_email": "officer@example.com"})
    assert payload["connected_account_id"] == "gmail_test_account"
    assert "user_id" not in payload


def test_composio_records_http_body_failure(monkeypatch):
    reset_last_notify()
    monkeypatch.setattr("app.services.composio_notify.get_settings", lambda: _ready_settings())

    class _Resp:
        status_code = 200
        text = '{"successful": false, "error": "No connected account found for toolkit gmail"}'

        def json(self):
            return {"successful": False, "error": "No connected account found for toolkit gmail"}

    class _Client:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("app.services.composio_notify.httpx.Client", _Client)

    class _Ev:
        public_code = "EVENT-TEST"
        event_type = type("T", (), {"value": "POTHOLE"})()
        extra = {}
        id = "x"

    out = notify_fleet_confirmed(_Ev())
    assert out["ok"] is False
    status = composio_status()
    assert status["honesty"] == "REAL"
    assert status["last_ok"] is False
    assert "connected account" in (status["last_error"] or "").lower()
    assert "Last ping failed" in status["note"]


def test_composio_records_http_404(monkeypatch):
    reset_last_notify()
    monkeypatch.setattr("app.services.composio_notify.get_settings", lambda: _ready_settings())

    class _Resp:
        status_code = 404
        text = '{"error":{"message":"No connected account found for user ID default for toolkit gmail"}}'

        def json(self):
            return {
                "error": {
                    "message": "No connected account found for user ID default for toolkit gmail"
                }
            }

    class _Client:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("app.services.composio_notify.httpx.Client", _Client)

    class _Ev:
        public_code = "EVENT-TEST"
        event_type = type("T", (), {"value": "POTHOLE"})()
        extra = {}
        id = "x"

    out = notify_fleet_confirmed(_Ev())
    assert out["ok"] is False
    assert out["status_code"] == 404
    assert "default" in (out.get("error") or "")
