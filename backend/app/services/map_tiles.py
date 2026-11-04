"""Which map tiles the server proxies.

Precedence: a custom MAP_TILE_URL, then the Azure Maps key, then nothing (the browser draws OpenStreetMap itself).

The tile URL (and the key inside it) never leaves the server. The browser only gets /maps/tiles/{z}/{x}/{y}.png?ticket=...
Only the host that the administrator wrote into MAP_TILE_URL is ever contacted: z, x and y are plain integers and are not
allowed in the host name, so a caller cannot steer the request somewhere else.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.config import get_settings

log = logging.getLogger("urbansense")

MAX_URL_CHARS = 2048
ALLOWED_PLACEHOLDERS = {"z", "x", "y", "s", "r"}
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_ANCHOR = re.compile(r'<a\s+href="(https?://[^"\s<>]+)"(?:\s+target="_blank")?(?:\s+rel="[^"]*")?\s*>', re.I)
_TAG = re.compile(r"</?a(?:\s[^>]*)?>", re.I)
_AZURE_TEMPLATE = (
    "https://atlas.microsoft.com/map/tile?api-version=2.1&tilesetId=microsoft.base.road"
    "&zoom={z}&x={x}&y={y}&subscription-key="
)
_warned: set[str] = set()


@dataclass(frozen=True)
class TileSource:
    kind: str  # "custom", "azure" or "none"
    provider: str
    attribution: str
    template: str | None = field(default=None, repr=False)  # holds the key: never log it, never return it
    problem: str | None = None  # why MAP_TILE_URL was ignored, if it was set but unusable


def template_problem(url: str) -> str | None:
    """None when the template is usable, otherwise a short reason. The reason never repeats any part of the URL."""
    if len(url) > MAX_URL_CHARS:
        return f"longer than {MAX_URL_CHARS} characters"
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        return "contains spaces or control characters"
    try:
        parts = urlsplit(url)
        host = parts.netloc
    except ValueError:
        return "is not a valid URL"
    if parts.scheme not in {"http", "https"} or not host:
        return "must start with http:// or https:// and include a host"
    if any(token in host for token in ("{z}", "{x}", "{y}", "{r}")):
        return "only {s} may appear in the host name"
    names = _PLACEHOLDER.findall(url)
    if any(name not in ALLOWED_PLACEHOLDERS for name in names):
        return "has a placeholder other than {z} {x} {y} {s} {r}. Put the key itself in the URL, not as a placeholder"
    for needed in ("z", "x", "y"):
        if needed not in names:
            return "is missing {" + needed + "}"
    return None


def clean_attribution(raw: str) -> str:
    """Leaflet writes attribution as HTML. Keep plain text and https links, escape everything else."""

    def text(chunk: str) -> str:
        return re.sub(r"&(?!#?\w+;)", "&amp;", chunk).replace("<", "&lt;").replace(">", "&gt;")

    out: list[str] = []
    pos = 0
    open_links = 0
    for match in _TAG.finditer(raw):
        out.append(text(raw[pos : match.start()]))
        tag = match.group(0)
        if tag.startswith("</"):
            if open_links:
                out.append("</a>")
                open_links -= 1
        else:
            anchor = _ANCHOR.fullmatch(tag)
            if anchor:
                out.append(f'<a href="{anchor.group(1)}" target="_blank" rel="noopener noreferrer">')
                open_links += 1
        pos = match.end()
    out.append(text(raw[pos:]))
    out.append("</a>" * open_links)
    return "".join(out).strip()


def _host_label(url: str) -> str:
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        host = ""
    return re.sub(r"^\{s\}\.", "", host)


def _warn_once(problem: str) -> None:
    if problem not in _warned:
        _warned.add(problem)
        log.warning("MAP_TILE_URL ignored: %s", problem)


def tile_source() -> TileSource:
    s = get_settings()
    raw = (s.map_tile_url or "").strip()
    problem: str | None = None
    if raw:
        problem = template_problem(raw)
        if problem is None:
            provider = (s.map_tile_provider or "").strip() or _host_label(raw) or "Custom map tiles"
            attribution = clean_attribution(s.map_tile_attribution or "") or "&copy; " + clean_attribution(provider)
            return TileSource("custom", provider, attribution, raw)
        _warn_once(problem)
    key = (s.azure_maps_subscription_key or "").strip()
    if key:
        return TileSource("azure", "Azure Maps", "&copy; Azure Maps", _AZURE_TEMPLATE + key, problem)
    return TileSource("none", "OpenStreetMap", "", None, problem)


def upstream_url(source: TileSource, z: int, x: int, y: int) -> str:
    """The provider URL for one tile. {s} becomes "a" and {r} (retina) is dropped: the server asks for plain tiles."""
    assert source.template is not None
    return (
        source.template.replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
        .replace("{s}", "a")
        .replace("{r}", "")
    )
