from tests.test_auth import auth_header

NAV = {
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "accept": "text/html,application/xhtml+xml",
}


def test_browser_refresh_on_event_path_serves_spa(client):
    r = client.get("/events/not-a-real-id", headers=NAV)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text.lower()
    assert "<!doctype html>" in body or "<html" in body


def test_api_missing_event_stays_json(client, admin_token):
    r = client.get("/events/not-a-real-id", headers=auth_header(admin_token))
    assert r.status_code == 404
    assert r.json()["detail"] == "Event not found"


def test_unauthenticated_api_event_is_401(client):
    r = client.get("/events/not-a-real-id")
    assert r.status_code == 401


def test_health_is_never_spa(client):
    r = client.get("/health", headers=NAV)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
