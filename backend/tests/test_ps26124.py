def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


JPEG = b"\xff\xd8\xff\xd9" + b"not-a-real-photo"


def test_ps26124_coverage(client, admin_token):
    r = client.get("/ai/ps26124", headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["problem_statement"] == "26124"
    ids = {row["id"] for row in body["items"]}
    assert "potholes" in ids
    assert "multicam" in ids
    assert "waterlogging" in ids
    assert body["counts"]["SIMULATED"] >= 1
    assert "FRONT" in body["camera_bays"]
    assert "CABIN" in body["camera_bays"]
    vehicles = next(row for row in body["items"] if row["id"] == "vehicles")
    assert vehicles["status"] == "RULE_BASED"
    assert "Azure Vision" in vehicles["how"]
    vru = next(row for row in body["items"] if row["id"] == "vru")
    assert "person net is off" in vru["how"]


def test_cabin_still_does_not_become_pothole(client, admin_token):
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("cabin.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.61", "longitude": "77.20", "source_id": "BUS-042-CABIN", "imu_mag": "2.4", "camera_bay": "CABIN"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["event"]["event_type"] != "POTHOLE"
    assert r.json()["event"]["extra"]["camera_bay"] == "CABIN"


def test_bus_stream_frame_front(client, admin_token):
    r = client.post(
        "/ingest/bus/stream-frame",
        headers=auth_header(admin_token),
        files={"file": ("front.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.612", "longitude": "77.201", "source_id": "BUS-042-FRONT", "camera_bay": "FRONT"},
    )
    assert r.status_code == 200, r.text
    ev = r.json()["event"]
    assert ev["extra"]["camera_bay"] == "FRONT"
