from app.services.camera_bridge import assert_snapshot_url


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


JPEG = b"\xff\xd8\xff\xd9" + b"cctv-demo"


def test_presets_list_vendors(client, admin_token):
    r = client.get("/cameras/presets", headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["items"]}
    assert {"BROWSER", "FILE_EXPORT", "CP_PLUS", "HP_DVR", "CUBIC_WIFI", "RTSP_HINT"} <= ids
    rtsp = next(row for row in r.json()["items"] if row["id"] == "RTSP_HINT")
    assert rtsp["honesty"] == "DISABLED"
    assert "cctv-bridge.ps1" in rtsp["how"]
    assert "-Loop" in rtsp["how"]
    assert "run_camera.py" in rtsp["how"]
    body = r.json()
    assert "cctv-bridge.ps1" in body["note"]


def test_field_token_can_register_camera(client, admin_token):
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-017"}, headers=auth_header(admin_token)).json()["code"]
    token = client.post("/auth/field-join", json={"code": code}).json()["access_token"]
    r = client.post(
        "/cameras",
        headers=auth_header(token),
        json={"code": "CAM-FIELD-01", "vendor": "BROWSER", "bay": "FRONT"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "CAM-FIELD-01"


def test_register_and_cctv_still(client, admin_token):
    made = client.post(
        "/cameras",
        headers=auth_header(admin_token),
        json={"code": "CAM-CPPLUS-01", "vendor": "CP_PLUS", "bay": "FRONT", "bus_code": "BUS-042", "kind": "BUS_CCTV"},
    )
    assert made.status_code == 200, made.text
    assert made.json()["code"] == "CAM-CPPLUS-01"

    still = client.post(
        "/ingest/cctv/still",
        headers=auth_header(admin_token),
        files={"file": ("ch1.jpg", JPEG, "image/jpeg")},
        data={
            "latitude": "28.63",
            "longitude": "77.22",
            "source_id": "CAM-CPPLUS-01",
            "bus_id": "BUS-042",
            "camera_bay": "FRONT",
            "vendor": "CP_PLUS",
            "source_kind": "BUS_CCTV",
        },
    )
    assert still.status_code == 200, still.text
    ev = still.json()["event"]
    assert ev["extra"]["connector"] == "any-camera-bridge"
    assert ev["extra"]["vendor"] == "CP_PLUS"
    assert ev["extra"]["camera_bay"] == "FRONT"

    listed = client.get("/cameras", headers=auth_header(admin_token))
    assert listed.status_code == 200
    assert any(row["code"] == "CAM-CPPLUS-01" for row in listed.json())


def test_cabin_cctv_cannot_invent_pothole(client, admin_token):
    r = client.post(
        "/ingest/cctv/still",
        headers=auth_header(admin_token),
        files={"file": ("cabin.jpg", JPEG, "image/jpeg")},
        data={"source_id": "CAM-CABIN", "camera_bay": "CABIN", "imu_mag": "3.1", "vendor": "CUBIC_WIFI"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["event"]["extra"]["camera_bay"] == "CABIN"
    assert r.json()["event"]["event_type"] != "POTHOLE"


def test_snapshot_url_rejects_rtsp_and_metadata():
    try:
        assert_snapshot_url("rtsp://admin:pass@192.168.1.64:554/stream")
        raise AssertionError("rtsp should fail")
    except ValueError as exc:
        assert "RTSP" in str(exc)
    try:
        assert_snapshot_url("http://169.254.169.254/latest/meta-data")
        raise AssertionError("metadata should fail")
    except ValueError as exc:
        assert "not allowed" in str(exc)
    try:
        assert_snapshot_url("http://127.0.0.1/snapshot.jpg")
        raise AssertionError("loopback should fail")
    except ValueError as exc:
        assert "not allowed" in str(exc)


def test_snapshot_url_allows_lan_when_enabled():
    assert_snapshot_url("http://192.168.1.64/cgi-bin/snapshot.cgi?channel=1", allow_private=True)


def test_snapshot_url_blocks_lan_when_disabled():
    try:
        assert_snapshot_url("http://10.0.0.8/snapshot.jpg", allow_private=False)
        raise AssertionError("private should fail")
    except ValueError as exc:
        assert "LAN" in str(exc)


def test_pull_rejects_rtsp(client, admin_token):
    r = client.post(
        "/cameras/pull",
        headers=auth_header(admin_token),
        json={"snapshot_url": "rtsp://192.168.1.64/stream", "code": "CAM-BAD"},
    )
    assert r.status_code == 400
    assert "RTSP" in r.json()["detail"]
