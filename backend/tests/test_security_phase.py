from app.config import get_settings
from app.main import app
from app.services.bbox_severity import severity_from_boxes
from app.services.departments import department_for
from app.services.dpdp import mask_contact, mask_plate
from app.services.extras import sanitize_extra
from app.services.redact import redact_text
from tests.test_auth import auth_header


def test_docs_follow_app_env():
    assert get_settings().is_development
    assert app.docs_url == "/docs"


def test_login_token_is_iccc_scope(client, admin_token):
    me = client.get("/auth/me", headers=auth_header(admin_token))
    assert me.status_code == 200
    assert me.json()["scope"] == "iccc"


def test_field_token_cannot_open_settings(client, admin_token):
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-017"}, headers=auth_header(admin_token)).json()["code"]
    token = client.post("/auth/field-join", json={"code": code}).json()["access_token"]
    r = client.get("/settings", headers=auth_header(token))
    assert r.status_code == 403


def test_field_token_cannot_list_events(client, admin_token):
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-017"}, headers=auth_header(admin_token)).json()["code"]
    token = client.post("/auth/field-join", json={"code": code}).json()["access_token"]
    r = client.get("/events", headers=auth_header(token))
    assert r.status_code == 403


def test_operator_cannot_register_camera(client, operator_token):
    r = client.post(
        "/cameras",
        headers=auth_header(operator_token),
        json={"code": "CAM-NOPE", "vendor": "CP_PLUS", "bay": "FRONT"},
    )
    assert r.status_code == 403


def test_operator_cannot_run_demo(client, operator_token):
    r = client.post("/demo/start", headers=auth_header(operator_token), json={"step": "pothole_a"})
    assert r.status_code == 403


def test_sanitize_extra_drops_secrets():
    cleaned = sanitize_extra({"password": "x", "token": "y", "ai_status": "REAL", "nested": {"secret": "z", "ok": 1}})
    assert cleaned is not None
    assert "password" not in cleaned
    assert "token" not in cleaned
    assert cleaned["ai_status"] == "REAL"
    assert cleaned["nested"]["ok"] == 1
    assert "secret" not in cleaned["nested"]


def test_redact_strips_maps_key_and_bearer():
    text = redact_text("url?subscription-key=abc123 and Bearer eyJhbGciOi.secret")
    assert "abc123" not in text
    assert "eyJhbGciOi.secret" not in text
    assert "[redacted]" in text


def test_plate_and_contact_mask():
    assert mask_plate("DL8CAF4321").endswith("••••")
    assert "4321" not in (mask_contact("9876543210") or "")
    assert (mask_contact("9876543210") or "").endswith("3210")


def test_department_pothole_is_pwd():
    row = department_for("POTHOLE")
    assert row["department_code"] == "PWD_ROADS"
    assert row["department_honesty"] == "RULE_BASED"


def test_bbox_area_severity_never_critical():
    low = severity_from_boxes([[0, 0, 10, 10]], frame_w=640, frame_h=640)
    high = severity_from_boxes([[0, 0, 400, 400]], frame_w=640, frame_h=640)
    assert low["severity"].value == "LOW"
    assert high["severity"].value == "HIGH"
    assert high["honesty"] == "RULE_BASED"


def test_citizen_own_tickets_hide_contact(client):
    r = client.post(
        "/citizen/report",
        json={
            "latitude": 28.63,
            "longitude": 77.21,
            "description": "joint noise",
            "contact": "9876543210",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claim_token"]
    assert body["contact_masked"].endswith("3210")
    tickets = client.get("/citizen/tickets", params={"claim": body["claim_token"]})
    assert tickets.status_code == 200
    items = tickets.json()["items"]
    assert items
    extra = items[0]["extra"] or {}
    assert extra.get("citizen_contact") != "9876543210"
    assert extra.get("department_code") == "PWD_BRIDGE"


def test_login_locks_after_five_failures(client, admin_token):
    for _ in range(5):
        bad = client.post("/auth/login", json={"email": "admin@test.local", "password": "wrong-pass"})
        assert bad.status_code == 401
    locked = client.post("/auth/login", json={"email": "admin@test.local", "password": "password12"})
    assert locked.status_code == 429


def test_extra_drops_secrets_and_keeps_desk(client, admin_token):
    made = client.post(
        "/observations",
        headers=auth_header(admin_token),
        json={
            "event_type": "POTHOLE",
            "severity": "HIGH",
            "latitude": 28.63,
            "longitude": 77.21,
            "source_type": "PHONE",
            "source_id": "BUS-042",
            "confidence": 0.7,
            "simulated": False,
            "extra": {
                "password": "UrbanSense@2026",
                "department_desk": "PWD Roads",
                "department_code": "PWD_ROADS",
            },
        },
    )
    assert made.status_code == 200, made.text
    extra = made.json()["event"]["extra"] or {}
    assert extra.get("password") is None
    assert extra.get("department_code") == "PWD_ROADS"


def test_operator_event_masks_plate(client, admin_token, operator_token):
    made = client.post(
        "/observations",
        headers=auth_header(admin_token),
        json={
            "event_type": "RASH_DRIVING",
            "severity": "HIGH",
            "latitude": 28.63,
            "longitude": 77.21,
            "source_type": "PHONE",
            "source_id": "BUS-042",
            "confidence": 0.8,
            "plate_text": "DL8CAF4321",
            "plate_confidence": 0.9,
            "simulated": False,
        },
    )
    assert made.status_code == 200, made.text
    eid = made.json()["event"]["id"]
    admin = client.get(f"/events/{eid}", headers=auth_header(admin_token))
    assert any(o.get("plate_text") == "DL8CAF4321" for o in admin.json().get("observations") or [])
    op = client.get(f"/events/{eid}", headers=auth_header(operator_token))
    assert op.status_code == 200
    plates = [o.get("plate_text") for o in op.json().get("observations") or [] if o.get("plate_text")]
    assert plates
    assert all("••••" in plate for plate in plates)
