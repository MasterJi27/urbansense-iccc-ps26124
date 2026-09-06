"""Reverse-geocode a GPS pin via Azure Maps. Not a scraped Twitter ward list."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_settings

_EMPTY = {
    "ok": False,
    "honesty": "DISABLED",
    "label": None,
    "locality": None,
    "admin": None,
    "country": None,
    "note": "Azure Maps key not set. GPS numbers still stand.",
}


def reverse_place(latitude: float | None, longitude: float | None) -> dict:
    if latitude is None or longitude is None:
        return {**_EMPTY, "note": "No GPS pin to reverse-geocode."}
    key = get_settings().azure_maps_subscription_key.strip()
    if not key:
        return dict(_EMPTY)
    query = urlencode(
        {
            "api-version": "1.0",
            "query": f"{float(latitude):.6f},{float(longitude):.6f}",
            "subscription-key": key,
        }
    )
    url = f"https://atlas.microsoft.com/search/address/reverse/json?{query}"
    req = Request(url, headers={"User-Agent": "SadakSaarthi-ICCC/1.0"})
    try:
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return {
            "ok": False,
            "honesty": "RULE_BASED",
            "label": None,
            "locality": None,
            "admin": None,
            "country": None,
            "note": "Azure Maps reverse geocode failed. GPS numbers still stand.",
        }
    addresses = payload.get("addresses") or []
    addr = (addresses[0] or {}).get("address") if addresses else None
    if not isinstance(addr, dict):
        return {
            "ok": False,
            "honesty": "REAL",
            "label": None,
            "locality": None,
            "admin": None,
            "country": None,
            "note": "Azure Maps returned no address for this pin.",
        }
    locality = (
        addr.get("municipalitySubdivision")
        or addr.get("neighbourhood")
        or addr.get("municipality")
        or addr.get("localName")
    )
    admin = addr.get("countrySubdivision") or addr.get("countrySecondarySubdivision")
    country = addr.get("country") or addr.get("countryCode")
    label = addr.get("freeformAddress") or ", ".join(p for p in (locality, admin, country) if p)
    return {
        "ok": True,
        "honesty": "REAL",
        "label": label,
        "locality": locality,
        "admin": admin,
        "country": country,
        "note": "Azure Maps reverse geocode of this GPS pin. Not official MCD ward GIS.",
    }
