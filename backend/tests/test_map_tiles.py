"""MAP_TILE_URL: any tile provider behind the server-side proxy. The key never reaches the browser or the logs."""

import pytest
from urllib.error import HTTPError

from app.api.routes import maps as maps_route
from app.config import get_settings
from app.services import map_tiles
from app.services.redact import redact_text
from tests.test_auth import auth_header

KEY = "k3y-must-never-leak"
TEMPLATE = f"https://tiles.example.test/v2/{{z}}/{{x}}/{{y}}.png?key={KEY}"
PNG = b"\x89PNG\r\n\x1a\nfake-tile"
ENV_NAMES = ("MAP_TILE_URL", "MAP_TILE_PROVIDER", "MAP_TILE_ATTRIBUTION", "AZURE_MAPS_SUBSCRIPTION_KEY")


@pytest.fixture
def maps_env(monkeypatch):
    def apply(**values):
        for name in ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()

    yield apply
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


class FakeResponse:
    def __init__(self, body=PNG, content_type="image/png"):
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=-1):
        return self.body if limit is None or limit < 0 else self.body[:limit]


def fake_upstream(monkeypatch, response=None, error=None):
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        if error is not None:
            raise error
        return response or FakeResponse()

    monkeypatch.setattr(maps_route, "urlopen", fake_urlopen)
    return seen


def config(client, admin_token):
    r = client.get("/maps/config", headers=auth_header(admin_token))
    assert r.status_code == 200
    return r.json()


def ticket_of(cfg):
    return cfg["tile_url"].split("ticket=", 1)[1]


# ---- default and precedence ---------------------------------------------------------------------------------------


def test_default_is_openstreetmap_in_the_browser(client, admin_token, maps_env):
    maps_env()
    body = config(client, admin_token)
    assert body["enabled"] is False
    assert body["provider"] == "OpenStreetMap"
    assert body["tile_url"] is None
    assert body["attribution"] is None
    assert map_tiles.tile_source().kind == "none"
    assert client.get("/settings", headers=auth_header(admin_token)).json()["map_provider"] == "OpenStreetMap"


def test_custom_url_turns_the_proxy_on_and_hides_the_key(client, admin_token, maps_env):
    maps_env(MAP_TILE_URL=TEMPLATE)
    r = client.get("/maps/config", headers=auth_header(admin_token))
    body = r.json()
    assert body["enabled"] is True
    assert body["provider"] == "tiles.example.test"  # host name when MAP_TILE_PROVIDER is not set
    assert body["tile_url"].startswith("/maps/tiles/{z}/{x}/{y}.png?ticket=")
    assert body["attribution"] == "&copy; tiles.example.test"
    assert KEY not in r.text and "tiles.example.test/v2" not in r.text
    settings = client.get("/settings", headers=auth_header(admin_token))
    assert settings.json()["map_provider"] == "tiles.example.test"
    assert "map_tile_url" not in settings.json() and KEY not in settings.text


def test_custom_url_wins_over_the_azure_key(client, admin_token, maps_env, monkeypatch):
    maps_env(MAP_TILE_URL=TEMPLATE, AZURE_MAPS_SUBSCRIPTION_KEY="azure-key-not-used")
    seen = fake_upstream(monkeypatch)
    cfg = config(client, admin_token)
    assert cfg["provider"] != "Azure Maps"
    r = client.get(f"/maps/tiles/3/1/2.png?ticket={ticket_of(cfg)}")
    assert r.status_code == 200
    assert seen[0].full_url.startswith("https://tiles.example.test/")
    assert "atlas.microsoft.com" not in seen[0].full_url


def test_provider_and_attribution_overrides(client, admin_token, maps_env):
    link = '<a href="https://www.maptiler.com/copyright/" target="_blank">&copy; MapTiler</a>'
    maps_env(MAP_TILE_URL=TEMPLATE, MAP_TILE_PROVIDER="MapTiler", MAP_TILE_ATTRIBUTION=link + " <script>alert(1)</script>")
    body = config(client, admin_token)
    assert body["provider"] == "MapTiler"
    assert '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener noreferrer">&copy; MapTiler</a>' in body["attribution"]
    assert "<script" not in body["attribution"]
    assert "&lt;script&gt;" in body["attribution"]


# ---- the proxy ----------------------------------------------------------------------------------------------------


def test_proxy_fetches_the_provider_tile(client, admin_token, maps_env, monkeypatch):
    maps_env(MAP_TILE_URL=TEMPLATE)
    seen = fake_upstream(monkeypatch)
    r = client.get(f"/maps/tiles/5/10/12.png?ticket={ticket_of(config(client, admin_token))}")
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert KEY not in str(dict(r.headers))
    assert seen[0].full_url == f"https://tiles.example.test/v2/5/10/12.png?key={KEY}"
    assert seen[0].get_header("User-agent") == "SadakSaarthi-ICCC/1.0"


def test_subdomain_and_retina_placeholders(client, admin_token, maps_env, monkeypatch):
    maps_env(MAP_TILE_URL="https://{s}.tiles.example.test/{z}/{x}/{y}{r}.png?key=abc")
    seen = fake_upstream(monkeypatch)
    cfg = config(client, admin_token)
    assert cfg["provider"] == "tiles.example.test"  # the {s}. prefix is not part of the label
    assert client.get(f"/maps/tiles/1/2/3.png?ticket={ticket_of(cfg)}").status_code == 200
    assert seen[0].full_url == "https://a.tiles.example.test/1/2/3.png?key=abc"


