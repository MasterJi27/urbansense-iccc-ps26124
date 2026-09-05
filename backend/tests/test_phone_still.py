def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


JPEG = b"\xff\xd8\xff\xd9" + b"not-a-real-photo"


def test_phone_still_without_azure_vision(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("bump.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.63", "longitude": "77.22", "source_id": "NODE-PHONE-01", "imu_mag": "18"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_event"] is True
    extra = body["event"]["extra"]
    assert extra["method"] == "phone-imu-shake"
    assert extra["ai_status"] == "DISABLED"
    assert body["event"]["event_type"] == "POTHOLE"


def test_phone_still_projects_pin_ahead(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    from app.config import get_settings
    import app.api.routes.ingest as ingest_mod

    get_settings.cache_clear()

    def fake_rdd(_data):
        return {
            "ok": True,
            "detections": [
                {
                    "klass": "Pothole",
                    "class_id": "D40",
                    "confidence": 0.72,
                    "bbox": [0.3, 0.4, 0.5, 0.5],
                    "event_type": "POTHOLE",
                    "severity": "HIGH",
                }
            ],
        }

    monkeypatch.setattr(ingest_mod, "detect_rdd", fake_rdd)
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("ahead.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.63", "longitude": "77.22", "source_id": "FIELD-AHEAD", "heading": "90"},
    )
    assert r.status_code == 200, r.text
    ev = r.json()["event"]
    assert ev["event_type"] == "POTHOLE"
    assert ev["longitude"] > 77.22
    assert ev["extra"]["gps_ahead"]["used"] is True
    assert ev["extra"]["gps_ahead"]["honesty"] == "RULE_BASED"


def test_phone_still_field_iphone_is_not_a_bus_fk(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("field.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.61", "longitude": "77.21", "source_id": "FIELD-IPHONE", "bus_id": "FIELD-IPHONE"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["observation"]["source_id"] == "FIELD-IPHONE"
    assert body["observation"]["bus_id"] is None


def test_phone_still_resolves_bus_code(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("bus.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.61", "longitude": "77.21", "source_id": "BUS-042-FRONT", "bus_id": "BUS-042", "imu_mag": "1.9"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["observation"]["bus_id"]


def test_phone_still_repeat_same_filename(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    payload = {
        "headers": auth_header(admin_token),
        "files": {"file": ("field-still.jpg", JPEG, "image/jpeg")},
        "data": {"latitude": "28.61", "longitude": "77.21", "source_id": "BUS-017-P1", "bus_id": "BUS-017"},
    }
    a = client.post("/ingest/phone/still", **payload)
    b = client.post("/ingest/phone/still", **payload)
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert a.json()["observation"]["id"] != b.json()["observation"]["id"]


def test_phone_still_rejects_empty(client, admin_token):
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("empty.jpg", b"", "image/jpeg")},
        data={"latitude": "28.63", "longitude": "77.22", "source_id": "NODE-PHONE-01"},
    )
    assert r.status_code == 400


def test_phone_still_rejects_non_image(client, admin_token):
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("notes.txt", b"hello-not-an-image", "text/plain")},
        data={"latitude": "28.63", "longitude": "77.22", "source_id": "NODE-PHONE-01"},
    )
    assert r.status_code == 400


def test_phone_still_rejects_oversize(client, admin_token):
    huge = b"\xff\xd8" + (b"\x00" * 3_600_000)
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("huge.jpg", huge, "image/jpeg")},
        data={"latitude": "28.63", "longitude": "77.22", "source_id": "NODE-PHONE-01"},
    )
    assert r.status_code == 400


def test_phone_probe_does_not_ingest(client, admin_token):
    r = client.post(
        "/ingest/phone/probe",
        headers=auth_header(admin_token),
        files={"file": ("probe.jpg", JPEG, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ingested"] is False
    assert body["ok"] is True
    assert "vision" in body
    assert "stack" in body


def test_edge_status(client, admin_token):
    r = client.get("/ingest/edge/status", headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["openai"]["ai_status"] == "DISABLED"
    assert body["vision"]["configured"] is False
    assert body["content_safety"]["configured"] is False


def test_officer_brief_disabled(client, admin_token):
    still = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("bump.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.63", "longitude": "77.21", "source_id": "NODE-PHONE-02", "imu_mag": "2.1"},
    )
    assert still.status_code == 200, still.text
    event_id = still.json()["event"]["id"]
    r = client.post(f"/events/{event_id}/brief", headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["openai"]["ai_status"] == "DISABLED"


def test_phone_still_maps_mocked_vision(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    from app.config import get_settings
    import app.api.routes.ingest as ingest_mod

    get_settings.cache_clear()

    def fake_vision(_data):
        return {
            "ok": True,
            "ai_status": "REAL",
            "engine_status": "REAL",
            "provider": "Azure AI Vision",
            "method": "azure-ai-vision",
            "model": "azure-ai-vision-image-analysis",
            "caption": "a cracked road",
            "tags": ["crack", "road"],
            "mapped_event_type": "ROAD_DAMAGE",
            "mapped_severity": "MEDIUM",
        }

    monkeypatch.setattr(ingest_mod, "analyze_still", fake_vision)
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("road.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.64", "longitude": "77.23", "source_id": "NODE-PHONE-03"},
    )
    assert r.status_code == 200, r.text
    ev = r.json()["event"]
    assert ev["event_type"] == "ROAD_DAMAGE"
    assert ev["extra"]["caption"] == "a cracked road"
    assert ev["extra"]["method"] == "azure-ai-vision"
