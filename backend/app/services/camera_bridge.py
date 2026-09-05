"""Any-camera still connector. We do not decode vendor NVRs or pull RTSP in the cloud."""

from __future__ import annotations

import ipaddress
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config import get_settings
from app.services.azure_edge import StillRejected, validate_still

PRESETS = [
    {
        "id": "BROWSER",
        "label": "USB / phone / cheap Wi-Fi as this browser",
        "protocol": "BROWSER_LENS",
        "honesty": "REAL",
        "how": "This device is the camera. Cubic-class, laptop webcam, or a phone on the depot Wi-Fi.",
        "url_hint": "",
    },
    {
        "id": "FILE_EXPORT",
        "label": "Any DVR software — export JPEG",
        "protocol": "FILE",
        "honesty": "RULE_BASED",
        "how": "HP, CP Plus, XM, Dahua client: save one still, drop it here. Vendor app stays theirs.",
        "url_hint": "",
    },
    {
        "id": "HTTP_SNAPSHOT",
        "label": "ONVIF / generic HTTP snapshot",
        "protocol": "HTTP_SNAPSHOT",
        "honesty": "RULE_BASED",
        "how": "Most DVRs expose one JPEG URL. We pull that frame. We do not ingest the RTSP video.",
        "url_hint": "http://USER:PASS@<dvr-ip>/cgi-bin/snapshot.cgi?channel=1",
    },
    {
        "id": "CP_PLUS",
        "label": "CP Plus / Dahua-class DVR",
        "protocol": "HTTP_SNAPSHOT",
        "honesty": "RULE_BASED",
        "how": "Dahua-family snapshot CGI. Same still ingest as every other camera.",
        "url_hint": "http://USER:PASS@<dvr-ip>/cgi-bin/snapshot.cgi?channel=1",
    },
    {
        "id": "HP_DVR",
        "label": "HP / generic H.264 DVR",
        "protocol": "HTTP_SNAPSHOT",
        "honesty": "RULE_BASED",
        "how": "Use the DVR web UI snapshot path, or export a still from the HP client.",
        "url_hint": "http://<dvr-ip>/snapshot.jpg",
    },
    {
        "id": "CUBIC_WIFI",
        "label": "Cubic / XM / Tuya ~₹2000 Wi-Fi",
        "protocol": "BROWSER_LENS",
        "honesty": "RULE_BASED",
        "how": "Proprietary cloud apps are DISABLED. Open this page on a phone next to the cam, or export a still from its app.",
        "url_hint": "",
    },
    {
        "id": "RTSP_HINT",
        "label": "RTSP (Hikvision / Uniview / XM)",
        "protocol": "RTSP",
        "honesty": "DISABLED",
        "how": "Azure does not decode RTSP or run 24×7 GPU. On the depot PC: scripts/cctv-bridge.ps1 -Loop on the JPEG snapshot URL, or python ai/urbansense_ai/run_camera.py --source rtsp://…",
        "url_hint": "rtsp://USER:PASS@<ip>:554/cam/realmonitor?channel=1&subtype=0",
    },
]


def lan_pull_enabled() -> bool:
    return bool(get_settings().allow_lan_camera_pull)


def _host_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool) -> str | None:
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return "host not allowed"
    if ip.is_private and not allow_private:
        return "LAN snapshot pull is off on this host. Open /cctv on a PC next to the DVR, or run scripts/cctv-bridge.ps1"
    return None


def assert_snapshot_url(url: str, *, allow_private: bool | None = None, resolve: bool = False) -> None:
    raw = (url or "").strip()
    if not raw or len(raw) > 500:
        raise ValueError("snapshot URL missing or too long")
    parsed = urlparse(raw)
    if parsed.scheme == "rtsp":
        raise ValueError("RTSP is not pulled here. Use the DVR JPEG snapshot URL, scripts/cctv-bridge.ps1 -Loop, or python ai/urbansense_ai/run_camera.py --source rtsp://")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("snapshot must be http or https")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in {"localhost", "metadata.google.internal", "metadata.azure.com"}:
        raise ValueError("host not allowed")
    allow = lan_pull_enabled() if allow_private is None else allow_private
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        reason = _host_blocked(ip, allow_private=allow)
        if reason:
            raise ValueError(reason)
        return
    if not resolve:
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError("snapshot host could not be resolved") from exc
    for info in infos:
        reason = _host_blocked(ipaddress.ip_address(info[4][0]), allow_private=allow)
        if reason:
            raise ValueError(reason)


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("snapshot redirects are not followed")


def fetch_snapshot(url: str) -> bytes:
    assert_snapshot_url(url, resolve=True)
    opener = build_opener(_RejectRedirect)
    req = Request(url, headers={"User-Agent": "UrbanSense-CCTV-Bridge/1.0"})
    try:
        with opener.open(req, timeout=8) as resp:
            data = resp.read((get_settings().still_max_bytes or 3_500_000) + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ValueError(f"snapshot fetch failed: {exc}") from exc
    try:
        validate_still(data)
    except StillRejected as exc:
        raise ValueError(str(exc)) from exc
    return data


def public_presets() -> list[dict]:
    return [{**row, "lan_pull": lan_pull_enabled()} for row in PRESETS]
