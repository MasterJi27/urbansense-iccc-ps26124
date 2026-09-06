from app.services.place import reverse_place
from tests.test_auth import auth_header


def test_reverse_place_without_key():
    out = reverse_place(28.61, 77.21)
    assert out["ok"] is False
    assert out["honesty"] == "DISABLED"
    assert out["label"] is None


def test_maps_place_requires_auth(client):
    r = client.get("/maps/place", params={"lat": 28.61, "lon": 77.21})
    assert r.status_code == 401


def test_maps_place_disabled_without_key(client, admin_token):
    r = client.get("/maps/place", params={"lat": 28.61, "lon": 77.21}, headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "subscription-key" not in r.text.lower()


def test_field_token_can_read_place(client, admin_token):
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-017"}, headers=auth_header(admin_token)).json()["code"]
    token = client.post("/auth/field-join", json={"code": code}).json()["access_token"]
    r = client.get("/maps/place", params={"lat": 28.61, "lon": 77.21}, headers=auth_header(token))
    assert r.status_code == 200
    assert r.json()["ok"] is False
