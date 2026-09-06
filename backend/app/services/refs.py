"""Resolve human codes (BUS-042, FIELD-IPHONE) to FK ids. Never write a label into buses.id."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.fleet import Bus

_BUS_NUM = re.compile(r"^(?:BUS-?)?(\d{1,4})(?:$|[^0-9])")


def normalize_bus_code(raw: str) -> str:
    token = (raw or "").strip().upper().replace(" ", "")
    if not token:
        raise ValueError("bus_code required")
    match = _BUS_NUM.match(token)
    if match:
        return f"BUS-{int(match.group(1)):03d}"
    if token.startswith("BUS-"):
        return token[:32]
    return f"BUS-{token[:28]}"


def ensure_bus(db: Session, code: str) -> Bus:
    normalized = normalize_bus_code(code)
    bus = db.query(Bus).filter(Bus.code == normalized).first()
    if bus:
        return bus
    bus = Bus(code=normalized, registration="", qr_payload=f"urbansense://bus/{normalized}")
    db.add(bus)
    db.flush()
    return bus


def coerce_bus_id(db: Session, raw: str | None) -> str | None:
    token = (raw or "").strip()
    if not token:
        return None
    bus = db.get(Bus, token)
    if bus:
        return bus.id
    try:
        code = normalize_bus_code(token)
    except ValueError:
        code = token.upper()
    bus = db.query(Bus).filter(Bus.code == code).first()
    if bus:
        return bus.id
    return None
