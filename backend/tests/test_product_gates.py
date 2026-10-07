"""One check per product gate added for the field desk."""

from types import SimpleNamespace

from app.config import get_settings
from app.security import hash_password
from app.services.composio_notify import notify_fleet_confirmed
from tests.test_auth import auth_header
from tests.test_phone_still import JPEG


def _still(client, token, **data):
    payload = {"gps_accuracy": "8", "latitude": "28.70", "longitude": "77.30", "source_id": "NODE-GATE"}
    payload.update(data)
    return client.post(
        "/ingest/phone/still",
        headers=auth_header(token),
        files={"file": ("bump.jpg", JPEG, "image/jpeg")},
        data=payload,
    )


def test_missing_gps_accuracy_is_refused(client, admin_token):
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("bump.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.70", "longitude": "77.30", "source_id": "NODE-NOACC"},
    )
    assert r.status_code == 400
    assert "accuracy" in r.text.lower()


def test_breaker_outside_25m_still_files(client, admin_token):
    made = client.post(
        "/assets",
        headers=auth_header(admin_token),
        json={
            "code": "BRK-FAR",
            "asset_type": "ROAD",
            "name": "Speed breaker",
            "latitude": 28.64,
            "longitude": 77.23,
        },
    )
    assert made.status_code == 200, made.text
    r = _still(client, admin_token, latitude="28.70", longitude="77.30", source_id="NODE-FAR-BRK")
    assert r.status_code == 200, r.text


def test_csv_skips_seed_and_keeps_field(client, admin_token):
    live = _still(client, admin_token, source_id="NODE-CSV")
    assert live.status_code == 200, live.text
    code = live.json()["event"]["public_code"]
    seeded = client.post(
        "/observations",
        headers=auth_header(admin_token),
        json={
            "event_type": "POTHOLE",
            "latitude": 28.5,
            "longitude": 77.1,
            "source_type": "PHONE",
            "source_id": "SEED-ROW",
            "confidence": 0.4,
            "simulated": True,
            "extra": {"payload_kind": "SEED"},
        },
    )
    assert seeded.status_code == 200, seeded.text
    csv = client.get("/events/export.csv", headers=auth_header(admin_token))
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    body = csv.text
    assert code in body
    assert "SEED-ROW" not in body
    assert "lat" in body.splitlines()[0]


def test_repair_due_only_inside_40m(client, admin_token):
    filed = _still(client, admin_token, latitude="28.81", longitude="77.41", source_id="NODE-REPAIR")
    assert filed.status_code == 200, filed.text
    event_id = filed.json()["event"]["id"]
    wo = client.post(
        "/work-orders",
        headers=auth_header(admin_token),
        json={"event_id": event_id, "title": "Patch"},
    )
    assert wo.status_code == 200, wo.text
    repair = client.post(
        f"/work-orders/{wo.json()['id']}/repair",
        headers=auth_header(admin_token),
        json={"notes": "Filled"},
    )
    assert repair.json()["status"] == "RE_VERIFICATION"
    near = client.get(
        "/ingest/repair-due",
        params={"latitude": 28.81, "longitude": 77.41},
        headers=auth_header(admin_token),
    )
    assert near.status_code == 200
    assert near.json()["due"] is True
    assert near.json()["event_code"] == filed.json()["event"]["public_code"]
    far = client.get(
        "/ingest/repair-due",
        params={"latitude": 27.0, "longitude": 76.0},
        headers=auth_header(admin_token),
    )
    assert far.json()["due"] is False


def test_citizen_ticket_says_waiting(client):
    report = client.post(
        "/citizen/report",
        json={"latitude": 28.62, "longitude": 77.22, "description": "crack by the stop"},
    )
    assert report.status_code == 200, report.text
    claim = report.json()["claim_token"]
    tickets = client.get("/citizen/tickets", params={"claim": claim})
    assert tickets.status_code == 200
    assert tickets.json()["items"][0]["public_status"] == "waiting"


def test_demo_password_blocked_when_not_development(client, db, monkeypatch):
    from app.models.user import User, UserRole

    db.add(
        User(
            email="jury@test.local",
            full_name="Jury",
            hashed_password=hash_password("UrbanSense@2026"),
            role=UserRole.ADMIN,
        )
    )
    db.commit()
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        blocked = client.post("/auth/login", json={"email": "jury@test.local", "password": "UrbanSense@2026"})
        assert blocked.status_code == 401
        assert "Demo password" in blocked.text
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()
    allowed = client.post("/auth/login", json={"email": "jury@test.local", "password": "UrbanSense@2026"})
    assert allowed.status_code == 200, allowed.text


def test_sms_webhook_fires_on_fleet_confirm(monkeypatch):
    monkeypatch.setenv("OFFICER_SMS_WEBHOOK", "https://example.test/sms")
    get_settings.cache_clear()
    calls = {}

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, timeout=8.0):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            calls["url"] = url
            calls["json"] = json
            return _Resp()

    monkeypatch.setattr("app.services.composio_notify.httpx.Client", _Client)
    try:
        event = SimpleNamespace(public_code="EVENT-SMS", event_type=SimpleNamespace(value="POTHOLE"), extra={}, id="ev1")
        out = notify_fleet_confirmed(event)
        assert calls["url"] == "https://example.test/sms"
        assert "FLEET_CONFIRMED" in calls["json"]["text"]
        assert out["sms"]["honesty"] == "REAL"
    finally:
        monkeypatch.delenv("OFFICER_SMS_WEBHOOK", raising=False)
        get_settings.cache_clear()
