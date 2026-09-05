from datetime import datetime, timezone

from tests.test_auth import auth_header


def _obs(**kwargs):
    base = {
        "event_type": "POTHOLE",
        "severity": "HIGH",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "gps_accuracy": 4.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_type": "PHONE",
        "source_id": "BUS-042",
        "confidence": 0.82,
        "simulated": True,
    }
    base.update(kwargs)
    return base


def test_observation_creates_event(client, admin_token):
    r = client.post("/observations", json=_obs(), headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_event"] is True
    assert body["event"]["public_code"].startswith("EVENT-")
    assert body["observation"]["id"]


def test_nearby_observations_fuse(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-042", latitude=28.6500, longitude=77.2300, confidence=0.82),
        headers=auth_header(admin_token),
    )
    b = client.post(
        "/observations",
        json=_obs(source_id="BUS-017", latitude=28.65012, longitude=77.23008, confidence=0.89),
        headers=auth_header(admin_token),
    )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["event"]["id"] == b.json()["event"]["id"]
    assert b.json()["fused"] is True
    ev = client.get(f"/events/{b.json()['event']['id']}", headers=auth_header(admin_token))
    assert ev.status_code == 200
    detail = ev.json()
    assert detail["observation_count"] >= 2
    assert detail["source_count"] >= 2
    assert "spatial proximity" in detail["fusion_reason"]
    assert detail["status"] == "CONFIRMED"
    assert detail["extra"]["patrol_state"] == "FLEET_CONFIRMED"


def test_same_bus_does_not_self_confirm(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-088", latitude=28.6410, longitude=77.2210),
        headers=auth_header(admin_token),
    )
    b = client.post(
        "/observations",
        json=_obs(source_id="BUS-088", latitude=28.64105, longitude=77.22104),
        headers=auth_header(admin_token),
    )
    assert a.status_code == 200 and b.status_code == 200
    ev = client.get(f"/events/{a.json()['event']['id']}", headers=auth_header(admin_token)).json()
    assert ev["source_count"] == 1
    assert ev["observation_count"] >= 2
    assert ev["status"] == "UNVERIFIED"
    assert ev["extra"]["patrol_state"] == "FIRST_SIGHTING"


def test_demo_steps_a_and_b_confirm(client, admin_token):
    a = client.post("/demo/start", json={"step": "pothole_a"}, headers=auth_header(admin_token))
    b = client.post("/demo/start", json={"step": "pothole_b"}, headers=auth_header(admin_token))
    assert a.status_code == 200 and b.status_code == 200, a.text + b.text
    assert a.json()["event_id"] == b.json()["event_id"]
    ev = client.get(f"/events/{b.json()['event_id']}", headers=auth_header(admin_token)).json()
    assert ev["extra"]["patrol_state"] == "FLEET_CONFIRMED"
    assert ev["status"] == "CONFIRMED"


def test_ledger_same_bus_ignored(client, admin_token):
    a = client.post("/observations", json=_obs(source_id="BUS-077", latitude=28.6550, longitude=77.2410), headers=auth_header(admin_token))
    client.post("/observations", json=_obs(source_id="BUS-077", latitude=28.65505, longitude=77.24104), headers=auth_header(admin_token))
    ledger = client.get(f"/events/{a.json()['event']['id']}/ledger", headers=auth_header(admin_token)).json()
    assert ledger["patrol_state"] == "FIRST_SIGHTING"
    assert ledger["same_bus_ignored"] >= 1
    assert ledger["confirm"] is None


def _heartbeat(client, token, source_id, lat, lon, **extra):
    body = {
        "bus_code": source_id,
        "sensor_code": f"NODE-{source_id}",
        "latitude": lat,
        "longitude": lon,
        "heading": extra.get("heading", 90),
    }
    if extra.get("device_label"):
        client.post(
            "/sensor-nodes",
            json={"sensor_code": f"NODE-{source_id}", "bus_code": source_id, "device_label": extra["device_label"]},
            headers=auth_header(token),
        )
    return client.post("/sensor-nodes/heartbeat", json=body, headers=auth_header(token))


def test_same_bus_heartbeat_is_not_a_clear_pass(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-042", latitude=28.6700, longitude=77.2600),
        headers=auth_header(admin_token),
    )
    assert a.status_code == 200
    eid = a.json()["event"]["id"]
    for _ in range(3):
        hb = _heartbeat(client, admin_token, "BUS-042", 28.6700, 77.2600)
        assert hb.status_code == 200, hb.text
    ev = client.get(f"/events/{eid}", headers=auth_header(admin_token)).json()
    assert ev["extra"]["patrol_state"] == "FIRST_SIGHTING"
    assert ev["extra"].get("clear_same_bus_ignored", 0) >= 1
    assert ev["extra"].get("clear_passes") in (None, [])
    ledger = client.get(f"/events/{eid}/ledger", headers=auth_header(admin_token)).json()
    assert ledger["patrol_state"] == "FIRST_SIGHTING"
    assert ledger["clear_same_bus_ignored"] >= 1


def test_three_clear_passes_expire_first_sighting(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-042", latitude=28.6710, longitude=77.2610),
        headers=auth_header(admin_token),
    )
    eid = a.json()["event"]["id"]
    for src in ("BUS-088", "BUS-091", "BUS-003"):
        r = _heartbeat(client, admin_token, src, 28.6710, 77.2610)
        assert r.status_code == 200, r.text
    ev = client.get(f"/events/{eid}", headers=auth_header(admin_token)).json()
    assert ev["extra"]["patrol_state"] == "EXPIRED"
    assert ev["status"] == "UNVERIFIED"
    ledger = client.get(f"/events/{eid}/ledger", headers=auth_header(admin_token)).json()
    assert ledger["patrol_state"] == "EXPIRED"
    assert len(ledger["expired_by"]) >= 3
    assert "pothole gone" not in (ev["extra"].get("patrol_note") or "").lower()


def test_clear_passes_do_not_unconfirm_fleet(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-042", latitude=28.6720, longitude=77.2620),
        headers=auth_header(admin_token),
    )
    b = client.post(
        "/observations",
        json=_obs(source_id="BUS-017", latitude=28.67205, longitude=77.26204),
        headers=auth_header(admin_token),
    )
    eid = b.json()["event"]["id"]
    assert a.json()["event"]["id"] == eid
    for src in ("BUS-088", "BUS-091", "BUS-003"):
        _heartbeat(client, admin_token, src, 28.6720, 77.2620)
    ev = client.get(f"/events/{eid}", headers=auth_header(admin_token)).json()
    assert ev["extra"]["patrol_state"] == "FLEET_CONFIRMED"
    assert ev["status"] == "CONFIRMED"
    ledger = client.get(f"/events/{eid}/ledger", headers=auth_header(admin_token)).json()
    assert ledger["patrol_state"] == "FLEET_CONFIRMED"
    assert len(ledger["clear_passes"]) >= 3


def test_repair_verify_then_reopen(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-042", latitude=28.6730, longitude=77.2630),
        headers=auth_header(admin_token),
    )
    client.post(
        "/observations",
        json=_obs(source_id="BUS-017", latitude=28.67304, longitude=77.26303),
        headers=auth_header(admin_token),
    )
    eid = a.json()["event"]["id"]
    wo = client.post(
        "/work-orders",
        json={"event_id": eid, "title": "Patch cell", "description": "fleet audit"},
        headers=auth_header(admin_token),
    )
    assert wo.status_code == 200, wo.text
    repair = client.post(
        f"/work-orders/{wo.json()['id']}/repair",
        json={"notes": "contractor closed", "evidence_url": None},
        headers=auth_header(admin_token),
    )
    assert repair.status_code == 200, repair.text
    assert repair.json()["status"] == "RE_VERIFICATION"
    for src in ("BUS-071", "BUS-072"):
        r = _heartbeat(client, admin_token, src, 28.6730, 77.2630)
        assert r.status_code == 200, r.text
    ev = client.get(f"/events/{eid}", headers=auth_header(admin_token)).json()
    assert ev["extra"]["patrol_state"] == "REPAIR_VERIFIED"
    ledger = client.get(f"/events/{eid}/ledger", headers=auth_header(admin_token)).json()
    assert ledger["patrol_state"] == "REPAIR_VERIFIED"
    assert len(ledger["repair_verified_by"]) >= 2
    again = client.post(
        "/observations",
        json=_obs(source_id="BUS-099", latitude=28.67302, longitude=77.26302, confidence=0.9),
        headers=auth_header(admin_token),
    )
    assert again.status_code == 200
    ev2 = client.get(f"/events/{eid}", headers=auth_header(admin_token)).json()
    assert ev2["status"] == "REOPENED"
    assert ev2["extra"]["patrol_state"] == "FLEET_CONFIRMED"
    wo2 = client.get(f"/work-orders/{wo.json()['id']}", headers=auth_header(admin_token)).json()
    assert wo2["status"] == "FAILED"


def test_cabin_pass_does_not_expire(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="BUS-042", latitude=28.6740, longitude=77.2640),
        headers=auth_header(admin_token),
    )
    eid = a.json()["event"]["id"]
    client.post(
        "/buses",
        json={"code": "BUS-CABIN-T", "registration": "DL1TEST"},
        headers=auth_header(admin_token),
    )
    client.post(
        "/sensor-nodes",
        json={"sensor_code": "NODE-CABIN-T", "bus_code": "BUS-CABIN-T", "device_label": "CABIN"},
        headers=auth_header(admin_token),
    )
    for i in range(3):
        client.post(
            "/sensor-nodes/heartbeat",
            json={
                "sensor_code": "NODE-CABIN-T",
                "bus_code": f"BUS-CAB{i}",
                "latitude": 28.6740,
                "longitude": 77.2640,
            },
            headers=auth_header(admin_token),
        )
    ev = client.get(f"/events/{eid}", headers=auth_header(admin_token)).json()
    assert ev["extra"]["patrol_state"] == "FIRST_SIGHTING"
    assert ev["extra"].get("clear_passes") in (None, [])


def test_distant_observations_remain_separate(client, admin_token):
    a = client.post(
        "/observations",
        json=_obs(source_id="A", latitude=28.40, longitude=77.10),
        headers=auth_header(admin_token),
    )
    b = client.post(
        "/observations",
        json=_obs(source_id="B", latitude=28.70, longitude=77.50),
        headers=auth_header(admin_token),
    )
    assert a.json()["event"]["id"] != b.json()["event"]["id"]