def test_proxy_still_needs_a_ticket_and_sane_coordinates(client, admin_token, maps_env):
    maps_env(MAP_TILE_URL=TEMPLATE)
    assert client.get("/maps/tiles/1/0/0.png").status_code == 401
    ticket = ticket_of(config(client, admin_token))
    assert client.get(f"/maps/tiles/99/0/0.png?ticket={ticket}").status_code == 400


def test_upstream_error_does_not_leak_the_key(client, admin_token, maps_env, monkeypatch):
    maps_env(MAP_TILE_URL=TEMPLATE)
    ticket = ticket_of(config(client, admin_token))
    fake_upstream(monkeypatch, error=HTTPError(TEMPLATE, 403, "Forbidden", {}, None))
    r = client.get(f"/maps/tiles/1/0/0.png?ticket={ticket}")
    assert r.status_code == 502
    assert "tiles.example.test" in r.text and "403" in r.text
    assert KEY not in r.text


def test_a_provider_answer_that_is_not_an_image_is_refused(client, admin_token, maps_env, monkeypatch):
    maps_env(MAP_TILE_URL=TEMPLATE)
    ticket = ticket_of(config(client, admin_token))
    fake_upstream(monkeypatch, FakeResponse(b"<html>quota exceeded</html>", "text/html"))
    r = client.get(f"/maps/tiles/1/0/0.png?ticket={ticket}")
    assert r.status_code == 502
    assert "quota exceeded" not in r.text


def test_an_oversized_tile_is_refused(client, admin_token, maps_env, monkeypatch):
    maps_env(MAP_TILE_URL=TEMPLATE)
    ticket = ticket_of(config(client, admin_token))
    fake_upstream(monkeypatch, FakeResponse(b"0" * (maps_route.MAX_TILE_BYTES + 1)))
    assert client.get(f"/maps/tiles/1/0/0.png?ticket={ticket}").status_code == 502


# ---- bad templates are ignored, never fetched ---------------------------------------------------------------------

BAD = [
    "ftp://tiles.example.test/{z}/{x}/{y}.png?key=zz-secret-zz",
    "file:///etc/passwd/{z}/{x}/{y}?key=zz-secret-zz",
    "tiles.example.test/{z}/{x}/{y}.png?key=zz-secret-zz",
    "https://tiles.example.test/{z}/{x}.png?key=zz-secret-zz",
    "https://tiles.example.test/{z}/{x}/{y}.png?key={apikey-zz-secret-zz}",
    "https://{x}.example.test/{z}/{y}.png?key=zz-secret-zz",
    "https://tiles.example.test/{z}/{x}/{y}.png key=zz-secret-zz",
    "https://tiles.example.test/" + "a" * 2100 + "/{z}/{x}/{y}.png",
]


@pytest.mark.parametrize("bad", BAD)
def test_unusable_template_is_ignored_with_a_reason(client, admin_token, maps_env, bad):
    maps_env(MAP_TILE_URL=bad)
    source = map_tiles.tile_source()
    assert source.kind == "none" and source.problem
    assert "zz-secret-zz" not in source.problem
    r = client.get("/maps/config", headers=auth_header(admin_token))
    body = r.json()
    assert body["enabled"] is False
    assert "MAP_TILE_URL was ignored" in body["note"]
    assert "zz-secret-zz" not in r.text


def test_a_bad_template_falls_back_to_the_azure_key(client, admin_token, maps_env):
    maps_env(MAP_TILE_URL="ftp://nope/{z}/{x}/{y}", AZURE_MAPS_SUBSCRIPTION_KEY="azure-key-not-used")
    body = config(client, admin_token)
    assert body["enabled"] is True and body["provider"] == "Azure Maps"
    assert "MAP_TILE_URL was ignored" in body["note"]
    assert "azure-key-not-used" not in str(body)


def test_the_key_is_not_in_the_source_repr():
    source = map_tiles.TileSource("custom", "p", "a", TEMPLATE)
    assert KEY not in repr(source)


# ---- attribution and logs -----------------------------------------------------------------------------------------


def test_attribution_keeps_text_and_https_links_and_escapes_the_rest():
    clean = map_tiles.clean_attribution
    assert clean("&copy; OpenStreetMap contributors & friends") == "&copy; OpenStreetMap contributors &amp; friends"
    assert "<a" not in clean('<a href="javascript:alert(1)">x</a>') and clean('<a href="javascript:alert(1)">x</a>') == "x"
    assert clean('<a href="https://e.test/c">c').endswith("</a>")  # an unclosed link is closed
    assert "<img" not in clean("<img src=x onerror=alert(1)>")


def test_logs_do_not_carry_the_tile_key():
    assert KEY not in redact_text("MAP_TILE_URL=" + TEMPLATE)
    out = redact_text("fetch https://t.example/1/2/3.png?foo=1&key=abc123 done")
    assert "abc123" not in out and "key=[redacted]" in out
