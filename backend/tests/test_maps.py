from app.config import get_settings
from tests.test_auth import auth_header
from tests.test_spa import NAV


def test_maps_config_requires_auth(client):
    r = client.get("/maps/config")
    assert r.status_code == 401


def test_maps_config_disabled_without_key(client, admin_token):
    r = client.get("/maps/config", headers=auth_header(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["provider"] == "OpenStreetMap"
    assert body["tile_url"] is None
    assert "atlas.microsoft.com" not in str(body)
    assert "subscription-key" not in str(body).lower()


def test_maps_tile_requires_ticket(client):
    r = client.get("/maps/tiles/1/0/0.png")
    assert r.status_code == 401


def test_maps_tile_404_without_key(client, admin_token, monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "test-key-not-used")
    get_settings.cache_clear()
    try:
        cfg = client.get("/maps/config", headers=auth_header(admin_token)).json()
        assert cfg["enabled"] is True
        ticket = cfg["tile_url"].split("ticket=", 1)[1]
        r = client.get(f"/maps/tiles/1/0/0.png?ticket={ticket}")
        assert r.status_code in {404, 502}
        assert "test-key-not-used" not in r.text
    finally:
        monkeypatch.delenv("AZURE_MAPS_SUBSCRIPTION_KEY", raising=False)
        get_settings.cache_clear()


def test_maps_tile_400_bad_zoom(client, admin_token, monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "test-key-not-used")
    get_settings.cache_clear()
    try:
        cfg = client.get("/maps/config", headers=auth_header(admin_token)).json()
        ticket = cfg["tile_url"].split("ticket=", 1)[1]
        r = client.get(f"/maps/tiles/99/0/0.png?ticket={ticket}")
        assert r.status_code == 400
    finally:
        monkeypatch.delenv("AZURE_MAPS_SUBSCRIPTION_KEY", raising=False)
        get_settings.cache_clear()


def test_maps_config_not_spa(client, admin_token):
    r = client.get("/maps/config", headers={**NAV, **auth_header(admin_token)})
    assert r.status_code == 200
    assert r.json()["enabled"] in (True, False)


def test_health_reports_azure_maps(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["azure_maps"] is False


def test_maps_config_enabled_hides_key(client, admin_token, monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "super-secret-maps-key")
    get_settings.cache_clear()
    try:
        r = client.get("/maps/config", headers=auth_header(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["provider"] == "Azure Maps"
        assert "/maps/tiles/" in body["tile_url"]
        assert "ticket=" in body["tile_url"]
        assert "super-secret-maps-key" not in r.text
    finally:
        monkeypatch.delenv("AZURE_MAPS_SUBSCRIPTION_KEY", raising=False)
        get_settings.cache_clear()


def test_settings_reports_maps_without_key(client, admin_token):
    r = client.get("/settings", headers=auth_header(admin_token))
    assert r.status_code == 200
    assert r.json()["azure_maps_enabled"] is False
    assert "azure_maps_subscription_key" not in r.json()
    assert r.json()["rdd_eval"]["honesty"] in {"EXPERIMENTAL", "REAL"}
