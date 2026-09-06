import json

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.test_auth import auth_header


def test_field_live_ws_rejects_iccc(client, admin_token):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/field-live?token={admin_token}"):
            pass
    assert exc.value.code in {4403, 1008, 403, 1006}


def test_field_live_ws_broadcasts_to_iccc(client, admin_token):
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-017"}, headers=auth_header(admin_token)).json()["code"]
    field = client.post("/auth/field-join", json={"code": code}).json()["access_token"]
    with client.websocket_connect(f"/ws/live?token={admin_token}") as desk:
        with client.websocket_connect(f"/ws/field-live?token={field}") as phone:
            phone.send_text(
                json.dumps(
                    {
                        "sensor_code": "BUS-017-P1",
                        "bus_code": "BUS-017",
                        "latitude": 28.61,
                        "longitude": 77.21,
                        "person_count": 1,
                        "overlay_mode": "ondevice",
                        "overlay_backend": "webgpu",
                        "infer_ms": 42,
                        "imu_mag": 1.2,
                        "imu_ax": 0.05,
                        "imu_ay": -0.1,
                        "imu_az": 9.7,
                        "gyro_z": 0.02,
                        "gps_accuracy": 6.5,
                        "gps_ok": True,
                        "last_boxes": [
                            {
                                "klass": "Pothole",
                                "event_type": "POTHOLE",
                                "confidence": 0.6,
                                "bbox": [0.1, 0.2, 0.3, 0.4],
                                "track_id": "t1",
                                "hits": 4,
                            }
                        ],
                    }
                )
            )
        msg = json.loads(desk.receive_text())
    assert msg["type"] == "live.heartbeat"
    assert msg["bus_code"] == "BUS-017"
    assert msg["last_boxes"][0]["klass"] == "Pothole"
    assert msg["last_boxes"][0]["track_id"] == "t1"
    assert msg["last_boxes"][0]["hits"] == 4
    assert msg["overlay_backend"] == "webgpu"
    assert msg["infer_ms"] == 42
    assert msg["person_count"] == 1
    assert msg["imu_mag"] == 1.2
    assert msg["imu_az"] == 9.7
    assert msg["gps_ok"] is True
    assert msg["gps_accuracy"] == 6.5
