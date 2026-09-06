from tests.test_auth import auth_header


def test_heartbeat_stores_live_boxes(client, admin_token):
    r = client.post(
        "/sensor-nodes/heartbeat",
        json={
            "sensor_code": "BUS-017-P1",
            "bus_code": "BUS-017",
            "latitude": 28.61,
            "longitude": 77.21,
            "person_count": 2,
            "overlay_fps": 6.0,
            "overlay_mode": "ondevice",
            "overlay_backend": "wasm",
            "infer_ms": 88,
            "last_boxes": [
                {
                    "klass": "Pothole",
                    "event_type": "POTHOLE",
                    "confidence": 0.52,
                    "bbox": [0.1, 0.2, 0.4, 0.5],
                    "track_id": "t9",
                    "hits": 3,
                }
            ],
        },
        headers=auth_header(admin_token),
    )
    assert r.status_code == 200, r.text
    nodes = client.get("/sensor-nodes", headers=auth_header(admin_token))
    assert nodes.status_code == 200
    row = next(n for n in nodes.json() if n["code"] == "BUS-017-P1")
    assert row["person_count"] == 2
    assert row["last_boxes"][0]["klass"] == "Pothole"
    assert row["last_boxes"][0]["bbox"][0] == 0.1
    assert row["last_boxes"][0]["track_id"] == "t9"
    assert row["last_boxes"][0]["hits"] == 3


def test_heartbeat_keeps_coords_and_wires_imu(client, admin_token):
    first = client.post(
        "/sensor-nodes/heartbeat",
        json={
            "sensor_code": "BUS-017-P1",
            "bus_code": "BUS-017",
            "latitude": 28.61,
            "longitude": 77.21,
        },
        headers=auth_header(admin_token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["bus_code"] == "BUS-017"
    second = client.post(
        "/sensor-nodes/heartbeat",
        json={
            "sensor_code": "BUS-017-P1",
            "bus_code": "BUS-017",
            "imu_mag": 1.4,
            "imu_ax": 0.1,
            "imu_ay": 0.2,
            "imu_az": 9.6,
            "gyro_z": 0.05,
            "gps_accuracy": 8.0,
            "gps_ok": False,
        },
        headers=auth_header(admin_token),
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["latitude"] == 28.61
    assert body["longitude"] == 77.21
    assert body["imu_mag"] == 1.4
    assert body["imu_ax"] == 0.1
    assert body["gps_ok"] is False
    nodes = client.get("/sensor-nodes", headers=auth_header(admin_token))
    row = next(n for n in nodes.json() if n["code"] == "BUS-017-P1")
    assert row["latitude"] == 28.61
    assert row["longitude"] == 77.21
    buses = client.get("/buses", headers=auth_header(admin_token))
    assert any(b["code"] == "BUS-017" for b in buses.json())
