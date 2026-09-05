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
