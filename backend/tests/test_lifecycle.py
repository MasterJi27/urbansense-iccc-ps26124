from tests.test_auth import auth_header


def test_qr_bus_lookup(client, admin_token):
    r = client.get("/qr/lookup", params={"payload": "urbansense://bus/BUS-042"}, headers=auth_header(admin_token))
    assert r.status_code == 200
    assert r.json()["found"] is True
    assert r.json()["code"] == "BUS-042"


def test_work_order_lifecycle(client, admin_token):
    obs = client.post(
        "/observations",
        json={
            "event_type": "ROAD_DAMAGE",
            "latitude": 28.61,
            "longitude": 77.21,
            "source_type": "PHONE",
            "source_id": "NODE-X",
            "confidence": 0.7,
            "simulated": True,
        },
        headers=auth_header(admin_token),
    )
    event_id = obs.json()["event"]["id"]
    wo = client.post(
        "/work-orders",
        json={"event_id": event_id, "title": "Fix road damage"},
        headers=auth_header(admin_token),
    )
    assert wo.status_code == 200, wo.text
    wo_id = wo.json()["id"]
    repair = client.post(
        f"/work-orders/{wo_id}/repair",
        json={"notes": "Patched", "evidence_url": "http://localhost/evidence/demo.jpg"},
        headers=auth_header(admin_token),
    )
    assert repair.json()["status"] == "RE_VERIFICATION"
    done = client.post(
        f"/work-orders/{wo_id}/verify",
        json={"passed": True, "notes": "Clear"},
        headers=auth_header(admin_token),
    )
    assert done.json()["status"] == "RESOLVED"
    ev = client.get(f"/events/{event_id}", headers=auth_header(admin_token))
    assert ev.json()["status"] == "RESOLVED"


def test_repair_failed_reopens(client, admin_token):
    obs = client.post(
        "/observations",
        json={
            "event_type": "WATERLOGGING",
            "latitude": 28.62,
            "longitude": 77.22,
            "source_type": "INSPECTOR",
            "source_id": "INSPECTOR",
            "confidence": 0.9,
        },
        headers=auth_header(admin_token),
    )
    event_id = obs.json()["event"]["id"]
    wo = client.post(
        "/work-orders",
        json={"event_id": event_id, "title": "Drain"},
        headers=auth_header(admin_token),
    )
    client.post(f"/work-orders/{wo.json()['id']}/repair", json={"notes": "attempt"}, headers=auth_header(admin_token))
    failed = client.post(
        f"/work-orders/{wo.json()['id']}/verify",
        json={"passed": False, "notes": "Still pooling"},
        headers=auth_header(admin_token),
    )
    assert failed.json()["status"] == "FAILED"
    ev = client.get(f"/events/{event_id}", headers=auth_header(admin_token))
    assert ev.json()["status"] == "REOPENED"
