def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_login_ok(client, admin_token):
    assert admin_token


def test_login_bad(client, admin_token):
    r = client.post("/auth/login", json={"email": "admin@test.local", "password": "nope"})
    assert r.status_code == 401


def test_me(client, admin_token):
    r = client.get("/auth/me", headers=auth_header(admin_token))
    assert r.status_code == 200
    assert r.json()["role"] == "ADMIN"


def test_field_join_can_ingest_water_tap(client, admin_token):
    code = client.post("/auth/field-booth", headers=auth_header(admin_token)).json()["code"]
    token = client.post("/auth/field-join", json={"code": code}).json()["access_token"]
    r = client.post(
        "/ingest/phone",
        headers=auth_header(token),
        json={
            "event_type": "WATERLOGGING",
            "severity": "HIGH",
            "latitude": 28.63,
            "longitude": 77.21,
            "source_type": "PHONE",
            "source_id": "FIELD-IPHONE",
            "confidence": 0.55,
            "simulated": False,
            "extra": {"method": "field-tap", "ai_status": "RULE_BASED", "patrol": True, "camera_bay": "FRONT"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["event"]["event_type"] == "WATERLOGGING"


def test_field_booth_issue_and_join(client, admin_token):
    armed = client.post("/auth/field-booth", headers=auth_header(admin_token))
    assert armed.status_code == 200, armed.text
    code = armed.json()["code"]
    assert len(code) == 6
    live = client.get("/auth/field-booth", headers=auth_header(admin_token))
    assert live.status_code == 200
    assert live.json()["code"] == code

    joined = client.post("/auth/field-join", json={"code": code})
    assert joined.status_code == 200, joined.text
    token = joined.json()["access_token"]
    me = client.get("/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["role"] == "ADMIN"
    assert me.json()["scope"] == "field"
    again = client.post("/auth/field-join", json={"code": code})
    assert again.status_code == 401


def test_field_join_rejects_bad_code(client, admin_token):
    client.post("/auth/field-booth", headers=auth_header(admin_token))
    bad = client.post("/auth/field-join", json={"code": "000000"})
    assert bad.status_code == 401


def test_field_booth_requires_login(client):
    r = client.post("/auth/field-booth")
    assert r.status_code == 401


def test_field_booth_missing(client, admin_token):
    r = client.get("/auth/field-booth", headers=auth_header(admin_token))
    assert r.status_code == 404
