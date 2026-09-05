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
