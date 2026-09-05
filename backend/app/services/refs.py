"""Resolve human codes (BUS-042, FIELD-IPHONE) to FK ids. Never write a label into buses.id."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.fleet import Bus


def coerce_bus_id(db: Session, raw: str | None) -> str | None:
    token = (raw or "").strip()
    if not token:
        return None
    bus = db.get(Bus, token)
    if bus:
        return bus.id
    bus = db.query(Bus).filter(Bus.code == token.upper()).first()
    if bus:
        return bus.id
    return None
