from tests.test_auth import auth_header


def _pothole(source_id="BUS-042", lat=28.61, lon=77.21, extra=None):
    return {
        "event_type": "POTHOLE",
        "severity": "HIGH",
        "latitude": lat,
        "longitude": lon,
        "source_type": "PHONE",
        "source_id": source_id,
        "confidence": 0.8,
        "simulated": False,
        "extra": extra or {"payload_kind": "FIELD", "ai_status": "REAL"},
    }


def _make_event(client, token, **kwargs):
    r = client.post("/observations", json=_pothole(**kwargs), headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()["event"]


def _field_token(client, admin_token):
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-042"}, headers=auth_header(admin_token)).json()["code"]
    return client.post("/auth/field-join", json={"code": code}).json()["access_token"]


def test_delete_one_event_officer(client, admin_token):
    ev = _make_event(client, admin_token)
    gone = client.delete(f"/events/{ev['id']}", headers=auth_header(admin_token))
    assert gone.status_code == 200, gone.text
    assert gone.json()["deleted"] == 1
    listed = client.get("/events", headers=auth_header(admin_token))
    assert listed.status_code == 200
    assert ev["id"] not in {row["id"] for row in listed.json()}
    missing = client.get(f"/events/{ev['id']}", headers=auth_header(admin_token))
    assert missing.status_code == 404


def test_delete_unknown_event_404(client, admin_token):
    r = client.delete("/events/not-a-real-id", headers=auth_header(admin_token))
    assert r.status_code == 404


def test_field_token_cannot_delete(client, admin_token):
    ev = _make_event(client, admin_token, lat=28.62, lon=77.22)
    field = _field_token(client, admin_token)
    denied = client.delete(f"/events/{ev['id']}", headers=auth_header(field))
    assert denied.status_code == 403
    still = client.get(f"/events/{ev['id']}", headers=auth_header(admin_token))
    assert still.status_code == 200


def test_field_token_cannot_clear(client, admin_token):
    field = _field_token(client, admin_token)
    r = client.post("/events/clear", json={"confirm": True}, headers=auth_header(field))
    assert r.status_code == 403
    batch = client.post("/events/batch-delete", json={"ids": ["x"]}, headers=auth_header(field))
    assert batch.status_code == 403


def test_operator_can_delete(client, admin_token, operator_token):
    ev = _make_event(client, admin_token, lat=28.63, lon=77.23)
    r = client.delete(f"/events/{ev['id']}", headers=auth_header(operator_token))
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 1


def test_batch_delete_by_ids(client, admin_token):
    a = _make_event(client, admin_token, lat=28.64, lon=77.24)
    b = _make_event(client, admin_token, lat=28.65, lon=77.25)
    keep = _make_event(client, admin_token, lat=28.66, lon=77.26)
    r = client.post(
        "/events/batch-delete",
        json={"ids": [a["id"], b["id"], "missing-id"]},
        headers=auth_header(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    live = {row["id"] for row in client.get("/events", headers=auth_header(admin_token)).json()}
    assert a["id"] not in live
    assert b["id"] not in live
    assert keep["id"] in live


def test_clear_requires_confirm(client, admin_token):
    _make_event(client, admin_token, lat=28.67, lon=77.27)
    bad = client.post("/events/clear", json={"confirm": False}, headers=auth_header(admin_token))
    assert bad.status_code == 400
    missing = client.post("/events/clear", json={}, headers=auth_header(admin_token))
    assert missing.status_code == 400
    listed = client.get("/events", headers=auth_header(admin_token)).json()
    assert listed


def test_clear_wipes_tickets_keeps_login(client, admin_token):
    _make_event(client, admin_token, lat=28.68, lon=77.28, extra={"payload_kind": "SEED", "ai_status": "SIMULATED"})
    _make_event(client, admin_token, lat=28.681, lon=77.281)
    wiped = client.post("/events/clear", json={"confirm": True}, headers=auth_header(admin_token))
    assert wiped.status_code == 200, wiped.text
    assert wiped.json()["deleted"] >= 1
    assert "Buses" in wiped.json()["note"]
    events = client.get("/events?limit=200", headers=auth_header(admin_token))
    assert events.status_code == 200
    assert events.json() == []
    me = client.get("/auth/me", headers=auth_header(admin_token))
    assert me.status_code == 200
    buses = client.get("/buses", headers=auth_header(admin_token))
    assert buses.status_code == 200
    assert any(row.get("code") == "BUS-042" for row in buses.json())
